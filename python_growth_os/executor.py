from __future__ import annotations
import asyncio
import json
import os
import uuid
from collections import deque
from .expressions import resolve
from .js_runtime import run_code
from .http_client import HTTPClient

class WorkflowError(RuntimeError):
    pass

class Executor:
    def __init__(self, workflow, db):
        self.wf = workflow
        self.db = db
        self.nodes = {n["name"]: n for n in workflow["nodes"]}
        self.connections = workflow.get("connections", {})
        self.http = HTTPClient()
        self.outputs = {}
        self.execution_id = str(uuid.uuid4())
        self.env = dict(os.environ)
        self.webhook_response = None

    def targets(self, name, index=0):
        groups = self.connections.get(name, {}).get("main", [])
        return [
            x["node"] for x in (groups[index] if index < len(groups) else [])
            if x.get("node") in self.nodes
        ]

    async def ev(self, value, item):
        return resolve(
            value,
            current=item,
            previous=self.outputs,
            env=self.env,
            execution={"id": self.execution_id, "mode": "python"},
        )

    async def execute_node(self, name, item):
        node = self.nodes[name]
        node_type = node["type"]
        params = node.get("parameters", {})

        if node_type in ("n8n-nodes-base.manualTrigger", "n8n-nodes-base.scheduleTrigger"):
            out, index = [item], 0
        elif node_type == "n8n-nodes-base.code":
            result = run_code(
                params.get("jsCode", ""),
                current=item,
                previous=self.outputs,
                env=self.env,
                execution={"id": self.execution_id, "mode": "python"},
            )
            out, index = self.norm(result), 0
        elif node_type == "n8n-nodes-base.postgres":
            query = params.get("query", "")
            replacement = params.get("options", {}).get("queryReplacement")
            args = await self.ev(replacement, item) if replacement else []
            if not isinstance(args, list):
                args = [args]
            rows = await self.db.execute(query, args)
            out, index = [{"json": row} for row in rows], 0
        elif node_type == "n8n-nodes-base.httpRequest":
            resolved = {
                "method": await self.ev(params.get("method", "GET"), item),
                "url": await self.ev(params.get("url", ""), item),
            }
            if params.get("sendHeaders"):
                resolved["headers"] = {
                    h["name"]: await self.ev(h.get("value", ""), item)
                    for h in params.get("headerParameters", {}).get("parameters", [])
                    if h.get("name")
                }
            if params.get("sendQuery"):
                resolved["params"] = {
                    q["name"]: await self.ev(q.get("value", ""), item)
                    for q in params.get("queryParameters", {}).get("parameters", [])
                    if q.get("name")
                }
            if params.get("sendBody"):
                if params.get("jsonBody") is not None:
                    resolved["body"] = await self.ev(params["jsonBody"], item)
                elif params.get("bodyParameters"):
                    resolved["body"] = await self.ev(params["bodyParameters"], item)
            result = await self.http.request(node, resolved, item=item)
            out, index = [result], 0
        elif node_type == "n8n-nodes-base.if":
            out, index = [item], 0 if await self.conditions(params.get("conditions", {}), item) else 1
        elif node_type == "n8n-nodes-base.switch":
            rules = params.get("rules", {}).get("values", [])
            index = len(rules)
            for i, rule in enumerate(rules):
                if await self.conditions(rule.get("conditions", {}), item):
                    index = i
                    break
            out = [item]
        elif node_type == "n8n-nodes-base.wait":
            seconds = await self.ev(params.get("amount", 0), item)
            await asyncio.sleep(max(0, float(seconds or 0)))
            out, index = [item], 0
        elif node_type == "n8n-nodes-base.respondToWebhook":
            self.webhook_response = item
            out, index = [], 0
        elif node_type == "n8n-nodes-base.webhook":
            out, index = [item], 0
        else:
            raise WorkflowError(f"Unsupported node type: {node_type} ({name})")

        # Store the actual node output, not the input. This makes $().item/.first/.all
        # behave correctly for downstream Code/Expression nodes.
        self.outputs[name] = out
        return out, index

    async def conditions(self, conditions, item):
        cs = conditions.get("conditions", [])
        results = []
        for condition in cs:
            left = await self.ev(condition.get("leftValue"), item)
            right = await self.ev(condition.get("rightValue"), item)
            op = condition.get("operator", {}).get("operation")
            if op == "true":
                ok = bool(left)
            elif op == "false":
                ok = not bool(left)
            elif op == "equals":
                ok = left == right
            elif op == "notEquals":
                ok = left != right
            elif op == "contains":
                ok = right in left if isinstance(left, (str, list)) else False
            elif op == "notContains":
                ok = right not in left if isinstance(left, (str, list)) else True
            elif op == "startsWith":
                ok = str(left).startswith(str(right))
            elif op == "endsWith":
                ok = str(left).endswith(str(right))
            elif op == "gt":
                ok = left > right
            elif op == "gte":
                ok = left >= right
            elif op == "lt":
                ok = left < right
            elif op == "lte":
                ok = left <= right
            elif op == "isEmpty":
                ok = left in (None, "", [], {})
            elif op == "isNotEmpty":
                ok = left not in (None, "", [], {})
            else:
                raise WorkflowError(f"Unsupported condition operator: {op}")
            results.append(ok)
        return all(results) if conditions.get("combinator", "and") == "and" else any(results)

    @staticmethod
    def norm(out):
        if out is None:
            return []
        if isinstance(out, dict) and "json" in out:
            return [out]
        if isinstance(out, list):
            return [
                x if isinstance(x, dict) and "json" in x else {"json": x}
                for x in out
            ]
        return [{"json": out}]

    async def run(self, start, initial=None, max_steps=2000):
        queue = deque([(start, initial or {"json": {}})])
        steps = 0
        while queue:
            name, item = queue.popleft()
            steps += 1
            if steps > max_steps:
                raise WorkflowError("Execution step limit reached; possible workflow cycle")
            try:
                out, index = await self.execute_node(name, item)
            except Exception as exc:
                if self.nodes[name].get("onError") == "continueErrorOutput":
                    out = [{
                        "json": {
                            **item.get("json", {}),
                            "error": {"message": str(exc), "node": name},
                        }
                    }]
                    index = 1
                    self.outputs[name] = out
                else:
                    raise
            for child in self.targets(name, index):
                for output_item in out:
                    queue.append((child, output_item))
        return self.webhook_response
