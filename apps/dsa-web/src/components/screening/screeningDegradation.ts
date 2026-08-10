import type { AlphaSiftScreenResponse } from '../../api/alphasift';
import { formatScreenMessage, toMessageList } from './screeningMessages';
import type { ScreeningText } from './screeningText';

export type ScreeningDegradationReasons = {
  general: string[];
  source: string[];
  llm: string[];
  enrichment: string[];
};

const isLlmWarning = (value: string) => /\bllm\b|gemini|language model/i.test(value);

const isSourceWarning = (value: string) =>
  /snapshot source|data source|source fallback|tushare|efinance|akshare|baostock|datacenter/i.test(
    value,
  );

export const getScreeningDegradationReasons = (
  meta: AlphaSiftScreenResponse | null,
  text: ScreeningText,
): ScreeningDegradationReasons => {
  const groups: ScreeningDegradationReasons = {
    general: [],
    source: [],
    llm: [],
    enrichment: [],
  };
  if (!meta) return groups;

  const seen = new Set<string>();
  const append = (group: keyof ScreeningDegradationReasons, value: string) => {
    const message = formatScreenMessage(value, text);
    if (!message) return;
    const key = message.trim().toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    groups[group].push(message);
  };

  toMessageList(meta.warnings).forEach((value) => {
    if (isLlmWarning(value)) {
      append('llm', value);
    } else if (isSourceWarning(value)) {
      append('source', value);
    } else {
      append('general', value);
    }
  });
  toMessageList(meta.sourceErrors).forEach((value) => append('source', value));
  toMessageList(meta.llmParseErrors).forEach((value) => append('llm', value));
  toMessageList(meta.dsaEnrichment?.warnings).forEach((value) => append('enrichment', value));

  if (meta.llmRanked === false && groups.llm.length === 0) {
    groups.llm.push(text.localRankingNotice);
  }
  return groups;
};
