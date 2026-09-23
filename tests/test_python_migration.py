import asyncio
import json
from pathlib import Path

from python_growth_os.executor import Executor
from python_growth_os.js_runtime import eval_js, run_code

ROOT = Path(__file__).resolve().parents[1]

def test_source_workflow_contract():
    wf = json.loads((ROOT / "workflow_source.json").read_text(encoding="utf-8"))
    assert len(wf["nodes"]) == 131
    scheduler = next(n for n in wf["nodes"] if n["name"] == "Every 15 Minutes")
    assert scheduler["parameters"]["rule"]["interval"][0]["minutesInterval"] == 15
    supported = {
        "n8n-nodes-base.manualTrigger", "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.webhook", "n8n-nodes-base.code",
        "n8n-nodes-base.postgres", "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.switch", "n8n-nodes-base.if",
        "n8n-nodes-base.wait", "n8n-nodes-base.respondToWebhook",
    }
    assert {n["type"] for n in wf["nodes"]} <= supported
    forbidden_globals = ("$helpers", "$workflow", "$node", "$items", "this.helpers", "$http", "$request")
    for node in wf["nodes"]:
        if node["type"] == "n8n-nodes-base.code":
            source = node["parameters"].get("jsCode", "")
            assert not any(token in source for token in forbidden_globals), node["name"]

def test_js_bridge_previous_items():
    previous = {"Producer": [{"json": {"value": 1}}, {"json": {"value": 2}}]}
    value = eval_js(
        '$("Producer").all().map(x => x.json.value).join(",")',
        current={"json": {}}, previous=previous, env={},
        execution={"id": "test", "mode": "manual"},
    )
    assert value == "1,2"

def test_code_node_execution():
    result = run_code(
        'return [{json:{sum:$json.a+$json.b, prior:$("Previous").item.json.value}}];',
        current={"json": {"a": 2, "b": 3}},
        previous={"Previous": [{"json": {"value": 7}}]}, env={},
        execution={"id": "test", "mode": "manual"},
    )
    assert result[0]["json"] == {"sum": 5, "prior": 7}

class FakeDB:
    async def execute(self, query, args):
        return [{"ok": True, "args": args}]

def test_executor_if_and_graph():
    wf = {
        "nodes": [
            {"name": "Start", "type": "n8n-nodes-base.manualTrigger", "parameters": {}},
            {"name": "Set", "type": "n8n-nodes-base.code", "parameters": {"jsCode": "return [{json:{value:3}}];"}},
            {"name": "Check", "type": "n8n-nodes-base.if", "parameters": {"conditions": {"conditions": [{
                "leftValue": "={{ $json.value }}", "rightValue": 3, "operator": {"operation": "equals"}
            }], "combinator": "and"}}},
            {"name": "Yes", "type": "n8n-nodes-base.code", "parameters": {"jsCode": "return [{json:{passed:true}}];"}},
            {"name": "No", "type": "n8n-nodes-base.code", "parameters": {"jsCode": "return [{json:{passed:false}}];"}},
        ],
        "connections": {
            "Start": {"main": [[{"node":"Set","type":"main","index":0}]]},
            "Set": {"main": [[{"node":"Check","type":"main","index":0}]]},
            "Check": {"main": [[{"node":"Yes","type":"main","index":0}], [{"node":"No","type":"main","index":0}]]}
        }
    }
    async def run():
        ex = Executor(wf, FakeDB())
        await ex.run("Start", {"json": {}})
        assert ex.outputs["Yes"][0]["json"]["passed"] is True
        assert "No" not in ex.outputs
    asyncio.run(run())

def test_ui_exists():
    ui = ROOT / "python_growth_os" / "ui" / "index.html"
    html = ui.read_text(encoding="utf-8")
    assert "YouTube Autonomous Growth OS" in html
    assert "/api/settings" in html
    assert "/api/run" in html
    assert "/api/scheduler" in html
