# Explicit income ledger

`ledger.json` is the only money source used by the daily draft generator. It
starts at zero. `settled_revenue` means an external payment has actually
arrived; `pending_revenue` and `estimated_revenue` are reported separately and
never added to income. Deployment, impressions, clicks, saved time, and
unsettled promises are never converted into money.

The shape is documented in [`ledger.schema.json`](./ledger.schema.json). For an
auditable payment, add a dated entry with a minimal receipt reference:

```json
{
  "date": "2026-08-20",
  "kind": "revenue",
  "amount": 1,
  "status": "settled",
  "receipt": "provider payout reference"
}
```

Every entry needs an ISO date and explicit status. Settled revenue additionally
needs a minimal, non-secret `receipt` reference. Use `status: "pending"` until
the money has settled. Cost entries use `"kind": "cost"`. Never commit
passwords, cookies, card numbers, or tokens.

`revenue-sources.json` records provisional platform observations separately
from the ledger. Paying-user counts, free runs, result counts, current-month
profit, credits, and pending payouts can be useful growth signals, but they do
not change `settled_revenue`. Only a final payout invoice plus an actually
settled payment can be copied into `ledger.json` as income.
