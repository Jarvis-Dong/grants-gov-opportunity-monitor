import asyncio
import json
import unittest
from pathlib import Path

from grants_gov_opportunity_monitor.core import (
    SourceError,
    build_search_payload,
    parse_search_response,
    reconcile_opportunities,
    search_grants,
    validate_codes,
    validate_keyword,
    validate_limit,
    validate_monitor_id,
    validate_statuses,
)
from grants_gov_opportunity_monitor.main import BASELINE_KEY, run_actor


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "search.json").read_text())


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return json.dumps(self.payload).encode()


class FakeActor:
    def __init__(self, actor_input=None):
        self.actor_input = actor_input or {"keyword": "artificial intelligence"}
        self.values = {}
        self.records = []
        self.charges = []
        self.status = None
        self.store_name = None

    async def get_input(self):
        return self.actor_input

    async def open_key_value_store(self, *, name):
        self.store_name = name
        return self

    async def get_value(self, key, *, default_value=None):
        return self.values.get(key, default_value)

    async def set_value(self, key, value):
        self.values[key] = value

    async def push_data(self, records):
        self.records.extend(records)

    async def charge(self, event_name, *, count):
        self.charges.append((event_name, count))

    async def set_status_message(self, message, *, is_terminal):
        self.status = (message, is_terminal)


class GrantsMonitorTests(unittest.TestCase):
    def test_validates_and_builds_a_bounded_query(self):
        query = {
            "keyword": validate_keyword("  artificial   intelligence "),
            "statuses": validate_statuses(["posted", "forecasted", "posted"]),
            "agencyCodes": validate_codes(["nsf", "HHS-NIH11"], "agencyCodes"),
            "eligibilityCodes": validate_codes(["23"], "eligibilityCodes", eligibility=True),
            "fundingCategoryCodes": validate_codes(["ST"], "fundingCategoryCodes"),
            "limit": validate_limit(25),
        }
        payload = build_search_payload(query)
        self.assertEqual(payload["keyword"], "artificial intelligence")
        self.assertEqual(payload["oppStatuses"], "posted|forecasted")
        self.assertEqual(payload["agencies"], "HHS-NIH11|NSF")
        self.assertEqual(payload["eligibilities"], "23")
        self.assertEqual(payload["rows"], 25)
        self.assertEqual(validate_statuses(["forecasted", "posted"]), ["posted", "forecasted"])
        self.assertEqual(validate_codes(["NSF", "hhs", "NSF"], "agencyCodes"), ["HHS", "NSF"])
        with self.assertRaises(ValueError):
            validate_limit(True)
        with self.assertRaises(ValueError):
            validate_statuses(["archived"])
        with self.assertRaises(ValueError):
            validate_monitor_id("Different Query")

    def test_parses_factual_search_rows_and_discards_source_metadata(self):
        opportunities, total = parse_search_response(FIXTURE)
        self.assertEqual(total, 2)
        self.assertEqual(opportunities[0]["title"], "American Innovation Hub: AI & Digital Skills")
        self.assertEqual(opportunities[0]["openDate"], "2026-07-23")
        self.assertIsNone(opportunities[1]["closeDate"])
        serialized = json.dumps(opportunities)
        self.assertNotIn("discard-this-source-metadata", serialized)
        self.assertNotIn("token", serialized.lower())

    def test_rejects_invalid_source_payloads(self):
        with self.assertRaises(SourceError):
            parse_search_response({"errorcode": 1, "data": {}})
        broken = json.loads(json.dumps(FIXTURE))
        broken["data"]["oppHits"][0]["openDate"] = "tomorrow"
        with self.assertRaises(SourceError):
            parse_search_response(broken)

    def test_search_posts_only_the_documented_filter_payload(self):
        captured = {}

        def opener(request, **_kwargs):
            captured["body"] = json.loads(request.data)
            captured["method"] = request.method
            return FakeResponse(FIXTURE)

        query = {
            "keyword": "AI",
            "statuses": ["posted"],
            "agencyCodes": [],
            "eligibilityCodes": [],
            "fundingCategoryCodes": [],
            "limit": 2,
        }
        opportunities, total = search_grants(build_search_payload(query), opener=opener)
        self.assertEqual((len(opportunities), total), (2, 2))
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["body"]["startRecordNum"], 0)
        self.assertNotIn("token", captured["body"])

    def test_reconciles_new_changed_and_unchanged_opportunities(self):
        opportunities, _total = parse_search_response(FIXTURE)
        rows, baseline, new, changed, unchanged = reconcile_opportunities(
            opportunities, {}, "2026-08-15T00:00:00Z"
        )
        self.assertEqual((new, changed, unchanged), (2, 0, 0))
        self.assertEqual([row["changeType"] for row in rows], ["new", "new"])

        current = json.loads(json.dumps(opportunities))
        current[0]["closeDate"] = "2026-09-01"
        rows, _next, new, changed, unchanged = reconcile_opportunities(
            current, baseline, "2026-08-16T00:00:00Z"
        )
        self.assertEqual((new, changed, unchanged), (0, 1, 1))
        self.assertEqual(rows[0]["changes"], [{
            "field": "closeDate",
            "previousValue": "2026-08-30",
            "currentValue": "2026-09-01",
        }])

    def test_actor_persists_query_and_charges_only_new_or_changed_records(self):
        opportunities, total = parse_search_response(FIXTURE)
        actor = FakeActor()
        fetcher = lambda _query: (opportunities, total)

        first = asyncio.run(run_actor(actor, fetcher=fetcher, observed_at="2026-08-15T00:00:00Z"))
        self.assertEqual(first["new"], 2)
        self.assertEqual(actor.charges, [("grant-opportunity", 2)])
        self.assertEqual(actor.store_name, "grants-gov-monitor-default")
        self.assertIn(BASELINE_KEY, actor.values)

        actor.records.clear()
        changed = json.loads(json.dumps(opportunities))
        changed[0]["opportunityStatus"] = "closed"
        second = asyncio.run(
            run_actor(actor, fetcher=lambda _query: (changed, total), observed_at="2026-08-16T00:00:00Z")
        )
        self.assertEqual(second["changed"], 1)
        self.assertEqual(actor.charges[-1], ("grant-change", 1))

        actor.actor_input["keyword"] = "small business"
        with self.assertRaisesRegex(ValueError, "different query"):
            asyncio.run(run_actor(actor, fetcher=fetcher))


if __name__ == "__main__":
    unittest.main()
