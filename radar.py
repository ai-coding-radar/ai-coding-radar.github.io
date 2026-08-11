#!/usr/bin/env python3
"""Build one factual Codex release post from the official Atom feed."""

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path


DEFAULT_FEED_URL = "https://github.com/openai/codex/releases.atom"
SOURCE_URL_PREFIX = "https://github.com/openai/codex/releases/tag/"
SITE_URL = "https://ai-coding-radar.github.io/"
ATOM = "{http://www.w3.org/2005/Atom}"
PRERELEASE = re.compile(r"(?:^|[.-])(alpha|beta|rc)(?:[.-]|$)", re.IGNORECASE)
STABLE_VERSION = re.compile(r"^\d+(?:\.\d+){1,3}$")

INDEX_STYLE = """
:root {
  --paper: #f2eddf;
  --ink: #161713;
  --signal: #ff4b1f;
  --acid: #d8ff47;
  --white: #fffdf7;
  --muted: #69695f;
  --line: 2px solid var(--ink);
}

* { box-sizing: border-box; }

html { background: var(--ink); }

body {
  min-height: 100vh;
  margin: 0;
  color: var(--ink);
  background-color: var(--paper);
  background-image:
    linear-gradient(rgba(22, 23, 19, .06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(22, 23, 19, .06) 1px, transparent 1px);
  background-size: 28px 28px;
  font-family: "Avenir Next Condensed", "PingFang SC", sans-serif;
}

a { color: inherit; }

a:focus-visible {
  outline: 4px solid var(--acid);
  outline-offset: 4px;
}

.shell {
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto;
  padding: 24px 0 48px;
}

.masthead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 14px 18px;
  border: var(--line);
  background: var(--ink);
  color: var(--white);
  box-shadow: 8px 8px 0 var(--signal);
}

.brand,
.status,
.eyebrow,
.release-meta,
.release-foot,
.metric-label,
.footer {
  font-family: Menlo, Monaco, "Courier New", monospace;
  text-transform: uppercase;
  letter-spacing: .08em;
}

.brand { font-weight: 800; }

.brand span { color: var(--acid); }

.status {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-size: 12px;
}

.status::before {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--acid);
  box-shadow: 0 0 0 4px rgba(216, 255, 71, .18);
  content: "";
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(260px, .5fr);
  gap: 40px;
  align-items: end;
  padding: 88px 0 56px;
}

.eyebrow {
  margin: 0 0 18px;
  color: var(--signal);
  font-size: 13px;
  font-weight: 800;
}

h1 {
  max-width: 850px;
  margin: 0;
  font-family: "Bodoni 72", "Songti SC", Georgia, serif;
  font-size: clamp(64px, 11vw, 148px);
  font-weight: 900;
  letter-spacing: -.075em;
  line-height: .75;
}

h1 span {
  display: inline-block;
  color: transparent;
  -webkit-text-stroke: 2px var(--ink);
}

.lede {
  max-width: 340px;
  margin: 0;
  padding: 20px 0 0 22px;
  border-left: 8px solid var(--signal);
  font-size: 18px;
  font-weight: 650;
  line-height: 1.65;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin-bottom: 64px;
  border-top: var(--line);
  border-left: var(--line);
}

.metric {
  min-height: 132px;
  padding: 18px;
  border-right: var(--line);
  border-bottom: var(--line);
  background: rgba(255, 253, 247, .72);
}

.metric strong {
  display: block;
  margin-bottom: 12px;
  font-family: "Bodoni 72", Georgia, serif;
  font-size: 52px;
  line-height: 1;
}

.metric-label { color: var(--muted); font-size: 11px; }

.section-head {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}

h2 {
  margin: 0;
  font-family: "Bodoni 72", "Songti SC", Georgia, serif;
  font-size: clamp(42px, 7vw, 78px);
  line-height: .9;
}

.rss {
  padding: 10px 14px;
  border: var(--line);
  background: var(--acid);
  font-family: Menlo, Monaco, monospace;
  font-size: 12px;
  font-weight: 800;
  text-decoration: none;
  box-shadow: 4px 4px 0 var(--ink);
}

.release-list { display: grid; gap: 22px; }

.release {
  position: relative;
  display: grid;
  grid-template-columns: minmax(220px, .7fr) minmax(0, 1.3fr);
  overflow: hidden;
  border: var(--line);
  background: var(--white);
  box-shadow: 10px 10px 0 var(--ink);
  animation: rise .55s both;
}

.release::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 10px;
  background: var(--signal);
  content: "";
}

.release-version {
  display: grid;
  place-items: center;
  min-height: 250px;
  padding: 30px;
  border-right: var(--line);
  background: var(--acid);
  font-family: "Bodoni 72", Georgia, serif;
  font-size: clamp(42px, 7vw, 82px);
  font-weight: 900;
  letter-spacing: -.06em;
  line-height: .9;
}

.release-body {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 36px;
  padding: 34px;
}

.release-meta { color: var(--signal); font-size: 11px; font-weight: 800; }

.release h3 {
  margin: 14px 0 10px;
  font-family: "Songti SC", Georgia, serif;
  font-size: clamp(29px, 4vw, 48px);
  line-height: 1.08;
}

.release p {
  max-width: 650px;
  margin: 0;
  color: var(--muted);
  font-size: 16px;
  line-height: 1.65;
}

.release-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  font-size: 11px;
}

.source-link {
  padding-bottom: 3px;
  border-bottom: 2px solid var(--ink);
  font-weight: 800;
  text-decoration: none;
}

.protocol {
  display: grid;
  grid-template-columns: .75fr 1.25fr;
  gap: 40px;
  margin: 72px 0;
  padding: 34px;
  border: var(--line);
  background: var(--signal);
  color: var(--white);
}

.protocol h2 { font-size: clamp(40px, 6vw, 68px); }

.protocol ul {
  margin: 0;
  padding: 0;
  list-style: none;
  font-family: Menlo, Monaco, monospace;
  font-size: 13px;
  line-height: 2.1;
}

.protocol li::before { color: var(--acid); content: "[OK] "; }

.footer {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding-top: 20px;
  border-top: var(--line);
  font-size: 10px;
}

@keyframes rise {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 760px) {
  .shell { width: min(100% - 24px, 1180px); padding-top: 12px; }
  .masthead { align-items: flex-start; flex-direction: column; box-shadow: 5px 5px 0 var(--signal); }
  .hero { grid-template-columns: 1fr; gap: 30px; padding: 64px 0 42px; }
  h1 { font-size: clamp(58px, 22vw, 96px); }
  .lede { max-width: none; }
  .metrics { grid-template-columns: 1fr; }
  .metric { min-height: 96px; }
  .release { grid-template-columns: 1fr; box-shadow: 6px 6px 0 var(--ink); }
  .release-version { min-height: 160px; border-right: 0; border-bottom: var(--line); }
  .release-body { padding: 26px 22px 28px; }
  .release-foot, .footer { align-items: flex-start; flex-direction: column; }
  .protocol { grid-template-columns: 1fr; padding: 26px 22px; }
}

@media (prefers-reduced-motion: reduce) {
  .release { animation: none; }
}
"""


