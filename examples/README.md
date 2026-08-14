# Automation recipes

These recipes call the public Apify Actor API with the caller's own API token.
They contain no token, cookie, browser session, private webhook URL, or payment
data. At the current published pay-per-event prices, the bounded input costs at
most `$0.15005` in result/start events per successful run before tax or
account-level charges.

## n8n: daily Grants.gov alerts

Import [`n8n-grants-gov-monitor.json`](./n8n-grants-gov-monitor.json). The
workflow runs at 08:00 every day in the `Asia/Shanghai` timezone, calls the
Actor's synchronous dataset endpoint, and passes `new` and `changed` rows to
the final node. It uses this valid input:

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

`monitorId` is the baseline key. Keep it unchanged for this exact query; use a
new lowercase ID when changing the keyword or filters. A first run may return
up to ten `new` rows, while an unchanged run returns an empty array. Empty
output means there was no new or changed opportunity, not that the workflow
failed.

### One-time setup

1. In n8n, create a **Header Auth** credential with header name
   `Authorization` and value `Bearer YOUR_APIFY_API_TOKEN`. Attach it to
   **Run Grants.gov Monitor**. Keep the token in n8n's credential store; never
   paste it into this workflow export.
2. Test the workflow once. The first run creates the Actor's baseline and can
   emit current opportunities as `new`; later runs only emit changes.
3. Replace **Connect Slack, email, or database here** with a Slack, email,
   Teams, Notion, database, or private webhook node. Preserve `sourceUrl` as
   the official evidence link and use `alertText` for a compact notification.
4. Activate the workflow after choosing a destination. Do not activate it
   until the token and destination are configured; each successful run uses
   your Apify balance and the Store's current prices.

The export intentionally has no `credentials` object. A 401 or 402 response
means the Apify token is invalid or the account cannot authorize the paid run.
The Actor does not apply for grants, assess eligibility, or send messages to
grant agencies.

## Make: scheduled monitoring recipe

Create a scenario with these modules:

1. **Scheduler**: run daily at 08:00 Asia/Shanghai (or choose a slower cadence
   that suits the use case).
2. **HTTP > Make a request**:
   - Method: `POST`
   - URL:
     `https://api.apify.com/v2/actors/ai-coding-radar~grants-gov-opportunity-monitor/run-sync-get-dataset-items?clean=1`
   - Header: `Authorization: Bearer YOUR_APIFY_API_TOKEN`, stored in a private
     Make connection or secret field.
   - Header: `Accept: application/json`
   - Body type: `application/json`
   - Body:

     ```json
     {
       "keyword": "artificial intelligence",
       "statuses": ["posted", "forecasted"],
       "agencyCodes": [],
       "eligibilityCodes": [],
       "fundingCategoryCodes": [],
       "limit": 10,
       "monitorId": "make-ai-grants"
     }
     ```

     Keep `make-ai-grants` stable between runs. This is a separate baseline
     from the n8n example; do not alternate both workflows with the same
     `monitorId` unless they intentionally share one monitor.
3. **JSON > Parse JSON**: parse the returned array and add an iterator if the
   Make HTTP module exposes it as one array bundle.
4. Add a filter that keeps `changeType = new` or `changeType = changed`.
5. Send the filtered rows to Slack, email, Teams, Notion, a database, or a
   private webhook. Keep `sourceUrl` in the message for source attribution.

At the current prices, the maximum event charge for this ten-row recipe is
`$0.15005` (`10 * $0.015` for changes plus the `$0.00005` start event). Do not
treat an empty array as a failure, and do not infer eligibility or award
likelihood from the feed. A 401 or 402 response means the token is
missing/invalid or the account cannot authorize the paid run.
