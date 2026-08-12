#!/usr/bin/env python3
"""Submit the generated public URLs to the IndexNow endpoint."""

import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from radar import INDEXNOW_KEY, SITE_URL


DEFAULT_ENDPOINT = "https://api.indexnow.org/indexnow"
SITEMAP_NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
SITE_HOST = urlparse(SITE_URL).hostname


def load_sitemap_urls(path):
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError("sitemap is unreadable") from exc
    if root.tag != f"{SITEMAP_NAMESPACE}urlset":
        raise ValueError("sitemap has an unsupported root element")

    urls = [
        node.text.strip()
        for node in root.findall(f".//{SITEMAP_NAMESPACE}loc")
        if node.text
    ]
    if not urls or len(urls) > 10_000:
        raise ValueError("sitemap URL count is outside the IndexNow limit")
    if len(urls) != len(set(urls)):
        raise ValueError("sitemap contains duplicate URLs")

    for url in urls:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != SITE_HOST
            or parsed.port is not None
            or parsed.username is not None
            or parsed.fragment
        ):
            raise ValueError("sitemap contains a URL outside the public site")
    return urls


def submit_urls(urls, endpoint=DEFAULT_ENDPOINT):
    payload = {
        "host": SITE_HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE_URL}{INDEXNOW_KEY}.txt",
        "urlList": urls,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "ai-coding-radar/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        status = response.status
    if status not in (200, 202):
        raise RuntimeError(f"IndexNow rejected the submission with HTTP {status}")
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sitemap", type=Path, default=Path(__file__).parent / "output/sitemap.xml"
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = parser.parse_args(argv)

    try:
        urls = load_sitemap_urls(args.sitemap)
        status = submit_urls(urls, args.endpoint)
        print(f"IndexNow accepted {len(urls)} URLs (HTTP {status})")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
