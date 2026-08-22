import argparse
import json
import os
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://api.cloudflare.com/client/v4"
RequestFunction = Callable[[str, str, str, dict[str, Any] | None], Any]


class CloudflareAPIError(RuntimeError):
    pass


def _request(
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            document = json.load(response)
    except HTTPError as exc:
        raise CloudflareAPIError(f"Cloudflare API returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise CloudflareAPIError("Cloudflare API request failed") from exc

    if not document.get("success"):
        errors = document.get("errors") or []
        message = errors[0].get("message", "unknown API error") if errors else "unknown API error"
        raise CloudflareAPIError(f"Cloudflare API rejected the request: {message}")
    return document.get("result")


def upsert_dns_record(
    *,
    zone_id: str,
    token: str,
    record_type: str,
    name: str,
    content: str,
    proxied: bool,
    request_function: RequestFunction = _request,
) -> str:
    normalized_name = name.rstrip(".")
    normalized_content = content.rstrip(".")
    query = urlencode({"type": record_type, "name": normalized_name})
    records = request_function(
        "GET",
        f"/zones/{zone_id}/dns_records?{query}",
        token,
        None,
    )
    payload = {
        "type": record_type,
        "name": normalized_name,
        "content": normalized_content,
        "ttl": 1,
        "proxied": proxied,
    }

    if records:
        request_function(
            "PUT",
            f"/zones/{zone_id}/dns_records/{records[0]['id']}",
            token,
            payload,
        )
        return "updated"

    request_function("POST", f"/zones/{zone_id}/dns_records", token, payload)
    return "created"


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    upsert = subparsers.add_parser("upsert")
    upsert.add_argument("--zone-id", required=True)
    upsert.add_argument("--type", dest="record_type", required=True)
    upsert.add_argument("--name", required=True)
    upsert.add_argument("--content", required=True)
    upsert.add_argument("--proxied", choices=("true", "false"), required=True)
    args = parser.parse_args()

    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        parser.error("CLOUDFLARE_API_TOKEN is required")

    action = upsert_dns_record(
        zone_id=args.zone_id,
        token=token,
        record_type=args.record_type,
        name=args.name,
        content=args.content,
        proxied=args.proxied == "true",
    )
    print(f"{action.capitalize()} {args.record_type} record {args.name.rstrip('.')}")


if __name__ == "__main__":
    main()