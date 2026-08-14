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

    def test_grants_payload_is_unpublished_and_keeps_decision_boundaries(self):
        payload = devto_guide.article_payload(
            Path(__file__).resolve().parents[1],
            published=False,
            guide="grants-gov-monitor",
        )["article"]

        self.assertFalse(payload["published"])
        self.assertEqual(
            payload["canonical_url"],
            "https://github.com/Jarvis-Dong/grants-gov-opportunity-monitor/"
            "blob/main/examples/README.md",
        )
        self.assertIn("grants-gov-opportunity-monitor", payload["body_markdown"])
        self.assertIn("examples/daily-ai-federal-grant-opportunity-alerts", payload["body_markdown"])
        self.assertIn("n8n-grants-gov-monitor.json", payload["body_markdown"])
        self.assertIn("https://www.grants.gov/api/api-guide", payload["body_markdown"])
        self.assertIn("$0.0075", payload["body_markdown"])
        self.assertIn("$0.015", payload["body_markdown"])
        self.assertIn("$0.00005", payload["body_markdown"])
        self.assertIn("not an eligibility determination", payload["body_markdown"])
        self.assertNotIn("DEVTO_API_KEY=", payload["body_markdown"])

    def test_remote_jobs_payload_links_the_ai_example_and_workflow(self):
        payload = devto_guide.article_payload(
            Path(__file__).resolve().parents[1],
            published=False,
            guide="remote-ai-jobs",
        )["article"]

        self.assertFalse(payload["published"])
        self.assertIn("remote-job-intelligence", payload["canonical_url"])
        self.assertIn(
            "examples/daily-remote-ai-and-machine-learning-jobs",
            payload["body_markdown"],
        )
        self.assertIn("n8n-remote-jobs-webhook.json", payload["body_markdown"])
        self.assertIn('"keywordMatchMode": "any"', payload["body_markdown"])
        self.assertIn("$0.001", payload["body_markdown"])
        self.assertIn("does not submit applications", payload["body_markdown"])
        self.assertNotIn("APIFY_API_TOKEN=", payload["body_markdown"])

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

    @patch("devto_guide.devto.publish_article")
    def test_grants_preview_selects_the_requested_guide(self, publish_article):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = devto_guide.main(
                ["--preview", "--guide", "grants-gov-monitor"]
            )

        article = json.loads(stdout.getvalue())["article"]
        self.assertEqual(result, 0)
        self.assertIn("Grants.gov", article["title"])
        self.assertFalse(article["published"])
        publish_article.assert_not_called()

    @patch("devto_guide.devto.publish_article")
    def test_remote_jobs_preview_selects_the_requested_guide(
        self, publish_article
    ):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = devto_guide.main(
                ["--preview", "--guide", "remote-ai-jobs"]
            )

        article = json.loads(stdout.getvalue())["article"]
        self.assertEqual(result, 0)
        self.assertIn("remote AI jobs", article["title"])
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
