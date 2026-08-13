#!/usr/bin/env python3
"""Backfill a missed daily GitHub Actions refresh without duplicating one."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo


BEIJING = ZoneInfo("Asia/Shanghai")
REPOSITORY = "ai-coding-radar/ai-coding-radar.github.io"
WORKFLOW = "publish.yml"
GH_CONFIG_DIR = Path.home() / ".config" / "gh-ai-coding-radar"


class RefreshError(RuntimeError):
    """Raised when the workflow state cannot be verified safely."""


def _run_gh(arguments: Sequence[str], *, env: Optional[Dict[str, str]] = None) -> str:
    environment = dict(os.environ)
    if GH_CONFIG_DIR.is_dir():
        environment["GH_CONFIG_DIR"] = str(GH_CONFIG_DIR)
    if env:
        environment.update(env)
    result = subprocess.run(
        ["gh", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env=environment,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RefreshError(detail or "gh command failed")
    return result.stdout


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise RefreshError("workflow run timestamp is missing a timezone")
    return parsed.astimezone(BEIJING)


def runs_today(records: Sequence[Dict[str, Any]], today: datetime) -> List[Dict[str, Any]]:
    target = today.astimezone(BEIJING).date()
    selected = []
    for record in records:
        created_at = record.get("createdAt")
        if not isinstance(created_at, str):
            continue
        if _parse_timestamp(created_at).date() == target:
            selected.append(record)
    return selected


def ensure_refresh(now: Optional[datetime] = None) -> Dict[str, Any]:
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
            "databaseId,event,status,conclusion,createdAt,url,headSha",
        ]
    )
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RefreshError("gh returned invalid workflow JSON") from exc
    if not isinstance(records, list):
        raise RefreshError("gh returned an unexpected workflow shape")

    today = runs_today(records, current)
    completed = [record for record in today if record.get("conclusion") == "success"]
    active = [record for record in today if record.get("status") in {"queued", "in_progress", "waiting", "pending"}]
    if completed or active:
        return {
            "status": "already_refreshed" if completed else "already_running",
            "date": current.date().isoformat(),
            "run": (completed or active)[-1],
        }

    _run_gh(["workflow", "run", WORKFLOW, "--repo", REPOSITORY, "--ref", "main"])
    return {
        "status": "dispatched",
        "date": current.date().isoformat(),
        "reason": "no successful or active workflow run existed today",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", help="ISO timestamp override used by tests")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    now = None
    if arguments.now:
        now = _parse_timestamp(arguments.now)
    try:
        print(json.dumps(ensure_refresh(now), ensure_ascii=False, indent=2))
    except (OSError, RefreshError, subprocess.SubprocessError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
