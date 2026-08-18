export type StockHistoryPeriod = 'daily' | 'weekly' | 'monthly';

export interface StockQuote {
  stockCode: string;
  stockName?: string | null;
  currentPrice: number;
  change?: number | null;
  changePercent?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  prevClose?: number | null;
  volume?: number | null;
  amount?: number | null;
  /** Server fetch time of the quote, not a proven market-data timestamp. */
  updateTime?: string | null;
}

export interface StockHistoryCandle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
  amount?: number | null;
  changePercent?: number | null;
}

export interface StockHistoryResponse {
  stockCode: string;
  stockName?: string | null;
  period: StockHistoryPeriod;
  data: StockHistoryCandle[];
}

export type FieldTrustStaleness = 'fresh' | 'stale' | 'unknown';
export type FieldTrustOrigin = 'primary' | 'supplement' | 'unknown';
export type FieldTrustStatus = 'ok' | 'degraded' | 'unavailable';
export type FieldTrustConfidence = 'high' | 'medium' | 'low';
export type FieldTrustProviderStatus = 'ok' | 'failed' | 'empty' | 'unavailable';
export type FieldTrustProviderRole = 'primary' | 'supplement' | 'attempted';

export interface FieldTrustEntry {
  field: string;
  value?: number | null;
  source?: string | null;
  origin: FieldTrustOrigin;
  providerTimestamp?: string | null;
  staleSeconds?: number | null;
  isStale?: boolean | null;
  staleness: FieldTrustStaleness;
  conflict: boolean;
}

export interface FieldTrustConflictValue {
  provider: string;
  value: number;
}

export interface FieldTrustConflict {
  field: string;
  severity: string;
  relativeDifference?: number | null;
  threshold?: number | null;
  values: FieldTrustConflictValue[];
}

export interface FieldTrustConflictCheck {
  primaryProvider?: string | null;
  secondaryProvider?: string | null;
  status: 'evaluated' | 'skipped';
  reason?: string | null;
}

export interface FieldTrustProviderHealth {
  provider: string;
  status: FieldTrustProviderStatus;
  role: FieldTrustProviderRole;
  circuitState?: string | null;
  available?: boolean | null;
  healthScore?: number | null;
}

export interface FieldTrustGap {
  code: string;
  field?: string | null;
  detail?: string | null;
}

export interface FieldTrustAnalysisInput {
  schemaVersion: 'field_trust_analysis_input/1.0';
  confidence: FieldTrustConfidence;
  gaps: FieldTrustGap[];
  conflictCount: number;
  failedProviderCount: number;
}

export interface StockFieldTrustResponse {
  schemaVersion: 'field_trust_view/1.0';
  stockCode: string;
  status: FieldTrustStatus;
  metadataPresent: boolean;
  quoteSource?: string | null;
  fetchedAt?: string | null;
  providerTimestamp?: string | null;
  staleSeconds?: number | null;
  isStale?: boolean | null;
  fallbackFrom?: string | null;
  dataQuality?: string | null;
  missingFields: string[];
  fields: FieldTrustEntry[];
  conflicts: FieldTrustConflict[];
  conflictChecks: FieldTrustConflictCheck[];
  providerHealth: FieldTrustProviderHealth[];
  analysisInput?: FieldTrustAnalysisInput | null;
  message?: string | null;
}
