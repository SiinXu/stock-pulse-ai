const GENERIC_MARKET_REVIEW_TITLES = new Set([
  'market review',
  '大盘复盘',
  '大盘复盘详情',
  'a股市场复盘',
  'a 股市场复盘',
]);

const SECTION_KIND_PATTERNS = {
  index: /指数|index|overview|大盘/,
  sentiment: /情绪|赚钱|sentiment|breadth|temperature/,
  rotation: /行业|板块|主题|轮动|sector|theme|rotation/,
  capital: /资金|成交|量能|flow|turnover|volume|capital/,
  risk: /风险|机会|观察|risk|watch|next/,
} as const;

export type MarketReviewSectionKind = keyof typeof SECTION_KIND_PATTERNS | 'default';

export const normalizeMarketReviewHeading = (value: string): string =>
  value.trim().replace(/\s+/g, ' ').toLowerCase();

export const isGenericMarketReviewTitle = (value: string): boolean =>
  GENERIC_MARKET_REVIEW_TITLES.has(normalizeMarketReviewHeading(value));

export const getMarketReviewSectionKind = (title: string): MarketReviewSectionKind => {
  const normalized = normalizeMarketReviewHeading(title);
  for (const [kind, pattern] of Object.entries(SECTION_KIND_PATTERNS)) {
    if (pattern.test(normalized)) {
      return kind as keyof typeof SECTION_KIND_PATTERNS;
    }
  }
  return 'default';
};
