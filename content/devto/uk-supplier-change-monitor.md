# Build a no-code UK supplier change monitor with n8n

A supplier record can change long after onboarding. A company may change its
registered name, status, office address, SIC codes, accounts dates, or filing
details. Checking every record by hand does not scale, but a full credit-risk
platform can be excessive when the requirement is simply: **tell me which
public register fields changed**.

This tutorial builds a scheduled n8n workflow around a small Companies House
change feed. It watches only company numbers you provide, stores a baseline,
and forwards observed differences or source failures. It does not scrape a
website, predict insolvency, or make a credit or legal decision.

> **Fastest path:** [open the preconfigured supplier-monitoring task](https://apify.com/ai-coding-radar/uk-company-change-alerts/examples/daily-uk-supplier-status-alerts). It uses one public example company, requires an Apify account, and shows the current price before you choose whether to run it.

## What the workflow does

The five-node workflow runs on a daily schedule:

1. Define a list of UK company numbers and a stable monitor ID.
2. Call the public Apify Actor through its official REST API.
3. Compare the latest basic register data with the named stored baseline.
4. Keep only `changed`, `source_not_found`, and `source_error` rows.
5. Hand those rows to a notification node that you choose.

The first successful check creates the baseline. Later healthy runs with no
differences return no alert rows by default. A source timeout or malformed
response remains visible as an error; it is never converted into "no change."

## Import the tested n8n workflow

Download and import this workflow JSON:

https://raw.githubusercontent.com/Jarvis-Dong/uk-company-change-alerts/main/examples/n8n-uk-company-alerts.json

The exported workflow contains no API token, cookie, credential ID, private
webhook, or notification destination. After import:

1. Create an n8n **Header Auth** credential named `Authorization` with value
   `Bearer YOUR_APIFY_API_TOKEN`.
2. Attach that credential to the HTTP Request node.
3. Replace the sample company number with the suppliers you actually monitor.
4. Keep the same `monitorId` on future runs of the same watchlist.
5. Replace the final no-op node with Slack, email, Teams, Notion, or a private
   webhook, then activate the schedule.

The sample input is deliberately small and valid:

```json
{
  "companyNumbers": ["02050399"],
  "monitorId": "supplier-watchlist",
  "emitUnchanged": false
}
```

Use a different `monitorId` for an independent watchlist. Reusing the same ID
for unrelated lists would mix their baselines.

## Call the same feed from any automation tool

n8n is optional. The same input works with Make, a scheduled script, GitHub
Actions, or another system that can send an authenticated HTTP request:

```sh
curl -X POST \
  'https://api.apify.com/v2/actors/ai-coding-radar~uk-company-change-alerts/run-sync-get-dataset-items?clean=1' \
  -H "Authorization: Bearer $APIFY_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"companyNumbers":["02050399"],"monitorId":"supplier-watchlist","emitUnchanged":false}'
```

Keep the token in your automation platform's credential store or an environment
variable. Do not place it in a public URL or exported workflow.

## Understand the output before alerting

A first observation returns a `baseline_created` row. That is setup evidence,
not a warning. Later differences return one `changed` row per changed field:

```json
{
  "companyNumber": "02050399",
  "companyName": "Example Company Limited",
  "observedAt": "2026-08-15T08:00:00Z",
  "sourceUrl": "https://data.companieshouse.gov.uk/doc/company/02050399.json",
  "status": "changed",
  "field": "companyStatus",
  "previousValue": "active",
  "currentValue": "dissolved",
  "errorCode": null,
  "errorMessage": null
}
```

The n8n filter forwards actual changes and explicit source errors. It ignores
`baseline_created` and healthy unchanged checks so the workflow does not send a
false alert during setup or create daily noise.

## Data and decision boundaries

The Actor reads the official Companies House URI JSON source. You can inspect
the sample record directly:

https://data.companieshouse.gov.uk/doc/company/02050399.json

Companies House documents its public data products here:

https://www.gov.uk/guidance/companies-house-data-products

The monitored fields stay at company level: company name and status, country
of origin, incorporation or dissolution dates, registered office address,
previous names, accounts and return dates, mortgage counts, and SIC text. The
feed does not collect officer or PSC profiles, birthdays, private databases,
or derived risk scores.

Register data can still contain personal information, especially when a
registered office is also a residential address. Downstream users remain
responsible for access control, retention, redistribution, and the decisions
they make from the observations. `observedAt` means when this workflow saw the
value; it is not a guarantee that the source updates in real time.

## Cost and source code

The ready-to-copy supplier monitoring task and public Actor are available here:

- Task: https://apify.com/ai-coding-radar/uk-company-change-alerts/examples/daily-uk-supplier-status-alerts
- Actor: https://apify.com/ai-coding-radar/uk-company-change-alerts

Its Store page shows the current pay-per-event price before a run. At the time
of writing, a successful company check is `$0.003`, an observed changed field
is `$0.01`, and the Actor-start event is `$0.00005`. Source failures and
rejected input are not charged as successful company checks. Apify platform
usage may also apply, so start with one company and confirm the displayed cost
for your own account before expanding a watchlist.

The source, n8n file, and Make setup notes are public:

https://github.com/Jarvis-Dong/uk-company-change-alerts

This is intentionally a narrow change-detection primitive. Treat its output as
an observed public-register difference that can trigger human review, not as a
credit report, legal opinion, compliance certification, or insolvency
prediction.
