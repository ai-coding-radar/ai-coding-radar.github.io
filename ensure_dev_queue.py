#!/usr/bin/env python3
"""Dispatch one daily DEV queue fallback when scheduled checks are absent."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from ensure_daily_refresh import (
    BEIJING,
    REPOSITORY,
    RefreshError,
    _parse_timestamp,
    _run_gh,
    runs_today,
)


WORKFLOW = "publish-dev-guide.yml"
SCHEDULE_TITLE = "DEV queue schedule"
FALLBACK_TITLE = "DEV queue fallback"
ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "pending", "requested"}


def queue_runs_today(
    records: Sequence[Dict[str, Any]], now: datetime
) -> List[Dict[str, Any]]:
    return [
        record
        for record in runs_today(records, now)
        if record.get("event") == "schedule"
        or record.get("displayTitle") in {SCHEDULE_TITLE, FALLBACK_TITLE}
    ]


def ensure_dev_queue(now: Optional[datetime] = None) -> Dict[str, Any]:
    current = (now or datetime.now(BEIJING)).astimezone(BEIJING)
    raw = _run_gh(
        [
            "run",
            "list",
            "--repo",
            REPOSITORY,
            "--workflow",
            WORKFLOW,
            "--limit",
            "100",
            "--json",
            "databaseId,displayTitle,event,status,conclusion,createdAt,url,headSha",
        ]
    )
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RefreshError("gh returned invalid workflow JSON") from exc
    if not isinstance(records, list):
        raise RefreshError("gh returned an unexpected workflow shape")

    today = queue_runs_today(records, current)
    completed = [record for record in today if record.get("conclusion") == "success"]
    active = [record for record in today if record.get("status") in ACTIVE_STATUSES]
    if completed or active:
        return {
            "status": "already_checked" if completed else "already_running",
            "date": current.date().isoformat(),
            "run": (completed or active)[-1],
        }

    failed_fallback = [
        record for record in today if record.get("displayTitle") == FALLBACK_TITLE
    ]
    if failed_fallback:
        return {
            "status": "fallback_failed",
            "date": current.date().isoformat(),
            "run": failed_fallback[-1],
        }

    _run_gh(
        [
            "workflow",
            "run",
            WORKFLOW,
            "--repo",
            REPOSITORY,
            "--ref",
            "main",
            "-f",
            "publish_next_due=true",
        ]
    )
    return {
        "status": "dispatched",
        "date": current.date().isoformat(),
        "reason": "no successful or active queue check existed today",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", help="ISO timestamp override used by tests")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    now = _parse_timestamp(arguments.now) if arguments.now else None
    try:
        print(json.dumps(ensure_dev_queue(now), ensure_ascii=False, indent=2))
    except (OSError, RefreshError, subprocess.SubprocessError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
