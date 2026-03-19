import json
import logging

import boto3

from app.config import settings

logger = logging.getLogger(__name__)

s3 = boto3.client("s3", region_name=settings.s3_region)


def load_data(prefix: str) -> list[dict]:
    all_data = []
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


def save_jsonl(key: str, data: list[dict]) -> None:
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in data).encode("utf-8")
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=body)


def save_json(key: str, data: dict) -> None:
    s3.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
    )


def load_json(key: str) -> dict | None:
    try:
        obj = s3.get_object(Bucket=settings.s3_bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception as e:
        logger.error("S3 load_json failed for key=%s: %s", key, e)
        return None


def list_objects(prefix: str) -> list[dict]:
    try:
        resp = s3.list_objects_v2(Bucket=settings.s3_bucket, Prefix=prefix)
        return resp.get("Contents", [])
    except Exception as e:
        logger.error("S3 list_objects failed for prefix=%s: %s", prefix, e)
        return []


def list_prefixes(prefix: str) -> list[str]:
    try:
        resp = s3.list_objects_v2(
            Bucket=settings.s3_bucket, Prefix=prefix, Delimiter="/"
        )
        return [p["Prefix"] for p in resp.get("CommonPrefixes", [])]
    except Exception as e:
        logger.error("S3 list_prefixes failed for prefix=%s: %s", prefix, e)
        return []


def delete_object(key: str) -> None:
    s3.delete_object(Bucket=settings.s3_bucket, Key=key)
