# Build a fact-only Grants.gov opportunity monitor in n8n

Grant searches are useful only when the search result and its limitations stay
visible. This workflow watches a focused Grants.gov query and emits an
opportunity the first time it is seen, then emits it again only when a watched
summary field changes. It is a small change feed for an n8n, Make, or scheduled
script workflow; it is not an application service or a grant-writing tool.

## Start with the public Actor and example

The tested [Grants.gov Opportunity Monitor Actor](https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor)
uses the official [Grants.gov API Guide](https://www.grants.gov/api/api-guide)
and needs no Grants.gov login, API key, cookie, proxy, or browser automation.
The ready-to-copy [Daily AI Federal Grant Opportunity Alerts example](https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor/examples/daily-ai-federal-grant-opportunity-alerts)
shows a narrow query that can be scheduled after you inspect one result.
Running the Actor requires an Apify account, and the Store shows the current
price before you choose whether to run it.
For a no-code starting point, import the credential-free
[n8n workflow](https://raw.githubusercontent.com/Jarvis-Dong/grants-gov-opportunity-monitor/main/examples/n8n-grants-gov-monitor.json)
and follow its [n8n and Make setup recipe](https://github.com/Jarvis-Dong/grants-gov-opportunity-monitor/blob/main/examples/README.md).

The source code and input/output contract are public in the
[Grants.gov monitor repository](https://github.com/Jarvis-Dong/grants-gov-opportunity-monitor).
The Actor calls only the official unrestricted
[`search2` endpoint](https://api.grants.gov/v1/api/search2). It does not call
the detail or attachment endpoints, so it does not download long descriptions,
contact records, or application files that are not needed for a change alert.

## Configure one stable monitor

Create an n8n HTTP Request node (or use the public example) with the following
JSON input. Keep one `monitorId` for one exact set of filters; use another ID
when the query changes so unrelated searches cannot share a baseline.

```json
{
  "keyword": "artificial intelligence",
  "statuses": ["posted", "forecasted"],
  "agencyCodes": [],
  "eligibilityCodes": [],
  "fundingCategoryCodes": [],
  "limit": 10,
  "monitorId": "n8n-ai-grants"
}
```

Send it to the official Apify synchronous dataset endpoint:

```text
POST https://api.apify.com/v2/actors/ai-coding-radar~grants-gov-opportunity-monitor/run-sync-get-dataset-items?clean=1
Authorization: Bearer <your Apify token from n8n's private credential store>
Content-Type: application/json
```

Keep the token in n8n's private credential store or an environment variable. Do
not place it in this workflow, a public URL, a repository, or a screenshot.
Start with `limit: 1`, inspect the returned official `sourceUrl`, and only then
increase the window or attach a notification node.

## Understand the change semantics

The first successful run stores the current rows and returns each as
`changeType: "new"`. Later runs return a new row for an unseen opportunity and
one `changeType: "changed"` row when a watched field changes. Healthy unchanged
rows produce no dataset row. An opportunity leaving a limited result window is
not called removed or closed: absence from a search window is not proof of a
status change. Preserve the source status and dates when routing alerts.

Each returned row links to the official Grants.gov detail page and contains the
opportunity number, title, agency, open and close dates, status, document type,
CFDA numbers, and local observation time. Search titles and agency names are
untrusted source text; the Actor does not send them to an AI model or execute
their contents.

## Keep eligibility and decision boundaries explicit

You can narrow a query with official agency codes and two-digit applicant
eligibility codes (for example, `23` is the Grants.gov small-business code),
but a filter is not an eligibility determination. The Actor does not decide
whether an organization qualifies, rank applicants, estimate award odds,
recommend an application, submit an application, send messages, or promise
funding. Verify the current notice and its instructions with Grants.gov and
the awarding agency before acting. Downstream users remain responsible for
their own legal, financial, privacy, and grant-management decisions.

## Pay-per-event pricing

The [public Actor page](https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor)
shows the current price before a run. The launch configuration lists these
pay-per-event prices:

| Event | Meaning | Price |
| --- | --- | ---: |
| `apify-actor-start` | One Actor start | `$0.00005` |
| `grant-opportunity` | One newly observed opportunity | `$0.0075` |
| `grant-change` | One previously observed opportunity whose watched summary changed | `$0.015` |

Source failures, invalid input, unchanged results, and total search hit counts
are not charged as opportunity or change events. The current Store listing says
platform usage is included in these event prices. Check the displayed price in
your own account before enabling a schedule; a test run or free user is not
creator revenue, and only a finalized payout that actually settles counts as
revenue.

## A narrow, reviewable primitive

This monitor is intentionally a factual search-and-change feed. It preserves
source failures instead of treating an unavailable response as “unchanged,”
does not persist the Grants.gov service token metadata, and does not download
attachments. Use it to route a candidate opportunity to your own review queue,
then read the authoritative notice before making any decision.
