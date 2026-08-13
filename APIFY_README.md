# AI Coding Release Intelligence

Get normalized, verified stable releases for OpenAI Codex, Claude Code, and
Gemini CLI. The Actor reads only the three allowlisted official GitHub Atom
feeds, rejects malformed or mismatched records, skips prereleases, and writes
one dataset item per release.

> This is an independent, unofficial community Actor. It is not affiliated
> with, endorsed by, or sponsored by OpenAI, Anthropic, or Google.

Use it in scheduled jobs, dependency dashboards, RAG pipelines, MCP workflows,
or release-notification automations without maintaining three different feed
parsers.

## What it returns

Each dataset item contains:

- `tool`, `product`, and official GitHub `repository`
- normalized numeric stable `version`
- official release timestamp and URL
- `riskSignals`: transparent keyword flags for breaking, security, or migration
  language found in the official feed content

The Actor does not generate release summaries, performance claims, or inferred
benchmarks. An empty `riskSignals` array means no configured keyword was found;
it is not a claim that the release has no risk.

## Input

```json
{
  "tools": ["codex", "claude-code", "gemini-cli"],
  "limitPerTool": 5
}
```

`tools` accepts only the three listed keys. `limitPerTool` must be between 1 and
20. The Actor fails closed if an official feed is malformed, empty, points to a
different repository, or contains a title/tag mismatch.

## Example output

```json
{
  "tool": "claude-code",
  "product": "Claude Code",
  "repository": "anthropics/claude-code",
  "version": "2.1.229",
  "channel": "stable",
  "publishedAt": "2026-08-12T12:00:00Z",
  "officialUrl": "https://github.com/anthropics/claude-code/releases/tag/v2.1.229",
  "riskSignals": []
}
```

## Pricing and limits

The pay-per-event dataset-item charge maps one-to-one to a visible dataset
record. When a run reaches its spending limit, the Actor stops cleanly without
pushing uncharged records. Platform compute costs and final event pricing are
shown by Apify before a run; the README does not make a price claim that could
drift from the Store configuration.

## Data provenance

- <https://github.com/openai/codex/releases>
- <https://github.com/anthropics/claude-code/releases>
- <https://github.com/google-gemini/gemini-cli/releases>

Only public official release metadata is read. No account cookies, private
repository data, personal data, or user-provided tokens are required.

## Reliability

The parser validates the Atom document, entry envelope, exact repository tag
URL, title/tag agreement, timestamp timezone, stable version format, and entry
ID uniqueness before returning data. Upstream errors fail the run instead of
being reported as successful empty output.