def fetch_feed(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "auto-media-radar/0.1"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def parse_source_timestamp(value):
    try:
        published = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("stable release has an invalid timestamp") from exc
    if published.tzinfo is None:
        raise ValueError("stable release timestamp is missing a timezone")
    return published


def parse_latest_stable(feed_bytes):
    try:
        root = ET.fromstring(feed_bytes)
    except ET.ParseError as exc:
        raise ValueError("invalid Atom feed") from exc

    for entry in root.findall(f"{ATOM}entry"):
        title = (entry.findtext(f"{ATOM}title") or "").strip()
        if not title or PRERELEASE.search(title):
            continue

        entry_id = (entry.findtext(f"{ATOM}id") or "").strip()
        updated = (entry.findtext(f"{ATOM}updated") or "").strip()
        link = next(
            (
                node.get("href", "").strip()
                for node in entry.findall(f"{ATOM}link")
                if node.get("rel") == "alternate"
            ),
            "",
        )
        if not entry_id or not updated or not link:
            raise ValueError("stable release is missing id, time, or source link")
        version = re.sub(r"^rust-v", "", title)
        if not STABLE_VERSION.fullmatch(version):
            raise ValueError("stable release has an unsupported version format")
        if link != f"{SOURCE_URL_PREFIX}rust-v{version}":
            raise ValueError("stable release link does not match the official tag")
        parse_source_timestamp(updated)

        return {
            "id": entry_id,
            "version": version,
            "source_published_at": updated,
            "source_url": link,
        }

    raise ValueError("no stable release found")


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def load_state(path):
    if not path.exists():
        return {"seen": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("state file is unreadable; refusing to overwrite it") from exc
    if not isinstance(state, dict) or not isinstance(state.get("seen"), dict):
        raise ValueError("state file has an invalid shape; refusing to overwrite it")
    return state


def render_post(release, detected_at):
    title = f"Codex 发布 {release['version']}"
    return f'''---
title: "{title}"
source_url: "{release['source_url']}"
source_published_at: "{release['source_published_at']}"
detected_at: "{detected_at}"
release_channel: "stable"
automated: true
ai_generated: false
---

# {title}

OpenAI Codex 官方发布了稳定版本 `{release['version']}`。

- 官方发布时间：`{release['source_published_at']}`
- 发布通道：稳定版
- 官方说明：[{release['source_url']}]({release['source_url']})

> 本文由自动化规则根据官方 Release 生成，不包含人工实测或额外性能结论；请以官方发布说明为准。
'''


def render_rss(records):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "AI Coding 更新雷达"
    ET.SubElement(channel, "link").text = SITE_URL
    ET.SubElement(channel, "description").text = "自动整理官方 Codex 稳定版发布"

    for record in sorted(
        records, key=lambda item: item["source_published_at"], reverse=True
    ):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = record["title"]
        ET.SubElement(item, "link").text = record["source_url"]
        guid = ET.SubElement(item, "guid", isPermaLink="false")
        guid.text = record["id"]
        published = parse_source_timestamp(record["source_published_at"])
        ET.SubElement(item, "pubDate").text = format_datetime(published)
        ET.SubElement(item, "description").text = "自动整理；请以官方说明为准。"

    body = ET.tostring(rss, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def render_index(records):
    ordered = sorted(
        records, key=lambda item: item["source_published_at"], reverse=True
    )
    cards = []
    for record in ordered:
        version = escape(record["version"])
        source_url = escape(record["source_url"], quote=True)
        published_at = escape(record["source_published_at"], quote=True)
        published_date = parse_source_timestamp(
            record["source_published_at"]
        ).strftime("%Y.%m.%d")
        cards.append(
            f'''<article class="release">
        <div class="release-version" aria-label="版本 {version}">{version}</div>
        <div class="release-body">
          <div>
            <div class="release-meta">Stable signal / {published_date}</div>
            <h3>Codex {version} 稳定版已发布</h3>
            <p>仅记录官方版本、时间与来源；没有人工实测，也不添加原始发布说明之外的性能结论。</p>
          </div>
          <div class="release-foot">
            <time datetime="{published_at}">{published_at}</time>
            <a class="source-link" href="{source_url}" target="_blank" rel="noopener noreferrer">核对官方来源 ↗</a>
          </div>
        </div>
      </article>'''
        )

    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="自动追踪 AI 编程工具官方稳定版发布，保留可核验来源。">
  <meta name="theme-color" content="#161713">
  <link rel="canonical" href="{SITE_URL}">
  <link rel="alternate" type="application/rss+xml" title="AI Coding 更新雷达 RSS" href="feed.xml">
  <title>AI Coding 更新雷达</title>
  <style>{INDEX_STYLE}</style>
</head>
<body>
  <div class="shell">
    <header class="masthead">
      <div class="brand">AUTO MEDIA <span>/ SIGNAL DESK</span></div>
      <div class="status">pipeline online · stable only</div>
    </header>

    <main>
      <section class="hero" aria-labelledby="page-title">
        <div>
          <p class="eyebrow">Unattended media / source-first</p>
          <h1 id="page-title"><span>AI Coding</span><br>更新雷达</h1>
        </div>
        <p class="lede">机器可以自动发布，事实不能自动放宽。这里只记录白名单官方来源、稳定版本与可追溯时间。</p>
      </section>

      <section class="metrics" aria-label="运行指标">
        <div class="metric"><strong>{len(ordered)}</strong><span class="metric-label">stable releases tracked</span></div>
        <div class="metric"><strong>0</strong><span class="metric-label">unsupported claims</span></div>
        <div class="metric"><strong>1</strong><span class="metric-label">official source allowlisted</span></div>
      </section>

      <section aria-labelledby="signals-title">
        <div class="section-head">
          <h2 id="signals-title">Stable signals</h2>
          <a class="rss" href="feed.xml">RSS / XML</a>
        </div>
        <div class="release-list">{''.join(cards)}</div>
      </section>

      <section class="protocol" aria-labelledby="protocol-title">
        <h2 id="protocol-title">发布协议</h2>
        <ul>
          <li>仅收录官方稳定版本</li>
          <li>每个版本只生成一次</li>
          <li>来源异常时拒绝产出</li>
          <li>自动内容明确标记</li>
          <li>没有外部图片与虚构实测</li>
        </ul>
      </section>
    </main>

    <footer class="footer">
      <span>AI Coding 更新雷达 / 自动事实卡</span>
      <span>AI_GENERATED: FALSE · AUTOMATED: TRUE</span>
    </footer>
  </div>
</body>
</html>
'''


def process_feed(feed_bytes, root_dir, now=None):
    release = parse_latest_stable(feed_bytes)
    root_dir = Path(root_dir)
    state_path = root_dir / "state" / "seen.json"
    state = load_state(state_path)
    created = release["id"] not in state["seen"]
    post_path = None
    post_content = None
    if created:
        detected_at = (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")
        date = release["source_published_at"][:10]
        version_slug = re.sub(r"[^0-9A-Za-z._-]+", "-", release["version"]).strip("-")
        relative_post = f"output/posts/{date}-codex-{version_slug}.md"
        post_path = root_dir / relative_post
        post_content = render_post(release, detected_at)
        state["seen"][release["id"]] = {
            **release,
            "title": f"Codex 发布 {release['version']}",
            "detected_at": detected_at,
            "post": relative_post,
        }

    records = list(state["seen"].values())
    rss_content = render_rss(records)
    index_content = render_index(records)

    if created:
        atomic_write(post_path, post_content)
        atomic_write(state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    atomic_write(root_dir / "output" / "feed.xml", rss_content)
    atomic_write(root_dir / "output" / "index.html", index_content)
    return created


def append_log(root_dir, status, detail):
    path = Path(root_dir) / "logs" / "runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "detail": detail,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed-url", default=DEFAULT_FEED_URL)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args(argv)

    try:
        created = process_feed(fetch_feed(args.feed_url), args.root)
        message = "created one stable release post" if created else "no new stable release"
        append_log(args.root, "ok", message)
        print(message)
        return 0
    except (OSError, ValueError) as exc:
        append_log(args.root, "error", str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
