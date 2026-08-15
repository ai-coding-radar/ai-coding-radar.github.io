#!/usr/bin/env python3
"""Publish a tested automation guide through DEV's official API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
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
            "https://raw.githubusercontent.com/Jarvis-Dong/"
            "markdown-code-to-image/main/docs/"
            "markdown-code-to-image-preview.png",
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
    "remote-ai-jobs": {
        "path": Path("content/devto/remote-ai-jobs-n8n.md"),
        "canonical_url": (
            "https://github.com/Jarvis-Dong/remote-job-intelligence/"
            "blob/main/examples/README.md"
        ),
        "title": "Build a daily remote AI jobs feed with n8n",
        "description": (
            "Aggregate and deduplicate public remote AI job feeds, then route "
            "fresh attributed records through an n8n workflow."
        ),
        "tags": "automation,n8n,api,career",
        "required_links": (
            "https://apify.com/ai-coding-radar/remote-job-intelligence",
            "https://apify.com/ai-coding-radar/remote-job-intelligence/"
            "examples/daily-remote-ai-and-machine-learning-jobs",
            "https://raw.githubusercontent.com/Jarvis-Dong/"
            "remote-job-intelligence/main/examples/"
            "n8n-remote-jobs-webhook.json",
            "https://github.com/Jarvis-Dong/remote-job-intelligence",
        ),
    },
}

CANONICAL_URL = str(GUIDES[DEFAULT_GUIDE]["canonical_url"])
GUIDE_QUEUE = (
    "oss-security",
    "grants-gov-monitor",
    "uk-supplier-monitor",
    "markdown-image-automation",
    "remote-ai-jobs",
)
MIN_PUBLISH_INTERVAL = timedelta(hours=24)


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


def parse_published_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise devto.DevToError("DEV article is missing published_at")
    try:
        published_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise devto.DevToError("DEV article has an invalid published_at") from exc
    if published_at.tzinfo is None:
        raise devto.DevToError("DEV article published_at has no timezone")
    return published_at


def publish_next_due(
    project_root: Path,
    token: str,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise devto.DevToError("queue check time must include a timezone")

    payloads = {
        guide: article_payload(project_root, published=True, guide=guide)
        for guide in GUIDE_QUEUE
    }
    articles = devto.list_articles(token)
    by_canonical: Dict[str, Mapping[str, Any]] = {}
    for article in articles:
        canonical_url = article.get("canonical_url")
        if isinstance(canonical_url, str):
            by_canonical.setdefault(canonical_url, article)
    existing = {
        guide: by_canonical.get(
            str(payloads[guide]["article"]["canonical_url"])
        )
        for guide in GUIDE_QUEUE
    }
    published_times: Dict[str, datetime] = {}
    first_unpublished: Optional[str] = None
    for guide in GUIDE_QUEUE:
        article = existing[guide]
        if article and article.get("published_at"):
            if first_unpublished is not None:
                raise devto.DevToError("DEV guide queue is published out of order")
            published_times[guide] = parse_published_at(article["published_at"])
        elif first_unpublished is None:
            first_unpublished = guide

    if DEFAULT_GUIDE not in published_times:
        raise devto.DevToError("the published OSS guide is required as queue baseline")
    if first_unpublished is None:
        return {"status": "queue_complete"}
    if first_unpublished == DEFAULT_GUIDE:
        raise devto.DevToError("the queue baseline is not published")

    previous_index = GUIDE_QUEUE.index(first_unpublished) - 1
    previous_guide = GUIDE_QUEUE[previous_index]
    previous_published_at = published_times.get(previous_guide)
    if previous_published_at is None:
        raise devto.DevToError("the previous DEV guide is not published")
    eligible_at = previous_published_at + MIN_PUBLISH_INTERVAL
    if checked_at < eligible_at:
        return {
            "status": "not_due",
            "guide": first_unpublished,
            "eligible_at": eligible_at.isoformat(),
        }

    result = devto.publish_article(
        payloads[first_unpublished],
        token,
        existing_articles=articles,
    )
    if result.get("status") != "published":
        raise devto.DevToError("DEV did not confirm the queued guide publication")
    article_id = result.get("id")
    if not isinstance(article_id, int) or isinstance(article_id, bool):
        raise devto.DevToError("published DEV guide is missing its article id")
    verified = devto.get_article(token, article_id)
    canonical_url = str(payloads[first_unpublished]["article"]["canonical_url"])
    if verified.get("canonical_url") != canonical_url:
        raise devto.DevToError("published DEV guide canonical URL did not verify")
    published_at = parse_published_at(verified.get("published_at"))
    return {
        "status": "published",
        "guide": first_unpublished,
        "id": verified.get("id"),
        "dev_url": verified.get("url"),
        "published_at": published_at.isoformat(),
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
    parser.add_argument(
        "--publish-next-due",
        action="store_true",
        help="publish at most one eligible guide from the ordered queue",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.publish_next_due:
            if arguments.preview or arguments.publish:
                raise devto.DevToError(
                    "--publish-next-due cannot be combined with --preview or --publish"
                )
            token = os.environ.get(devto.TOKEN_ENV, "").strip()
            if not token:
                raise devto.DevToError(f"{devto.TOKEN_ENV} is not set")
            print(
                json.dumps(
                    publish_next_due(arguments.project_root, token),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
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
