import io
import json
import os
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import devto
import devto_guide


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OSS_PUBLISHED_AT = "2026-08-14T19:19:24Z"


def article(guide, published_at=None):
    return {
        "id": devto_guide.GUIDE_QUEUE.index(guide) + 100,
        "url": f"https://dev.to/aicodingradar/{guide}",
        "canonical_url": devto_guide.GUIDES[guide]["canonical_url"],
        "published_at": published_at,
    }


class DevToQueueTest(unittest.TestCase):
    @patch("devto_guide.devto.publish_article")
    @patch("devto_guide.devto.list_articles")
    def test_waits_until_twenty_four_hours_after_previous_guide(
        self, list_articles, publish_article
    ):
        list_articles.return_value = [
            article("oss-security", OSS_PUBLISHED_AT),
            article("grants-gov-monitor"),
            article("uk-supplier-monitor"),
            article("markdown-image-automation"),
            article("remote-ai-jobs"),
        ]

        result = devto_guide.publish_next_due(
            PROJECT_ROOT,
            "secret",
            now=datetime(2026, 8, 15, 19, 19, 23, tzinfo=timezone.utc),
        )

        self.assertEqual(result["status"], "not_due")
        self.assertEqual(result["guide"], "grants-gov-monitor")
        self.assertEqual(result["eligible_at"], "2026-08-15T19:19:24+00:00")
        list_articles.assert_called_once_with("secret")
        publish_article.assert_not_called()

    @patch("devto_guide.devto.get_article")
    @patch("devto_guide.devto.publish_article")
    @patch("devto_guide.devto.list_articles")
    def test_publishes_and_verifies_only_the_first_due_guide(
        self, list_articles, publish_article, get_article
    ):
        published_grants = article(
            "grants-gov-monitor", "2026-08-15T19:20:00Z"
        )
        articles = [
            article("oss-security", OSS_PUBLISHED_AT),
            article("grants-gov-monitor"),
            article("uk-supplier-monitor"),
            article("markdown-image-automation"),
            article("remote-ai-jobs"),
        ]
        list_articles.return_value = articles
        publish_article.return_value = {
            "status": "published",
            "id": published_grants["id"],
        }
        get_article.return_value = published_grants

        result = devto_guide.publish_next_due(
            PROJECT_ROOT,
            "secret",
            now=datetime(2026, 8, 15, 19, 19, 24, tzinfo=timezone.utc),
        )

        self.assertEqual(result["status"], "published")
        self.assertEqual(result["guide"], "grants-gov-monitor")
        self.assertEqual(result["id"], published_grants["id"])
        list_articles.assert_called_once_with("secret")
        publish_article.assert_called_once()
        self.assertTrue(
            publish_article.call_args.args[0]["article"]["published"]
        )
        self.assertIs(publish_article.call_args.kwargs["existing_articles"], articles)
        get_article.assert_called_once_with("secret", published_grants["id"])

    @patch("devto_guide.devto.publish_article")
    @patch("devto_guide.devto.list_articles")
    def test_rejects_an_out_of_order_publication(
        self, list_articles, publish_article
    ):
        list_articles.return_value = [
            article("oss-security", OSS_PUBLISHED_AT),
            article("grants-gov-monitor"),
            article("uk-supplier-monitor"),
            article("markdown-image-automation", "2026-08-16T19:20:00Z"),
            article("remote-ai-jobs"),
        ]

        with self.assertRaisesRegex(devto.DevToError, "out of order"):
            devto_guide.publish_next_due(PROJECT_ROOT, "secret")

        publish_article.assert_not_called()

    @patch("devto_guide.devto.publish_article")
    @patch("devto_guide.devto.list_articles")
    def test_complete_queue_is_a_noop(self, list_articles, publish_article):
        list_articles.return_value = [
            article(guide, f"2026-08-{15 + index:02d}T19:20:00Z")
            for index, guide in enumerate(devto_guide.GUIDE_QUEUE)
        ]

        result = devto_guide.publish_next_due(PROJECT_ROOT, "secret")

        self.assertEqual(result, {"status": "queue_complete"})
        publish_article.assert_not_called()

    @patch("devto_guide.devto.publish_article")
    @patch("devto_guide.devto.list_articles")
    def test_missing_published_baseline_fails_closed(
        self, list_articles, publish_article
    ):
        list_articles.return_value = [
            article("oss-security"),
            article("grants-gov-monitor"),
            article("uk-supplier-monitor"),
            article("markdown-image-automation"),
            article("remote-ai-jobs"),
        ]

        with self.assertRaisesRegex(devto.DevToError, "baseline"):
            devto_guide.publish_next_due(PROJECT_ROOT, "secret")

        publish_article.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("devto_guide.devto.list_articles")
    def test_queue_cli_needs_a_secret_without_network(self, list_articles):
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            result = devto_guide.main(["--publish-next-due"])

        self.assertEqual(result, 2)
        self.assertIn("DEVTO_API_KEY is not set", stderr.getvalue())
        list_articles.assert_not_called()

    def test_workflow_has_a_guarded_daily_schedule(self):
        workflow = (
            PROJECT_ROOT / ".github/workflows/publish-dev-guide.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('cron: "20 1 * * *"', workflow)
        self.assertIn('cron: "20 2 * * *"', workflow)
        self.assertIn("DEV queue fallback", workflow)
        self.assertIn("publish_next_due", workflow)
        self.assertIn("github.event_name == 'schedule' || inputs.publish_next_due", workflow)
        self.assertIn("--publish-next-due", workflow)
        self.assertIn("cancel-in-progress: false", workflow)


if __name__ == "__main__":
    unittest.main()
