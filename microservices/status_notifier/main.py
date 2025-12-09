"""Status notifier microservice for Discord webhooks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib import request, error


def _status_color(status: str) -> int:
    normalized = status.lower()
    if normalized in {"success", "succeeded", "passed", "open", "opened"}:
        return 0x2ecc71
    if normalized in {"failure", "failed", "error", "closed"}:
        return 0xe74c3c
    if normalized in {"in_progress", "running", "started"}:
        return 0xf1c40f
    if normalized in {"cancelled", "canceled"}:
        return 0x95a5a6
    return 0x3498db


def _build_title(event: str, status: str) -> str:
    base = event.replace("_", " ").title()
    return f"{base}: {status.replace('_', ' ').title()}"


def build_payload(args: argparse.Namespace) -> Dict:
    fields: List[Dict[str, str]] = []

    if args.ref:
        fields.append({"name": "Ref", "value": args.ref, "inline": True})
    if args.commit:
        fields.append({"name": "Commit", "value": f"`{args.commit[:8]}`", "inline": True})
    if args.actor:
        fields.append({"name": "Actor", "value": args.actor, "inline": True})
    if args.component:
        fields.append({"name": "Component", "value": args.component, "inline": True})
    if args.url:
        fields.append({"name": "Link", "value": args.url, "inline": False})

    description_parts = [args.summary] if args.summary else []
    if args.notes:
        description_parts.append(args.notes)

    embed = {
        "title": _build_title(args.event, args.status),
        "description": "\n".join([p for p in description_parts if p]),
        "color": _status_color(args.status),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    if fields:
        embed["fields"] = fields

    return {"embeds": [embed]}


def send_webhook(webhook: str, payload: Dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Guildest-StatusNotifier/1.0",
        },
        method="POST",
    )
    try:
        with request.urlopen(req) as resp:  # noqa: S310 (Discord webhook)
            if resp.status >= 300:
                raise RuntimeError(f"Webhook responded with status {resp.status}")
    except error.HTTPError as exc:
        if exc.code == 404:
            # Gracefully handle deleted/invalid webhooks so the notifier doesn't crash
            print("Webhook returned 404 (not found); skipping notification.")
            return
        raise RuntimeError(f"Failed to send webhook: {exc}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Failed to send webhook: {exc}") from exc


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send status updates to Discord webhook.")
    parser.add_argument("--event", required=True, help="Event type (pr, push, deploy, build)")
    parser.add_argument("--status", required=True, help="Status string (success, failure, started, etc.)")
    parser.add_argument("--summary", help="One-line summary or title.")
    parser.add_argument("--ref", help="Git ref or PR title.")
    parser.add_argument("--commit", help="Commit SHA.")
    parser.add_argument("--url", help="Link to PR/commit/run.")
    parser.add_argument("--actor", help="Actor or author.")
    parser.add_argument("--component", help="Component being reported (docker, bot, etc.).")
    parser.add_argument("--notes", help="Additional notes.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    webhook = os.getenv("STATUS_WEBHOOK") or os.getenv("STATUS") or os.getenv("status")
    if not webhook:
        raise SystemExit("STATUS_WEBHOOK env var is required")

    payload = build_payload(args)
    send_webhook(webhook, payload)


if __name__ == "__main__":
    main()
