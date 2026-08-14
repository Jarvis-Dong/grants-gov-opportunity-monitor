# Grants.gov Opportunity Monitor API

Search active U.S. federal grant opportunities through the official public
Grants.gov API, then emit only opportunities that are new or changed since the
previous run. The Actor needs no Grants.gov account, API key, login, cookie,
proxy, or browser automation.

- [Run the Actor on Apify](https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor)
- Official source: [Grants.gov API Guide](https://www.grants.gov/api/api-guide)

Ready-made public examples:

- [Daily small-business federal grant alerts](https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor/examples/daily-small-business-federal-grant-alerts)
- [Daily nonprofit federal grant alerts](https://apify.com/ai-coding-radar/grants-gov-opportunity-monitor/examples/daily-nonprofit-federal-grant-alerts)

This is a factual search and change feed. It does not decide whether an
organization is eligible, recommend an application, estimate the chance of an
award, or promise funding.

## Input

```json
{
  "keyword": "artificial intelligence",
  "statuses": ["posted", "forecasted"],
  "agencyCodes": [],
  "eligibilityCodes": [],
  "fundingCategoryCodes": [],
  "limit": 25,
  "monitorId": "ai-grants"
}
```

Use Grants.gov agency codes such as `NSF` or `HHS-NIH11`. Applicant eligibility
codes are the two-digit values returned by Grants.gov; for example, `23` is the
small-business code. Keep one stable `monitorId` for one exact set of filters.
Changing the query under the same ID fails before a source request so unrelated
searches cannot share a baseline.

## Monitoring semantics

1. The first run stores the current results and emits each one as `new`.
2. Later runs emit a `new` row for an unseen opportunity and one `changed` row
   when a watched summary field changes.
3. Unchanged opportunities create no dataset row and no result event charge.
4. Opportunities that leave the top result window are not called removed or
   closed; absence from a limited search is not proof of a status change.
5. Reuse the same `monitorId` in an Apify Task scheduled daily or weekly.

The watched facts are opportunity number, title, agency, open and close dates,
status, document type, and CFDA numbers. Every row links to the official
Grants.gov detail page and includes the local observation time. Search titles
and agency names are untrusted source text; the Actor does not send them to an
AI model or execute their contents.

## Copy-paste REST quickstart

Keep your Apify token in an environment variable and send it in a header:

```sh
curl -X POST \
  'https://api.apify.com/v2/actors/ai-coding-radar~grants-gov-opportunity-monitor/run-sync-get-dataset-items?clean=1' \
  -H "Authorization: Bearer $APIFY_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"keyword":"artificial intelligence","statuses":["posted","forecasted"],"limit":25,"monitorId":"ai-grants"}'
```

The Grants.gov `search2` response includes service metadata that the Actor does
not persist or expose. It does not call the detail or attachment endpoints, so
it avoids downloading long descriptions, contact records, or application
files that are not needed for a change alert.

## No-code automation

Import the ready-made [n8n daily monitoring workflow](https://github.com/Jarvis-Dong/grants-gov-opportunity-monitor/blob/main/examples/n8n-grants-gov-monitor.json)
and follow the [n8n and Make setup recipe](https://github.com/Jarvis-Dong/grants-gov-opportunity-monitor/blob/main/examples/README.md).
The example uses a stable `monitorId` (`n8n-ai-grants`) and `limit: 10`. At the
current published event prices, even ten changed rows cost at most
`10 * $0.015 + $0.00005 = $0.15005` before tax or account-level charges. The
workflow does not run the Actor until you manually execute or activate it with
your own Apify token.
Connect its final node to a Slack, email, database, or private webhook that you
control. Do not put tokens or delivery credentials in the exported JSON.

## Pay-per-event setup

Suggested launch prices are explicit and only successful result events are
charged:

| Event | Meaning | Suggested price |
| --- | --- | ---: |
| `apify-actor-start` | One Actor start | `$0.00005` |
| `grant-opportunity` | One newly observed opportunity | `$0.0075` |
| `grant-change` | One previously observed opportunity whose summary changed | `$0.015` |

Source failures, invalid input, unchanged results, and total search hit counts
are not charged as opportunity or change events. Prices are configured in the
Apify publication wizard; this repository does not claim revenue.

## Source and boundaries

- Uses only `POST https://api.grants.gov/v1/api/search2`.
- Grants.gov documents `search2` as unrestricted and requiring no authentication.
- Does not download attachments or full opportunity descriptions.
- Does not apply, send messages, rank applicants, infer eligibility, or provide
  financial, legal, or grant-writing advice.
- Preserves source status and dates instead of treating an unavailable source
  as an unchanged monitor.

## Local checks

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q grants_gov_opportunity_monitor
npx --yes apify-cli validate-schema
python3 -m grants_gov_opportunity_monitor.main --fixture tests/fixtures/search.json
```
