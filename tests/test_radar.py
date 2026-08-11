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

INVALID_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:github.com,2008:Repository/1/rust-v1.0.0</id>
    <updated>2026-08-10T01:00:00Z</updated>
    <title>1.0.0</title>
  </entry>
</feed>'''


class RadarTest(unittest.TestCase):
    def test_first_run_creates_one_post_and_second_run_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime(2026, 8, 11, 2, 0, tzinfo=timezone.utc)

            self.assertTrue(radar.process_feed(VALID_FEED, root, now))
            self.assertFalse(radar.process_feed(VALID_FEED, root, now))

            posts = list((root / "output" / "posts").glob("*.md"))
            self.assertEqual(len(posts), 1)
            self.assertIn("Codex 发布 1.0.0", posts[0].read_text(encoding="utf-8"))
            rss = ET.parse(root / "output" / "feed.xml")
            self.assertEqual(rss.findtext("./channel/link"), radar.SITE_URL)
            index = (root / "output" / "index.html").read_text(encoding="utf-8")
            self.assertIn("AI Coding 更新雷达", index)
            self.assertIn("1.0.0", index)
            self.assertIn('rel="alternate" type="application/rss+xml"', index)
            self.assertIn('rel="noopener noreferrer"', index)
            self.assertIn(f'rel="canonical" href="{radar.SITE_URL}"', index)

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

            with self.assertRaisesRegex(ValueError, "version format"):
                radar.process_feed(feed, root)

            self.assertFalse((root / "output").exists())
            self.assertFalse((root / "state").exists())

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
