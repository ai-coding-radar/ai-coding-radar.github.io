import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import devto


def http_error(code, *, headers=None, body=b"Retry later"):
    return urllib.error.HTTPError(
        "https://dev.to/api/articles/me/all",
        code,
        "rate limited",
        headers or {},
        io.BytesIO(body),
    )


def write_state(root: Path) -> None:
    state_dir = root / "state"
    state_dir.mkdir()
    records = {}
    for version, published_at in (
        ("2.1.228", "2026-08-11T19:50:59Z"),
        ("2.1.229", "2026-08-12T20:56:22Z"),
    ):
        record_id = f"tag:github.com,2008:Repository/2/v{version}"
        records[record_id] = {
            "id": record_id,
            "source_key": "claude-code",
            "product": "Claude Code",
            "version": version,
            "source_published_at": published_at,
            "source_url": (
                "https://github.com/anthropics/claude-code/releases/tag/v"
                f"{version}"
            ),
            "detected_at": "2026-08-13T01:00:00Z",
            "title": f"Claude Code {version} released",
            "post": f"output/posts/2026-08-12-claude-code-{version}.md",
        }
    (state_dir / "seen.json").write_text(
        json.dumps({"seen": records}), encoding="utf-8"
    )


class DevToTest(unittest.TestCase):
    def test_newest_release_uses_source_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_state(root)

            record = devto.newest_release(root)

            self.assertEqual(record["version"], "2.1.229")

    def test_payload_is_a_draft_with_the_release_canonical_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_state(root)

            payload = devto.article_payload(
                devto.newest_release(root), published=False
            )["article"]

            self.assertFalse(payload["published"])
            self.assertEqual(
                payload["canonical_url"],
                "https://ai-coding-radar.github.io/releases/claude-code/2.1.229/",
            )
            self.assertIn("2.1.229", payload["title"])
            self.assertIn("Official release notes", payload["body_markdown"])

    @patch("devto._request")
    def test_existing_canonical_url_is_not_created_again(self, request):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_state(root)
            canonical_url = (
                "https://ai-coding-radar.github.io/releases/claude-code/2.1.229/"
            )
            request.return_value = [
                {
                    "id": 123,
                    "url": "https://dev.to/ai-coding-radar/example",
                    "canonical_url": canonical_url,
                    "published_at": None,
                }
            ]

            result = devto.publish_latest(root, "secret", published=False)

            self.assertEqual(result["status"], "already_exists")
            self.assertEqual(request.call_count, 1)
            self.assertEqual(
                request.call_args.args[0], "/articles/me/all?page=1&per_page=100"
            )

    @patch("devto._request")
    def test_create_posts_only_after_dedupe(self, request):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_state(root)
            request.side_effect = [
                [],
                {"id": 456, "url": "https://dev.to/ai-coding-radar/example"},
            ]

            result = devto.publish_latest(root, "secret", published=False)

            self.assertEqual(result["status"], "draft_created")
            self.assertEqual(request.call_count, 2)
            create = request.call_args_list[1]
            self.assertEqual(create.args, ("/articles", "secret"))
            self.assertEqual(create.kwargs["method"], "POST")
            self.assertFalse(create.kwargs["body"]["article"]["published"])

    @patch("devto._request")
    def test_publish_upgrades_an_existing_draft(self, request):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_state(root)
            canonical_url = (
                "https://ai-coding-radar.github.io/releases/claude-code/2.1.229/"
            )
            request.side_effect = [
                [
                    {
                        "id": 123,
                        "url": "https://dev.to/ai-coding-radar/example",
                        "canonical_url": canonical_url,
                        "published_at": None,
                    }
                ],
                {"id": 123, "url": "https://dev.to/ai-coding-radar/example"},
            ]

            result = devto.publish_latest(root, "secret", published=True)

            self.assertEqual(result["status"], "published")
            update = request.call_args_list[1]
            self.assertEqual(update.args, ("/articles/123", "secret"))
            self.assertEqual(update.kwargs["method"], "PUT")
            self.assertTrue(update.kwargs["body"]["article"]["published"])
            self.assertIn("2.1.229", update.kwargs["body"]["article"]["title"])

    @patch("devto._request")
    def test_refresh_updates_an_existing_unpublished_draft(self, request):
        payload = {
            "article": {
                "title": "Updated guide",
                "canonical_url": "https://example.com/guide",
                "published": False,
                "body_markdown": "Current tested content",
            }
        }
        request.side_effect = [
            [
                {
                    "id": 321,
                    "url": "https://dev.to/example/guide-temp-slug",
                    "canonical_url": "https://example.com/guide",
                    "published_at": None,
                }
            ],
            {"id": 321, "url": "https://dev.to/example/guide-temp-slug"},
        ]

        result = devto.publish_article(
            payload, "secret", refresh_draft=True
        )

        self.assertEqual(result["status"], "draft_updated")
        update = request.call_args_list[1]
        self.assertEqual(update.args, ("/articles/321", "secret"))
        self.assertEqual(update.kwargs["method"], "PUT")
        self.assertEqual(update.kwargs["body"], payload)

    @patch("devto._request")
    def test_preloaded_articles_avoid_a_second_dedupe_scan(self, request):
        payload = {
            "article": {
                "title": "Queued guide",
                "canonical_url": "https://example.com/guide",
                "published": True,
            }
        }
        existing = [
            {
                "id": 321,
                "url": "https://dev.to/example/guide",
                "canonical_url": "https://example.com/guide",
                "published_at": None,
            }
        ]
        request.return_value = {
            "id": 321,
            "url": "https://dev.to/example/guide",
        }

        result = devto.publish_article(
            payload,
            "secret",
            existing_articles=existing,
        )

        self.assertEqual(result["status"], "published")
        request.assert_called_once()
        self.assertEqual(request.call_args.args, ("/articles/321", "secret"))

    @patch("devto._request")
    def test_dedupe_checks_every_full_page(self, request):
        canonical_url = "https://ai-coding-radar.github.io/releases/codex/1.0.0/"
        full_page = [
            {"canonical_url": f"https://example.com/{index}"}
            for index in range(100)
        ]
        request.side_effect = [full_page] * 10 + [
            [{"canonical_url": canonical_url}]
        ]

        result = devto.find_existing("secret", canonical_url)

        self.assertEqual(result["canonical_url"], canonical_url)
        self.assertEqual(request.call_count, 11)

    @patch("devto._request", return_value=["invalid"])
    def test_malformed_article_record_fails_closed(self, request):
        with self.assertRaisesRegex(devto.DevToError, "invalid article record"):
            devto.find_existing("secret", "https://example.com/release")

    @patch("devto.time.sleep")
    @patch("devto.urllib.request.urlopen")
    def test_rate_limit_honors_retry_after(self, urlopen, sleep):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok": true}'
        urlopen.side_effect = [
            http_error(429, headers={"Retry-After": "3"}),
            response,
        ]

        result = devto._request("/articles/me/all", "secret")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(3.0)

    @patch("devto.time.sleep")
    @patch("devto.urllib.request.urlopen")
    def test_rate_limit_stops_after_bounded_retries(self, urlopen, sleep):
        urlopen.side_effect = [http_error(429), http_error(429), http_error(429)]

        with self.assertRaisesRegex(devto.DevToError, "HTTP 429"):
            devto._request("/articles/me/all", "secret")

        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(5.0), call(10.0)])

    @patch("devto.time.sleep")
    @patch("devto.urllib.request.urlopen")
    def test_long_retry_after_fails_without_retrying_early(self, urlopen, sleep):
        urlopen.side_effect = [http_error(429, headers={"Retry-After": "60"})]

        with self.assertRaisesRegex(devto.DevToError, "retry budget"):
            devto._request("/articles/me/all", "secret")

        urlopen.assert_called_once()
        sleep.assert_not_called()

    @patch("devto._request")
    def test_invalid_article_payload_fails_before_network(self, request):
        with self.assertRaisesRegex(devto.DevToError, "canonical_url"):
            devto.publish_article(
                {"article": {"canonical_url": "not-a-url", "published": False}},
                "secret",
            )
        request.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("devto._request")
    def test_missing_api_key_fails_without_network(self, request):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_state(root)
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                result = devto.main(["--project-root", str(root)])

            self.assertEqual(result, 2)
            self.assertIn("DEVTO_API_KEY is not set", stderr.getvalue())
            request.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("devto._request")
    def test_preview_needs_no_key_or_network(self, request):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_state(root)
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                result = devto.main(["--project-root", str(root), "--preview"])

            self.assertEqual(result, 0)
            self.assertFalse(json.loads(stdout.getvalue())["article"]["published"])
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
