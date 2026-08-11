# AI Coding Radar

An unattended, source-first release radar for OpenAI Codex. It watches the
official Atom feed, rejects uncertain records, and renders a static homepage,
RSS feed, and one factual Markdown card per stable release.

Live site: <https://ai-coding-radar.github.io/>

## Run

```sh
python3 radar.py
python3 radar.py
```

The first run creates one post, `output/index.html`, `output/feed.xml`, state,
and a JSONL run log. Later runs rebuild the site but must not duplicate content.

Preview the site locally:

```sh
python3 -m http.server 8000 --directory output
```

## Test

```sh
python3 -m unittest discover -s tests -v
```

## Automation

GitHub Actions tests and deploys the site on pushes and manual runs. A daily
schedule is present, but scheduled feed refreshes stay off unless the repository
variable `AUTOPUBLISH` is exactly `true`. This is the global stop switch.

The first public version deliberately skips AI summaries, affiliate data,
platform distribution, analytics, and monetization claims. Add them only after
the source-first publishing loop is stable.
