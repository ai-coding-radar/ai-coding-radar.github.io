"""Fetch and normalize stable releases from allowlisted AI coding tool feeds."""

from __future__ import annotations

import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime


ATOM = "{http://www.w3.org/2005/Atom}"
SOURCES = (
    {
        "key": "codex",
        "product": "OpenAI Codex",
        "repository": "openai/codex",
        "feed_url": "https://github.com/openai/codex/releases.atom",
        "tag_url_prefix": "https://github.com/openai/codex/releases/tag/rust-v",
        "title_prefixes": ("", "rust-v"),
    },
    {
        "key": "claude-code",
        "product": "Claude Code",
        "repository": "anthropics/claude-code",
        "feed_url": "https://github.com/anthropics/claude-code/releases.atom",
        "tag_url_prefix": "https://github.com/anthropics/claude-code/releases/tag/v",
        "title_prefixes": ("v",),
    },
    {
        "key": "gemini-cli",
        "product": "Gemini CLI",
        "repository": "google-gemini/gemini-cli",
        "feed_url": "https://github.com/google-gemini/gemini-cli/releases.atom",
        "tag_url_prefix": "https://github.com/google-gemini/gemini-cli/releases/tag/v",
        "title_prefixes": ("Release v",),
    },
)
SOURCE_BY_KEY = {source["key"]: source for source in SOURCES}
PRERELEASE = re.compile(
    r"(?:^|[.-])(?:alpha|beta|rc|release-candidate|preview|nightly|dev|development|canary)(?:[.\d-]|$)",
    re.IGNORECASE,
)
STABLE_VERSION = re.compile(r"^\d+(?:\.\d+){1,3}$")
TAG_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,127}$")
RISK_WORDS = {
    "breaking": re.compile(r"\bbreak(?:ing|s)?\b", re.IGNORECASE),
    "security": re.compile(r"\b(?:security|vulnerab(?:ility|ilities)|cve-\d+)\b", re.IGNORECASE),
    "migration": re.compile(r"\b(?:migration|migrate|deprecated?|remov(?:e|ed|al))\b", re.IGNORECASE),
}


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("stable release has an invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("stable release timestamp is missing a timezone")
    return parsed


def risk_signals(text: str) -> list[str]:
    return [name for name, pattern in RISK_WORDS.items() if pattern.search(text)]


def parse_feed(feed_bytes: bytes, source: dict[str, object]) -> list[dict[str, object]]:
    try:
        root = ET.fromstring(feed_bytes)
    except ET.ParseError as exc:
        raise ValueError("invalid Atom feed") from exc
    if root.tag != f"{ATOM}feed":
        raise ValueError("document is not an Atom feed")
    entries = root.findall(f"{ATOM}entry")
    if not entries:
        raise ValueError("Atom feed contains no release entries")

    releases: list[tuple[datetime, dict[str, object]]] = []
    entry_ids: set[str] = set()
    for entry in entries:
        title = (entry.findtext(f"{ATOM}title") or "").strip()
        entry_id = (entry.findtext(f"{ATOM}id") or "").strip()
        updated = (entry.findtext(f"{ATOM}updated") or "").strip()
        content = (entry.findtext(f"{ATOM}content") or "").strip()
        link = next(
            (
                node.get("href", "").strip()
                for node in entry.findall(f"{ATOM}link")
                if node.get("rel") == "alternate"
            ),
            "",
        )
        if not title or not entry_id or not updated or not link:
            raise ValueError("release is missing title, id, time, or source link")
        prefix = str(source["tag_url_prefix"])
        if not link.startswith(prefix):
            raise ValueError("release link is outside the source allowlist")
        version = link.removeprefix(prefix)
        if not TAG_VERSION.fullmatch(version):
            raise ValueError("release tag has unsupported characters")
        expected_titles = {
            f"{title_prefix}{version}" for title_prefix in source["title_prefixes"]
        }
        if title not in expected_titles:
            raise ValueError("release title does not match the official tag")
        is_prerelease = bool(PRERELEASE.search(version))
        if not is_prerelease and not STABLE_VERSION.fullmatch(version):
            raise ValueError("stable release has an unsupported version format")
        if entry_id in entry_ids:
            raise ValueError("duplicate release id in Atom feed")
        entry_ids.add(entry_id)
        published = parse_timestamp(updated)
        if is_prerelease:
            continue
        releases.append(
            (
                published,
                {
                    "id": entry_id,
                    "tool": source["key"],
                    "product": source["product"],
                    "repository": source["repository"],
                    "version": version,
                    "channel": "stable",
                    "publishedAt": updated,
                    "officialUrl": link,
                    "riskSignals": risk_signals(content),
                },
            )
        )
    releases.sort(key=lambda item: item[0], reverse=True)
    return [release for _, release in releases]


def fetch_feed(source: dict[str, object], timeout: int = 20) -> bytes:
    request = urllib.request.Request(
        str(source["feed_url"]),
        headers={"User-Agent": "ai-coding-release-intelligence/1.0"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError("unreachable")


def collect_releases(
    tools: list[str] | None = None,
    limit_per_tool: int = 5,
    feed_payloads: dict[str, bytes] | None = None,
) -> list[dict[str, object]]:
    selected = [source["key"] for source in SOURCES] if tools is None else tools
    if not isinstance(selected, list) or not selected:
        raise ValueError("at least one tool is required")
    if not isinstance(limit_per_tool, int) or isinstance(limit_per_tool, bool):
        raise ValueError("limitPerTool must be an integer")
    if not 1 <= limit_per_tool <= 20:
        raise ValueError("limitPerTool must be between 1 and 20")
    if len(selected) != len(set(selected)):
        raise ValueError("tools must not contain duplicates")
    unknown = [key for key in selected if key not in SOURCE_BY_KEY]
    if unknown:
        raise ValueError(f"unsupported tool: {unknown[0]}")

    results: list[dict[str, object]] = []
    for key in selected:
        source = SOURCE_BY_KEY[key]
        payload = feed_payloads[key] if feed_payloads is not None else fetch_feed(source)
        results.extend(parse_feed(payload, source)[:limit_per_tool])
    results.sort(key=lambda item: parse_timestamp(str(item["publishedAt"])), reverse=True)
    return results
