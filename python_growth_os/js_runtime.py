from __future__ import annotations
import json, os, subprocess
from pathlib import Path
BRIDGE = Path(__file__).with_name("js_bridge.js")
class JSRuntimeError(RuntimeError): pass
def _run(payload: dict, timeout: float = 130.0):
    proc = subprocess.run(["node", str(BRIDGE)], input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True, timeout=timeout, env=os.environ.copy())
    if proc.returncode:
        try: detail=json.loads(proc.stderr)
        except Exception: detail={"message":proc.stderr.strip()}
        raise JSRuntimeError(detail.get("message", "JavaScript execution failed"))
    try: return json.loads(proc.stdout)
    except Exception as exc: raise JSRuntimeError("Invalid JavaScript bridge output") from exc
def eval_js(source: str, *, current: dict, previous: dict, env: dict, execution: dict):
    return _run({"mode":"expr","source":source,"current":current,"previous":previous,"env":env,"execution":execution}, 35)
def run_code(source: str, *, current: dict, previous: dict, env: dict, execution: dict):
    return _run({"mode":"code","source":source,"current":current,"previous":previous,"env":env,"execution":execution}, 150)
