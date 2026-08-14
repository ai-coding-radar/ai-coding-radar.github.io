#!/usr/bin/env python3
"""Publish the tested OSS security workflow guide through DEV's official API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import devto


ARTICLE_PATH = Path("content/devto/oss-exact-version-security.md")
CANONICAL_URL = (
    "https://github.com/Jarvis-Dong/oss-package-health-monitor/"
    "blob/main/examples/README.md"
)


def article_payload(project_root: Path, *, published: bool) -> Dict[str, Any]:
    body = (project_root / ARTICLE_PATH).read_text(encoding="utf-8").strip()
    required_links = (
        "https://apify.com/ai-coding-radar/oss-package-health-monitor",
        "https://raw.githubusercontent.com/Jarvis-Dong/oss-package-health-monitor/",
        "https://osv.dev/",
        "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
    )
    if len(body) < 1_000 or any(link not in body for link in required_links):
        raise devto.DevToError("guide body is incomplete")
    return {
        "article": {
            "title": "Fail-closed npm and PyPI vulnerability checks in n8n",
            "published": published,
            "canonical_url": CANONICAL_URL,
            "description": (
                "A repeatable exact-version OSV and CISA KEV workflow that "
                "keeps registry and vulnerability-source failures visible."
            ),
            "tags": "security,devops,n8n,opensource",
            "body_markdown": body,
        }
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parent
    )
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--publish", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        payload = article_payload(arguments.project_root, published=arguments.publish)
        if arguments.preview:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        token = os.environ.get(devto.TOKEN_ENV, "").strip()
        if not token:
            raise devto.DevToError(f"{devto.TOKEN_ENV} is not set")
        print(
            json.dumps(
                devto.publish_article(payload, token),
                ensure_ascii=False,
                indent=2,
            )
        )
    except (devto.DevToError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
