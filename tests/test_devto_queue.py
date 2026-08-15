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
    @patch("devto_guide.devto.find_existing")
    def test_waits_until_twenty_four_hours_after_previous_guide(
        self, find_existing, publish_article
    ):
        find_existing.side_effect = [
            article("oss-security", OSS_PUBLISHED_AT),
            article("uk-supplier-monitor"),
            article("markdown-image-automation"),
            article("grants-gov-monitor"),
            article("remote-ai-jobs"),
        ]

        result = devto_guide.publish_next_due(
            PROJECT_ROOT,
            "secret",
            now=datetime(2026, 8, 15, 19, 19, 23, tzinfo=timezone.utc),
        )

        self.assertEqual(result["status"], "not_due")
        self.assertEqual(result["guide"], "uk-supplier-monitor")
        self.assertEqual(result["eligible_at"], "2026-08-15T19:19:24+00:00")
        publish_article.assert_not_called()

    @patch("devto_guide.devto.publish_article")
    @patch("devto_guide.devto.find_existing")
    def test_publishes_and_verifies_only_the_first_due_guide(
        self, find_existing, publish_article
    ):
        published_uk = article(
            "uk-supplier-monitor", "2026-08-15T19:20:00Z"
        )
        find_existing.side_effect = [
            article("oss-security", OSS_PUBLISHED_AT),
            article("uk-supplier-monitor"),
            article("markdown-image-automation"),
            article("grants-gov-monitor"),
            article("remote-ai-jobs"),
            published_uk,
        ]
        publish_article.return_value = {"status": "published"}

        result = devto_guide.publish_next_due(
            PROJECT_ROOT,
            "secret",
            now=datetime(2026, 8, 15, 19, 19, 24, tzinfo=timezone.utc),
        )

        self.assertEqual(result["status"], "published")
        self.assertEqual(result["guide"], "uk-supplier-monitor")
        self.assertEqual(result["id"], published_uk["id"])
        publish_article.assert_called_once()
        self.assertTrue(
            publish_article.call_args.args[0]["article"]["published"]
        )

    @patch("devto_guide.devto.publish_article")
    @patch("devto_guide.devto.find_existing")
    def test_rejects_an_out_of_order_publication(
        self, find_existing, publish_article
    ):
        find_existing.side_effect = [
            article("oss-security", OSS_PUBLISHED_AT),
            article("uk-supplier-monitor"),
            article("markdown-image-automation", "2026-08-16T19:20:00Z"),
            article("grants-gov-monitor"),
            article("remote-ai-jobs"),
        ]

        with self.assertRaisesRegex(devto.DevToError, "out of order"):
            devto_guide.publish_next_due(PROJECT_ROOT, "secret")

        publish_article.assert_not_called()

    @patch("devto_guide.devto.publish_article")
    @patch("devto_guide.devto.find_existing")
    def test_complete_queue_is_a_noop(self, find_existing, publish_article):
        find_existing.side_effect = [
            article(guide, f"2026-08-{15 + index:02d}T19:20:00Z")
            for index, guide in enumerate(devto_guide.GUIDE_QUEUE)
        ]

        result = devto_guide.publish_next_due(PROJECT_ROOT, "secret")

        self.assertEqual(result, {"status": "queue_complete"})
        publish_article.assert_not_called()

    @patch("devto_guide.devto.publish_article")
    @patch("devto_guide.devto.find_existing")
    def test_missing_published_baseline_fails_closed(
        self, find_existing, publish_article
    ):
        find_existing.side_effect = [
            article("oss-security"),
            article("uk-supplier-monitor"),
            article("markdown-image-automation"),
            article("grants-gov-monitor"),
            article("remote-ai-jobs"),
        ]

        with self.assertRaisesRegex(devto.DevToError, "baseline"):
            devto_guide.publish_next_due(PROJECT_ROOT, "secret")

        publish_article.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("devto_guide.devto.find_existing")
    def test_queue_cli_needs_a_secret_without_network(self, find_existing):
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            result = devto_guide.main(["--publish-next-due"])

        self.assertEqual(result, 2)
        self.assertIn("DEVTO_API_KEY is not set", stderr.getvalue())
        find_existing.assert_not_called()

    def test_workflow_has_a_guarded_daily_schedule(self):
        workflow = (
            PROJECT_ROOT / ".github/workflows/publish-dev-guide.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('cron: "20 1 * * *"', workflow)
        self.assertIn("github.event_name == 'schedule'", workflow)
        self.assertIn("--publish-next-due", workflow)
        self.assertIn("cancel-in-progress: false", workflow)


if __name__ == "__main__":
    unittest.main()
