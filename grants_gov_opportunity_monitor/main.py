"""Apify Actor entry point for Grants.gov opportunity monitoring."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .core import (
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

BASELINE_KEY = "GRANTS_GOV_OPPORTUNITIES_V1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def run_actor(
    actor: Any,
    *,
    fetcher: Callable[[dict[str, Any]], tuple[list[dict[str, Any]], int]] = search_grants,
    observed_at: str | None = None,
) -> dict[str, Any]:
    actor_input = await actor.get_input() or {}
    if not isinstance(actor_input, dict):
        raise ValueError("Actor input must be an object")
    query = {
        "keyword": validate_keyword(
            actor_input.get("keyword", "artificial intelligence")
        ),
        "statuses": validate_statuses(actor_input.get("statuses", ["posted", "forecasted"])),
        "agencyCodes": validate_codes(actor_input.get("agencyCodes"), "agencyCodes"),
        "eligibilityCodes": validate_codes(
            actor_input.get("eligibilityCodes"), "eligibilityCodes", eligibility=True
        ),
        "fundingCategoryCodes": validate_codes(
            actor_input.get("fundingCategoryCodes"), "fundingCategoryCodes"
        ),
        "limit": validate_limit(actor_input.get("limit", 25)),
    }
    monitor_id = validate_monitor_id(actor_input.get("monitorId"))
    state_store = await actor.open_key_value_store(name=f"grants-gov-monitor-{monitor_id}")
    state = await state_store.get_value(BASELINE_KEY)
    if state is None:
        state = {"query": query, "opportunities": {}}
    if (
        not isinstance(state, dict)
        or not isinstance(state.get("query"), dict)
        or not isinstance(state.get("opportunities"), dict)
    ):
        raise ValueError("stored monitor state was invalid")
    if state["query"] != query:
        raise ValueError("monitorId already belongs to a different query; use a new monitorId")

    opportunities, total_matches = await asyncio.to_thread(fetcher, build_search_payload(query))
    observed = observed_at or utc_now()
    rows, next_opportunities, new_count, changed_count, unchanged_count = reconcile_opportunities(
        opportunities,
        state["opportunities"],
        observed,
    )
    await state_store.set_value(
        BASELINE_KEY,
        {"query": query, "opportunities": next_opportunities},
    )
    if rows:
        await actor.push_data(rows)
    if new_count:
        await actor.charge("grant-opportunity", count=new_count)
    if changed_count:
        await actor.charge("grant-change", count=changed_count)
    summary = {
        "totalMatches": total_matches,
        "checked": len(opportunities),
        "new": new_count,
        "changed": changed_count,
        "unchanged": unchanged_count,
        "records": len(rows),
    }
    await actor.set_status_message(
        "Matched {totalMatches}; checked {checked}, new {new}, changed {changed}, "
        "unchanged {unchanged}".format(**summary),
        is_terminal=True,
    )
    return summary


async def _run_fixture(path: Path) -> None:
    payload = json.loads(path.read_text())
    opportunities, total_matches = parse_search_response(payload)

    class LocalActor:
        def __init__(self) -> None:
            self.values: dict[str, Any] = {}
            self.records: list[dict[str, Any]] = []

        async def get_input(self) -> dict[str, Any]:
            return {"keyword": "artificial intelligence"}

        async def open_key_value_store(self, *, name: str) -> Any:
            return self

        async def get_value(self, key: str, *, default_value: Any = None) -> Any:
            return self.values.get(key, default_value)

        async def set_value(self, key: str, value: Any) -> None:
            self.values[key] = value

        async def push_data(self, records: list[dict[str, Any]]) -> None:
            self.records.extend(records)

        async def charge(self, _event_name: str, *, count: int) -> None:
            return None

        async def set_status_message(self, message: str, *, is_terminal: bool) -> None:
            print(message)

    actor = LocalActor()
    await run_actor(
        actor,
        fetcher=lambda _query: (opportunities, total_matches),
        observed_at="2026-08-15T00:00:00Z",
    )
    print(json.dumps(actor.records, ensure_ascii=False, indent=2))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, help="run an offline Grants.gov search fixture")
    args = parser.parse_args()
    if args.fixture:
        await _run_fixture(args.fixture)
        return

    from apify import Actor

    async with Actor:
        await run_actor(Actor)


if __name__ == "__main__":
    asyncio.run(main())
