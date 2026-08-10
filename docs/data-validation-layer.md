# Financial Data Validation Layer

Issue reference: #185. The implementation lives in `data_provider/data_validation.py`; provider-candidate wiring lives in `data_provider/manager_parts/daily_source_health.py`, and final-exit/reload wiring lives in `data_provider/manager_parts/data_validation_wiring.py`.

## Boundary and modes

Every non-empty daily or realtime provider candidate is validated before the manager accepts or caches it. Fresh and stale cache reads are revalidated against the current policy before return; a cached item accepted under an earlier warn-only policy therefore cannot bypass a later strict scope. In strict mode, a rejected provider candidate raises `DataValidationRejected` inside the existing bounded provider loop, is recorded in provider health/run diagnostics, and allows that loop to continue to the next eligible provider. Returning `None` from an outer manager wrapper is not provider failover and is not used by this implementation.

| Configuration | Default | Contract |
| --- | --- | --- |
| `DATA_VALIDATION_ENABLED` | `true` | Run validation and emit typed evidence. |
| `DATA_VALIDATION_STRICT` | `false` | Reject provider candidates with reject-severity findings before acceptance/cache. |
| `DATA_VALIDATION_STRICT_SCOPES` | `*/*` | Comma-separated `market/instrument` selectors, for example `cn/equity,hk/etf,us/index`. `*` is a wildcard. |
| `DATA_VALIDATION_INSTRUMENT_OVERRIDES` | empty | Comma-separated authoritative `SYMBOL=instrument` identities for offshore symbols that cannot be classified safely from code alone, for example `SPY=etf,HK02800=etf,1306.T=etf`. |
| `DATA_VALIDATION_UPPER_LAYER_MODE` | `warn` | Aggregated fundamental results remain warn/evidence-only by default. `reject` explicitly raises at that separate upper boundary; it is not described as provider failover. |

All five fields are loaded by the typed `Config` owner and remain environment-managed; this change does not add a parallel Web-settings surface. Explicit provider/caller `instrument_type` metadata takes precedence, then the configured symbol override, then conservative code inference. Disabling validation is the immediate rollback switch.
Malformed strict selectors do not silently disable rejection: when no selector is valid, strict mode falls back to `*/*`.

## Numeric contract

All covered numeric fields use the same classification:

| Input form | Classification | Result |
| --- | --- | --- |
| `None`, empty string, `-`, `--`, `N/A` | missing | Required price/close rejects; optional/offshore/ETF valuation fields remain absent without a finding. |
| Python/NumPy Boolean or a nonnumeric value such as `"not-a-number"` | invalid type | Reject with a field-specific `*_invalid_type` code. |
| `NaN`, `+Infinity`, `-Infinity` | non-finite | Reject with a field-specific `*_non_finite` code. |
| Finite numeric value outside the field range | out of range | Reject with a field-specific `*_out_of_range` code. |
| Finite numeric value inside the field range | finite | Continue to relational checks such as high/low and percentage-change consistency. |

Field-specific code families are version-stable:

- Daily OHLCV: `dv_ohlcv_<field>_<reason>`
- Realtime quote: `dv_quote_<field>_<reason>`
- Fundamentals: `dv_fund_pe_<reason>` and `dv_fund_pb_<reason>`
- Selected technical indicators: `dv_technical_<field>_<reason>` for `ma5`, `ma10`, `ma20`, `bias_ma5`, `bias_ma10`, `trend_strength`, and `signal_score`

Cross-field codes cover high below low, close/price outside the high-low range, percentage-change inconsistency, volume-unit suspicion, duplicate dates, and out-of-order dates. Negative PE is warn-only because it is valid for loss-making issuers. Zero volume and amount are valid for suspended instruments. Missing PE/PB is valid for ETFs and partial/offshore providers. Provider rounding within ±0.51 percentage points is accepted.

## Evidence and diagnostics

Findings are projected as `data_quality_evidence.v1`. Each record contains bounded issue lists plus sanitized severity, symbol, canonical market, canonical instrument type, provider, and available cache/fallback/staleness provenance. Realtime evidence is regenerated after supplementation and final fallback metadata are complete, so the evidence describes the returned quote rather than an earlier provider candidate. Non-finite values are converted to strict-JSON-safe values before evidence persistence.

The existing run-diagnostics owner logs the structured fields and stores evidence in `diagnostics.data_quality_evidence`. This evidence:

- survives DataFrame-to-row/database conversion because it does not rely on `DataFrame.attrs`;
- appears in the user-facing run-diagnostics data-quality component;
- is projected into `AnalysisContextPack.data_quality.metadata.validation_evidence` and its prompt warnings;
- is included in the persisted low-sensitivity AnalysisContextPack overview;
- is available to realtime callers through the additive typed `UnifiedRealtimeQuote.data_quality_evidence` field.

Daily `DataFrame.attrs["data_validation"]` remains a local convenience annotation. Public fundamental dictionaries are not mutated with ad-hoc keys.

## Wrapper lifecycle

Final-exit wrappers are installed per method on each target class. Installation uses a lock and a reload token, unwraps an older wrapper before replacement, and installs a class-local `__init_subclass__` hook so runtime subclass overrides are covered automatically. Partial installation, concurrent installation, and module/facade reloads cannot silently bypass validation.

## Compatibility and rollback

Warn mode preserves daily tuple, realtime quote, and fundamental dictionary return shapes. The realtime evidence field is optional and additive; API/Web/Desktop mappings that enumerate quote fields continue to work unchanged. Strict candidate rejection uses the existing provider loop and does not add an unbounded retry path. An opt-in upper-layer fundamental rejection is exposed as `status=validation_rejected` with typed reason codes and evidence; it is not mislabeled as a provider or pipeline failure.

Rollback by setting `DATA_VALIDATION_ENABLED=false`, or revert the introducing change.
