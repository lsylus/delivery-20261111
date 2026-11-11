"""Persistent, owner/session scoped jobs; only committed complete runs download."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from uuid import uuid4


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ApiError(ValueError):
    def __init__(self, status, message, code="INVALID_REQUEST"):
        self.status, self.message, self.code = status, message, code


def identifier(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,160}", value))


class Store:
    def __init__(self, root, template, receipt_key, *, timeout=1800, start_worker=True):
        self.root, self.template = Path(root).resolve(), Path(template).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.key = receipt_key.encode()
        self.timeout = timeout
        self.lock, self.wake, self.stop = threading.RLock(), threading.Event(), threading.Event()
        self.db = sqlite3.connect(self.root / "jobs.sqlite3", check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, session TEXT NOT NULL,
          name TEXT NOT NULL, state TEXT NOT NULL, snapshot TEXT NOT NULL, run TEXT,
          revision_seq INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, job TEXT NOT NULL, op TEXT NOT NULL,
          payload TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, job TEXT NOT NULL, revision_hash TEXT NOT NULL,
          state TEXT NOT NULL, manifest_sha TEXT, artifacts TEXT NOT NULL DEFAULT '[]',
          review TEXT NOT NULL DEFAULT '{"status":"pending"}', error TEXT, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS idempotency(owner TEXT, session TEXT, job TEXT, key TEXT,
          payload_sha TEXT NOT NULL, run TEXT NOT NULL, PRIMARY KEY(owner,session,job,key));
        CREATE TABLE IF NOT EXISTS receipts(nonce TEXT PRIMARY KEY, claims TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY, job TEXT NOT NULL, snapshot TEXT NOT NULL,
          created REAL NOT NULL);
        ''')
        # Never auto-publish a directory left between file rename and DB commit.
        self.db.execute("UPDATE runs SET state='paused_error',error=? WHERE state IN ('queued','running')",
                        (json.dumps({"code": "WORKER_INTERRUPTED", "message": "后台中断，可重新生成"}),))
        self.db.execute("UPDATE jobs SET state='paused_error' WHERE state IN ('queued','running','validating','resolving')")
        self.db.execute("UPDATE tasks SET state='interrupted' WHERE state IN ('queued','running')")
        self.thread = threading.Thread(target=self._loop, name="heater-single-worker", daemon=True)
        if start_worker:
            self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread.is_alive():
            self.thread.join(timeout=8)

    def _job(self, job_id, owner, session):
        row = self.db.execute("SELECT * FROM jobs WHERE id=? AND owner=? AND session=?", (job_id, owner, session)).fetchone()
        if row is None:
            raise ApiError(404, "当前会话找不到该任务", "NOT_FOUND")
        return row

    def get(self, job_id, owner, session):
        with self.lock:
            row = self._job(job_id, owner, session)
            value = {"id": row["id"], "name": row["name"], "state": row["state"],
                     "created": row["created"], **json.loads(row["snapshot"])}
            if row["run"]:
                run = dict(self.db.execute("SELECT * FROM runs WHERE id=?", (row["run"],)).fetchone())
                value["run"] = {k: run[k] for k in ("id", "state", "revision_hash", "created", "manifest_sha")}
                value["run"].update(artifacts=json.loads(run["artifacts"]), review=json.loads(run["review"]),
                                     error=json.loads(run["error"]) if run["error"] else None)
            return value

    def listing(self, owner, session):
        with self.lock:
            return [dict(r) for r in self.db.execute(
                "SELECT id,name,state,created FROM jobs WHERE owner=? AND session=? ORDER BY created DESC LIMIT 100",
                (owner, session))]

    def _task(self, job_id, op, payload):
        task_id = uuid4().hex
        self.db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?)", (task_id, job_id, op, json.dumps(payload), "queued", time.time()))
        self.wake.set()

    def upload(self, owner, session, name, content):
        if (not isinstance(name, str) or len(name) > 100 or not name.strip()
                or any(c in name for c in '/\\\0\r\n') or name in (".", "..")):
            raise ApiError(400, "合并文件名不可为空或含路径字符")
        if not content or len(content) > 10 * 1024 * 1024:
            raise ApiError(413, "Excel 文件上限为 10 MiB", "PAYLOAD_TOO_LARGE")
        with self.lock:
            if self.db.execute("SELECT count(*) FROM tasks WHERE state IN ('queued','running')").fetchone()[0] >= 20:
                raise ApiError(503, "后台队列已满，请稍后重试", "CAPABILITY_UNAVAILABLE")
            job_id = uuid4().hex
            directory = self.root / "jobs" / job_id
            directory.mkdir(parents=True, mode=0o700)
            (directory / "original.xlsx").write_bytes(content)
            now = time.time()
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                                (job_id, owner, session, name, "validating", "{}", None, 0, now, now))
                self._task(job_id, "analyze", {})
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            return self.get(job_id, owner, session)

    def _receipt(self, receipt, owner, session, job_id, action, revision, payload):
        try:
            encoded, signature = receipt.split(".")
            expected = hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if (claims["owner"] != owner or claims["session"] != session or claims["job"] != job_id
                    or claims["action"] != action or claims["revision"] != revision
                    or claims["payload_sha"] != hashlib.sha256(canonical(payload)).hexdigest()
                    or not time.time() < claims["expires"] <= time.time() + 125
                    or not identifier(claims["nonce"])):
                raise ValueError()
            self.db.execute("INSERT INTO receipts VALUES(?,?)", (claims["nonce"], json.dumps(claims)))
            return claims["nonce"]
        except Exception:
            raise ApiError(409, "确认已过期、被使用或内容已改变，请刷新后重新确认", "REVISION_CONFLICT") from None

    def decision(self, job_id, owner, session, body):
        if set(body) != {"base_revision_hash", "selection", "receipt"}:
            raise ApiError(400, "确认请求字段不正确")
        selection = body["selection"]
        if (not isinstance(selection, dict) or set(selection) != {"kind", "row_ids", "issue_ids", "proposal_ids", "reason"}
                or selection["kind"] not in ("skip", "scale") or not isinstance(selection["reason"], str)
                or not 1 <= len(selection["reason"].strip()) <= 1000
                or any(not isinstance(selection[k], list) or len(selection[k]) > 500
                       or len(set(selection[k])) != len(selection[k]) for k in ("row_ids", "issue_ids", "proposal_ids"))):
            raise ApiError(400, "确认清单不正确")
        with self.lock:
            row = self._job(job_id, owner, session)
            snapshot = json.loads(row["snapshot"])
            if row["state"] != "awaiting_resolution" or not snapshot.get("revision") or snapshot["revision"]["revision_hash"] != body["base_revision_hash"]:
                raise ApiError(409, "任务或修订已改变", "REVISION_CONFLICT")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                nonce = self._receipt(body["receipt"], owner, session, job_id, "decision",
                                      body["base_revision_hash"], selection)
                self._task(job_id, "decide", {"current": snapshot, "selection": selection,
                                              "actor": owner, "receipt_id": nonce})
                self.db.execute("UPDATE jobs SET state='resolving' WHERE id=?", (job_id,))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return self.get(job_id, owner, session)

    def start(self, job_id, owner, session, body, key):
        if set(body) != {"revision_hash"} or not identifier(key):
            raise ApiError(400, "缺少修订或有效的幂等键")
        with self.lock:
            row = self._job(job_id, owner, session)
            payload_sha = hashlib.sha256(canonical(body)).hexdigest()
            prior = self.db.execute("SELECT * FROM idempotency WHERE owner=? AND session=? AND job=? AND key=?",
                                    (owner, session, job_id, key)).fetchone()
            if prior:
                if prior["payload_sha"] != payload_sha:
                    raise ApiError(409, "幂等键已用于不同内容", "REVISION_CONFLICT")
                return {"run_id": prior["run"], "idempotent": True}
            snapshot = json.loads(row["snapshot"])
            if (row["state"] not in ("ready", "paused_error", "failed", "cancelled", "generated")
                    or not snapshot.get("exportable")
                    or snapshot["revision"]["revision_hash"] != body["revision_hash"]):
                raise ApiError(409, "请先解决全部错误和比例建议", "REVISION_CONFLICT")
            run_id = uuid4().hex
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("INSERT INTO runs(id,job,revision_hash,state,created) VALUES(?,?,?,?,?)",
                                (run_id, job_id, body["revision_hash"], "queued", time.time()))
                self.db.execute("INSERT INTO idempotency VALUES(?,?,?,?,?,?)",
                                (owner, session, job_id, key, payload_sha, run_id))
                self.db.execute("UPDATE jobs SET state='queued',run=? WHERE id=?", (run_id, job_id))
                self._task(job_id, "generate", {"run_id": run_id, "revision": snapshot["revision"]})
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            return {"run_id": run_id, "state": "queued"}

    def cancel(self, job_id, run_id, owner, session, revision):
        with self.lock:
            row = self._job(job_id, owner, session)
            run = self.db.execute("SELECT * FROM runs WHERE id=? AND job=?", (run_id, job_id)).fetchone()
            if not run or run["revision_hash"] != revision or row["run"] != run_id or run["state"] not in ("queued", "running"):
                raise ApiError(409, "任务已结束或修订已改变", "REVISION_CONFLICT")
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("UPDATE runs SET state='cancelled' WHERE id=?", (run_id,))
            self.db.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (job_id,))
            self.db.execute("COMMIT")
        self.wake.set()
        return {"state": "cancelled"}

    def review(self, job_id, run_id, owner, session, body):
        if set(body) != {"revision_hash", "status", "comment", "receipt"} or body["status"] not in ("approved", "rejected") or not isinstance(body["comment"], str) or len(body["comment"]) > 2000:
            raise ApiError(400, "复核记录字段不正确")
        with self.lock:
            job = self._job(job_id, owner, session)
            run = self.db.execute("SELECT * FROM runs WHERE id=? AND job=?", (run_id, job_id)).fetchone()
            if not run or job["run"] != run_id or run["state"] != "generated" or run["revision_hash"] != body["revision_hash"]:
                raise ApiError(409, "只能复核当前完整出图结果", "REVISION_CONFLICT")
            payload = {"run_id": run_id, "status": body["status"], "comment": body["comment"], "manifest_sha": run["manifest_sha"]}
            self.db.execute("BEGIN IMMEDIATE")
            try:
                nonce = self._receipt(body["receipt"], owner, session, job_id, "review", body["revision_hash"], payload)
                record = {**payload, "actor": owner, "time": time.time(), "receipt_id": nonce,
                          "artifacts": json.loads(run["artifacts"])}
                self.db.execute("UPDATE runs SET review=? WHERE id=?", (json.dumps(record), run_id))
                self.db.execute("INSERT INTO history VALUES(?,?,?,?)", (uuid4().hex, job_id, json.dumps(record), time.time()))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return record

    def artifact(self, job_id, run_id, artifact_id, owner, session):
        with self.lock:
            self._job(job_id, owner, session)
            run = self.db.execute("SELECT * FROM runs WHERE id=? AND job=?", (run_id, job_id)).fetchone()
            if not run or run["state"] != "generated":
                raise ApiError(404, "完整文件尚未发布", "NOT_FOUND")
            entry = next((a for a in json.loads(run["artifacts"]) if a["id"] == artifact_id), None)
            if entry is None:
                raise ApiError(404, "文件不可见", "NOT_FOUND")
            folder = self.root / "jobs" / job_id / "runs" / run_id / "package"
            path = folder / entry["path"]
            if (path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()) or not path.is_file()
                    or path.stat().st_size != entry["bytes"] or sha(path) != entry["sha256"]):
                raise ApiError(409, "文件完整性检查失败，已阻止下载", "REVISION_CONFLICT")
            return path, entry

    def _loop(self):
        while not self.stop.is_set():
            with self.lock:
                task = self.db.execute("SELECT * FROM tasks WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
                if task:
                    self.db.execute("UPDATE tasks SET state='running' WHERE id=?", (task["id"],))
            if not task:
                self.wake.wait(1)
                self.wake.clear()
                continue
            try:
                self._execute(task)
            except Exception:
                with self.lock:
                    self.db.execute("UPDATE tasks SET state='failed' WHERE id=?", (task["id"],))
                    payload = json.loads(task["payload"])
                    if task["op"] == "generate":
                        error = json.dumps({"code": "WORKER_FAILED", "message": "后台检查未通过，可重新生成；完整交付未发布"})
                        self.db.execute("UPDATE runs SET state='paused_error',error=? WHERE id=? AND state IN ('queued','running')", (error, payload["run_id"]))
                        self.db.execute("UPDATE jobs SET state='paused_error' WHERE id=? AND run=? AND state IN ('queued','running')", (task["job"], payload["run_id"]))
                    else:
                        self.db.execute("UPDATE jobs SET state='failed' WHERE id=? AND state NOT IN ('cancelled','generated')", (task["job"],))

    def _execute(self, task):
        job_id, op = task["job"], task["op"]
        payload = json.loads(task["payload"])
        folder = self.root / "jobs" / job_id
        scratch = folder / "operations" / task["id"]
        scratch.mkdir(parents=True)
        with self.lock:
            row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if op == "generate":
                run_id = payload["run_id"]
                run = self.db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
                if run["state"] != "queued":
                    self.db.execute("UPDATE tasks SET state='cancelled' WHERE id=?", (task["id"],))
                    return
                self.db.execute("UPDATE runs SET state='running' WHERE id=?", (run_id,))
                self.db.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
                run_folder = folder / "runs" / run_id
                run_folder.mkdir(parents=True)
                revision_file = run_folder / "revision.json"
                revision_file.write_text(json.dumps(payload.pop("revision"), ensure_ascii=False))
                payload.update(revision_file=str(revision_file), output=str(run_folder / "package"), name=row["name"])
        request = {"op": op, "template": str(self.template), "source": str(folder / "original.xlsx"), **payload}
        request_file = scratch / "request.json"
        request_file.write_text(json.dumps(request, ensure_ascii=False))
        with (scratch / "worker.log").open("wb") as log:
            process = subprocess.Popen([sys.executable, "-m", "heater_drawing.app.worker", str(request_file)],
                                       stdout=log, stderr=log, start_new_session=True,
                                       env={**os.environ, "HEATER_WORKER_PARENT": str(os.getpid())})
            deadline = time.monotonic() + self.timeout
            cancelled = False
            while process.poll() is None:
                if op == "generate":
                    with self.lock:
                        cancelled = self.db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()[0] == "cancelled"
                if cancelled or self.stop.is_set() or time.monotonic() > deadline:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                    break
                self.stop.wait(.2)
            process.wait()
        result_file = scratch / "result.json"
        result = json.loads(result_file.read_text()) if result_file.is_file() else {"ok": False, "code": "WORKER_INTERRUPTED", "message": "后台运行中断，可重试"}
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if op == "generate":
                    run = self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
                    if run["state"] == "cancelled" or self.stop.is_set():
                        self.db.execute("UPDATE tasks SET state='cancelled' WHERE id=?", (task["id"],))
                    elif not result["ok"]:
                        self.db.execute("UPDATE runs SET state='paused_error',error=? WHERE id=?", (json.dumps(result), run_id))
                        self.db.execute("UPDATE jobs SET state='paused_error' WHERE id=? AND run=?", (job_id, run_id))
                    else:
                        package = run_folder / "package"
                        manifest = json.loads((package / "manifest.json").read_text())
                        if manifest["revision_hash"] != run["revision_hash"]:
                            raise ValueError("revision_binding_mismatch")
                        files = [{"path": a["relative_path"], "kind": a["kind"], "media_type": a["media_type"]}
                                 for a in manifest["files"]]
                        files += [{"path": manifest["package_name"] + ".zip", "kind": "zip", "media_type": "application/zip"},
                                  {"path": "manifest.json", "kind": "manifest", "media_type": "application/json"}]
                        artifacts = [{**a, "id": uuid4().hex, "sha256": sha(package / a["path"]),
                                      "bytes": (package / a["path"]).stat().st_size} for a in files]
                        self.db.execute("UPDATE runs SET state='generated',manifest_sha=?,artifacts=? WHERE id=?",
                                        (sha(package / "manifest.json"), json.dumps(artifacts), run_id))
                        self.db.execute("UPDATE jobs SET state='generated' WHERE id=? AND run=?", (job_id, run_id))
                elif result["ok"]:
                    value = result["value"]
                    state = "ready" if value["exportable"] else "awaiting_resolution"
                    self.db.execute("UPDATE jobs SET state=?,snapshot=?,revision_seq=revision_seq+1,updated=? WHERE id=?",
                                    (state, json.dumps(value), time.time(), job_id))
                    self.db.execute("INSERT INTO history VALUES(?,?,?,?)", (uuid4().hex, job_id, json.dumps(value), time.time()))
                elif op == "decide":
                    value = json.loads(row["snapshot"])
                    value["error"] = result
                    self.db.execute("UPDATE jobs SET state='awaiting_resolution',snapshot=? WHERE id=?", (json.dumps(value), job_id))
                else:
                    self.db.execute("UPDATE jobs SET state='failed',snapshot=? WHERE id=?", (json.dumps({"error": result}), job_id))
                self.db.execute("UPDATE tasks SET state=? WHERE id=?", ("done" if result["ok"] else "failed", task["id"]))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
