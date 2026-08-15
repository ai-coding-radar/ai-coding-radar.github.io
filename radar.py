#!/usr/bin/env python3
"""Build factual AI coding release posts from official Atom feeds."""

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


SITE_URL = "https://ai-coding-radar.github.io/"
INDEXNOW_KEY = "283f1da55b1668cf01c7a66f3da004fb"
ATOM = "{http://www.w3.org/2005/Atom}"
SOURCES = (
    {
        "key": "codex",
        "product": "OpenAI Codex",
        "feed_url": "https://github.com/openai/codex/releases.atom",
        "tag_url_prefix": "https://github.com/openai/codex/releases/tag/rust-v",
        "title_prefixes": ("", "rust-v"),
    },
    {
        "key": "claude-code",
        "product": "Claude Code",
        "feed_url": "https://github.com/anthropics/claude-code/releases.atom",
        "tag_url_prefix": "https://github.com/anthropics/claude-code/releases/tag/v",
        "title_prefixes": ("v",),
    },
    {
        "key": "gemini-cli",
        "product": "Gemini CLI",
        "feed_url": "https://github.com/google-gemini/gemini-cli/releases.atom",
        "tag_url_prefix": "https://github.com/google-gemini/gemini-cli/releases/tag/v",
        "title_prefixes": ("Release v",),
    },
)
SOURCE_BY_KEY = {source["key"]: source for source in SOURCES}
DEFAULT_FEED_URL = SOURCES[0]["feed_url"]
SOURCE_URL_PREFIX = SOURCES[0]["tag_url_prefix"]
PRERELEASE = re.compile(
    r"(?:^|[.-])(?:alpha|beta|rc|release-candidate|preview|nightly|dev|development|canary)(?:[.\d-]|$)",
    re.IGNORECASE,
)
STABLE_VERSION = re.compile(r"^\d+(?:\.\d+){1,3}$")
TAG_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,127}$")
INDEX_LIMIT = 30
RSS_LIMIT = 50
AUTOMATIONS = (
    {
        "slug": "remote-jobs-api",
        "title": "Remote Jobs Aggregator API for n8n",
        "description": (
            "Aggregate and deduplicate fresh remote jobs from four public "
            "feeds for n8n alerts, job boards, and hiring research."
        ),
        "eyebrow": "Hiring data / four public feeds",
        "signal": "$0.001",
        "signal_unit": "per returned job",
        "source": "Arbeitnow, Jobicy, Remote OK, and Himalayas",
        "delivery": "JSON / CSV / Excel / API",
        "price": "$0.001 per returned job + $0.00005 per start",
        "actor_url": "https://apify.com/ai-coding-radar/remote-job-intelligence",
        "example_url": (
            "https://apify.com/ai-coding-radar/remote-job-intelligence/"
            "examples/daily-remote-ai-and-machine-learning-jobs"
        ),
        "example_label": "Open AI jobs example",
        "repository_url": (
            "https://github.com/Jarvis-Dong/remote-job-intelligence"
        ),
        "workflow_url": (
            "https://github.com/Jarvis-Dong/remote-job-intelligence/blob/main/"
            "examples/n8n-remote-jobs-webhook.json"
        ),
        "input": '''{
  "sources": ["arbeitnow", "jobicy", "remoteok", "himalayas"],
  "keywords": ["machine learning", "artificial intelligence", "llm"],
  "keywordMatchMode": "any",
  "maxAgeDays": 7,
  "limit": 50,
  "includeDescription": false
}''',
        "steps": (
            "Filter fresh listings by keyword, location, and age.",
            "Deduplicate each run while preserving source and application links.",
            "Send attributed records to n8n, Make, a job board, or a database.",
        ),
        "boundaries": (
            "No login, cookie, proxy, or CAPTCHA bypass.",
            "Does not submit applications or contact employers.",
            "Cross-day delivery deduplication belongs in the caller workflow.",
            "Descriptions are omitted by default because listing text is untrusted.",
        ),
    },
    {
        "slug": "npm-pypi-vulnerability-api",
        "title": "npm and PyPI Vulnerability API",
        "description": (
            "Check exact npm and PyPI versions against registry metadata, "
            "OSV vulnerabilities, and CISA KEV with visible source status."
        ),
        "eyebrow": "Dependency security / exact versions",
        "signal": "$0.0015",
        "signal_unit": "per package record",
        "source": "npm, PyPI, OSV, and CISA KEV",
        "delivery": "JSON / CSV / Excel / n8n",
        "price": "$0.0015 per package record + $0.00005 per start",
        "actor_url": (
            "https://apify.com/ai-coding-radar/oss-package-health-monitor"
        ),
        "example_url": (
            "https://apify.com/ai-coding-radar/oss-package-health-monitor/"
            "examples/scan-installed-npm-and-pypi-versions-for-cves"
        ),
        "example_label": "Open exact-version scan",
        "repository_url": (
            "https://github.com/Jarvis-Dong/oss-package-health-monitor"
        ),
        "workflow_url": (
            "https://github.com/Jarvis-Dong/oss-package-health-monitor/blob/main/"
            "examples/n8n-oss-exact-version-scan.json"
        ),
        "input": '''{
  "packages": [
    {"name": "lodash", "ecosystem": "npm", "version": "4.17.20"},
    {"name": "requests", "ecosystem": "PyPI", "version": "2.31.0"}
  ],
  "includeVulnerabilities": true,
  "includeCisaKev": true
}''',
        "steps": (
            "Resolve the exact requested version against its public registry.",
            "Query OSV and match returned CVEs against the CISA KEV catalog.",
            "Keep partial and failed source states visible to downstream alerts.",
        ),
        "boundaries": (
            "No private package, registry login, or repository credential access.",
            "A source error is not converted into a clean vulnerability result.",
            "Does not update dependencies or certify that a package is safe.",
            "Use installed lockfile versions, not a floating latest tag.",
        ),
    },
    {
        "slug": "markdown-code-to-image-api",
        "title": "Markdown and Code to PNG API",
        "description": (
            "Render Markdown, code, tables, and AI answers into downloadable "
            "PNG files for n8n, Make, newsletters, and documentation."
        ),
        "eyebrow": "Content automation / deterministic PNG",
        "signal": "$0.005",
        "signal_unit": "per generated image",
        "source": "Structured Markdown supplied by the caller",
        "delivery": "PNG / API / n8n / Make",
        "price": "$0.005 per generated image + $0.00005 per start",
        "actor_url": (
            "https://apify.com/ai-coding-radar/markdown-code-to-image"
        ),
        "example_url": (
            "https://apify.com/ai-coding-radar/markdown-code-to-image/"
            "examples/chatgpt-markdown-answer-to-png"
        ),
        "example_label": "Open AI answer example",
        "repository_url": (
            "https://github.com/Jarvis-Dong/markdown-code-to-image"
        ),
        "workflow_url": (
            "https://github.com/Jarvis-Dong/markdown-code-to-image/blob/main/"
            "examples/n8n-markdown-code-to-image.json"
        ),
        "preview_url": (
            "https://raw.githubusercontent.com/Jarvis-Dong/"
            "markdown-code-to-image/main/docs/"
            "markdown-code-to-image-preview.png"
        ),
        "input": '''{
  "documents": [{
    "title": "Release note",
    "markdown": "# Shipped\\n\\nThe useful change is live."
  }],
  "theme": "paper",
  "width": 1080,
  "fontSize": 22,
  "watermark": ""
}''',
        "steps": (
            "Send one to twenty bounded Markdown documents in one request.",
            "Render with paper, midnight, terminal, or clean presentation.",
            "Pass runtime PNG URLs to storage, email, a CMS, or another workflow.",
        ),
        "boundaries": (
            "Does not automate ChatGPT or screenshot an authenticated browser.",
            "Raw HTML is disabled and remote image requests are blocked.",
            "Runtime download URLs should not be hard-coded or republished.",
            "Output is PNG only and each image has a bounded height.",
        ),
    },
    {
        "slug": "uk-company-change-api",
        "title": "UK Companies House Change API",
        "description": (
            "Monitor selected Companies House records for observed status, "
            "filing, address, SIC, accounts, mortgage, and name changes."
        ),
        "eyebrow": "Company monitoring / official register",
        "signal": "$0.003",
        "signal_unit": "per company check",
        "source": "Official Companies House URI JSON",
        "delivery": "Change rows / API / n8n / Make",
        "price": "$0.003 per check + $0.01 per changed field + $0.00005 per start",
        "actor_url": (
            "https://apify.com/ai-coding-radar/uk-company-change-alerts"
        ),
        "example_url": (
            "https://apify.com/ai-coding-radar/uk-company-change-alerts/"
            "examples/daily-uk-supplier-status-alerts"
        ),
        "example_label": "Open supplier alert example",
        "repository_url": (
            "https://github.com/Jarvis-Dong/uk-company-change-alerts"
        ),
        "workflow_url": (
            "https://github.com/Jarvis-Dong/uk-company-change-alerts/blob/main/"
            "examples/n8n-uk-company-alerts.json"
        ),
        "input": '''{
  "companyNumbers": ["02050399"],
  "monitorId": "supplier-watchlist",
  "emitUnchanged": false
}''',
        "steps": (
            "Read current public company-level facts for an explicit watchlist.",
            "Store one named baseline and compare watched fields on later runs.",
            "Emit observed changes and source failures for downstream review.",
        ),
        "boundaries": (
            "No officer or PSC profiles, birthdays, or private databases.",
            "Does not predict insolvency or provide a credit or legal decision.",
            "A first baseline is setup evidence, not a warning.",
            "Source failures are visible and are not billed as successful checks.",
        ),
    },
    {
        "slug": "grants-gov-alerts-api",
        "title": "Grants.gov Opportunity Alerts API",
        "description": (
            "Track new and changed federal grant opportunities from the "
            "official Grants.gov search API with stable monitor baselines."
        ),
        "eyebrow": "Federal grants / official search API",
        "signal": "$0.0075",
        "signal_unit": "per new opportunity",
        "source": "Official Grants.gov search2 endpoint",
        "delivery": "New and changed rows / API / n8n",
        "price": "$0.0075 per new grant + $0.015 per change + $0.00005 per start",
        "actor_url": (
            "https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor"
        ),
        "example_url": (
            "https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor/"
            "examples/daily-small-business-federal-grant-alerts"
        ),
        "example_label": "Open small-business example",
        "repository_url": (
            "https://github.com/Jarvis-Dong/grants-gov-opportunity-monitor"
        ),
        "workflow_url": (
            "https://github.com/Jarvis-Dong/grants-gov-opportunity-monitor/blob/"
            "main/examples/n8n-grants-gov-monitor.json"
        ),
        "input": '''{
  "keyword": "small business",
  "statuses": ["posted", "forecasted"],
  "eligibilityCodes": ["23"],
  "limit": 10,
  "monitorId": "small-business-grants"
}''',
        "steps": (
            "Search a bounded official query by keyword, status, and eligibility.",
            "Store one stable baseline for that exact filter set.",
            "Emit only newly observed or changed opportunity summaries.",
        ),
        "boundaries": (
            "Does not decide eligibility, rank applicants, or predict an award.",
            "Does not submit applications or download attachments and contacts.",
            "Leaving a limited result window is not called a closed grant.",
            "Always verify the current notice with Grants.gov and the agency.",
        ),
    },
)
AUTOMATION_BY_SLUG = {item["slug"]: item for item in AUTOMATIONS}
AUTOMATION_LASTMOD = "2026-08-15"

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

