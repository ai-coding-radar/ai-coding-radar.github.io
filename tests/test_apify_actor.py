import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from apify_actor.core import (
    SOURCE_BY_KEY,
    collect_releases,
    fetch_feed,
    parse_feed,
    risk_signals,
)
from apify_actor.main import run_actor


def feed(entries):
    body = "".join(entries)
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{body}</feed>'.encode()


def entry(entry_id, title, updated, url, content=""):
    return f"""
    <entry>
      <id>{entry_id}</id><title>{title}</title><updated>{updated}</updated>
      <link rel="alternate" href="{url}"/><content>{content}</content>
    </entry>"""


class ActorCoreTests(unittest.TestCase):
    def test_parses_stable_release_and_risk_signals(self):
        source = SOURCE_BY_KEY["claude-code"]
        payload = feed(
            [
                entry(
                    "tag:github.com,2008:Repository/1/v2.1.9",
                    "v2.1.9",
                    "2026-08-13T01:02:03Z",
                    "https://github.com/anthropics/claude-code/releases/tag/v2.1.9",
                    "Security fix with a migration note",
                )
            ]
        )
        releases = parse_feed(payload, source)
        self.assertEqual(releases[0]["version"], "2.1.9")
        self.assertEqual(releases[0]["riskSignals"], ["security", "migration"])

    def test_skips_valid_prerelease(self):
        source = SOURCE_BY_KEY["gemini-cli"]
        payload = feed(
            [
                entry(
                    "tag:github.com,2008:Repository/2/v1.0.0-preview.1",
                    "Release v1.0.0-preview.1",
                    "2026-08-13T01:02:03Z",
                    "https://github.com/google-gemini/gemini-cli/releases/tag/v1.0.0-preview.1",
                )
            ]
        )
        self.assertEqual(parse_feed(payload, source), [])

    def test_rejects_source_or_title_mismatch(self):
        source = SOURCE_BY_KEY["codex"]
        payload = feed(
            [
                entry(
                    "id-1",
                    "rust-v1.0.1",
                    "2026-08-13T01:02:03Z",
                    "https://example.com/openai/codex/releases/tag/rust-v1.0.1",
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "allowlist"):
            parse_feed(payload, source)

    def test_collects_selected_tools_with_limit(self):
        payloads = {
            "codex": feed(
                [
                    entry(
                        f"id-{version}",
                        version,
                        f"2026-08-{day:02d}T00:00:00Z",
                        f"https://github.com/openai/codex/releases/tag/rust-v{version}",
                    )
                    for version, day in (("1.0.0", 12), ("1.0.1", 13))
                ]
            )
        }
        results = collect_releases(["codex"], 1, payloads)
        self.assertEqual([item["version"] for item in results], ["1.0.1"])

    def test_rejects_unknown_or_duplicate_tools(self):
        with self.assertRaisesRegex(ValueError, "unsupported tool"):
            collect_releases(["unknown"], feed_payloads={})
        with self.assertRaisesRegex(ValueError, "duplicates"):
            collect_releases(["codex", "codex"], feed_payloads={})
        with self.assertRaisesRegex(ValueError, "at least one"):
            collect_releases([], feed_payloads={})
        with self.assertRaisesRegex(ValueError, "integer"):
            collect_releases(["codex"], True, feed_payloads={})

    def test_risk_signals_are_factual_keyword_flags(self):
        self.assertEqual(risk_signals("Routine patch"), [])
        self.assertEqual(risk_signals("BREAKING: remove old API"), ["breaking", "migration"])

    @patch("apify_actor.core.time.sleep")
    @patch("apify_actor.core.urllib.request.urlopen")
    def test_fetch_retries_transient_network_errors(self, urlopen, sleep):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"feed"
        urlopen.side_effect = [OSError("temporary"), response]

        self.assertEqual(fetch_feed(SOURCE_BY_KEY["codex"]), b"feed")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1)


class ActorRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def actor(self, actor_input, charged_count):
        actor = SimpleNamespace(
            get_input=AsyncMock(return_value=actor_input),
            push_data=AsyncMock(
                return_value=SimpleNamespace(charged_count=charged_count)
            ),
            set_status_message=AsyncMock(),
            log=MagicMock(),
        )
        return actor

    @patch("apify_actor.main.collect_releases")
    async def test_passes_input_and_charges_only_dataset_records(self, collect):
        releases = [{"version": "1.0.0"}, {"version": "1.0.1"}]
        collect.return_value = releases
        actor = self.actor(
            {"tools": ["codex"], "limitPerTool": 2}, charged_count=1
        )

        await run_actor(actor)

        collect.assert_called_once_with(tools=["codex"], limit_per_tool=2)
        actor.push_data.assert_awaited_once_with(releases)
        actor.log.info.assert_called_once()
        actor.set_status_message.assert_awaited_once_with(
            "Published 1 verified stable release records"
        )

    @patch("apify_actor.main.collect_releases", side_effect=OSError("offline"))
    async def test_collection_failure_pushes_and_charges_nothing(self, collect):
        actor = self.actor({}, charged_count=0)

        with self.assertRaisesRegex(OSError, "offline"):
            await run_actor(actor)

        collect.assert_called_once_with(tools=None, limit_per_tool=5)
        actor.push_data.assert_not_awaited()
        actor.set_status_message.assert_not_awaited()

    async def test_non_object_input_fails_before_collection(self):
        actor = self.actor(["codex"], charged_count=0)

        with self.assertRaisesRegex(ValueError, "must be an object"):
            await run_actor(actor)

        actor.push_data.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
