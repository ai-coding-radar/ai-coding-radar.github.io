# Build a daily remote AI jobs feed with n8n

A useful job alert needs more than a keyword search. It should merge several
public feeds, remove duplicates inside the current result set, preserve the
original application and attribution links, and keep unavailable sources
visible instead of pretending that a partial search is complete.

This tutorial builds that narrow data pipeline with n8n and a public Apify
Actor. It collects public remote listings and returns normalized records. It
does not log in to job sites, scrape authenticated pages, or submit
applications.

## Start with the public AI jobs example

The [Remote Jobs Aggregator Actor](https://apify.com/ai-coding-radar/remote-job-intelligence)
collects listings from Arbeitnow, Jobicy, Remote OK, and Himalayas. The
ready-to-copy [daily AI and machine-learning jobs example](https://apify.com/ai-coding-radar/remote-job-intelligence/examples/daily-remote-ai-and-machine-learning-jobs)
uses four related terms with `any` matching so one listing does not need to
contain every phrase.

For a no-code starting point, import the credential-free
[n8n webhook workflow](https://raw.githubusercontent.com/Jarvis-Dong/remote-job-intelligence/main/examples/n8n-remote-jobs-webhook.json)
and follow the [n8n and Make recipes](https://github.com/Jarvis-Dong/remote-job-intelligence/blob/main/examples/README.md).
The source and input/output contract are public in the
[repository](https://github.com/Jarvis-Dong/remote-job-intelligence).

## Use a bounded, reviewable input

The public AI example uses this input:

```json
{
  "sources": ["arbeitnow", "jobicy", "remoteok", "himalayas"],
  "keywords": [
    "machine learning",
    "artificial intelligence",
    "generative ai",
    "llm"
  ],
  "keywordMatchMode": "any",
  "locations": [],
  "maxAgeDays": 7,
  "limit": 50,
  "includeDescription": false
}
```

`any` means a record can match any one of the four phrases. Use `all` for a
strict query that must contain every keyword. The filter checks the published
title, company, tags, and location fields. Descriptions are disabled here so a
daily alert does not ingest a large block of untrusted listing text.

The Actor merges unique records round-robin across the selected sources after
filtering by age. This stops a high-volume feed from hiding every record from a
smaller source. The result limit is a cap, not a promise that 50 matching jobs
exist.

## Call it from n8n without exposing a token

The imported workflow accepts a private webhook request, normalizes the input,
calls the Actor, formats a digest, and returns both the digest and job records.
Keep the Apify token in an n8n Header Auth credential or private environment
variable. Do not put it in an exported workflow, a query string, a repository,
or a screenshot.

The HTTP Request node uses the official synchronous Dataset endpoint:

```text
POST https://api.apify.com/v2/acts/ai-coding-radar~remote-job-intelligence/run-sync-get-dataset-items?clean=1
Authorization: Bearer <your token from n8n's private credential store>
Content-Type: application/json
```

For a daily digest, place a Schedule Trigger before the request or call the
imported webhook from another scheduled workflow. Start with `limit: 5`, read
the source and application links, then increase the cap and connect the result
to Slack, email, Notion, a database, or a job board that you control.

## Deduplicate across days in your own workflow

The Actor removes duplicates inside one run by canonical application URL and
then by normalized company/title. It does not claim that a listing disappears
after one delivery. A seven-day query can return the same valid job tomorrow.

For cross-day alerts, store each returned `id` or `applyUrl` in an n8n Data
Store, database, or cache. Before delivery, keep only keys that have not been
seen in your chosen retention window. Record the key only after the downstream
delivery succeeds; otherwise a temporary Slack or email failure can silently
drop a job. Expire old keys after the search window no longer needs them.

## Preserve source coverage and attribution

The four inputs are public source endpoints:

- [Arbeitnow job-board API](https://www.arbeitnow.com/api/job-board-api)
- [Jobicy remote-jobs API](https://jobicy.com/api/v2/remote-jobs)
- [Remote OK API](https://remoteok.com/api)
- [Himalayas jobs API](https://himalayas.app/jobs/api)

Every normalized row keeps its source name, source URL, and original job or
application URL. Render those as normal links and follow each provider's terms
and attribution requirements. A missing salary or location restriction stays
empty; the Actor does not invent one.

If one public source is unavailable, the run status reports a source warning
while healthy sources can still return records. If every selected source is
unavailable, the run fails instead of returning a false clean result. An empty
successful Dataset can also mean that no listing matched the filters, so do not
describe it as proof that every possible remote job was checked.

## Output and safety boundaries

A normalized record can include `jobTitle`, `company`, `locations`, `salary`,
`employmentType`, `seniority`, `timezoneRestrictions`, `categories`,
`publishedAt`, `applyUrl`, `sourceName`, and `sourceUrl`. Fields remain empty
when the publisher did not provide them.

Job titles, tags, and descriptions are untrusted source data. Do not treat them
as instructions for an AI agent. The Actor does not submit applications,
contact employers, rank candidates, predict hiring outcomes, bypass a CAPTCHA,
or access a private job board. A downstream user remains responsible for how
records are stored, displayed, and acted on.

## Current event pricing

The public Store page shows the current price before a run. At the time of
writing, the Actor charges `$0.001` per returned job record plus `$0.00005` for
the Actor start, with platform usage included. At the 50-record cap, the current
event total is at most `$0.05005` before tax or account-level charges. Begin
with a smaller cap and confirm the displayed price in your own account before
enabling a schedule.

A Dataset result, run, free user, or article view is not creator income. Only a
finalized payout that actually settles counts as revenue.