.brand { font-weight: 800; text-decoration: none; }

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

.internal-link { text-decoration-thickness: 3px; text-underline-offset: 5px; }

.breadcrumb {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 58px 0 24px;
  font-family: Menlo, Monaco, monospace;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.breadcrumb span { color: var(--signal); }

.detail-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(260px, .65fr);
  border: var(--line);
  background: var(--white);
  box-shadow: 10px 10px 0 var(--ink);
}

.detail-copy { padding: clamp(28px, 6vw, 64px); }

.detail-title {
  max-width: 800px;
  margin: 14px 0 18px;
  font-family: "Bodoni 72", Georgia, serif;
  font-size: clamp(50px, 8vw, 104px);
  letter-spacing: -.06em;
  line-height: .82;
}

.detail-copy p {
  max-width: 670px;
  margin: 0;
  color: var(--muted);
  font-size: 17px;
  line-height: 1.7;
}

.detail-signal {
  display: grid;
  place-items: center;
  min-height: 360px;
  padding: 30px;
  border-left: var(--line);
  background: var(--acid);
  font-family: "Bodoni 72", Georgia, serif;
  font-size: clamp(48px, 8vw, 90px);
  font-weight: 900;
  letter-spacing: -.07em;
  line-height: .85;
  text-align: center;
  text-decoration: none;
}

