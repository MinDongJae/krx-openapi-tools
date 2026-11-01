# Public specification sources and verification scope

Observed on 2026-11-01:

| Dataset | Public specification page |
| --- | --- |
| KOSPI daily equity trading | https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC |
| KOSDAQ daily equity trading | https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=hZjGpkllgCBCWqeTsYFj |
| KONEX daily equity trading | https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=HSiRvxGSYnvaKuAuqpqp |

The pages publish field definitions as part of their output-value UI. Only the public request/output field names, short labels, formatting/missing markers, and sample route were extracted. Server implementation content, credentials, private code, and internal business documents are not included.

Each dataset's downloadable developer specification was checked for its own production endpoint and output fields. The paths are `/svc/apis/sto/stk_bydd_trd`, `/svc/apis/sto/ksq_bydd_trd`, and `/svc/apis/sto/knx_bydd_trd` on `https://data-dbg.krx.co.kr`. The request field is `basDd` and the response block is `OutBlock_1`. The source document hashes are included in the contracts. These services have not been exercised with an approved API key for this release.

The contract marks semantic interpretations as this project's rules. It does not infer a currency, economic meaning, license, or provider guarantee from the word “OpenAPI”. Future additions should include their own public source and actual verification scope.

Verification distinguishes:

1. Source-field agreement with the public definitions.
2. Offline validation and normalization using synthetic data.
3. Mocked transport behavior, secret-safe errors, and redirect rejection.
4. Package installation/resource integrity.
5. Authenticated live behavior: not verified for this initial release.

No downstream adoption, production deployment, or upstream pykrx acceptance is claimed.
