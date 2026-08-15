# n8n Creator Hub submission draft

Status: prepared locally and not submitted. A Creator account must accept the
n8n submission terms before this text and the workflow JSON are uploaded.

## Title

Monitor Grants.gov opportunities daily with Apify

## Description

### Who is this for?

This workflow is for small-business teams, nonprofits, grant consultants, and
research staff who need a factual daily feed of new or changed U.S. federal
grant opportunities.

### How it works

The Schedule Trigger runs every morning. An authenticated HTTP Request calls
the Grants.gov Opportunity Monitor Actor with a bounded query. The Actor stores
a baseline for the stable `monitorId`; the Code node keeps `new` and `changed`
rows and formats an alert with the official source URL. The final placeholder
is where you connect Slack, email, Teams, Notion, or a database.

### How to set up

Create an n8n Header Auth credential with header name `Authorization` and value
`Bearer YOUR_APIFY_API_TOKEN`, then attach it to **Run Grants.gov Monitor**.
Run once to create the baseline, replace the final placeholder with your
private destination, and activate the workflow.

### Requirements

- An Apify account and API token stored in n8n's credential manager.
- Sufficient Apify balance for the Store's current pay-per-event price.
- A notification or storage destination that you control.

### How to customize

Edit the HTTP Request JSON to change the keyword, status, agency, eligibility,
funding category, or ten-result limit. Use a new lowercase `monitorId` when the
filters change and keep it stable afterward. An empty response is a healthy
no-change result. Always verify eligibility and the current notice on
Grants.gov before making an application decision.
