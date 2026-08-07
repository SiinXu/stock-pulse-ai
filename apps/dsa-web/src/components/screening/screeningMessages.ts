import type { AlphaSiftScreenResponse } from '../../api/alphasift';
import { formatUiText } from '../../i18n/uiText';
import type { ScreeningText } from './screeningText';

const KNOWN_SNAPSHOT_SOURCES = new Set(['tushare', 'efinance', 'akshare_em', 'em_datacenter', 'baostock']);
const MAX_MESSAGE_DETAIL_LENGTH = 96;

export const toMessageList = (values: string[] | undefined) =>
  Array.isArray(values) ? values.map((value) => String(value).trim()).filter(Boolean) : [];

export const truncateMessageDetail = (value: string, maxLength = MAX_MESSAGE_DETAIL_LENGTH) => {
  const text = value.replace(/\s+/g, ' ').trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1)}…`;
};

export const formatStableAlphaSiftDiagnostic = (value: string, text: ScreeningText) => {
  const messages: Record<string, string> = {
    alphasift_warning: text.diagnosticWarning,
    alphasift_error: text.diagnosticInternal,
    alphasift_source_error: text.diagnosticSourceUnavailable,
    alphasift_llm_parse_error: text.diagnosticLlmParse,
    alphasift_internal_error: text.diagnosticInternal,
    alphasift_hotspot_refresh_failed: text.hotspotLoadFailed,
    alphasift_hotspot_source_error: text.diagnosticSourceUnavailable,
    alphasift_hotspot_direct_fallback_failed: text.hotspotLoadFailed,
    alphasift_hotspot_direct_fallback_used: text.cacheFallback,
    alphasift_hotspot_detail_prefetch_failed: text.hotspotDetailLoadFailed,
    alphasift_hotspot_detail_stale_cache: text.cacheFallback,
    alphasift_hotspot_detail_fallback: text.cacheFallback,
    alphasift_hotspot_detail_source_error: text.diagnosticSourceUnavailable,
    eastmoney_hotspot_unavailable: text.diagnosticNetwork,
    dsa_candidate_enrichment_failed: text.diagnosticWarning,
    dsa_stock_name_failed: text.diagnosticSourceUnavailable,
    dsa_realtime_quote_missing: text.diagnosticEmpty,
    dsa_realtime_quote_failed: text.diagnosticSourceUnavailable,
    dsa_fundamental_context_failed: text.diagnosticSourceUnavailable,
    dsa_search_unavailable: text.diagnosticSourceUnavailable,
    stock_news_unavailable: text.diagnosticSourceUnavailable,
    stock_news_failed: text.diagnosticSourceUnavailable,
  };
  return messages[value] || '';
};

export const summarizeAlphaSiftDiagnostic = (detail: string, text: ScreeningText) => {
  const stableMessage = formatStableAlphaSiftDiagnostic(detail, text);
  if (stableMessage) {
    return stableMessage;
  }
  if (/trade_cal returned no open trading days/i.test(detail)) {
    return text.diagnosticCalendar;
  }
  if (/too many requests|rate limit|http\s*429/i.test(detail)) {
    return text.diagnosticRateLimit;
  }
  if (/403 forbidden|forbidden|access denied/i.test(detail)) {
    return text.diagnosticForbidden;
  }
  if (/timeout|timed out/i.test(detail)) {
    return text.diagnosticTimeout;
  }
  if (/RemoteDisconnected|Connection aborted|ProtocolError|ConnectionPool|Max retries exceeded|ProxyError|NameResolutionError/i.test(detail)) {
    return text.diagnosticNetwork;
  }
  if (/missing .*api key|GEMINI_API_KEY|GOOGLE_API_KEY|gemini_api_key/i.test(detail)) {
    return text.diagnosticMissingKey;
  }
  if (/returned no data|empty/i.test(detail)) {
    return text.diagnosticEmpty;
  }

  const withoutUrl = detail
    .replace(/https?:\/\/\S+/gi, 'URL')
    .replace(/\bwith url:\s*\S+/gi, 'with url: URL')
    .replace(/\burl:\s*\S+/gi, 'url: URL');
  return truncateMessageDetail(withoutUrl);
};

export const parseSourceDiagnostic = (value: string) => {
  const match = value.match(/^([a-zA-Z0-9_-]+)\s*[:：]\s*(.+)$/);
  if (!match) {
    return null;
  }
  return {
    source: match[1],
    detail: match[2],
  };
};

export const normalizeScreenMessageKey = (value: string, text: ScreeningText) => {
  const formatted = formatScreenMessage(value, text);
  return formatted ? formatted.trim().toLowerCase() : value.trim().toLowerCase();
};

export const formatScreenMessage = (value: string, text: ScreeningText) => {
  const stableMessage = formatStableAlphaSiftDiagnostic(value, text);
  if (stableMessage) {
    return stableMessage;
  }
  if (/^DSA provider context applied \d+ of \d+ candidates/i.test(value)) {
    return '';
  }
  if (/^LLM ranking failed/i.test(value)) {
    return formatUiText(text.llmRankingFallback, { detail: summarizeAlphaSiftDiagnostic(value, text) });
  }

  const snapshotFallback = value.match(/^Snapshot source fallback:\s*(.+)$/i);
  if (snapshotFallback) {
    const parsed = parseSourceDiagnostic(snapshotFallback[1]);
    if (parsed) {
      return formatUiText(text.sourceFallbackNamed, { source: parsed.source, detail: summarizeAlphaSiftDiagnostic(parsed.detail, text) });
    }
    return formatUiText(text.sourceFallback, { detail: summarizeAlphaSiftDiagnostic(snapshotFallback[1], text) });
  }

  const parsed = parseSourceDiagnostic(value);
  if (parsed && KNOWN_SNAPSHOT_SOURCES.has(parsed.source.toLowerCase())) {
    return formatUiText(text.sourceFallbackNamed, { source: parsed.source, detail: summarizeAlphaSiftDiagnostic(parsed.detail, text) });
  }
  return truncateMessageDetail(value);
};

export const getScreenMessages = (meta: AlphaSiftScreenResponse | null, text: ScreeningText) => {
  if (!meta) {
    return [];
  }
  const messages: string[] = [];
  const seen = new Set<string>();
  [...toMessageList(meta.warnings), ...toMessageList(meta.sourceErrors), ...toMessageList(meta.llmParseErrors)].forEach(
    (value) => {
      const key = normalizeScreenMessageKey(value, text);
      if (seen.has(key)) {
        return;
      }
      const message = formatScreenMessage(value, text);
      if (!message) {
        return;
      }
      seen.add(key);
      messages.push(message);
    },
  );
  return messages;
};
