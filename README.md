# KRX OpenAPI Tools

Source-linked contracts, validation, and a small Python client for KRX daily equity data. Supports KOSPI, KOSDAQ, and KONEX. Python 3.10+; no runtime dependencies.

The tool helps preserve instrument identifiers, interpret missing numeric values, detect response changes, and attach source metadata before data enters a notebook, pipeline, or AI application.

Community software maintained by [MinDongJae](https://github.com/MinDongJae). The code license covers this software; data access and use remain subject to KRX's terms. This project is independently published and does not represent an official KRX product or endorsement.

## Install and try without a key

```sh
python -m pip install .
krx-openapi catalog --market kospi
krx-openapi validate --market kospi examples/synthetic-kospi.json --date 2026-01-02 --normalized
```

The fixture is synthetic, not a historical market observation. Invalid responses exit with status 1. Malformed files, arguments, and transport failures exit with status 2.

## What it checks

- An `OutBlock_1` array is present. An API error object is not treated as an empty dataset.
- The 15 declared output fields are present and retain the official wire string type.
- Dates are real calendar dates and match the requested date when supplied.
- Six-character instrument codes retain leading zeros and support uppercase letters, such as `0043Y0`.
- Decimal values use exact strings rather than binary floating point. Incorrect comma grouping, NaN, and infinity are rejected.
- The documented numeric missing marker `-` becomes `null`; zero stays zero. Text `-` remains text.
- Unexpected fields and duplicate date/instrument pairs produce warnings. Additional fields are retained during normalization.
- An empty response produces a warning. It does not automatically mean a holiday, an outage, or successful authorization.

The date/code/numeric interpretations and nonnegative checks are project validation rules. The public provider definitions declare strings. Units are marked unknown where the referenced field definitions do not state them; confirm units before aggregation or AI-generated analysis. Normalized dates use ISO format and are not the original wire response.

## Fetch an approved dataset

Follow [KRX's access procedure](https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp): obtain a key and approval for the particular service. This client does not supply a key or change service permissions.

Set `KRX_AUTH_KEY` in your process environment using your normal secret-management method, then run:

```sh
krx-openapi fetch --market kospi --date 2026-01-02 --output response.json
```

Each command makes one GET request, with a finite timeout and 20 MiB response limit. There is no automatic retry or date-range crawler. The key goes only in the `AUTH_KEY` header to the fixed official host; redirects are refused. Exceptions omit response bodies and credentials. Existing output files are not overwritten.

The output contains the raw response, validation report, endpoint, requested date, UTC retrieval time, and contract source. To validate it later, pass its `data` object to `validate()`; the CLI validator expects a raw `OutBlock_1` response.

```python
import os
from krx_openapi_tools import Client, normalize

result = Client(os.environ["KRX_AUTH_KEY"]).fetch("kospi", "2026-01-02")
records = normalize(result["data"], "kospi", expected_date="2026-01-02")
```

Authenticated live calls have not been verified in v0.1.0. Verification uses public specifications, synthetic fixtures, and mocked HTTP responses. Read `docs/sources.md` for the source and verification boundary.

## Machine-readable contracts

`krx_openapi_tools/contracts.json` records Korean labels, wire fields, missing markers, semantic types, source URLs, and observation dates. `schemas/` contains JSON Schema descriptions of the raw response shape. These can accompany retrieval results as context for AI applications; they do not guarantee correct downstream interpretation.

## Relationship to pykrx

[pykrx](https://github.com/sharebook-kr/pykrx) offers a broader Python interface using its own data-retrieval paths. These tools use the separately approved official OpenAPI services. Their coverage, authentication, dates, and response definitions can differ. This is not a drop-in replacement, and does not patch pykrx login or imply a contribution merged into pykrx.

## Develop

```sh
python -m unittest discover -s tests -v
```

Tests use synthetic data and mocked HTTP only. `python tools/verify_release.py` also checks wheel contents and installed-package resources, and writes `_mac_out/verification.json`. Project-wide checks for the initial release were submitted to the maintainer's registered iMac runner; the collected receipt is maintained outside the source tree.

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding contracts or reporting changes.
