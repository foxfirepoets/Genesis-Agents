"""Artifact store - uploads job outputs to S3 with signed read URLs.

Falls back to a local Render persistent disk path if AWS credentials
are absent. Phase 9 of the marketplace plan.

Env vars:
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
  GENESIS_S3_BUCKET (default: swarmsync-genesis-artifacts)
  GENESIS_LOCAL_ARTIFACT_DIR (fallback: /var/data/genesis-artifacts)
  GENESIS_SIGNED_URL_TTL_SECONDS (default: 604800 = 7 days)
"""
from __future__ import annotations
import logging, os, shutil
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

S3_BUCKET = os.getenv("GENESIS_S3_BUCKET", "swarmsync-genesis-artifacts")
LOCAL_DIR = Path(os.getenv("GENESIS_LOCAL_ARTIFACT_DIR", "/var/data/genesis-artifacts"))
SIGNED_URL_TTL_S = int(os.getenv("GENESIS_SIGNED_URL_TTL_SECONDS", str(7 * 24 * 3600)))

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
    _BOTO_AVAILABLE = True
except ImportError:
    log.warning("boto3 not installed; artifact_store will use local disk only")
    boto3 = None  # type: ignore
    _BOTO_AVAILABLE = False


def _s3_available() -> bool:
    """True iff boto3 is importable AND we have AWS creds in env."""
    if not _BOTO_AVAILABLE:
        return False
    return bool(os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))


def _s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )


def upload_file(
    *,
    job_id: str,
    local_path: Path,
    object_name: str | None = None,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """Upload a single file. Returns {ok, uri, signed_url, expires_at} or {ok: False, error: ...}."""
    if not local_path.exists():
        return {"ok": False, "error": "local_file_missing", "path": str(local_path)}

    name = object_name or local_path.name
    key = f"{job_id}/{name}"

    if _s3_available():
        try:
            client = _s3_client()
            client.upload_file(
                str(local_path), S3_BUCKET, key,
                ExtraArgs={"ContentType": content_type},
            )
            signed_url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": key},
                ExpiresIn=SIGNED_URL_TTL_S,
            )
            return {
                "ok": True,
                "backend": "s3",
                "uri": f"s3://{S3_BUCKET}/{key}",
                "signed_url": signed_url,
                "expires_in_seconds": SIGNED_URL_TTL_S,
            }
        except (ClientError, BotoCoreError):
            log.exception("S3 upload failed; falling back to local")
            # Fall through to local path

    # Local fallback
    dest = LOCAL_DIR / job_id / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_path, dest)
    return {
        "ok": True,
        "backend": "local",
        "uri": f"file://{dest}",
        "signed_url": f"/artifacts/{job_id}/{name}",  # gateway endpoint serves these
        "expires_in_seconds": None,
    }


def upload_dir(*, job_id: str, local_dir: Path) -> dict[str, Any]:
    """Upload every file in a directory under {job_id}/. Returns {ok, files: [...]}."""
    if not local_dir.exists() or not local_dir.is_dir():
        return {"ok": False, "error": "dir_missing", "path": str(local_dir)}

    results: list[dict[str, Any]] = []
    for entry in local_dir.rglob("*"):
        if entry.is_file():
            rel = entry.relative_to(local_dir).as_posix()
            r = upload_file(job_id=job_id, local_path=entry, object_name=rel)
            results.append(r)

    return {
        "ok": True,
        "files": results,
        "backend": results[0]["backend"] if results else "none",
    }


def get_signed_url(*, job_id: str, name: str) -> dict[str, Any]:
    """Issue a fresh signed URL for an existing artifact."""
    key = f"{job_id}/{name}"
    if _s3_available():
        try:
            client = _s3_client()
            url = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": key},
                ExpiresIn=SIGNED_URL_TTL_S,
            )
            return {"ok": True, "signed_url": url, "expires_in_seconds": SIGNED_URL_TTL_S}
        except (ClientError, BotoCoreError) as e:
            return {"ok": False, "error": "s3_error", "message": str(e)}

    # Local fallback - return the gateway path
    return {
        "ok": True,
        "signed_url": f"/artifacts/{job_id}/{name}",
        "expires_in_seconds": None,
    }


def list_artifacts(*, job_id: str) -> dict[str, Any]:
    """List all artifacts for a job."""
    if _s3_available():
        try:
            client = _s3_client()
            resp = client.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"{job_id}/")
            items = [
                {"name": obj["Key"].split("/", 1)[1], "size": obj["Size"]}
                for obj in resp.get("Contents", [])
            ]
            return {"ok": True, "backend": "s3", "items": items}
        except (ClientError, BotoCoreError) as e:
            return {"ok": False, "error": "s3_error", "message": str(e)}

    job_dir = LOCAL_DIR / job_id
    if not job_dir.exists():
        return {"ok": True, "backend": "local", "items": []}
    items = [
        {"name": str(p.relative_to(job_dir)), "size": p.stat().st_size}
        for p in job_dir.rglob("*") if p.is_file()
    ]
    return {"ok": True, "backend": "local", "items": items}
