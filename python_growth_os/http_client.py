from __future__ import annotations
import base64,os,httpx
from .credentials import credential_headers,credential_query
class HTTPClient:
 async def request(self,node,resolved):
  p=node.get("parameters",{}); method=str(resolved.get("method") or "GET").upper(); url=str(resolved.get("url") or "")
  headers=dict(resolved.get("headers") or {})
  cred=next(iter((node.get("credentials") or {}).values()),{}).get("name")
  headers.update(credential_headers(cred)); params=credential_query(cred)
  body=resolved.get("body"); timeout=float(p.get("options",{}).get("timeout",120000))/1000
  follow=bool(p.get("options",{}).get("redirect",{}).get("redirect",{}).get("followRedirects",False))
  async with httpx.AsyncClient(timeout=timeout,follow_redirects=follow) as c:
   r=await c.request(method,url,headers=headers,params=params,json=body if isinstance(body,(dict,list)) else None,content=body.encode() if isinstance(body,str) else None)
  if p.get("options",{}).get("response",{}).get("response",{}).get("responseFormat")=="file":
   b=base64.b64encode(r.content).decode()
   return {"json":{"statusCode":r.status_code,"headers":dict(r.headers)},"binary":{"data":{"data":b,"mimeType":r.headers.get("content-type","application/octet-stream"),"fileName":url.rstrip("/").split("/")[-1] or "download.bin","fileSize":len(r.content)}}}
  try: payload=r.json()
  except Exception: payload=r.text
  return {"json":{"statusCode":r.status_code,"headers":dict(r.headers),"body":payload}}
