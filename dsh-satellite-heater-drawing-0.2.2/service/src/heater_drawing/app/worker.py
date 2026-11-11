"""One bounded engine operation per child process, never user code."""
import argparse
import ctypes
import json
import os
import signal
from pathlib import Path


def main():
    parent = int(os.environ.get("HEATER_WORKER_PARENT", "0"))
    if parent:
        if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL) != 0 or os.getppid() != parent:
            os._exit(127)
    from .engine import analyze, decide, generate

    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    result = args.request.with_name("result.json")
    try:
        template = Path(request["template"])
        if request["op"] == "analyze":
            value = analyze(Path(request["source"]), template)
        elif request["op"] == "decide":
            value = decide(request["current"], request["selection"], request["actor"], request["receipt_id"], template)
        elif request["op"] == "generate":
            value = generate(Path(request["source"]), Path(request["revision_file"]),
                             template, Path(request["output"]), request["name"])
        else:
            raise ValueError("unknown_operation")
        value = {"ok": True, "value": value}
    except Exception as exc:
        # Public errors never leak paths, secrets or Python tracebacks.
        value = {"ok": False, "code": getattr(exc, "code", "ENGINE_FAILED"),
                 "message": "出图检查未通过，请核查输入、字体和 CAD 运行环境；完整交付未发布"}
        args.request.with_name("diagnostic.txt").write_text(type(exc).__name__ + ": " + str(exc))
    temporary = result.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False))
    temporary.replace(result)


if __name__ == "__main__":
    main()
