import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import devto_guide


class DevToGuideTest(unittest.TestCase):
    def test_payload_is_a_complete_draft_without_credentials(self):
        payload = devto_guide.article_payload(
            Path(__file__).resolve().parents[1], published=False
        )["article"]

        self.assertFalse(payload["published"])
        self.assertEqual(payload["canonical_url"], devto_guide.CANONICAL_URL)
        self.assertIn("vulnerabilities", payload["body_markdown"])
        self.assertIn("CISA", payload["body_markdown"])
        self.assertNotIn("apify_api_", payload["body_markdown"])

    def test_uk_payload_uses_a_distinct_canonical_url_and_valid_input(self):
        payload = devto_guide.article_payload(
            Path(__file__).resolve().parents[1],
            published=False,
            guide="uk-supplier-monitor",
        )["article"]

        self.assertFalse(payload["published"])
        self.assertIn("uk-company-change-alerts", payload["canonical_url"])
        self.assertIn('"companyNumbers"', payload["body_markdown"])
        self.assertIn("Companies House", payload["body_markdown"])
        self.assertIn(
            "examples/daily-uk-supplier-status-alerts",
            payload["body_markdown"],
        )
        self.assertNotIn("APIFY_API_TOKEN=", payload["body_markdown"])

    def test_markdown_image_payload_links_the_tested_workflow_and_example(self):
        payload = devto_guide.article_payload(
            Path(__file__).resolve().parents[1],
            published=False,
            guide="markdown-image-automation",
        )["article"]

        self.assertFalse(payload["published"])
        self.assertIn("markdown-code-to-image", payload["canonical_url"])
        self.assertIn(
            "n8n-markdown-code-to-image.json", payload["body_markdown"]
        )
        self.assertIn(
            "examples/chatgpt-markdown-answer-to-png",
            payload["body_markdown"],
        )
        self.assertIn('"documents"', payload["body_markdown"])
        self.assertNotIn("APIFY_TOKEN=", payload["body_markdown"])

    @patch("devto_guide.devto.publish_article")
    def test_preview_needs_no_token_or_network(self, publish_article):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = devto_guide.main(["--preview"])

        self.assertEqual(result, 0)
        self.assertFalse(json.loads(stdout.getvalue())["article"]["published"])
        publish_article.assert_not_called()

    @patch("devto_guide.devto.publish_article")
    def test_uk_preview_selects_the_requested_guide(self, publish_article):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = devto_guide.main(
                ["--preview", "--guide", "uk-supplier-monitor"]
            )

        article = json.loads(stdout.getvalue())["article"]
        self.assertEqual(result, 0)
        self.assertIn("UK supplier", article["title"])
        self.assertFalse(article["published"])
        publish_article.assert_not_called()

    @patch("devto_guide.devto.publish_article")
    def test_markdown_image_preview_selects_the_requested_guide(
        self, publish_article
    ):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = devto_guide.main(
                ["--preview", "--guide", "markdown-image-automation"]
            )

        article = json.loads(stdout.getvalue())["article"]
        self.assertEqual(result, 0)
        self.assertIn("PNG files in n8n", article["title"])
        self.assertFalse(article["published"])
        publish_article.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("devto_guide.devto.publish_article")
    def test_missing_token_fails_before_network(self, publish_article):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = devto_guide.main([])

        self.assertEqual(result, 2)
        self.assertIn("DEVTO_API_KEY is not set", stderr.getvalue())
        publish_article.assert_not_called()


if __name__ == "__main__":
    unittest.main()