.facts {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin: 54px 0;
  border-top: var(--line);
  border-left: var(--line);
}

.fact {
  min-height: 122px;
  padding: 20px;
  border-right: var(--line);
  border-bottom: var(--line);
  background: rgba(255, 253, 247, .78);
}

.fact span {
  display: block;
  margin-bottom: 14px;
  color: var(--signal);
  font-family: Menlo, Monaco, monospace;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.fact strong { font-size: clamp(20px, 3vw, 32px); }

.history {
  margin: 22px 0 70px;
  border-top: var(--line);
  border-left: var(--line);
}

.history-row {
  display: grid;
  grid-template-columns: minmax(150px, .5fr) minmax(220px, 1fr) auto;
  gap: 20px;
  align-items: center;
  min-height: 82px;
  padding: 18px 20px;
  border-right: var(--line);
  border-bottom: var(--line);
  background: var(--white);
}

.history-version {
  font-family: "Bodoni 72", Georgia, serif;
  font-size: 34px;
  font-weight: 900;
}

.history time,
.history-channel {
  color: var(--muted);
  font-family: Menlo, Monaco, monospace;
  font-size: 11px;
  text-transform: uppercase;
}

.toolbox { margin: 72px 0; }

.toolbox-copy {
  max-width: 760px;
  margin: 20px 0 28px;
  color: var(--muted);
  font-size: 17px;
  line-height: 1.65;
}

.tool-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.tool-card {
  display: flex;
  min-height: 310px;
  flex-direction: column;
  justify-content: space-between;
  gap: 32px;
  padding: 28px;
  border: var(--line);
  background: var(--white);
  box-shadow: 7px 7px 0 var(--ink);
}

.tool-card:nth-child(2) { background: var(--acid); }

.tool-tag {
  color: var(--signal);
  font-family: Menlo, Monaco, monospace;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.tool-card h3 {
  margin: 16px 0 12px;
  font-family: "Songti SC", Georgia, serif;
  font-size: clamp(28px, 3vw, 40px);
  line-height: 1.08;
}

.tool-card p {
  margin: 0;
  color: var(--muted);
  font-size: 15px;
  line-height: 1.6;
}

.tool-link {
  align-self: flex-start;
  padding-bottom: 4px;
  border-bottom: 3px solid var(--ink);
  font-family: Menlo, Monaco, monospace;
  font-size: 11px;
  font-weight: 800;
  text-decoration: none;
  text-transform: uppercase;
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
  .tool-grid { grid-template-columns: 1fr; }
  .tool-card { min-height: 240px; }
  .protocol { grid-template-columns: 1fr; padding: 26px 22px; }
  .detail-hero { grid-template-columns: 1fr; box-shadow: 6px 6px 0 var(--ink); }
  .detail-signal { min-height: 180px; border-top: var(--line); border-left: 0; }
  .facts { grid-template-columns: 1fr; }
  .history-row { grid-template-columns: 1fr; gap: 8px; }
}

@media (prefers-reduced-motion: reduce) {
  .release { animation: none; }
}
"""

AUTOMATION_STYLE = """
.price-signal { align-content: center; }

.price-signal strong { display: block; }

.price-signal span {
  display: block;
  margin-top: 18px;
  font-family: Menlo, Monaco, monospace;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
  line-height: 1.45;
  text-transform: uppercase;
}

.automation-layout {
  display: grid;
  grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
  margin: 54px 0;
  border-top: var(--line);
  border-left: var(--line);
}

.automation-panel {
  min-width: 0;
  padding: clamp(26px, 5vw, 48px);
  border-right: var(--line);
  border-bottom: var(--line);
  background: var(--white);
}

.automation-panel:nth-child(2) { background: var(--acid); }

.automation-panel h2 {
  margin-bottom: 24px;
  font-size: clamp(38px, 5vw, 62px);
}

.automation-steps {
  margin: 0;
  padding-left: 24px;
  color: var(--muted);
  font-size: 16px;
  line-height: 1.7;
}

.automation-steps li + li { margin-top: 14px; }

.code-sample {
  overflow-x: auto;
  margin: 0;
  padding: 24px;
  border: var(--line);
  background: var(--ink);
  color: var(--white);
  font-family: Menlo, Monaco, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.65;
  box-shadow: 6px 6px 0 var(--signal);
}

.automation-preview {
  margin: 0 0 54px;
  border: var(--line);
  background: var(--white);
  box-shadow: 8px 8px 0 var(--ink);
}

.automation-preview img {
  display: block;
  width: 100%;
  height: auto;
}

.automation-preview figcaption {
  padding: 14px 18px;
  border-top: var(--line);
  font-family: Menlo, Monaco, monospace;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .04em;
  line-height: 1.5;
  text-transform: uppercase;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  align-items: center;
  margin: 0 0 72px;
}

.secondary-action {
  padding: 10px 14px;
  border: var(--line);
  background: var(--white);
  font-family: Menlo, Monaco, monospace;
  font-size: 12px;
  font-weight: 800;
  text-decoration: none;
  text-transform: uppercase;
}

@media (max-width: 760px) {
  .automation-layout { grid-template-columns: 1fr; }
  .automation-panel { padding: 28px 22px; }
  .action-row { align-items: stretch; flex-direction: column; }
  .action-row a { text-align: center; }
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


def parse_stable_releases(feed_bytes, source):
    try:
        root = ET.fromstring(feed_bytes)
    except ET.ParseError as exc:
        raise ValueError("invalid Atom feed") from exc

    if root.tag != f"{ATOM}feed":
        raise ValueError("document is not an Atom feed")
    entries = root.findall(f"{ATOM}entry")
    if not entries:
        raise ValueError("Atom feed contains no release entries")

    releases = []
    entry_ids = set()
    for entry in entries:
        title = (entry.findtext(f"{ATOM}title") or "").strip()
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
        if not title or not entry_id or not updated or not link:
            raise ValueError("release is missing title, id, time, or source link")
        if not link.startswith(source["tag_url_prefix"]):
            raise ValueError("release link is outside the source allowlist")

        version = link.removeprefix(source["tag_url_prefix"])
        if not TAG_VERSION.fullmatch(version):
            raise ValueError("release tag has unsupported characters")
        expected_titles = {
            f"{prefix}{version}" for prefix in source["title_prefixes"]
        }
        if title not in expected_titles:
            raise ValueError("release title does not match the official tag")
        is_prerelease = bool(PRERELEASE.search(version))
        if not is_prerelease and not STABLE_VERSION.fullmatch(version):
            raise ValueError("stable release has an unsupported version format")
        if entry_id in entry_ids:
            raise ValueError("duplicate release id in Atom feed")
        entry_ids.add(entry_id)
        published = parse_source_timestamp(updated)
        if is_prerelease:
            continue
        releases.append(
            (
                published,
                {
                    "id": entry_id,
                    "source_key": source["key"],
                    "product": source["product"],
                    "version": version,
                    "source_published_at": updated,
                    "source_url": link,
                },
            )
        )

    releases.sort(key=lambda item: item[0], reverse=True)
    return [release for _, release in releases]


def parse_latest_stable(feed_bytes, source=None):
    releases = parse_stable_releases(feed_bytes, source or SOURCES[0])
    if not releases:
        raise ValueError("no stable release found")
    return releases[0]


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


def post_path_for(record):
    date = record["source_published_at"][:10]
    return f'output/posts/{date}-{record["source_key"]}-{record["version"]}.md'


def release_page_path(record):
    return f'output/releases/{record["source_key"]}/{record["version"]}/index.html'


def release_page_url(record):
    return f'{SITE_URL}releases/{record["source_key"]}/{record["version"]}/'


def source_page_path(source_key):
    return f"output/tools/{source_key}/index.html"


def source_page_url(source_key):
    return f"{SITE_URL}tools/{source_key}/"


def automation_page_path(automation):
    return f'output/automations/{automation["slug"]}/index.html'


def automation_page_url(automation):
    return f'{SITE_URL}automations/{automation["slug"]}/'


def source_for_record(record):
    source_key = record.get("source_key")
    if source_key:
        source = SOURCE_BY_KEY.get(source_key)
        if not source:
            raise ValueError("state record has an unknown source")
        return source

    source_url = record.get("source_url", "")
    source = next(
        (
            candidate
            for candidate in SOURCES
            if source_url.startswith(candidate["tag_url_prefix"])
        ),
        None,
    )
    if not source:
        raise ValueError("state record is outside the source allowlist")
    return source


def normalize_state(state):
    changed = False
    for state_id, record in state["seen"].items():
        if not isinstance(record, dict) or record.get("id") != state_id:
            raise ValueError("state record has an invalid identity")

        source = source_for_record(record)
        required = (
            "version",
            "source_published_at",
            "source_url",
            "detected_at",
        )
        if any(not isinstance(record.get(field), str) for field in required):
            raise ValueError("state record is missing required fields")
        if not STABLE_VERSION.fullmatch(record["version"]):
            raise ValueError("state record has an unsupported version")
        if record["source_url"] != f'{source["tag_url_prefix"]}{record["version"]}':
            raise ValueError("state record does not match its official source")
        parse_source_timestamp(record["source_published_at"])
        parse_source_timestamp(record["detected_at"])

        canonical = {
            "source_key": source["key"],
            "product": source["product"],
            "title": f'{source["product"]} {record["version"]} released',
            "post": post_path_for({**record, "source_key": source["key"]}),
        }
        for field, value in canonical.items():
            if record.get(field) != value:
                record[field] = value
                changed = True
    return changed


def render_post(record):
    title = record["title"]
    return f'''---
title: "{title}"
product: "{record['product']}"
source_url: "{record['source_url']}"
source_published_at: "{record['source_published_at']}"
detected_at: "{record['detected_at']}"
release_channel: "stable"
automated: true
ai_generated: false
---

# {title}

{record['product']} published stable release `{record['version']}`.

- Official timestamp: `{record['source_published_at']}`
- Release channel: stable
- Official notes: [{record['source_url']}]({record['source_url']})

> Generated automatically from the official release feed. This record contains no synthetic benchmark, hands-on claim, or unsupported conclusion.
'''


def render_rss(records):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "AI Coding Release Radar"
    ET.SubElement(channel, "link").text = SITE_URL
    ET.SubElement(channel, "description").text = (
        "Verified stable releases from official AI coding tool feeds"
    )
    ET.SubElement(channel, "language").text = "en-us"

    for record in sorted(
        records,
        key=lambda item: parse_source_timestamp(item["source_published_at"]),
        reverse=True,
    )[:RSS_LIMIT]:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = record["title"]
        page_url = release_page_url(record)
        ET.SubElement(item, "link").text = page_url
        guid = ET.SubElement(item, "guid", isPermaLink="true")
        guid.text = page_url
        published = parse_source_timestamp(record["source_published_at"])
        ET.SubElement(item, "pubDate").text = format_datetime(published)
        ET.SubElement(item, "description").text = (
            f'Verified from the official {record["product"]} release feed. '
            f'Official notes: {record["source_url"]}'
        )

    body = ET.tostring(rss, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def render_index(records):
    ordered = sorted(
        records,
        key=lambda item: parse_source_timestamp(item["source_published_at"]),
        reverse=True,
    )
    source_count = len({record["source_key"] for record in ordered})
    latest_by_source = {}
    for record in ordered:
        latest_by_source.setdefault(record["source_key"], record)
    latest_summary = ", ".join(
        f'{source["product"]} {latest_by_source[source["key"]]["version"]}'
        for source in SOURCES
        if source["key"] in latest_by_source
    )
    page_title = "Claude Code, Codex & Gemini CLI Release Tracker"
    page_description = (
        f"Latest verified stable releases: {latest_summary}. "
        "Automatically checked from official GitHub feeds."
        if latest_summary
        else "Verified stable releases from official Claude Code, Codex, and Gemini CLI feeds."
    )
    cards = []
    for record in ordered[:INDEX_LIMIT]:
        product = escape(record["product"])
        version = escape(record["version"])
        source_url = escape(record["source_url"], quote=True)
        published_at = escape(record["source_published_at"], quote=True)
        page_url = escape(release_page_url(record), quote=True)
        product_url = escape(source_page_url(record["source_key"]), quote=True)
        published_date = parse_source_timestamp(
            record["source_published_at"]
        ).strftime("%Y.%m.%d")
        cards.append(
            f'''<article class="release" aria-label="{product} {version} stable release">
        <div class="release-version" aria-label="{product} version {version}">{version}</div>
        <div class="release-body">
          <div>
            <div class="release-meta"><a class="internal-link" href="{product_url}">{product}</a> / stable / {published_date}</div>
            <h3><a class="internal-link" href="{page_url}">{product} {version} is out</a></h3>
            <p>Detected automatically from the official release feed. No synthetic benchmark, hands-on claim, or unsupported conclusion is added.</p>
          </div>
          <div class="release-foot">
            <time datetime="{published_at}">{published_at}</time>
            <a class="source-link" href="{page_url}">Verified release record →</a>
          </div>
        </div>
      </article>'''
        )

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(page_description, quote=True)}">
  <meta name="theme-color" content="#161713">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{escape(page_title, quote=True)}">
  <meta property="og:description" content="{escape(page_description, quote=True)}">
  <meta property="og:url" content="{SITE_URL}">
  <meta name="twitter:card" content="summary">
  <meta name="google-site-verification" content="eF8UPNP73pZWcNA8MbjSH1hxhlstnVC-o7ESFCLKu30">
  <link rel="canonical" href="{SITE_URL}">
  <link rel="alternate" type="application/rss+xml" title="AI Coding Release Radar RSS" href="feed.xml">
  <title>{escape(page_title)}</title>
  <style>{INDEX_STYLE}</style>
  <style>
    @media (min-width: 761px) {{ .tool-grid-five {{ grid-template-columns: repeat(3, 1fr); }} }}
    .tool-grid-five .tool-card:nth-child(even) {{ background: var(--acid); }}
  </style>
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
          <p class="eyebrow">Official feeds / stable only</p>
          <h1 id="page-title"><span>AI Coding</span><br>Releases</h1>
        </div>
        <p class="lede">Latest verified: {escape(latest_summary or "Codex, Claude Code, and Gemini CLI")}. Updated from official GitHub feeds. <a class="internal-link" href="#toolbox-title">Explore developer automation →</a></p>
      </section>

      <section class="metrics" aria-label="Radar metrics">
        <div class="metric"><strong>{len(ordered)}</strong><span class="metric-label">stable releases tracked</span></div>
        <div class="metric"><strong>0</strong><span class="metric-label">unsupported claims</span></div>
        <div class="metric"><strong>{source_count}</strong><span class="metric-label">official sources allowlisted</span></div>
      </section>

      <section aria-labelledby="signals-title">
        <div class="section-head">
          <h2 id="signals-title">Stable releases</h2>
          <a class="rss" href="feed.xml">RSS / XML</a>
        </div>
        <div class="release-list">{''.join(cards)}</div>
      </section>

      <section class="toolbox" aria-labelledby="toolbox-title">
        <p class="eyebrow">Community-built / optional</p>
        <h2 id="toolbox-title">Developer automation</h2>
        <p class="toolbox-copy">Small paid APIs maintained by this publisher. Each linked guide documents its source, input, current event price, and limits. They are separate from the verified release index and never influence its source records.</p>
        <div class="tool-grid tool-grid-five">
          <article class="tool-card">
            <div>
              <div class="tool-tag">Federal grants / public example</div>
              <h3><a class="internal-link" href="{automation_page_url(AUTOMATION_BY_SLUG["grants-gov-alerts-api"])}">Monitor Grants.gov opportunities</a></h3>
              <p>Track new and changed federal grant opportunities from the official Grants.gov search API.</p>
            </div>
            <a class="tool-link" href="https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor/examples/daily-ai-federal-grant-opportunity-alerts" target="_blank" rel="noopener noreferrer">Try grant alerts →</a>
          </article>
          <article class="tool-card">
            <div>
              <div class="tool-tag">Dependency security / public example</div>
              <h3><a class="internal-link" href="{automation_page_url(AUTOMATION_BY_SLUG["npm-pypi-vulnerability-api"])}">Check exact npm and PyPI versions</a></h3>
              <p>Collect registry metadata, OSV vulnerabilities, and CISA KEV matches with visible source status.</p>
            </div>
            <a class="tool-link" href="https://apify.com/ai-coding-radar/oss-package-health-monitor/examples/scan-installed-npm-and-pypi-versions-for-cves" target="_blank" rel="noopener noreferrer">Try CVE scan →</a>
          </article>
          <article class="tool-card">
            <div>
              <div class="tool-tag">Content automation / public example</div>
              <h3><a class="internal-link" href="{automation_page_url(AUTOMATION_BY_SLUG["markdown-code-to-image-api"])}">Render Markdown and code to PNG</a></h3>
              <p>Generate image cards through an API for n8n, Make, schedules, and batch workflows.</p>
            </div>
            <a class="tool-link" href="https://apify.com/ai-coding-radar/markdown-code-to-image/examples/render-markdown-and-code-to-a-png" target="_blank" rel="noopener noreferrer">Try PNG render →</a>
          </article>
          <article class="tool-card">
            <div>
              <div class="tool-tag">Hiring data / public example</div>
              <h3><a class="internal-link" href="{automation_page_url(AUTOMATION_BY_SLUG["remote-jobs-api"])}">Aggregate fresh remote software jobs</a></h3>
              <p>Deduplicate four public feeds into attributed records for alerts, job boards, and research.</p>
            </div>
            <a class="tool-link" href="https://apify.com/ai-coding-radar/remote-job-intelligence/examples/daily-remote-software-jobs" target="_blank" rel="noopener noreferrer">Try remote jobs →</a>
          </article>
          <article class="tool-card">
            <div>
              <div class="tool-tag">Company monitoring / public example</div>
              <h3><a class="internal-link" href="{automation_page_url(AUTOMATION_BY_SLUG["uk-company-change-api"])}">Monitor UK supplier record changes</a></h3>
              <p>Compare official Companies House records over time and emit observed status, filing, address, SIC, accounts, or name changes.</p>
            </div>
            <a class="tool-link" href="https://apify.com/ai-coding-radar/uk-company-change-alerts/examples/daily-uk-supplier-status-alerts" target="_blank" rel="noopener noreferrer">Try supplier alerts →</a>
          </article>
        </div>
      </section>

      <section class="protocol" aria-labelledby="protocol-title">
        <h2 id="protocol-title">Source policy</h2>
        <ul>
          <li>Official GitHub release feeds only</li>
          <li>Stable numeric tags only</li>
          <li>Each release is recorded once</li>
          <li>Malformed sources stop the run</li>
          <li>No invented tests or performance claims</li>
        </ul>
      </section>
    </main>

    <footer class="footer">
      <span>AI Coding Release Radar / verified release index</span>
      <span>AI_SUMMARY: OFF · AUTOMATED: TRUE</span>
    </footer>
  </div>
</body>
</html>
'''


def render_robots():
    return f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n"


def render_page_head(title, description, canonical_url):
    return f'''<meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(description, quote=True)}">
  <meta name="theme-color" content="#161713">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{escape(title, quote=True)}">
  <meta property="og:description" content="{escape(description, quote=True)}">
  <meta property="og:url" content="{escape(canonical_url, quote=True)}">
  <meta name="twitter:card" content="summary">
  <link rel="canonical" href="{escape(canonical_url, quote=True)}">
  <link rel="alternate" type="application/rss+xml" title="AI Coding Release Radar RSS" href="{SITE_URL}feed.xml">
  <title>{escape(title)}</title>
  <style>{INDEX_STYLE}</style>'''


def render_release_page(record):
    product = escape(record["product"])
    version = escape(record["version"])
    published_at = escape(record["source_published_at"], quote=True)
    source_url = escape(record["source_url"], quote=True)
    page_url = release_page_url(record)
    tool_url = source_page_url(record["source_key"])
    title = f'{record["product"]} {record["version"]} stable release'
    description = (
        f'Verified release record for {record["product"]} {record["version"]}, '
        "including the official timestamp and source notes."
    )
    return f'''<!doctype html>
<html lang="en">
<head>
  {render_page_head(title, description, page_url)}
</head>
<body>
  <div class="shell">
    <header class="masthead">
      <a class="brand" href="{SITE_URL}">AUTO MEDIA <span>/ SIGNAL DESK</span></a>
      <div class="status">verified stable release</div>
    </header>
    <main>
      <nav class="breadcrumb" aria-label="Breadcrumb">
        <a href="{SITE_URL}">Release radar</a><span>/</span>
        <a href="{tool_url}">{product}</a><span>/</span>
        <span>{version}</span>
      </nav>
      <article class="detail-hero">
        <div class="detail-copy">
          <p class="eyebrow">Official source / stable channel</p>
          <h1 class="detail-title">{product}<br>{version}</h1>
          <p>This page records a stable release detected from the allowlisted official feed. It contains no synthetic benchmark, hands-on claim, or unsupported performance conclusion.</p>
        </div>
        <div class="detail-signal" aria-label="Version {version}">{version}</div>
      </article>
      <section class="facts" aria-label="Release facts">
        <div class="fact"><span>Product</span><strong>{product}</strong></div>
        <div class="fact"><span>Channel</span><strong>Stable</strong></div>
        <div class="fact"><span>Published</span><strong><time datetime="{published_at}">{published_at[:10]}</time></strong></div>
      </section>
      <section class="protocol" aria-labelledby="verification-title">
        <h2 id="verification-title">Verified at source</h2>
        <ul>
          <li>Exact official repository allowlist</li>
          <li>Numeric stable tag validated</li>
          <li>Original timestamp preserved</li>
          <li>No AI-generated summary</li>
          <li><a class="source-link" href="{source_url}" target="_blank" rel="noopener noreferrer">Read official release notes ↗</a></li>
        </ul>
      </section>
    </main>
    <footer class="footer"><span>AI Coding Release Radar / release record</span><span><a href="{tool_url}">All {product} releases →</a></span></footer>
  </div>
</body>
</html>
'''


def render_source_page(source, records):
    ordered = sorted(
        records,
        key=lambda item: parse_source_timestamp(item["source_published_at"]),
        reverse=True,
    )
    latest = ordered[0]
    product = escape(source["product"])
    page_url = source_page_url(source["key"])
    title = f'{source["product"]} stable release history'
    description = (
        f'Verified {source["product"]} stable release history, latest version, '
        "official timestamps, and source links."
    )
    rows = []
    for record in ordered:
        version = escape(record["version"])
        published_at = escape(record["source_published_at"], quote=True)
        rows.append(
            f'''<article class="history-row">
        <a class="history-version internal-link" href="{release_page_url(record)}">{version}</a>
        <time datetime="{published_at}">{published_at}</time>
        <span class="history-channel">stable / verified</span>
      </article>'''
        )
    return f'''<!doctype html>
<html lang="en">
<head>
  {render_page_head(title, description, page_url)}
</head>
<body>
  <div class="shell">
    <header class="masthead">
      <a class="brand" href="{SITE_URL}">AUTO MEDIA <span>/ SIGNAL DESK</span></a>
      <div class="status">release history online</div>
    </header>
    <main>
      <nav class="breadcrumb" aria-label="Breadcrumb"><a href="{SITE_URL}">Release radar</a><span>/</span><span>{product}</span></nav>
      <article class="detail-hero">
        <div class="detail-copy">
          <p class="eyebrow">Latest verified stable release</p>
          <h1 class="detail-title">{product}</h1>
          <p>An automatically maintained stable release history sourced only from the official GitHub release feed.</p>
        </div>
        <a class="detail-signal internal-link" href="{release_page_url(latest)}" aria-label="Latest version {escape(latest['version'])}">{escape(latest['version'])}</a>
      </article>
      <section class="facts" aria-label="Product release facts">
        <div class="fact"><span>Latest stable</span><strong>{escape(latest['version'])}</strong></div>
        <div class="fact"><span>Releases tracked</span><strong>{len(ordered)}</strong></div>
        <div class="fact"><span>Unsupported claims</span><strong>0</strong></div>
      </section>
      <section aria-labelledby="history-title">
        <div class="section-head"><h2 id="history-title">Release history</h2><a class="rss" href="{SITE_URL}feed.xml">RSS / XML</a></div>
        <div class="history">{''.join(rows)}</div>
      </section>
    </main>
    <footer class="footer"><span>{product} / verified release history</span><span>UPDATED AUTOMATICALLY</span></footer>
  </div>
</body>
</html>
'''


def render_automation_page(automation):
    title = automation["title"]
    description = automation["description"]
    page_url = automation_page_url(automation)
    steps = "".join(
        f"<li>{escape(step)}</li>" for step in automation["steps"]
    )
    boundaries = "".join(
        f"<li>{escape(boundary)}</li>"
        for boundary in automation["boundaries"]
    )
    preview = ""
    if preview_url := automation.get("preview_url"):
        preview = f'''      <figure class="automation-preview">
        <img src="{escape(preview_url, quote=True)}" alt="Example output from {escape(title, quote=True)}" width="1080" height="743" loading="lazy" decoding="async">
        <figcaption>Output from the same public renderer used by the API. <a href="{escape(automation['example_url'], quote=True)}" target="_blank" rel="noopener noreferrer">Try the public example</a>.</figcaption>
      </figure>
'''
    return f'''<!doctype html>
<html lang="en">
<head>
  {render_page_head(title, description, page_url)}
  <style>{AUTOMATION_STYLE}</style>
</head>
<body>
  <div class="shell">
    <header class="masthead">
      <a class="brand" href="{SITE_URL}">AUTO MEDIA <span>/ SIGNAL DESK</span></a>
      <div class="status">automation guide online</div>
    </header>
    <main>
      <nav class="breadcrumb" aria-label="Breadcrumb"><a href="{SITE_URL}">Release radar</a><span>/</span><span>Automation</span><span>/</span><span>{escape(title)}</span></nav>
      <article class="detail-hero">
        <div class="detail-copy">
          <p class="eyebrow">{escape(automation["eyebrow"])}</p>
          <h1 class="detail-title">{escape(title)}</h1>
          <p>{escape(description)} This page describes the public input, source boundary, and launch pricing before you run anything.</p>
        </div>
        <div class="detail-signal price-signal" aria-label="Launch price {escape(automation['signal'])} {escape(automation['signal_unit'])}">
          <div><strong>{escape(automation["signal"])}</strong><span>{escape(automation["signal_unit"])}<br>launch price</span></div>
        </div>
      </article>
      <section class="facts" aria-label="Automation facts">
        <div class="fact"><span>Current event price</span><strong>{escape(automation["price"])}</strong></div>
        <div class="fact"><span>Public source</span><strong>{escape(automation["source"])}</strong></div>
        <div class="fact"><span>Delivery</span><strong>{escape(automation["delivery"])}</strong></div>
      </section>
{preview}      <section class="automation-layout" aria-label="How the automation works">
        <article class="automation-panel">
          <p class="eyebrow">Three-step flow</p>
          <h2>How it works</h2>
          <ol class="automation-steps">{steps}</ol>
        </article>
        <article class="automation-panel">
          <p class="eyebrow">Copyable starting point</p>
          <h2>Example input</h2>
          <pre class="code-sample"><code>{escape(automation["input"])}</code></pre>
        </article>
      </section>
      <section class="protocol" aria-labelledby="boundary-title">
        <h2 id="boundary-title">Decision boundary</h2>
        <ul>{boundaries}<li>Check the current Store price in your own account before scheduling.</li></ul>
      </section>
      <div class="action-row" aria-label="Automation links">
        <a class="rss" href="{escape(automation['example_url'], quote=True)}" target="_blank" rel="noopener noreferrer">{escape(automation["example_label"])}</a>
        <a class="secondary-action" href="{escape(automation['actor_url'], quote=True)}" target="_blank" rel="noopener noreferrer">Actor and API docs</a>
        <a class="secondary-action" href="{escape(automation['workflow_url'], quote=True)}" target="_blank" rel="noopener noreferrer">Open n8n workflow</a>
      </div>
    </main>
    <footer class="footer">
      <span>AI Coding Radar / automation guide</span>
      <span><a href="{escape(automation['repository_url'], quote=True)}" target="_blank" rel="noopener noreferrer">Open source repository</a></span>
    </footer>
  </div>
</body>
</html>
'''


def render_sitemap(records):
    urlset = ET.Element(
        "urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
    )
    urls = [(SITE_URL, None)]
    source_keys = sorted({record["source_key"] for record in records})
    urls.extend((source_page_url(source_key), None) for source_key in source_keys)
    urls.extend(
        (automation_page_url(automation), AUTOMATION_LASTMOD)
        for automation in AUTOMATIONS
    )
    urls.extend(
        (release_page_url(record), record["source_published_at"][:10])
        for record in sorted(
            records,
            key=lambda item: parse_source_timestamp(item["source_published_at"]),
            reverse=True,
        )
    )
    for location, modified in urls:
        url = ET.SubElement(urlset, "url")
        ET.SubElement(url, "loc").text = location
        if modified:
            ET.SubElement(url, "lastmod").text = modified
    body = ET.tostring(urlset, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def process_feeds(feed_payloads, root_dir, now=None):
    releases = []
    source_keys = set()
    for source, feed_bytes in feed_payloads:
        if SOURCE_BY_KEY.get(source.get("key")) != source:
            raise ValueError("feed source is outside the source allowlist")
        if source["key"] in source_keys:
            raise ValueError("duplicate feed source")
        source_keys.add(source["key"])
        releases.extend(parse_stable_releases(feed_bytes, source))
    if not source_keys:
        raise ValueError("no feed sources supplied")

    root_dir = Path(root_dir)
    state_path = root_dir / "state" / "seen.json"
    state = load_state(state_path)
    state_changed = normalize_state(state)
    created_count = 0
    detected_at = (now or datetime.now(timezone.utc)).isoformat().replace(
        "+00:00", "Z"
    )
    for release in releases:
        existing = state["seen"].get(release["id"])
        if existing:
            if any(
                existing[field] != release[field]
                for field in ("source_key", "product", "version", "source_url")
            ):
                raise ValueError("release id conflicts with existing state")
            continue

        record = {
            **release,
            "title": f'{release["product"]} {release["version"]} released',
            "detected_at": detected_at,
            "post": post_path_for(release),
        }
        state["seen"][release["id"]] = record
        state_changed = True
        created_count += 1

    records = list(state["seen"].values())
    post_contents = {
        root_dir / record["post"]: render_post(record) for record in records
    }
    if len(post_contents) != len(records):
        raise ValueError("multiple releases resolve to the same post path")
    release_page_contents = {
        root_dir / release_page_path(record): render_release_page(record)
        for record in records
    }
    if len(release_page_contents) != len(records):
        raise ValueError("multiple releases resolve to the same public page")
    source_page_contents = {
        root_dir / source_page_path(source["key"]): render_source_page(
            source,
            [record for record in records if record["source_key"] == source["key"]],
        )
        for source in SOURCES
        if any(record["source_key"] == source["key"] for record in records)
    }
    automation_page_contents = {
        root_dir / automation_page_path(automation): render_automation_page(
            automation
        )
        for automation in AUTOMATIONS
    }
    rss_content = render_rss(records)
    index_content = render_index(records)
    state_content = json.dumps(state, ensure_ascii=False, indent=2) + "\n"

    for post_path, post_content in post_contents.items():
        atomic_write(post_path, post_content)
    for page_path, page_content in release_page_contents.items():
        atomic_write(page_path, page_content)
    for page_path, page_content in source_page_contents.items():
        atomic_write(page_path, page_content)
    for page_path, page_content in automation_page_contents.items():
        atomic_write(page_path, page_content)
    if state_changed:
        atomic_write(state_path, state_content)
    atomic_write(root_dir / "output" / "feed.xml", rss_content)
    atomic_write(root_dir / "output" / "index.html", index_content)
    atomic_write(root_dir / "output" / "robots.txt", render_robots())
    atomic_write(root_dir / "output" / "sitemap.xml", render_sitemap(records))
    atomic_write(
        root_dir / "output" / f"{INDEXNOW_KEY}.txt", INDEXNOW_KEY + "\n"
    )
    return created_count


def process_feed(feed_bytes, root_dir, now=None):
    return process_feeds(((SOURCES[0], feed_bytes),), root_dir, now) > 0


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
    parser.add_argument(
        "--feed-url",
        default=DEFAULT_FEED_URL,
        help="override the Codex feed URL; other allowlisted feeds stay enabled",
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args(argv)

    try:
        feed_payloads = [
            (
                source,
                fetch_feed(
                    args.feed_url
                    if source["key"] == "codex"
                    else source["feed_url"]
                ),
            )
            for source in SOURCES
        ]
        created = process_feeds(feed_payloads, args.root)
        if created:
            suffix = "post" if created == 1 else "posts"
            message = f"created {created} stable release {suffix}"
        else:
            message = "no new stable releases"
        append_log(args.root, "ok", message)
        print(message)
        return 0
    except (OSError, ValueError) as exc:
        append_log(args.root, "error", str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
