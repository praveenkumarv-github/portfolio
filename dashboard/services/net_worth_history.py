import csv
import json
import math
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from threading import RLock

from django.conf import settings
from django.utils import timezone

import boto3
from botocore.config import Config


_LOCK = RLock()
_FIELDS = ("date", "total_net_worth")
S3_HISTORY_PREFIX = "net-worth/history/"


def uses_s3_history():
    return bool(getattr(settings, "NET_WORTH_HISTORY_BUCKET", ""))


def _s3_client():
    return boto3.client("s3", config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2}))


def _read_s3_history():
    client = _s3_client()
    bucket = settings.NET_WORTH_HISTORY_BUCKET
    records = []
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=S3_HISTORY_PREFIX)
    for page in pages:
        for item in page.get("Contents", []):
            key = item["Key"]
            if not key.endswith(".json"):
                continue
            day = date.fromisoformat(key.removeprefix(S3_HISTORY_PREFIX).removesuffix(".json")).isoformat()
            response = client.get_object(Bucket=bucket, Key=key)
            try:
                record = json.loads(response["Body"].read())
            finally:
                response["Body"].close()
            amount = float(record["total_net_worth"])
            if record["date"] != day or not math.isfinite(amount):
                raise ValueError("Invalid S3 net worth record")
            records.append({"date": day, "total_net_worth": amount})
    return sorted(records, key=lambda record: record["date"])


def _history_path(demo=False):
    filename = "net_worth_demo.csv" if demo else "net_worth.csv"
    return Path(settings.BASE_DIR) / "cache" / filename


def read_history(demo=False):
    if uses_s3_history():
        if demo:
            raise ValueError("Demo history is local only")
        return _read_s3_history()
    path = _history_path(demo)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != list(_FIELDS):
            raise ValueError("Invalid net worth CSV columns")
        records = {}
        for row in reader:
            day = date.fromisoformat(row["date"]).isoformat()
            amount = float(row["total_net_worth"])
            if not math.isfinite(amount):
                raise ValueError("Net worth must be finite")
            records[day] = {"date": day, "total_net_worth": amount}
    return [records[day] for day in sorted(records)]


def _write_history(records, demo=False):
    path = _history_path(demo)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", dir=path.parent,
            prefix=path.stem + "_", suffix=".tmp", delete=False,
        ) as target:
            temporary_path = Path(target.name)
            writer = csv.DictWriter(target, fieldnames=_FIELDS)
            writer.writeheader()
            for record in records:
                writer.writerow({"date": record["date"], "total_net_worth": f'{record["total_net_worth"]:.2f}'})
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def save_net_worth(value, day=None):
    amount = round(float(value), 2)
    if not math.isfinite(amount):
        raise ValueError("Net worth must be finite")
    day = (day or (timezone.localdate() if uses_s3_history() else date.today())).isoformat()
    if uses_s3_history():
        _s3_client().put_object(
            Bucket=settings.NET_WORTH_HISTORY_BUCKET,
            Key=f"{S3_HISTORY_PREFIX}{day}.json",
            Body=json.dumps({"date": day, "total_net_worth": amount}, allow_nan=False).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        return
    with _LOCK:
        records = {record["date"]: record for record in read_history()}
        records[day] = {"date": day, "total_net_worth": amount}
        _write_history([records[key] for key in sorted(records)])


def seed_demo_history(value, day=None):
    if uses_s3_history():
        raise ValueError("Demo history is local only")
    today = day or date.today()
    amount = float(value)
    if not math.isfinite(amount):
        raise ValueError("Net worth must be finite")
    start = today - timedelta(days=365)
    offsets = list(range(0, 365, 7)) + [365]
    records = []
    for offset in offsets:
        progress = offset / 365
        factor = 0.78 + 0.22 * progress + 0.025 * math.sin(progress * 8 * math.pi)
        records.append({"date": (start + timedelta(days=offset)).isoformat(), "total_net_worth": round(amount * factor, 2)})
    with _LOCK:
        _write_history(records, demo=True)