"""Cloudinary-backed storage for uploaded documents and media.

Uploaded files used to be written to the local filesystem (uploads/), which
Render wipes on every deploy/restart — every previously uploaded file then
404'd while its DB row survived. This module uploads the bytes to Cloudinary
instead, and serves them back through the *existing* same-origin endpoints
(/documents/file/{id}, /media/file/{id}) by proxying the download. Proxying
(rather than redirecting the browser to Cloudinary) keeps the auth cookie,
CSP (`img-src 'self'`) and CORS behaviour of those endpoints exactly as they
were, and preserves HTTP Range requests so video seeking still works.

Configured purely from env vars:
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET
    CLOUDINARY_FOLDER      (optional, default "cpbot")

When those are unset (local dev, tests) is_configured() is False and callers
fall back to the previous local-disk behaviour.

Storage references written to the documents/media `file_path` column:
    "cloudinary:<public_id>"   -> stored on Cloudinary
    anything else              -> legacy local disk path
"""
import hashlib
import os
import time

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
API_KEY = os.getenv("CLOUDINARY_API_KEY", "").strip()
API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "").strip()
BASE_FOLDER = os.getenv("CLOUDINARY_FOLDER", "cpbot").strip().strip("/")

CLOUD_PREFIX = "cloudinary:"

# Large media uploads can legitimately take a while on a slow link.
_UPLOAD_TIMEOUT = httpx.Timeout(120.0, read=300.0)
# Downloads stream indefinitely (a long video must not be cut off mid-stream).
_STREAM_TIMEOUT = httpx.Timeout(60.0, read=None)


def is_configured() -> bool:
    return bool(CLOUD_NAME and API_KEY and API_SECRET)


def cloud_ref(public_id: str) -> str:
    return f"{CLOUD_PREFIX}{public_id}"


def is_cloud_ref(path: str | None) -> bool:
    return bool(path) and path.startswith(CLOUD_PREFIX)


def public_id_of(ref: str) -> str:
    return ref[len(CLOUD_PREFIX):]


def _signature(params: dict) -> str:
    # Cloudinary signs the alphabetically-sorted, &-joined params (excluding
    # file, api_key, resource_type and cloud_name) with the api_secret.
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hashlib.sha1((to_sign + API_SECRET).encode("utf-8")).hexdigest()


def delivery_url(public_id: str, resource_type: str) -> str:
    return f"https://res.cloudinary.com/{CLOUD_NAME}/{resource_type}/upload/{public_id}"


async def upload_bytes(
    data: bytes,
    *,
    folder: str,
    resource_type: str,
    filename: str | None,
    public_id: str,
) -> dict:
    """Uploads `data` to Cloudinary and returns {public_id, resource_type, url}.

    resource_type is one of "image", "video" or "raw" (documents always use
    "raw"). Raises HTTPException(502) if Cloudinary rejects the upload so the
    caller's request fails loudly rather than silently storing a dead row.
    """
    if not is_configured():
        raise RuntimeError("Cloudinary is not configured")

    # For image/video Cloudinary derives the format from the upload itself and
    # expects a public_id without an extension; for raw it keeps the extension.
    if resource_type != "raw":
        public_id = os.path.splitext(public_id)[0]

    timestamp = int(time.time())
    full_public_id = f"{BASE_FOLDER}/{folder.strip('/')}/{public_id}" if folder else f"{BASE_FOLDER}/{public_id}"
    sign_params = {
        "folder": f"{BASE_FOLDER}/{folder.strip('/')}" if folder else BASE_FOLDER,
        "public_id": public_id,
        "timestamp": timestamp,
        "type": "upload",
    }
    form = dict(sign_params)
    form["api_key"] = API_KEY
    form["signature"] = _signature(sign_params)

    url = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/{resource_type}/upload"
    try:
        async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
            resp = await client.post(
                url,
                data=form,
                files={"file": (filename or public_id, data, "application/octet-stream")},
            )
    except httpx.HTTPError as e:
        logger.error(f"Cloudinary upload transport error: {e}")
        raise HTTPException(status_code=502, detail="File storage upload failed")

    if resp.status_code >= 400:
        logger.error(f"Cloudinary upload failed ({resp.status_code}): {resp.text[:500]}")
        raise HTTPException(status_code=502, detail="File storage upload failed")

    payload = resp.json()
    # Prefer the public_id Cloudinary echoes back (it includes the folder and,
    # for raw, the extension) so delivery URLs are reconstructed exactly.
    return {
        "public_id": payload.get("public_id", full_public_id),
        "resource_type": payload.get("resource_type", resource_type),
        "url": payload.get("secure_url"),
    }


async def delete(ref: str, resource_type: str) -> None:
    """Best-effort delete of a Cloudinary-backed file (never raises)."""
    if not is_configured():
        return
    public_id = public_id_of(ref)
    timestamp = int(time.time())
    sign_params = {"public_id": public_id, "timestamp": timestamp, "type": "upload"}
    form = dict(sign_params)
    form["api_key"] = API_KEY
    form["signature"] = _signature(sign_params)
    url = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/{resource_type}/destroy"
    try:
        async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
            resp = await client.post(url, data=form)
        if resp.status_code >= 400:
            logger.warning(f"Cloudinary delete failed for {public_id} ({resp.status_code}): {resp.text[:200]}")
    except httpx.HTTPError as e:
        logger.warning(f"Cloudinary delete transport error for {public_id}: {e}")


async def proxy(
    ref: str,
    resource_type: str,
    *,
    range_header: str | None = None,
    filename: str | None = None,
    content_type: str | None = None,
) -> StreamingResponse:
    """Streams a Cloudinary-backed file through our own endpoint."""
    public_id = public_id_of(ref)
    url = delivery_url(public_id, resource_type)
    headers = {"Accept-Encoding": "identity"}
    if range_header:
        headers["Range"] = range_header

    client = httpx.AsyncClient(timeout=_STREAM_TIMEOUT)
    try:
        upstream = await client.send(
            client.build_request("GET", url, headers=headers), stream=True
        )
    except httpx.HTTPError as e:
        await client.aclose()
        logger.warning(f"Cloudinary fetch failed for {public_id}: {e}")
        raise HTTPException(status_code=502, detail="Could not fetch stored file")

    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=404, detail="File missing from storage")

    passthrough = {}
    for header in ("content-length", "content-range", "accept-ranges", "etag", "last-modified"):
        value = upstream.headers.get(header)
        if value:
            passthrough[header] = value
    passthrough["content-type"] = content_type or upstream.headers.get("content-type", "application/octet-stream")
    if filename:
        passthrough["content-disposition"] = f'inline; filename="{filename.replace(chr(34), "")}"'

    async def body():
        try:
            # aiter_raw (not aiter_bytes) so a Range response's length/range
            # headers still line up with the bytes we forward (no decompression).
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(body(), status_code=upstream.status_code, headers=passthrough)
