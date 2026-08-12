import json
import os
import struct
import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from xiaohongshu.daily import DailyReportError, generate_daily_report, summarize_ledger


class DailyReportTest(unittest.TestCase):
    def setUp(self):
        self.site_patch = patch(
            "xiaohongshu.daily._site_facts",
            return_value={
                "public_url": "https://ai-coding-radar.github.io/",
                "local_build_ready": False,
                "files": {},
                "sitemap_url_count": 0,
                "http_checked": True,
                "http_ok": True,
                "http_status": {},
                "note": "公开站点均返回 HTTP 200",
            },
        )
        self.actions_patch = patch(
            "xiaohongshu.daily._actions_facts",
            return_value={
                "available": True,
                "today_count": 1,
                "success_count": 1,
                "failure_count": 0,
                "runs": [],
                "note": "今日 GitHub Actions 1 次，成功 1 次",
            },
        )
        self.site_patch.start()
        self.actions_patch.start()

    def tearDown(self):
        self.actions_patch.stop()
        self.site_patch.stop()

    def _repo(self, directory):
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
        (root / "logs").mkdir()
        (root / "state").mkdir()
        (root / "logs" / "runs.jsonl").write_text(
            "\n".join(
                [
                    json.dumps({"time": "2026-08-12T10:00:00Z", "status": "ok", "detail": "created 1 post"}),
                    json.dumps({"time": "2026-08-11T15:00:00Z", "status": "error", "detail": "old run"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "state" / "seen.json").write_text(
            json.dumps(
                {
                    "seen": {
                        "today": {
                            "source_key": "codex",
                            "product": "OpenAI Codex",
                            "version": "0.147.0",
                            "detected_at": "2026-08-12T10:01:00Z",
                        },
                        "old": {
                            "source_key": "claude-code",
                            "product": "Claude Code",
                            "version": "2.1.1",
                            "detected_at": "2026-08-11T10:01:00Z",
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        (root / "README.md").write_text("test", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-qm", "feat: 今天完成 <测试> & review"],
            check=True,
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": "2026-08-12T17:00:00+08:00",
                "GIT_COMMITTER_DATE": "2026-08-12T17:00:00+08:00",
            },
        )
        return root

    def test_generation_is_idempotent_and_uses_beijing_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory)
            output = root / "drafts" / "xiaohongshu"
            first = generate_daily_report("2026-08-12", root, output)
            snapshot = {path.name: path.read_bytes() for path in first.iterdir()}
            second = generate_daily_report("2026-08-12", root, output)
            self.assertEqual(first, second)
            self.assertEqual(snapshot, {path.name: path.read_bytes() for path in second.iterdir()})

            facts = json.loads((first / "facts.json").read_text(encoding="utf-8"))
            self.assertEqual(facts["date"], "2026-08-12")
            self.assertEqual(facts["timezone"], "Asia/Shanghai")
            self.assertEqual(facts["day_index"], 1)
            self.assertEqual(facts["git"]["today_count"], 1)
            self.assertEqual(facts["runs"]["today_count"], 1)
            self.assertEqual(facts["state"]["today_new_count"], 1)
            self.assertEqual(facts["actions"]["success_count"], 1)
            self.assertEqual(
                sorted(path.name for path in first.iterdir()),
                ["caption.md", "cover.png", "facts.json", "metrics.png", "progress.png", "title.txt", "tomorrow.png"],
            )

    def test_png_magic_and_dimensions_are_real_1242_by_1660(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory)
            destination = generate_daily_report("2026-08-12", root, root / "drafts" / "xiaohongshu")
            for name in ("cover.png", "progress.png", "metrics.png", "tomorrow.png"):
                data = (destination / name).read_bytes()
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", data[16:24]), (1242, 1660))

    def test_default_contract_paths_and_zero_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory)
            destination = generate_daily_report("2026-08-12", root)
            self.assertEqual(destination, (root / "drafts" / "xiaohongshu" / "2026-08-12").resolve())
            ledger = json.loads((root / "metrics" / "ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["settled_revenue"], 0)
            self.assertEqual(ledger["cost"], 0)
            self.assertEqual(ledger["pending_revenue"], 0)
            self.assertEqual(ledger["estimated_revenue"], 0)
            self.assertIn("Day 1", (destination / "title.txt").read_text(encoding="utf-8"))

    def test_revenue_requires_settled_and_does_not_infer_traffic(self):
        ledger = {
            "currency": "CNY",
            "settled_revenue": 999,
            "cost": 2,
            "pending_revenue": 7,
            "estimated_revenue": 8,
            "impressions": 99999,
            "entries": [
                {"date": "2026-08-12", "kind": "revenue", "amount": 9, "status": "pending"},
                {"date": "2026-08-12", "kind": "revenue", "amount": 1, "status": "settled", "receipt": "payout-1"},
                {"date": "2026-08-12", "kind": "cost", "amount": 0.5, "status": "paid"},
            ],
        }
        result = summarize_ledger(ledger, datetime(2026, 8, 12).date())
        self.assertEqual(result["today"]["settled_revenue"], 1)
        self.assertEqual(result["today"]["pending_revenue"], 9)
        self.assertEqual(result["today"]["estimated_revenue"], 0)
        self.assertEqual(result["cumulative"]["settled_revenue"], 1)
        self.assertEqual(result["cumulative"]["cost"], 0.5)
        self.assertTrue(result["warnings"])

    def test_facts_and_caption_have_the_same_money_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory)
            (root / "metrics").mkdir()
            (root / "metrics" / "ledger.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "currency": "CNY",
                        "entries": [
                            {"date": "2026-08-12", "kind": "revenue", "amount": 1, "status": "settled", "receipt": "payout-1"},
                            {"date": "2026-08-12", "kind": "cost", "amount": 0.5, "status": "paid"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            destination = generate_daily_report("2026-08-12", root, root / "drafts" / "xiaohongshu")
            facts = json.loads((destination / "facts.json").read_text(encoding="utf-8"))
            caption = (destination / "caption.md").read_text(encoding="utf-8")
            self.assertIn("今日已结算到账：**¥1**", caption)
            self.assertIn("累计已结算到账：**¥1**", caption)
            self.assertIn("累计成本：**¥0.50**", caption)
            self.assertEqual(facts["money"]["today"]["settled_revenue"], 1)
            self.assertEqual(facts["money"]["cumulative"]["cost"], 0.5)

    def test_cover_contains_day_and_real_revenue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory)
            destination = generate_daily_report("2026-08-12", root)
            self.assertIn("Day 1", (destination / "title.txt").read_text(encoding="utf-8"))
            facts = json.loads((destination / "facts.json").read_text(encoding="utf-8"))
            self.assertEqual(facts["money"]["today"]["settled_revenue"], 0)
            self.assertGreater((destination / "cover.png").stat().st_size, 10_000)

    def test_chinese_and_untrusted_text_are_escaped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory)
            (root / "logs" / "runs.jsonl").write_text(
                json.dumps(
                    {
                        "time": "2026-08-12T10:00:00Z",
                        "status": "ok",
                        "detail": "中文 <script>alert(1)</script> [link](https://bad.example) `code`\u0001",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            destination = generate_daily_report("2026-08-12", root, root / "drafts" / "xiaohongshu")
            caption = (destination / "caption.md").read_text(encoding="utf-8")
            self.assertIn("中文", caption)
            self.assertNotIn("<script>", caption)
            self.assertNotIn("[link]", caption)
            self.assertIn("facts.json", [path.name for path in destination.iterdir()])

    def test_invalid_money_is_rejected(self):
        with self.assertRaisesRegex(DailyReportError, "non-negative number"):
            summarize_ledger({"entries": [{"date": "2026-08-12", "kind": "revenue", "amount": -1, "status": "settled", "receipt": "payout-1"}]}, datetime(2026, 8, 12).date())

    def test_private_branch_commits_are_not_collected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory)
            subprocess.run(["git", "-C", str(root), "branch", "private"], check=True)
            subprocess.run(["git", "-C", str(root), "switch", "private"], check=True, capture_output=True)
            (root / "secret.txt").write_text("secret", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "secret.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-qm", "PRIVATE SECRET subject"],
                check=True,
                env={**os.environ, "GIT_AUTHOR_DATE": "2026-08-12T18:00:00+08:00", "GIT_COMMITTER_DATE": "2026-08-12T18:00:00+08:00"},
            )
            subprocess.run(["git", "-C", str(root), "switch", "master"], check=True, capture_output=True)
            destination = generate_daily_report("2026-08-12", root)
            facts = (destination / "facts.json").read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE SECRET", facts)

    def test_settled_revenue_requires_date_status_and_receipt(self):
        target = datetime(2026, 8, 12).date()
        invalid = (
            {"entries": [{"kind": "revenue", "amount": 1, "status": "settled", "receipt": "payout-1"}]},
            {"entries": [{"date": "2026-08-12", "kind": "settled_revenue", "amount": 1, "receipt": "payout-1"}]},
            {"entries": [{"date": "2026-08-12", "kind": "revenue", "amount": 1, "status": "settled"}]},
        )
        with self.assertRaisesRegex(DailyReportError, "ISO date"):
            summarize_ledger(invalid[0], target)
        result = summarize_ledger(invalid[1], target)
        self.assertEqual(result["cumulative"]["settled_revenue"], 0)
        with self.assertRaisesRegex(DailyReportError, "receipt"):
            summarize_ledger(invalid[2], target)

    def test_invalid_or_future_experiment_start_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory)
            (root / "metrics").mkdir()
            (root / "metrics" / "experiment.json").write_text("not json", encoding="utf-8")
            with self.assertRaisesRegex(DailyReportError, "metadata is invalid"):
                generate_daily_report("2026-08-12", root)
            (root / "metrics" / "experiment.json").write_text(
                json.dumps({"start_date": "2026-08-13"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(DailyReportError, "future"):
                generate_daily_report("2026-08-12", root)

    def test_missing_pillow_fails_instead_of_writing_fake_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._repo(directory)
            with patch("xiaohongshu.daily._require_pillow", side_effect=DailyReportError("生成四张真实 PNG 需要 Pillow")):
                with self.assertRaisesRegex(DailyReportError, "真实 PNG"):
                    generate_daily_report("2026-08-12", root)
            self.assertFalse((root / "drafts").exists())


if __name__ == "__main__":
    unittest.main()
