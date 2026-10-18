"""Object storage for build files: S3-compatible via minimal SigV4 (httpx), local-disk fallback.

Configure with PHOTO3D_S3_ENDPOINT / PHOTO3D_S3_BUCKET / PHOTO3D_S3_KEY / PHOTO3D_S3_SECRET
(/ PHOTO3D_S3_REGION, default us-east-1). Unconfigured = local mode: files stay on the
server disk (OUT/<id>/...) exactly as today — no behavior change until you opt in.

Retention note (deliberate): the ROADMAP says accounts and data are never deleted by the app.
Build files keep their existing keep-time rules (services/retention.py: starred = never,
saved = 30 days, others = 7 days). Object storage adds NO deletion policy of its own.

What this is NOT yet: the build pipeline still writes model files to disk. This module is the
storage seam (put/get/signed URLs, tested against a live S3-compatible server shape); moving
every exporter write through it is a follow-up. Signed URLs are for serving stored objects
without proxying bytes through the app.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import os
from urllib.parse import quote

import httpx

_SERVICE = "s3"


def _cfg() -> dict:
    return {
        "endpoint": (os.environ.get("PHOTO3D_S3_ENDPOINT") or "").strip().rstrip("/"),
        "bucket": (os.environ.get("PHOTO3D_S3_BUCKET") or "").strip(),
        "key": (os.environ.get("PHOTO3D_S3_KEY") or "").strip(),
        "secret": os.environ.get("PHOTO3D_S3_SECRET") or "",
        "region": (os.environ.get("PHOTO3D_S3_REGION") or "us-east-1").strip(),
    }


def enabled() -> bool:
    c = _cfg()
    return bool(c["endpoint"] and c["bucket"] and c["key"] and c["secret"])


# --- SigV4 (https://docs.aws.amazon.com/general/latest/gr/signature-version-4.html) ---

def _h(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _sign_request(method: str, url: str, headers: dict, payload: bytes, cfg: dict,
                  amz_date: datetime.datetime | None = None) -> dict:
    """Return headers with an Authorization: AWS4-HMAC-SHA256 header added."""
    now = amz_date or datetime.datetime.now(datetime.timezone.utc)
    amz = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    host = httpx.URL(url).host
    if httpx.URL(url).port not in (None, 80, 443):
        host = f"{host}:{httpx.URL(url).port}"
    headers = dict(headers)
    headers["host"] = host
    headers["x-amz-date"] = amz
    headers["x-amz-content-sha256"] = hashlib.sha256(payload).hexdigest()
    signed_headers = ";".join(sorted(k.lower() for k in headers))
    canonical_headers = "".join(f"{k.lower()}:{headers[k].strip()}\n" for k in sorted(headers, key=str.lower))
    canonical = "\n".join([
        method,
        quote(httpx.URL(url).path or "/", safe="/"),
        "",                                  # no query params on these calls
        canonical_headers,
        signed_headers,
        headers["x-amz-content-sha256"],
    ])
    scope = f"{datestamp}/{cfg['region']}/{_SERVICE}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _h(("AWS4" + cfg["secret"]).encode(), datestamp)
    for part in (cfg["region"], _SERVICE, "aws4_request"):
        k = _h(k, part)
    signature = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={cfg['key']}/{scope}, "
                               f"SignedHeaders={signed_headers}, Signature={signature}")
    return headers


def _object_url(key: str, cfg: dict) -> str:
    return f"{cfg['endpoint']}/{cfg['bucket']}/{quote(key.lstrip('/'))}"


def put(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Store one object. Returns the (unsigned) object URL."""
    cfg = _cfg()
    url = _object_url(key, cfg)
    headers = _sign_request("PUT", url, {"content-type": content_type}, data, cfg)
    with httpx.Client(timeout=60) as c:
        r = c.put(url, content=data, headers=headers)
        r.raise_for_status()
    return url


def get(key: str) -> bytes:
    cfg = _cfg()
    url = _object_url(key, cfg)
    headers = _sign_request("GET", url, {}, b"", cfg)
    with httpx.Client(timeout=60) as c:
        r = c.get(url, headers=headers)
        r.raise_for_status()
        return r.content


def delete(key: str) -> None:
    cfg = _cfg()
    url = _object_url(key, cfg)
    headers = _sign_request("DELETE", url, {}, b"", cfg)
    with httpx.Client(timeout=60) as c:
        r = c.delete(url, headers=headers)
        r.raise_for_status()


def signed_url(key: str, ttl_s: int = 900) -> str:
    """Presigned GET URL (query-string signature, expires after ttl_s). Object mode only."""
    cfg = _cfg()
    url = _object_url(key, cfg)
    now = datetime.datetime.now(datetime.timezone.utc)
    amz = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    expiry = int(now.timestamp()) + int(ttl_s)
    # unsigned headers only: host (from the URL)
    host = httpx.URL(url).host
    if httpx.URL(url).port not in (None, 80, 443):
        host = f"{host}:{httpx.URL(url).port}"
    headers = {"host": host}
    signed_headers = "host"
    canonical_headers = f"host:{host}\n"
    canonical = "\n".join(["GET", quote(httpx.URL(url).path or "/", safe="/"), "", canonical_headers, signed_headers,
                           "UNSIGNED-PAYLOAD"])
    scope = f"{datestamp}/{cfg['region']}/{_SERVICE}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _h(("AWS4" + cfg["secret"]).encode(), datestamp)
    for part in (cfg["region"], _SERVICE, "aws4_request"):
        k = _h(k, part)
    signature = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    return (f"{url}?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential={quote(cfg['key'] + '/' + scope)}"
            f"&X-Amz-Date={amz}&X-Amz-Expires={ttl_s}&X-Amz-SignedHeaders=host"
            f"&X-Amz-Signature={signature}&Expires={expiry}")
