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

The first public version deliberately skips AI summaries, affiliate data,
platform distribution, analytics, and monetization claims. Add them only after
the source-first publishing loop is stable.
