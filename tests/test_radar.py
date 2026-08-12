import json
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import radar


VALID_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:github.com,2008:Repository/1/rust-v1.1.0-alpha.1</id>
    <updated>2026-08-11T01:00:00Z</updated>
    <link rel="alternate" href="https://github.com/openai/codex/releases/tag/rust-v1.1.0-alpha.1"/>
    <title>1.1.0-alpha.1</title>
  </entry>
  <entry>
    <id>tag:github.com,2008:Repository/1/rust-v1.0.0</id>
    <updated>2026-08-10T01:00:00Z</updated>
    <link rel="alternate" href="https://github.com/openai/codex/releases/tag/rust-v1.0.0"/>
    <title>1.0.0</title>
  </entry>
</feed>'''

PRERELEASE_ONLY_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:github.com,2008:Repository/1/rust-v1.1.0-alpha.1</id>
    <updated>2026-08-11T01:00:00Z</updated>
    <link rel="alternate" href="https://github.com/openai/codex/releases/tag/rust-v1.1.0-alpha.1"/>
    <title>1.1.0-alpha.1</title>
  </entry>
</feed>'''

INVALID_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:github.com,2008:Repository/1/rust-v1.0.0</id>
    <updated>2026-08-10T01:00:00Z</updated>
    <title>1.0.0</title>
  </entry>
</feed>'''

EMPTY_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>'''

CLAUDE_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:github.com,2008:Repository/2/v2.1.2</id>
    <updated>2026-08-11T03:00:00Z</updated>
    <link rel="alternate" href="https://github.com/anthropics/claude-code/releases/tag/v2.1.2"/>
    <title>v2.1.2</title>
  </entry>
  <entry>
    <id>tag:github.com,2008:Repository/2/v2.1.1</id>
    <updated>2026-08-10T03:00:00Z</updated>
    <link rel="alternate" href="https://github.com/anthropics/claude-code/releases/tag/v2.1.1"/>
    <title>v2.1.1</title>
  </entry>
</feed>'''

GEMINI_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:github.com,2008:Repository/3/v0.56.0-preview.1</id>
    <updated>2026-08-11T04:00:00Z</updated>
    <link rel="alternate" href="https://github.com/google-gemini/gemini-cli/releases/tag/v0.56.0-preview.1"/>
    <title>Release v0.56.0-preview.1</title>
  </entry>
  <entry>
    <id>tag:github.com,2008:Repository/3/v0.55.1</id>
    <updated>2026-08-11T02:00:00Z</updated>
    <link rel="alternate" href="https://github.com/google-gemini/gemini-cli/releases/tag/v0.55.1"/>
    <title>Release v0.55.1</title>
  </entry>
</feed>'''


