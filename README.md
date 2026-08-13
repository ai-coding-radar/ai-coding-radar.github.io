# AI Coding Radar

An unattended, source-first release radar for AI coding tools. It watches three
official Atom feeds, rejects uncertain records, and renders an English static
homepage, RSS feed, one factual Markdown record, one public HTML page per stable
release, and a release-history page per tool.

Live site: <https://ai-coding-radar.github.io/>

## Sources

- [OpenAI Codex](https://github.com/openai/codex/releases)
- [Claude Code](https://github.com/anthropics/claude-code/releases)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli/releases)

Only numeric stable tags from these exact repositories are accepted. Preview,
nightly, alpha, beta, release-candidate, development, and canary tags are skipped.

## Run

```sh
python3 radar.py
python3 radar.py
```

The first run imports every stable release still visible in each feed and creates
the homepage, tool histories, release pages, RSS, sitemap, robots file, state,
Markdown records, and a JSONL run log. Later runs rebuild the site but must not
duplicate content.

After a public site change, the deployment workflow submits the sitemap URLs to
the official IndexNow endpoint. The public root key file proves site ownership;
IndexNow failure is reported by Actions but never blocks the Pages deployment.

Preview the site locally:

```sh
python3 -m http.server 8000 --directory output
```

## Test

```sh
python3 -m unittest discover -s tests -v
```

## Automation

GitHub Actions tests and deploys the site on pushes and manual runs. The daily
feed refresh is enabled after the public smoke test. Set the repository variable
`AUTOPUBLISH` to exactly `false` to pause it; this is the global stop switch.
The tracked IndexNow key remains public even while feed refreshes are paused.

The 09:00 Asia/Shanghai Codex heartbeat also runs
`python3 ensure_daily_refresh.py`. It is a narrow missed-run backstop: if a
successful or active Publish radar workflow already exists for the Beijing
calendar day, it does nothing; otherwise it dispatches one manual refresh.

The first public version deliberately skips AI summaries, affiliate data,
analytics, and monetization claims. Add them only after the source-first
publishing loop is stable.

## DEV Community distribution

`devto.py` uses DEV's official Forem API to cross-post the newest verified
release record. Previewing is offline, and the default network action creates
an unpublished draft. Public posting requires the explicit `--publish` flag.
Before creating anything, the adapter scans the authenticated account's article
history for the same canonical URL so repeat runs do not duplicate a release.

```sh
python3 devto.py --preview
DEVTO_API_KEY=... python3 devto.py
DEVTO_API_KEY=... python3 devto.py --publish
```

Create the key at <https://dev.to/settings/extensions>. Keep it out of the
repository and chat history; use a local environment variable or a repository
secret named `DEVTO_API_KEY`. The manual **Draft latest release on DEV**
workflow can then create the first draft without exposing the key. No browser
cookie is read. Distribution is not scheduled until the account and one draft
have been verified.

## XiaoHongShu daily draft

The local data collector turns one Beijing calendar day of
repository evidence into a Chinese XiaoHongShu-ready draft. It reads Git
history, `logs/runs.jsonl`, `state/seen.json`, local site facts, and the
explicit `metrics/ledger.json` ledger. Deployment, impressions, clicks, and
saved time are never counted as income; without an explicitly settled ledger
entry the report says `¥0`.

The morning monitor writes only visibly verified Search Console facts to
`metrics/search-console.json`. Values that Google is still processing remain
`null`; sitemap errors are recorded as errors rather than inferred from the
public HTTP response.

```sh
python3 -m xiaohongshu.daily --date 2026-08-12
```

Use `--project-root` for another checkout and `--output-dir` for another draft
parent. The command writes the same
`drafts/xiaohongshu/YYYY-MM-DD/{title.txt,caption.md,facts.json,*.png}` files
on repeat runs, including four 1242x1660 (3:4) carousel PNGs. Pillow is
required at runtime for real PNG rendering; if it is absent the command fails
without writing fake image files. The generator creates the zero-valued ledger
on first use; its accounting rules are documented in
[`metrics/README.md`](metrics/README.md). It does not log in to or publish to
XiaoHongShu, and it does not use cookies, browser automation, or CAPTCHA
bypasses.

A Codex heartbeat runs the generator at 20:00 Asia/Shanghai on the computer
hosting this workspace. The existing 09:00 search-index monitor shares the same
heartbeat. Keep that computer awake and connected at those times. Drafts remain
local because the public XiaoHongShu ecommerce API catalogue does not expose a
verified ordinary-creator note publishing endpoint.
