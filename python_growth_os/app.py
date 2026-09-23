from __future__ import annotations
import argparse,asyncio,json,os,base64
from pathlib import Path
from fastapi import FastAPI,Header,HTTPException,Request
from fastapi.responses import JSONResponse,Response
import uvicorn
from dotenv import load_dotenv
from .executor import Executor
from .storage import Postgres
ROOT=Path(__file__).resolve().parent.parent; WORKFLOW=ROOT/"workflow_source.json"; load_dotenv(ROOT/".env")
async def build_executor():
 dsn=os.getenv("POSTGRES_DSN")
 if not dsn: raise RuntimeError("POSTGRES_DSN is required; the source workflow uses PostgreSQL.")
 db=Postgres(dsn); await db.connect(); return Executor(json.loads(WORKFLOW.read_text(encoding="utf-8")),db),db
async def run_once(trigger="manual",body=None):
 ex,db=await build_executor()
 try:return await ex.run({"manual":"Manual Start","scheduled":"Every 15 Minutes"}[trigger],{"json":{"trigger":trigger,"input":body or {"mode":"full_cycle"}}})
 finally:await db.close()
app=FastAPI(title="YouTube Autonomous Growth OS - Python")
def auth(token):
 expected=os.getenv("WORKER_CREDENTIAL_VALUE")
 if expected and token!=expected: raise HTTPException(401,"Invalid worker credential")
@app.post("/webhook/youtube-autonomous-growth-os")
async def control(payload:dict,x_worker_key:str|None=Header(default=None)):
 auth(x_worker_key); ex,db=await build_executor()
 try:return JSONResponse(content=await ex.run("Authenticated Control Webhook",{"json":{"body":payload}}) or {"accepted":True})
 finally:await db.close()
@app.post("/webhook/youtube-growth-os-v2/worker-bundle")
async def bundle(x_worker_key:str|None=Header(default=None)):
 auth(x_worker_key); ex,db=await build_executor()
 try:
  out=await ex.run("Authenticated Worker Bundle Download",{"json":{"headers":{"x-worker-key":x_worker_key}}})
  if not out: raise HTTPException(404,"Worker bundle was not produced")
  binary=out.get("binary",{}).get("data",{}) if isinstance(out,dict) else {}
  data=base64.b64decode(binary["data"]) if binary.get("data") else None
  if not data: raise HTTPException(500,"Worker bundle binary missing")
  return Response(data,media_type=binary.get("mimeType","application/zip"),headers={"Content-Disposition":f'attachment; filename="{binary.get("fileName","growth_os_v2_local_worker.zip")}"'})
 finally:await db.close()
async def scheduler():
 while True:
  try:
   if os.getenv("SCHEDULE_ENABLED","true").lower()=="true": await run_once("scheduled")
  except Exception as e: print("[scheduler]",e)
  await asyncio.sleep(900)
async def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--run",action="store_true"); ap.add_argument("--schedule",action="store_true"); ap.add_argument("--host",default="127.0.0.1"); ap.add_argument("--port",type=int,default=8443); ap.add_argument("--mode",default="full_cycle"); ap.add_argument("--action",default="run"); ap.add_argument("--job-id"); ap.add_argument("--actor"); a=ap.parse_args()
 if a.run:
  r=await run_once("manual",{"mode":a.mode,"action":a.action,"job_id":a.job_id,"actor":a.actor}); print(json.dumps(r or {"status":"completed"},ensure_ascii=False,indent=2,default=str)); return
 if a.schedule: await scheduler(); return
 await uvicorn.Server(uvicorn.Config(app,host=a.host,port=a.port,log_level="info")).serve()
if __name__=="__main__":asyncio.run(main())
