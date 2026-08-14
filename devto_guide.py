#!/usr/bin/env python3
"""Publish a tested automation guide through DEV's official API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import devto


DEFAULT_GUIDE = "oss-security"
GUIDES: Mapping[str, Mapping[str, Any]] = {
    "oss-security": {
        "path": Path("content/devto/oss-exact-version-security.md"),
        "canonical_url": (
            "https://github.com/Jarvis-Dong/oss-package-health-monitor/"
            "blob/main/examples/README.md"
        ),
        "title": "Fail-closed npm and PyPI vulnerability checks in n8n",
        "description": (
            "A repeatable exact-version OSV and CISA KEV workflow that "
            "keeps registry and vulnerability-source failures visible."
        ),
        "tags": "security,devops,n8n,opensource",
        "required_links": (
            "https://apify.com/ai-coding-radar/oss-package-health-monitor",
            "https://raw.githubusercontent.com/Jarvis-Dong/oss-package-health-monitor/",
            "https://osv.dev/",
            "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
        ),
    },
    "uk-supplier-monitor": {
        "path": Path("content/devto/uk-supplier-change-monitor.md"),
        "canonical_url": (
            "https://github.com/Jarvis-Dong/uk-company-change-alerts/"
            "blob/main/examples/README.md"
        ),
        "title": "Build a no-code UK supplier change monitor with n8n",
        "description": (
            "Monitor selected Companies House records on a schedule and route "
            "observed status, filing, address, or name changes without scraping."
        ),
        "tags": "automation,n8n,api,opensource",
        "required_links": (
            "https://apify.com/ai-coding-radar/uk-company-change-alerts",
            "https://apify.com/ai-coding-radar/uk-company-change-alerts/"
            "examples/daily-uk-supplier-status-alerts",
            "https://raw.githubusercontent.com/Jarvis-Dong/uk-company-change-alerts/",
            "https://www.gov.uk/guidance/companies-house-data-products",
            "https://data.companieshouse.gov.uk/doc/company/02050399.json",
        ),
    },
    "markdown-image-automation": {
        "path": Path("content/devto/markdown-ai-answer-to-png.md"),
        "canonical_url": (
            "https://github.com/Jarvis-Dong/markdown-code-to-image/"
            "blob/main/examples/README.md"
        ),
        "title": "Turn Markdown and AI answers into PNG files in n8n",
        "description": (
            "Import a tested n8n workflow that renders Markdown, code, and "
            "AI answers into PNG files without browser screenshots."
        ),
        "tags": "automation,n8n,api,opensource",
        "required_links": (
            "https://apify.com/ai-coding-radar/markdown-code-to-image",
            "https://apify.com/ai-coding-radar/markdown-code-to-image/"
            "examples/chatgpt-markdown-answer-to-png",
            "https://raw.githubusercontent.com/Jarvis-Dong/"
            "markdown-code-to-image/main/examples/"
            "n8n-markdown-code-to-image.json",
            "https://cardify.1222155.xyz/chatgpt-to-image/",
        ),
    },
    "grants-gov-monitor": {
        "path": Path("content/devto/grants-gov-opportunity-monitor.md"),
        "canonical_url": (
            "https://github.com/Jarvis-Dong/grants-gov-opportunity-monitor/"
            "blob/main/examples/README.md"
        ),
        "title": "Build a fact-only Grants.gov opportunity monitor in n8n",
        "description": (
            "Track new and changed U.S. federal grant opportunities from the "
            "official Grants.gov search API without deciding eligibility."
        ),
        "tags": "automation,n8n,api,opensource",
        "required_links": (
            "https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor",
            "https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor/"
            "examples/daily-ai-federal-grant-opportunity-alerts",
            "https://www.grants.gov/api/api-guide",
            "https://api.grants.gov/v1/api/search2",
            "https://github.com/Jarvis-Dong/grants-gov-opportunity-monitor",
            "https://raw.githubusercontent.com/Jarvis-Dong/"
            "grants-gov-opportunity-monitor/main/examples/"
            "n8n-grants-gov-monitor.json",
        ),
    },
}

CANONICAL_URL = str(GUIDES[DEFAULT_GUIDE]["canonical_url"])


def article_payload(
    project_root: Path, *, published: bool, guide: str = DEFAULT_GUIDE
) -> Dict[str, Any]:
    config = GUIDES.get(guide)
    if config is None:
        raise devto.DevToError(f"unknown guide: {guide}")
    body = (project_root / config["path"]).read_text(encoding="utf-8").strip()
    if len(body) < 1_000 or any(
        link not in body for link in config["required_links"]
    ):
        raise devto.DevToError("guide body is incomplete")
    return {
        "article": {
            "title": config["title"],
            "published": published,
            "canonical_url": config["canonical_url"],
            "description": config["description"],
            "tags": config["tags"],
            "body_markdown": body,
        }
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parent
    )
    parser.add_argument(
        "--guide", choices=tuple(GUIDES), default=DEFAULT_GUIDE
    )
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--publish", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        payload = article_payload(
            arguments.project_root,
            published=arguments.publish,
            guide=arguments.guide,
        )
        if arguments.preview:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        token = os.environ.get(devto.TOKEN_ENV, "").strip()
        if not token:
            raise devto.DevToError(f"{devto.TOKEN_ENV} is not set")
        print(
            json.dumps(
                devto.publish_article(payload, token, refresh_draft=True),
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
