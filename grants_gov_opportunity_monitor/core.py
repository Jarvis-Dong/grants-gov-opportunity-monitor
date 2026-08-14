"""Fact-only client and change detector for the public Grants.gov search API."""

from __future__ import annotations

import copy
import html
import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Callable

SEARCH_URL = "https://api.grants.gov/v1/api/search2"
USER_AGENT = "grants-gov-opportunity-monitor/0.1 (+https://apify.com/)"
MAX_PAYLOAD_BYTES = 5_000_000
MONITOR_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
CODE_RE = re.compile(r"^[A-Z0-9-]{1,30}$")
ELIGIBILITY_RE = re.compile(r"^[0-9]{2}$")
VALID_STATUSES = ("posted", "forecasted")
WATCH_FIELDS = (
    "opportunityNumber",
    "title",
    "agencyCode",
    "agency",
    "openDate",
    "closeDate",
    "opportunityStatus",
    "documentType",
    "cfdaNumbers",
)


class SourceError(Exception):
    """Grants.gov could not return a valid search response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_keyword(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("keyword must be a string")
    keyword = " ".join(value.split())
    if not 1 <= len(keyword) <= 200 or any(ord(char) < 32 for char in keyword):
        raise ValueError("keyword must contain 1-200 printable characters")
    return keyword


def validate_statuses(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("statuses must be a non-empty array")
    for item in value:
        if item not in VALID_STATUSES:
            raise ValueError(f"unsupported opportunity status: {item!r}")
    return [status for status in VALID_STATUSES if status in value]


def validate_codes(value: Any, name: str, *, eligibility: bool = False) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 50:
        raise ValueError(f"{name} must be an array with at most 50 values")
    pattern = ELIGIBILITY_RE if eligibility else CODE_RE
    codes: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{name} values must be strings")
        code = item.strip().upper()
        if not pattern.fullmatch(code):
            raise ValueError(f"invalid {name} value: {item!r}")
        if code not in codes:
            codes.append(code)
    return sorted(codes)


def validate_limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    return value


def validate_monitor_id(value: Any) -> str:
    if value is None:
        return "default"
    if not isinstance(value, str) or not MONITOR_ID_RE.fullmatch(value):
        raise ValueError(
            "monitorId must use 1-32 lowercase letters, digits, or hyphens "
            "without a leading or trailing hyphen"
        )
    return value


def build_search_payload(query: dict[str, Any]) -> dict[str, Any]:
    return {
        "keyword": query["keyword"],
        "oppStatuses": "|".join(query["statuses"]),
        "agencies": "|".join(query["agencyCodes"]),
        "eligibilities": "|".join(query["eligibilityCodes"]),
        "fundingCategories": "|".join(query["fundingCategoryCodes"]),
        "rows": query["limit"],
        "startRecordNum": 0,
        "sortBy": "openDate|desc",
    }


def _source_date(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise SourceError("invalid_payload", f"{field} was not a string")
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except ValueError as exc:
        raise SourceError("invalid_payload", f"{field} was not MM/DD/YYYY") from exc


def _source_text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise SourceError("invalid_payload", f"{field} was missing")
        return None
    if not isinstance(value, str):
        raise SourceError("invalid_payload", f"{field} was not a string")
    cleaned = " ".join(html.unescape(value).split())
    if required and not cleaned:
        raise SourceError("invalid_payload", f"{field} was empty")
    return cleaned or None


def normalize_opportunity(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SourceError("invalid_payload", "an opportunity was not an object")
    opportunity_id = str(raw.get("id", "")).strip()
    if not opportunity_id.isdigit():
        raise SourceError("invalid_payload", "an opportunity id was missing or invalid")
    cfda = raw.get("cfdaList", [])
    if not isinstance(cfda, list) or not all(isinstance(item, str) for item in cfda):
        raise SourceError("invalid_payload", "cfdaList was not a string array")
    status = _source_text(raw.get("oppStatus"), "oppStatus", required=True)
    if status not in (*VALID_STATUSES, "closed", "archived"):
        raise SourceError("invalid_payload", f"unsupported source status: {status!r}")
    return {
        "opportunityId": opportunity_id,
        "opportunityNumber": _source_text(raw.get("number"), "number", required=True),
        "title": _source_text(raw.get("title"), "title", required=True),
        "agencyCode": _source_text(raw.get("agencyCode"), "agencyCode", required=True),
        "agency": _source_text(raw.get("agency"), "agency", required=True),
        "openDate": _source_date(raw.get("openDate"), "openDate"),
        "closeDate": _source_date(raw.get("closeDate"), "closeDate"),
        "opportunityStatus": status,
        "documentType": _source_text(raw.get("docType"), "docType"),
        "cfdaNumbers": list(dict.fromkeys(item.strip() for item in cfda if item.strip())),
        "sourceUrl": f"https://www.grants.gov/search-results-detail/{opportunity_id}",
    }


def parse_search_response(payload: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(payload, dict) or payload.get("errorcode") != 0:
        raise SourceError("source_error", "Grants.gov search did not succeed")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SourceError("invalid_payload", "Grants.gov response did not contain data")
    hits = data.get("oppHits")
    hit_count = data.get("hitCount")
    if not isinstance(hits, list) or isinstance(hit_count, bool) or not isinstance(hit_count, int):
        raise SourceError("invalid_payload", "Grants.gov response did not contain search results")
    opportunities: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in hits:
        opportunity = normalize_opportunity(raw)
        opportunity_id = opportunity["opportunityId"]
        if opportunity_id in seen:
            raise SourceError("invalid_payload", "Grants.gov returned a duplicate opportunity id")
        seen.add(opportunity_id)
        opportunities.append(opportunity)
    return opportunities, hit_count


def search_grants(
    search_payload: dict[str, Any],
    *,
    timeout: int = 30,
    opener: Callable[..., Any] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    request = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps(search_payload, separators=(",", ":")).encode(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout) as response:
            body = response.read(MAX_PAYLOAD_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise SourceError(f"http_{exc.code}", f"Grants.gov returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError("network_error", "Grants.gov request failed") from exc
    if len(body) > MAX_PAYLOAD_BYTES:
        raise SourceError("payload_too_large", "Grants.gov response exceeded the safety limit")
    try:
        payload = json.loads(body)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SourceError("invalid_json", "Grants.gov did not return valid JSON") from exc
    return parse_search_response(payload)


def _json_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, ensure_ascii=False, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def reconcile_opportunities(
    opportunities: list[dict[str, Any]],
    previous: dict[str, Any],
    observed_at: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], int, int, int]:
    next_opportunities = copy.deepcopy(previous)
    rows: list[dict[str, Any]] = []
    new_count = 0
    changed_count = 0
    unchanged_count = 0
    for opportunity in opportunities:
        opportunity_id = opportunity["opportunityId"]
        old = previous.get(opportunity_id)
        next_opportunities[opportunity_id] = copy.deepcopy(opportunity)
        if old is None:
            new_count += 1
            rows.append({**copy.deepcopy(opportunity), "observedAt": observed_at, "changeType": "new", "changes": []})
            continue
        if not isinstance(old, dict):
            raise ValueError("stored opportunity baseline was invalid")
        changes = [
            {
                "field": field,
                "previousValue": copy.deepcopy(old.get(field)),
                "currentValue": copy.deepcopy(opportunity.get(field)),
            }
            for field in WATCH_FIELDS
            if not _json_equal(old.get(field), opportunity.get(field))
        ]
        if changes:
            changed_count += 1
            rows.append(
                {
                    **copy.deepcopy(opportunity),
                    "observedAt": observed_at,
                    "changeType": "changed",
                    "changes": changes,
                }
            )
        else:
            unchanged_count += 1
    return rows, next_opportunities, new_count, changed_count, unchanged_count
