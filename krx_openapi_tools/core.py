from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from importlib.resources import files
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOST = "https://data-dbg.krx.co.kr"
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
NUMBER = re.compile(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?\Z")
CODE = re.compile(r"[A-Z0-9]{6}\Z")


class KRXError(Exception):
    """A sanitized transport or data error."""


class ValidationError(KRXError):
    def __init__(self, report: Report):
        self.report = report
        super().__init__("Response failed the data contract; inspect report.issues")


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    row: int | None
    field: str | None
    message: str


@dataclass
class Report:
    market: str
    row_count: int
    issues: list[Issue]

    @property
    def valid(self) -> bool:
        return not any(i.level == "error" for i in self.issues)

    def to_dict(self) -> dict:
        return {"valid": self.valid, **asdict(self)}


def contract(market: str) -> dict:
    """Return a fresh copy of a bundled, source-linked public contract."""
    catalog = json.loads(files("krx_openapi_tools").joinpath("contracts.json").read_text(encoding="utf-8"))
    if market not in catalog["datasets"]:
        raise ValueError("market must be kospi, kosdaq, or konex")
    return catalog["datasets"][market]


def _date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2})", value):
        raise ValueError("date must be a calendar date in YYYYMMDD or YYYY-MM-DD format")
    fmt = "%Y-%m-%d" if "-" in value else "%Y%m%d"
    return datetime.strptime(value, fmt).strftime("%Y%m%d")


def _number(value: str) -> Decimal:
    if not NUMBER.fullmatch(value):
        raise ValueError("invalid decimal string")
    return Decimal(value.replace(",", ""))


def validate(payload: Any, market: str, *, expected_date: str | None = None) -> Report:
    spec = contract(market)
    expected = _date(expected_date) if expected_date is not None else None
    issues: list[Issue] = []
    report = Report(market, 0, issues)

    def issue(code, row=None, field=None, message="", level="error"):
        issues.append(Issue(level, code, row, field, message))

    if not isinstance(payload, dict) or not isinstance(payload.get(spec["block"]), list):
        issue("invalid_envelope", message="Expected an object with an OutBlock_1 array; an error body is not an empty dataset.")
        return report
    rows = payload[spec["block"]]
    report.row_count = len(rows)
    if not rows:
        issue("empty_dataset", message="No rows returned; this alone does not identify a holiday or prove API availability.", level="warning")
    known = {field["name"]: field for field in spec["fields"]}
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            issue("invalid_row", index, message="Each row must be an object.")
            continue
        for key in sorted(row.keys() - known.keys()):
            issue("unknown_field", index, str(key), "Unrecognized field retained; review the upstream contract.", "warning")
        for name, field in known.items():
            if name not in row:
                issue("missing_field", index, name, "Required wire field is absent.")
                continue
            value = row[name]
            if not isinstance(value, str):
                issue("invalid_type", index, name, "The referenced API declares a string; numeric coercion can lose identifiers or precision.")
                continue
            if field["semantic_type"] == "date":
                try:
                    actual = _date(value)
                    if not re.fullmatch(r"[0-9]{8}", value):
                        issue("invalid_date", index, name, "Wire date must use YYYYMMDD.")
                    elif expected and actual != expected:
                        issue("date_mismatch", index, name, "Returned date differs from the requested date.")
                except ValueError:
                    issue("invalid_date", index, name, "Invalid calendar date.")
            elif field["semantic_type"] == "identifier":
                if not CODE.fullmatch(value):
                    issue("invalid_identifier", index, name, "Expected six uppercase alphanumeric characters; preserve leading zeros.")
            elif field["semantic_type"] == "decimal":
                if value == field.get("missing_marker"):
                    continue
                try:
                    number = _number(value)
                    if field.get("nonnegative") and number < 0:
                        issue("negative_value", index, name, "This contract expects a nonnegative quantity.")
                except ValueError:
                    issue("invalid_number", index, name, "Expected a decimal string, optional valid thousands grouping, or the documented missing marker.")
        identity = (row.get("BAS_DD"), row.get("ISU_CD"))
        if all(isinstance(v, str) for v in identity):
            if identity in seen:
                issue("duplicate_record", index, "ISU_CD", "Repeated date and instrument pair; check data duplication.", "warning")
            seen.add(identity)
    return report


def normalize(payload: Any, market: str, *, expected_date: str | None = None) -> list[dict]:
    """Validate first; return exact decimal strings and ISO dates, preserving codes."""
    report = validate(payload, market, expected_date=expected_date)
    if not report.valid:
        raise ValidationError(report)
    spec = contract(market)
    output = []
    for raw in payload[spec["block"]]:
        row = dict(raw)
        for field in spec["fields"]:
            name, kind = field["name"], field["semantic_type"]
            if kind == "decimal":
                row[name] = None if row[name] == field.get("missing_marker") else format(_number(row[name]), "f")
            elif kind == "date":
                row[name] = datetime.strptime(row[name], "%Y%m%d").date().isoformat()
        output.append(row)
    return output


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise KRXError("Redirect refused; the authentication header is restricted to the official API endpoint")


class Client:
    """A bounded GET client; each service still needs the user's KRX approval."""

    def __init__(self, api_key: str, *, timeout: float = 20):
        if not isinstance(api_key, str) or not api_key.strip() or any(c in api_key for c in "\r\n"):
            raise ValueError("A nonempty API key without line breaks is required")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        self._api_key = api_key
        self.timeout = timeout
        self._opener = build_opener(_NoRedirect())

    def fetch(self, market: str, date: str) -> dict:
        spec = contract(market)
        day = _date(date)
        url = HOST + spec["production_path"] + "?" + urlencode({"basDd": day})
        request = Request(url, headers={"AUTH_KEY": self._api_key, "Accept": "application/json", "User-Agent": "krx-openapi-tools/0.1.0"})
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise KRXError("Unexpected HTTP status from KRX")
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise KRXError(f"KRX HTTP {exc.code}; check key, per-service approval, and request limits") from None
        except (URLError, TimeoutError, OSError):
            raise KRXError("KRX request failed or timed out; request details and credentials are omitted") from None
        if len(body) > MAX_RESPONSE_BYTES:
            raise KRXError("KRX response exceeds the 20 MiB limit")
        try:
            payload = json.loads(body.decode("utf-8-sig"))
        except (UnicodeError, ValueError):
            raise KRXError("KRX did not return valid UTF-8 JSON") from None
        report = validate(payload, market, expected_date=day)
        if not report.valid:
            raise ValidationError(report)
        return {"data": payload, "validation": report.to_dict(), "provenance": {"endpoint": HOST + spec["production_path"], "requested_date": day, "retrieved_at": datetime.now(timezone.utc).isoformat(), "contract_source": spec["source_url"], "contract_verified_on": spec["verified_on"]}}
