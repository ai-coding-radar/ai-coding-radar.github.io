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

    @patch("devto_guide.devto.publish_article")
    def test_preview_needs_no_token_or_network(self, publish_article):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = devto_guide.main(["--preview"])

        self.assertEqual(result, 0)
        self.assertFalse(json.loads(stdout.getvalue())["article"]["published"])
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
