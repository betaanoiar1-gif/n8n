from __future__ import annotations
import asyncio,json,os,uuid
from collections import deque
from .expressions import resolve
from .js_runtime import run_code
from .http_client import HTTPClient
class WorkflowError(RuntimeError): pass
class Executor:
 def __init__(self,workflow,db):
    self.wf=workflow; self.db=db; self.nodes={n["name"]:n for n in workflow["nodes"]}; self.connections=workflow.get("connections",{}); self.http=HTTPClient(); self.outputs={}; self.execution_id=str(uuid.uuid4()); self.env=dict(os.environ)
 def targets(self,name,index=0):
    groups=self.connections.get(name,{}).get("main",[]); return [x["node"] for x in (groups[index] if index<len(groups) else []) if x.get("node") in self.nodes]
 async def ev(self,v,item): return resolve(v,current=item,previous=self.outputs,env=self.env,execution={"id":self.execution_id,"mode":"python"})
 async def execute_node(self,name,item):
    n=self.nodes[name]; t=n["type"]; p=n.get("parameters",{}); self.outputs[name]=item
    if t in ("n8n-nodes-base.manualTrigger","n8n-nodes-base.scheduleTrigger"): return [item],0
    if t=="n8n-nodes-base.code": return self.norm(run_code(p.get("jsCode",""),current=item,previous=self.outputs,env=self.env,execution={"id":self.execution_id,"mode":"python"})),0
    if t=="n8n-nodes-base.postgres":
        q=p.get("query",""); repl=p.get("options",{}).get("queryReplacement"); args=await self.ev(repl,item) if repl else []
        rows=await self.db.execute(q,args if isinstance(args,list) else [args]); return [{"json":r} for r in rows],0
    if t=="n8n-nodes-base.httpRequest":
        resolved={k:await self.ev(v,item) for k,v in {"method":p.get("method"),"url":p.get("url"),"body":p.get("jsonBody")}.items() if v is not None}
        if isinstance(resolved.get("body"),str):
            try: resolved["body"]=json.loads(resolved["body"])
            except Exception: pass
        return [await self.http.request(n,resolved)],0
    if t=="n8n-nodes-base.if": return [item],0 if await self.conditions(p.get("conditions",{}),item) else 1
    if t=="n8n-nodes-base.switch":
        for i,r in enumerate(p.get("rules",{}).get("values",[])):
            if await self.conditions(r.get("conditions",{}),item): return [item],i
        return [item],len(p.get("rules",{}).get("values",[]))
    if t=="n8n-nodes-base.wait": return [item],0
    if t=="n8n-nodes-base.respondToWebhook": self.webhook_response=item; return [],0
    if t=="n8n-nodes-base.webhook": return [item],0
    raise WorkflowError(f"Unsupported node type: {t} ({name})")
 async def conditions(self,c,item):
    cs=c.get("conditions",[]); results=[]
    for x in cs:
        left=await self.ev(x.get("leftValue"),item); right=await self.ev(x.get("rightValue"),item); op=x.get("operator",{}).get("operation")
        if op=="true": ok=bool(left)
        elif op=="false": ok=not bool(left)
        elif op=="equals": ok=left==right
        elif op=="notEquals": ok=left!=right
        elif op=="contains": ok=right in left if isinstance(left,(str,list)) else False
        elif op=="notContains": ok=right not in left if isinstance(left,(str,list)) else True
        elif op=="startsWith": ok=str(left).startswith(str(right))
        elif op=="endsWith": ok=str(left).endswith(str(right))
        elif op=="gt": ok=left>right
        elif op=="gte": ok=left>=right
        elif op=="lt": ok=left<right
        elif op=="lte": ok=left<=right
        elif op=="isEmpty": ok=left in (None,"",[],{})
        elif op=="isNotEmpty": ok=left not in (None,"",[],{})
        else: raise WorkflowError(f"Unsupported condition operator: {op}")
        results.append(ok)
    return all(results) if c.get("combinator","and")=="and" else any(results)
 def norm(self,out):
    if out is None:return []
    if isinstance(out,dict) and "json" in out:return [out]
    if isinstance(out,list): return [x if isinstance(x,dict) and "json" in x else {"json":x} for x in out]
    return [{"json":out}]
 async def run(self,start,initial=None,max_steps=2000):
    q=deque([(start,initial or {"json":{}})]); steps=0
    while q:
        name,item=q.popleft(); steps+=1
        if steps>max_steps: raise WorkflowError("Execution step limit reached; possible workflow cycle")
        try: out,idx=await self.execute_node(name,item)
        except Exception as exc:
            if self.nodes[name].get("onError")=="continueErrorOutput": out=[{"json":{**item.get("json",{}),"error":{"message":str(exc),"node":name}}}]; idx=1
            else: raise
        for child in self.targets(name,idx):
            for o in out:q.append((child,o))
    return getattr(self,"webhook_response",None)