class RadarTest(unittest.TestCase):
    def test_prerelease_only_source_is_a_valid_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feeds = (
                (radar.SOURCE_BY_KEY["codex"], PRERELEASE_ONLY_FEED),
                (radar.SOURCE_BY_KEY["claude-code"], CLAUDE_FEED),
            )

            self.assertEqual(radar.process_feeds(feeds, root), 2)
            state = json.loads(
                (root / "state" / "seen.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                {record["source_key"] for record in state["seen"].values()},
                {"claude-code"},
            )

    def test_malformed_prerelease_source_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            malformed = PRERELEASE_ONLY_FEED.replace(
                b"2026-08-11T01:00:00Z", b"not-a-date"
            )

            with self.assertRaisesRegex(ValueError, "invalid timestamp"):
                radar.process_feed(malformed, root)

            self.assertFalse((root / "output").exists())
            self.assertFalse((root / "state").exists())

    def test_common_prerelease_suffixes_are_skipped(self):
        variants = (
            "1.1.0-rc1",
            "1.1.0-preview1",
            "1.1.0-nightly20260811",
            "1.1.0-development.1",
            "1.1.0-release-candidate.1",
        )
        source = radar.SOURCE_BY_KEY["codex"]
        for version in variants:
            with self.subTest(version=version):
                feed = PRERELEASE_ONLY_FEED.replace(
                    b"1.1.0-alpha.1", version.encode("ascii")
                )
                self.assertEqual(radar.parse_stable_releases(feed, source), [])

    def test_empty_atom_feed_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            with self.assertRaisesRegex(ValueError, "no release entries"):
                radar.process_feed(EMPTY_FEED, root)

            self.assertFalse((root / "output").exists())
            self.assertFalse((root / "state").exists())

    def test_release_title_must_match_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mismatched = VALID_FEED.replace(
                b"<title>1.0.0</title>", b"<title>9.9.9</title>"
            )

            with self.assertRaisesRegex(ValueError, "title"):
                radar.process_feed(mismatched, root)

            self.assertFalse((root / "output").exists())
            self.assertFalse((root / "state").exists())

    def test_multi_source_run_creates_all_stable_posts_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime(2026, 8, 11, 2, 0, tzinfo=timezone.utc)
            feeds = (
                (radar.SOURCE_BY_KEY["codex"], VALID_FEED),
                (radar.SOURCE_BY_KEY["claude-code"], CLAUDE_FEED),
                (radar.SOURCE_BY_KEY["gemini-cli"], GEMINI_FEED),
            )

            self.assertEqual(radar.process_feeds(feeds, root, now), 4)
            self.assertEqual(radar.process_feeds(feeds, root, now), 0)

            posts = list((root / "output" / "posts").glob("*.md"))
            self.assertEqual(len(posts), 4)
            post_text = "\n".join(
                post.read_text(encoding="utf-8") for post in posts
            )
            self.assertIn("OpenAI Codex 1.0.0 released", post_text)
            self.assertIn("Claude Code 2.1.2 released", post_text)
            self.assertIn("Gemini CLI 0.55.1 released", post_text)
            rss = ET.parse(root / "output" / "feed.xml")
            self.assertEqual(rss.findtext("./channel/link"), radar.SITE_URL)
            self.assertEqual(
                rss.findtext("./channel/title"), "AI Coding Release Radar"
            )
            self.assertEqual(len(rss.findall("./channel/item")), 4)
            self.assertEqual(
                rss.findtext("./channel/item/link"),
                radar.release_page_url(
                    {"source_key": "claude-code", "version": "2.1.2"}
                ),
            )
            index = (root / "output" / "index.html").read_text(encoding="utf-8")
            self.assertIn('<html lang="en">', index)
            self.assertIn("AI Coding Release Radar", index)
            self.assertIn("OpenAI Codex 1.0.0 is out", index)
            self.assertIn("Claude Code 2.1.2 is out", index)
            self.assertIn("Gemini CLI 0.55.1 is out", index)
            self.assertIn("official sources allowlisted", index)
            self.assertIn('rel="alternate" type="application/rss+xml"', index)
            self.assertIn(f'rel="canonical" href="{radar.SITE_URL}"', index)
            self.assertIn(
                f"Sitemap: {radar.SITE_URL}sitemap.xml",
                (root / "output" / "robots.txt").read_text(encoding="utf-8"),
            )
            release_page = (
                root / "output" / "releases" / "claude-code" / "2.1.2" / "index.html"
            ).read_text(encoding="utf-8")
            self.assertIn("Claude Code 2.1.2 stable release", release_page)
            self.assertIn(
                "https://github.com/anthropics/claude-code/releases/tag/v2.1.2",
                release_page,
            )
            self.assertIn('rel="noopener noreferrer"', release_page)
            tool_page = (
                root / "output" / "tools" / "claude-code" / "index.html"
            ).read_text(encoding="utf-8")
            self.assertIn("Claude Code stable release history", tool_page)
            self.assertIn("2.1.2", tool_page)
            self.assertIn("2.1.1", tool_page)
            sitemap = ET.parse(root / "output" / "sitemap.xml")
            namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            locations = {
                node.text for node in sitemap.findall(".//s:loc", namespace)
            }
            self.assertEqual(len(locations), 8)
            self.assertIn(
                radar.release_page_url(
                    {"source_key": "claude-code", "version": "2.1.2"}
                ),
                locations,
            )
            self.assertIn(radar.source_page_url("claude-code"), locations)

    def test_invalid_stable_release_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                radar.process_feed(INVALID_FEED, root)
            self.assertFalse((root / "output").exists())
            self.assertFalse((root / "state").exists())

    def test_invalid_timestamp_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feed = VALID_FEED.replace(
                b"2026-08-10T01:00:00Z", b"not-a-date"
            )

            with self.assertRaisesRegex(ValueError, "invalid timestamp"):
                radar.process_feed(feed, root)

            self.assertFalse((root / "output").exists())
            self.assertFalse((root / "state").exists())

    def test_unsafe_version_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feed = VALID_FEED.replace(
                b"rust-v1.0.0", b"rust-v1.0.0%22-injected"
            ).replace(b"<title>1.0.0</title>", b"<title>1.0.0\"-injected</title>")

            with self.assertRaisesRegex(ValueError, "title|version format|tag"):
                radar.process_feed(feed, root)

            self.assertFalse((root / "output").exists())
            self.assertFalse((root / "state").exists())

    def test_one_invalid_source_prevents_partial_multi_source_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feeds = (
                (radar.SOURCE_BY_KEY["codex"], VALID_FEED),
                (radar.SOURCE_BY_KEY["claude-code"], INVALID_FEED),
            )

            with self.assertRaises(ValueError):
                radar.process_feeds(feeds, root)

            self.assertFalse((root / "output").exists())
            self.assertFalse((root / "state").exists())

    def test_old_codex_state_migrates_to_english_without_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_id = "tag:github.com,2008:Repository/1/rust-v1.0.0"
            old_state = {
                "seen": {
                    state_id: {
                        "id": state_id,
                        "version": "1.0.0",
                        "source_published_at": "2026-08-10T01:00:00Z",
                        "source_url": "https://github.com/openai/codex/releases/tag/rust-v1.0.0",
                        "title": "Codex legacy title",
                        "detected_at": "2026-08-10T02:00:00Z",
                        "post": "output/posts/2026-08-10-codex-1.0.0.md",
                    }
                }
            }
            state_dir = root / "state"
            state_dir.mkdir()
            (state_dir / "seen.json").write_text(
                json.dumps(old_state), encoding="utf-8"
            )

            self.assertFalse(radar.process_feed(VALID_FEED, root))

            migrated = json.loads(
                (state_dir / "seen.json").read_text(encoding="utf-8")
            )["seen"][state_id]
            self.assertEqual(migrated["source_key"], "codex")
            self.assertEqual(migrated["product"], "OpenAI Codex")
            self.assertEqual(migrated["title"], "OpenAI Codex 1.0.0 released")
            post = root / migrated["post"]
            self.assertIn(
                "OpenAI Codex 1.0.0 released",
                post.read_text(encoding="utf-8"),
            )
            self.assertEqual(len(list((root / "output" / "posts").glob("*.md"))), 1)

    def test_network_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "radar.urllib.request.urlopen",
                side_effect=urllib.error.URLError("offline"),
            ):
                with self.assertRaises(urllib.error.URLError):
                    radar.fetch_feed(radar.DEFAULT_FEED_URL)
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
