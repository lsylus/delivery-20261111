import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import time
from uuid import uuid4

import pytest
from heater_drawing.app.store import Store, ApiError, canonical


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path, tmp_path, "k"*64, start_worker=False)
    yield value
    value.close()


def ready(store):
    value = store.upload("owner", "session", "图纸", b"not used by these storage tests")
    snapshot = {"revision": {"revision_hash": "a"*64}, "exportable": True}
    store.db.execute("UPDATE jobs SET state='ready',snapshot=? WHERE id=?", (json.dumps(snapshot), value["id"]))
    return value["id"]


def receipt(store, job, payload, **changes):
    claims = {"owner": "owner", "session": "session", "job": job, "action": "decision",
              "revision": "a"*64, "payload_sha": hashlib.sha256(canonical(payload)).hexdigest(),
              "nonce": uuid4().hex, "expires": time.time()+100, **changes}
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return encoded+"."+hmac.new(store.key, encoded.encode(), hashlib.sha256).hexdigest()


def test_concurrent_start_is_one_run_and_idempotent(store):
    job = ready(store)
    def start(_):
        return store.start(job, "owner", "session", {"revision_hash": "a"*64}, "one-key")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(start, range(8)))
    assert len({r["run_id"] for r in results}) == 1
    assert store.db.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
    with pytest.raises(ApiError) as caught:
        store.start(job, "owner", "session", {"revision_hash": "b"*64}, "one-key")
    assert caught.value.status == 409
    with pytest.raises(ApiError):
        store.start(job, "owner", "session", {"revision_hash": "a"*64}, "different-key")


def test_cross_owner_session_and_unpublished_artifacts_are_invisible(store):
    job = ready(store)
    for owner, session in [("other", "session"), ("owner", "other")]:
        with pytest.raises(ApiError) as caught:
            store.get(job, owner, session)
        assert caught.value.status == 404
    run = store.start(job, "owner", "session", {"revision_hash": "a"*64}, "key")["run_id"]
    with pytest.raises(ApiError):
        store.artifact(job, run, "anything", "owner", "session")
    store.cancel(job, run, "owner", "session", "a"*64)
    assert store.get(job, "owner", "session")["run"]["state"] == "cancelled"
    store.start(job, "owner", "session", {"revision_hash": "a"*64}, "retry-new-key")
    assert store.db.execute("SELECT count(*) FROM runs").fetchone()[0] == 2


def test_receipt_rejects_replay_changed_payload_wrong_session_and_expiry(store):
    payload = {"kind": "skip", "row_ids": ["Sheet1:2"], "reason": "用户选择"}
    token = receipt(store, "job", payload)
    store._receipt(token, "owner", "session", "job", "decision", "a"*64, payload)
    with pytest.raises(ApiError):
        store._receipt(token, "owner", "session", "job", "decision", "a"*64, payload)
    for token, session, body in [
        (receipt(store, "job", payload), "different", payload),
        (receipt(store, "job", payload), "session", {**payload, "row_ids": ["Sheet1:3"]}),
        (receipt(store, "job", payload, expires=time.time()-1), "session", payload),
        ("confirmed:true", "session", payload),
    ]:
        with pytest.raises(ApiError):
            store._receipt(token, "owner", session, "job", "decision", "a"*64, body)


def test_restart_never_publishes_orphan_or_running_directory(store):
    job = ready(store)
    run = store.start(job, "owner", "session", {"revision_hash": "a"*64}, "key")["run_id"]
    package = store.root / "jobs" / job / "runs" / run / "package"
    package.mkdir(parents=True)
    (package / "orphan.pdf").write_bytes(b"partial")
    restarted = Store(store.root, store.template, "k"*64, start_worker=False)
    try:
        value = restarted.get(job, "owner", "session")
        assert value["state"] == value["run"]["state"] == "paused_error"
        assert value["run"]["artifacts"] == []
        with pytest.raises(ApiError):
            restarted.artifact(job, run, "orphan.pdf", "owner", "session")
    finally:
        restarted.close()


def test_download_rehashes_file_and_denies_symlink(store):
    job = ready(store)
    run = store.start(job, "owner", "session", {"revision_hash": "a"*64}, "key")["run_id"]
    package = store.root / "jobs" / job / "runs" / run / "package"
    package.mkdir(parents=True)
    file = package / "file.pdf"
    file.write_bytes(b"valid")
    entry = {"id": "artifact", "path": "file.pdf", "bytes": 5, "sha256": hashlib.sha256(b"valid").hexdigest()}
    store.db.execute("UPDATE runs SET state='generated',artifacts=? WHERE id=?", (json.dumps([entry]), run))
    assert store.artifact(job, run, "artifact", "owner", "session")[0] == file
    file.write_bytes(b"wrong")
    with pytest.raises(ApiError):
        store.artifact(job, run, "artifact", "owner", "session")
    file.unlink()
    outside = store.root / "outside"
    outside.write_bytes(b"valid")
    file.symlink_to(outside)
    with pytest.raises(ApiError):
        store.artifact(job, run, "artifact", "owner", "session")


def test_unconfirmed_or_unknown_decision_fields_never_queue(store):
    job = ready(store)
    with pytest.raises(ApiError):
        store.decision(job, "owner", "session", {"confirmed": True})
    with pytest.raises(ApiError):
        store.start(job, "owner", "session", {"revision_hash": "a"*64, "confirmed": True}, "key")


def test_review_rejects_old_run_even_with_fresh_valid_receipt(store):
    job = ready(store)
    old = store.start(job, "owner", "session", {"revision_hash": "a"*64}, "first")["run_id"]
    store.db.execute("UPDATE runs SET state='generated',manifest_sha='old-manifest' WHERE id=?", (old,))
    store.db.execute("UPDATE jobs SET state='generated' WHERE id=?", (job,))
    new = store.start(job, "owner", "session", {"revision_hash": "a"*64}, "second")["run_id"]
    payload = {"run_id": old, "status": "approved", "comment": "stale", "manifest_sha": "old-manifest"}
    token = receipt(store, job, payload, action="review")
    with pytest.raises(ApiError) as caught:
        store.review(job, old, "owner", "session", {"revision_hash": "a"*64, "status": "approved", "comment": "stale", "receipt": token})
    assert caught.value.status == 409
    assert store.get(job, "owner", "session")["run"]["id"] == new


def test_unexpected_worker_exception_stops_running_state(store, monkeypatch):
    job = ready(store)
    run = store.start(job, "owner", "session", {"revision_hash": "a"*64}, "first")["run_id"]
    store.db.execute("UPDATE tasks SET state='done' WHERE op='analyze'")
    def fail(_task):
        store.stop.set()
        raise OSError("disk error during generation")
    monkeypatch.setattr(store, "_execute", fail)
    store._loop()
    result = store.get(job, "owner", "session")
    assert result["state"] == result["run"]["state"] == "paused_error"
    assert result["run"]["id"] == run
    assert result["run"]["artifacts"] == []
