import json
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import radar
import submit_indexnow


class IndexNowHandler(BaseHTTPRequestHandler):
    payload = None
    content_type = None

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        type(self).payload = json.loads(self.rfile.read(length))
        type(self).content_type = self.headers["Content-Type"]
        self.send_response(202)
        self.end_headers()

    def log_message(self, *_):
        pass


class IndexNowTest(unittest.TestCase):
    def test_sitemap_urls_are_validated_and_submitted(self):
        with tempfile.TemporaryDirectory() as directory:
            sitemap = Path(directory) / "sitemap.xml"
            sitemap.write_text(
                radar.render_sitemap(
                    [
                        {
                            "source_key": "codex",
                            "version": "1.0.0",
                            "source_published_at": "2026-08-10T01:00:00Z",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            urls = submit_indexnow.load_sitemap_urls(sitemap)

            server = ThreadingHTTPServer(("127.0.0.1", 0), IndexNowHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status = submit_indexnow.submit_urls(
                    urls, f"http://127.0.0.1:{server.server_port}/indexnow"
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

            self.assertEqual(status, 202)
            self.assertEqual(IndexNowHandler.payload["host"], "ai-coding-radar.github.io")
            self.assertEqual(IndexNowHandler.payload["key"], radar.INDEXNOW_KEY)
            self.assertEqual(IndexNowHandler.payload["urlList"], urls)
            self.assertEqual(IndexNowHandler.content_type, "application/json; charset=utf-8")

            root = ET.parse(sitemap).getroot()
            foreign = root.find(f".//{submit_indexnow.SITEMAP_NAMESPACE}loc")
            foreign.text = "https://example.com/"
            ET.ElementTree(root).write(sitemap, encoding="unicode")
            with self.assertRaisesRegex(ValueError, "outside the public site"):
                submit_indexnow.load_sitemap_urls(sitemap)
