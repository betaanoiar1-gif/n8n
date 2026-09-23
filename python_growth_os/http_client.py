from __future__ import annotations
import base64
import os
import httpx
from .credentials import credential_headers, credential_query, youtube_oauth_env

class HTTPClient:
    async def _youtube_access_token(self):
        cfg = youtube_oauth_env()
        if cfg["access_token"]:
            return cfg["access_token"]
        if not all((cfg["client_id"], cfg["client_secret"], cfg["refresh_token"])):
            raise RuntimeError(
                "YOUTUBE_CREDENTIAL requires YOUTUBE_ACCESS_TOKEN or "
                "YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET/YOUTUBE_REFRESH_TOKEN"
            )
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                    "refresh_token": cfg["refresh_token"],
                    "grant_type": "refresh_token",
                },
            )
        if r.status_code >= 400:
            raise RuntimeError(f"YouTube OAuth refresh failed: HTTP {r.status_code}: {r.text[:1000]}")
        token = r.json().get("access_token")
        if not token:
            raise RuntimeError("YouTube OAuth refresh response did not contain access_token")
        os.environ["YOUTUBE_ACCESS_TOKEN"] = token
        return token

    async def request(self, node, resolved, item=None):
        p = node.get("parameters", {})
        method = str(resolved.get("method") or "GET").upper()
        url = str(resolved.get("url") or "")
        headers = dict(resolved.get("headers") or {})
        credentials = node.get("credentials") or {}
        cred = next(iter(credentials.values()), {}).get("name")
        if cred == "YOUTUBE_CREDENTIAL":
            headers["Authorization"] = "Bearer " + await self._youtube_access_token()
        else:
            headers.update(credential_headers(cred))
        params = dict(resolved.get("params") or {})
        params.update(credential_query(cred))

        body = resolved.get("body")
        timeout = float(p.get("options", {}).get("timeout", 120000)) / 1000
        follow = bool(
            p.get("options", {}).get("redirect", {})
             .get("redirect", {}).get("followRedirects", False)
        )

        content = None
        json_body = None
        if p.get("contentType") == "binaryData" or p.get("inputDataFieldName"):
            binary = (item or {}).get("binary") or {}
            field = p.get("inputDataFieldName", "data")
            entry = binary.get(field) or {}
            encoded = entry.get("data") if isinstance(entry, dict) else None
            if encoded:
                content = base64.b64decode(encoded)
                headers.setdefault("Content-Type", entry.get("mimeType", "application/octet-stream"))
            elif body is not None:
                content = body.encode() if isinstance(body, str) else body
        elif isinstance(body, (dict, list)):
            json_body = body
        elif body is not None:
            content = body.encode() if isinstance(body, str) else body

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=follow) as c:
            r = await c.request(
                method, url, headers=headers, params=params, json=json_body, content=content
            )

        response_opts = p.get("options", {}).get("response", {}).get("response", {})
        response_format = response_opts.get("responseFormat", "json")
        if response_format == "file":
            b = base64.b64encode(r.content).decode()
            return {
                "json": {"statusCode": r.status_code, "headers": dict(r.headers)},
                "binary": {"data": {
                    "data": b,
                    "mimeType": r.headers.get("content-type", "application/octet-stream"),
                    "fileName": url.rstrip("/").split("/")[-1] or "download.bin",
                    "fileSize": len(r.content),
                }},
            }

        if response_format == "text":
            payload = r.text
        else:
            try:
                payload = r.json()
            except Exception:
                payload = r.text

        return {"json": {"statusCode": r.status_code, "headers": dict(r.headers), "body": payload}}
