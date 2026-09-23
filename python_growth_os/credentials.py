from __future__ import annotations
import os

SPECIFIC = {
    "KIOS_CREDENTIAL": ("KIOS_API_KEY", "Authorization", "Bearer "),
    "PEXELS_CREDENTIAL": ("PEXELS_API_KEY", "Authorization", ""),
    "PIXABAY_CREDENTIAL": ("PIXABAY_API_KEY", "key", ""),
    "OPENROUTER_CREDENTIAL": ("OPENROUTER_API_KEY", "Authorization", "Bearer "),
    "WORKER_CREDENTIAL": ("WORKER_CREDENTIAL_VALUE", "x-worker-key", ""),
}

def credential_headers(name):
    if not name:
        return {}
    key, header, prefix = SPECIFIC.get(
        name,
        (f"CRED_{name}_VALUE", os.getenv(f"CRED_{name}_HEADER", "Authorization"), ""),
    )
    value = os.getenv(key) or os.getenv(f"CRED_{name}_VALUE")
    return {header: prefix + value} if value else {}

def credential_query(name):
    if name == "PIXABAY_CREDENTIAL" and os.getenv("PIXABAY_API_KEY"):
        return {"key": os.environ["PIXABAY_API_KEY"]}
    return {}

def youtube_oauth_env():
    return {
        "access_token": os.getenv("YOUTUBE_ACCESS_TOKEN", "").strip(),
        "client_id": os.getenv("YOUTUBE_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", "").strip(),
        "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip(),
    }
