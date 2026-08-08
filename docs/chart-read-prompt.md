# Chart Read Prompt (Vision LLM)

This document records the full `CHART_READ_PROMPT` from
`src/services/chart_reading_service.py` for PR review.

**When modifying `CHART_READ_PROMPT`**: update this file and include the complete
current prompt in the PR description (same house rule as `EXTRACT_PROMPT` in
`AGENTS.md`).

---

## Current Prompt (complete)

```
Analyze this financial chart image (K-line/candlestick, line, bar, or similar market chart).

Return ONLY a valid JSON object (no markdown fences, no commentary) with this shape:
{
  "chart_type": "candlestick|line|bar|area|unknown",
  "symbol_hints": ["optional ticker or name strings visible on the chart"],
  "timeframe_hint": "e.g. 1D, 1H, weekly, unknown",
  "trend": "up|down|sideways|unclear",
  "key_levels": [{"label": "support|resistance|ma|other", "value": "as shown or approximate", "confidence": "high|medium|low"}],
  "observations": ["short factual visual observations"],
  "confidence": "high|medium|low"
}

Rules:
- Do not invent prices or indicators that are not visible.
- If the image is not a market chart, set chart_type to "unknown", trend to "unclear", confidence to "low", and explain in observations.
- Cap symbol_hints to 8, key_levels to 12, observations to 12.
- observation strings must be concise and non-advisory (no buy/sell instructions).
```
