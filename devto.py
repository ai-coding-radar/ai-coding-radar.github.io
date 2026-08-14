#!/usr/bin/env python3
"""Publish the newest verified release record through DEV's official API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import radar


API_ROOT = "https://dev.to/api"
TOKEN_ENV = "DEVTO_API_KEY"


class DevToError(RuntimeError):
    """Raised when a DEV request or local release record is invalid."""


def newest_release(project_root: Path) -> Dict[str, Any]:
    state = radar.load_state(project_root / "state" / "seen.json")
    radar.normalize_state(state)
    records = list(state["seen"].values())
    if not records:
        raise DevToError("no release record is available")
    return max(
        records,
        key=lambda record: radar.parse_source_timestamp(record["source_published_at"]),
    )


def article_payload(record: Mapping[str, Any], *, published: bool) -> Dict[str, Any]:
    product = str(record["product"])
    version = str(record["version"])
    canonical_url = radar.release_page_url(record)
    return {
        "article": {
            "title": f"{product} {version} released: verified stable release",
            "published": published,
            "canonical_url": canonical_url,
            "description": f"A source-verified stable release record for {product} {version}.",
            "tags": "ai,programming,opensource,news",
            "body_markdown": (
                f"{product} published stable release `{version}`.\n\n"
                f"- Official timestamp: `{record['source_published_at']}`\n"
                f"- Official release notes: {record['source_url']}\n"
                f"- Verified record: {canonical_url}\n\n"
                "This post is generated from an allowlisted official release feed. "
                "It contains no synthetic benchmark, hands-on claim, or unsupported conclusion.\n"
            ),
        }
    }


def _request(
    path: str,
    token: str,
    *,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.forem.api-v1+json",
            "Content-Type": "application/json",
            "api-key": token,
            "User-Agent": "AI-Coding-Radar/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise DevToError(f"DEV API returned HTTP {exc.code}: {detail}") from exc
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise DevToError(f"DEV API request failed: {exc}") from exc


def find_existing(token: str, canonical_url: str) -> Optional[Mapping[str, Any]]:
    page = 1
    while True:
        articles = _request(f"/articles/me/all?page={page}&per_page=100", token)
        if not isinstance(articles, list):
            raise DevToError("DEV API returned an unexpected article list")
        if any(not isinstance(article, dict) for article in articles):
            raise DevToError("DEV API returned an invalid article record")
        match = next(
            (article for article in articles if article.get("canonical_url") == canonical_url),
            None,
        )
        if match:
            return match
        if len(articles) < 100:
            return None
        page += 1


def publish_article(payload: Mapping[str, Any], token: str) -> Dict[str, Any]:
    article_payload_value = payload.get("article")
    if not isinstance(article_payload_value, dict):
        raise DevToError("article payload must contain an article object")
    canonical_url = article_payload_value.get("canonical_url")
    published = article_payload_value.get("published")
    if not isinstance(canonical_url, str) or not canonical_url.startswith("https://"):
        raise DevToError("article canonical_url must be an HTTPS URL")
    if not isinstance(published, bool):
        raise DevToError("article published flag must be a boolean")

    existing = find_existing(token, canonical_url)
    if existing:
        is_published = bool(existing.get("published_at"))
        if published and not is_published:
            article_id = existing.get("id")
            if not isinstance(article_id, int):
                raise DevToError("DEV draft is missing its article id")
            article = _request(
                f"/articles/{article_id}",
                token,
                method="PUT",
                body={"article": {"published": True}},
            )
            if not isinstance(article, dict):
                raise DevToError("DEV API returned an unexpected update response")
            return {
                "status": "published",
                "canonical_url": canonical_url,
                "dev_url": article.get("url") or existing.get("url"),
                "id": article_id,
            }
        return {
            "status": "already_exists",
            "canonical_url": canonical_url,
            "dev_url": existing.get("url"),
            "published": is_published,
        }
    article = _request("/articles", token, method="POST", body=payload)
    if not isinstance(article, dict):
        raise DevToError("DEV API returned an unexpected create response")
    return {
        "status": "published" if published else "draft_created",
        "canonical_url": canonical_url,
        "dev_url": article.get("url"),
        "id": article.get("id"),
    }


def publish_latest(
    project_root: Path, token: str, *, published: bool
) -> Dict[str, Any]:
    record = newest_release(project_root)
    return publish_article(article_payload(record, published=published), token)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parent
    )
    parser.add_argument(
        "--preview", action="store_true", help="print the payload without network access"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="publish immediately instead of creating a DEV draft",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        record = newest_release(arguments.project_root)
        if arguments.preview:
            print(json.dumps(article_payload(record, published=arguments.publish), ensure_ascii=False, indent=2))
            return 0
        token = os.environ.get(TOKEN_ENV, "").strip()
        if not token:
            raise DevToError(f"{TOKEN_ENV} is not set")
        result = publish_latest(
            arguments.project_root, token, published=arguments.publish
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (DevToError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
