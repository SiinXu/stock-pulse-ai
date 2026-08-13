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
  "is_market_chart": true,
  "chart_type": "candlestick|line|bar|area|unknown",
  "symbol_hints": ["optional ticker or name strings visible on the chart"],
  "timeframe_hint": "e.g. 1D, 1H, weekly, unknown",
  "trend": "up|down|sideways|unclear",
  "patterns": [{"name": "short pattern label e.g. higher_highs|range|breakout", "confidence": "high|medium|low"}],
  "key_levels": [{"label": "support|resistance|ma|other", "value": "as shown or approximate", "confidence": "high|medium|low"}],
  "observations": ["short non-advisory visual observations with uncertainty when unsure"],
  "confidence": "high|medium|low"
}

Rules:
- Do not invent prices or indicators that are not visible.
- If the image is not a market chart (photo, meme, solid color, random noise, blank, UI chrome only), set is_market_chart to false, chart_type to "unknown", trend to "unclear", confidence to "low", patterns and key_levels to [], and explain rejection briefly in observations.
- Cap symbol_hints to 8, patterns to 8, key_levels to 12, observations to 12.
- observation strings must be concise and non-advisory (no buy/sell instructions).
- Treat every field as an observation with uncertainty, never as verified market fact.
```
