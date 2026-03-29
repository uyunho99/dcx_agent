import json
import logging
import os
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage abstraction: S3 vs local filesystem
# Set STORAGE=local in .env to use local disk instead of AWS S3.
# ---------------------------------------------------------------------------

_USE_LOCAL = settings.storage == "local"
_DATA_DIR = Path(settings.local_data_dir)


# ===========================================================================
# Local filesystem implementation
# ===========================================================================

def _local_path(key: str) -> Path:
    """Convert an S3 key to a local file path."""
    return _DATA_DIR / key


def _local_load_data(prefix: str) -> list[dict]:
    base = _local_path(prefix)
    all_data: list[dict] = []
    if not base.exists():
        return all_data
    # If prefix points to a directory, read all files inside
    target = base if base.is_dir() else base.parent
    for fp in sorted(target.iterdir()):
        if not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8").strip()
            for line in text.split("\n"):
                if line:
                    try:
                        all_data.append(json.loads(line))
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Local load_data failed for %s: %s", fp, e)
    return all_data


def _local_save_jsonl(key: str, data: list[dict]) -> None:
    fp = _local_path(key)
    fp.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in data)
    fp.write_text(body, encoding="utf-8")


def _local_save_json(key: str, data: dict) -> None:
    fp = _local_path(key)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _local_load_json(key: str) -> dict | None:
    fp = _local_path(key)
    try:
        if not fp.exists():
            return None
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Local load_json failed for %s: %s", fp, e)
        return None


def _local_list_objects(prefix: str) -> list[dict]:
    base = _local_path(prefix)
    if not base.exists():
        return []
    target = base if base.is_dir() else base.parent
    results = []
    for fp in sorted(target.rglob("*")):
        if fp.is_file():
            # Return S3-compatible format: {"Key": "relative/path"}
            rel = str(fp.relative_to(_DATA_DIR))
            results.append({"Key": rel})
    return results


def _local_list_prefixes(prefix: str) -> list[str]:
    base = _local_path(prefix)
    if not base.exists() or not base.is_dir():
        return []
    prefixes = []
    for d in sorted(base.iterdir()):
        if d.is_dir():
            rel = str(d.relative_to(_DATA_DIR))
            # Match S3 format: ends with "/"
            prefixes.append(rel + "/")
    return prefixes


def _local_delete_object(key: str) -> None:
    fp = _local_path(key)
    if fp.exists():
        fp.unlink()


# ===========================================================================
# S3 (AWS) implementation — original code
# ===========================================================================

def _init_s3_client():
    """Lazily create the boto3 S3 client (only when actually using S3)."""
    import boto3
    return boto3.client("s3", region_name=settings.s3_region)


# Only create the boto3 client if we are actually using S3
s3 = None if _USE_LOCAL else _init_s3_client()


def _s3_load_data(prefix: str) -> list[dict]:
    all_data: list[dict] = []
    try:
        resp = s3.list_objects_v2(Bucket=settings.s3_bucket, Prefix=prefix)
        for f in resp.get("Contents", []):
            body = s3.get_object(Bucket=settings.s3_bucket, Key=f["Key"])["Body"]
            for line in body.read().decode("utf-8").strip().split("\n"):
                if line:
                    try:
                        all_data.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        logger.error("S3 load_data failed for prefix=%s: %s", prefix, e)
    return all_data


def _s3_save_jsonl(key: str, data: list[dict]) -> None:
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in data).encode("utf-8")
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=body)


def _s3_save_json(key: str, data: dict) -> None:
    s3.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
    )


def _s3_load_json(key: str) -> dict | None:
    try:
        obj = s3.get_object(Bucket=settings.s3_bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception as e:
        logger.error("S3 load_json failed for key=%s: %s", key, e)
        return None


def _s3_list_objects(prefix: str) -> list[dict]:
    try:
        resp = s3.list_objects_v2(Bucket=settings.s3_bucket, Prefix=prefix)
        return resp.get("Contents", [])
    except Exception as e:
        logger.error("S3 list_objects failed for prefix=%s: %s", prefix, e)
        return []


def _s3_list_prefixes(prefix: str) -> list[str]:
    try:
        resp = s3.list_objects_v2(
            Bucket=settings.s3_bucket, Prefix=prefix, Delimiter="/"
        )
        return [p["Prefix"] for p in resp.get("CommonPrefixes", [])]
    except Exception as e:
        logger.error("S3 list_prefixes failed for prefix=%s: %s", prefix, e)
        return []


def _s3_delete_object(key: str) -> None:
    s3.delete_object(Bucket=settings.s3_bucket, Key=key)


# ===========================================================================
# Public API — same signatures regardless of backend
# ===========================================================================

if _USE_LOCAL:
    load_data = _local_load_data
    save_jsonl = _local_save_jsonl
    save_json = _local_save_json
    load_json = _local_load_json
    list_objects = _local_list_objects
    list_prefixes = _local_list_prefixes
    delete_object = _local_delete_object
    logger.info("Storage backend: LOCAL (%s)", _DATA_DIR.resolve())
else:
    load_data = _s3_load_data
    save_jsonl = _s3_save_jsonl
    save_json = _s3_save_json
    load_json = _s3_load_json
    list_objects = _s3_list_objects
    list_prefixes = _s3_list_prefixes
    delete_object = _s3_delete_object
    logger.info("Storage backend: S3 (%s)", settings.s3_bucket)
