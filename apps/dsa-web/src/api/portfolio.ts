import { z } from 'zod';
import apiClient from './index';
import { createApiError, createParsedApiError } from './error';
import { toCamelCase } from './utils';
import type { TaskAccepted } from '../types/analysis';
import type {
  PortfolioAccountItem,
  PortfolioAccountCreateRequest,
  PortfolioAccountUpdateRequest,
  PortfolioAccountListResponse,
  PortfolioCashLedgerCreateRequest,
  PortfolioCashLedgerListResponse,
  PortfolioCorporateActionCreateRequest,
  PortfolioCorporateActionListResponse,
  PortfolioCostMethod,
  PortfolioDeleteResponse,
  PortfolioEventCreatedResponse,
  PortfolioFxRefreshResponse,
  PortfolioImportBrokerListResponse,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PaperTradeCreateRequest,
  PaperTradeCreatedResponse,
  PortfolioPositionAnalysisRequest,
  PortfolioRiskResponse,
  PortfolioSnapshotResponse,
  PortfolioTradeCreateRequest,
  PortfolioTradeListResponse,
} from '../types/portfolio';

import type { components } from '../types/api.generated';

type OpenApiPortfolioSnapshot = components['schemas']['PortfolioSnapshotResponse'];
type OpenApiPortfolioAccountItem = components['schemas']['PortfolioAccountItem'];
type OpenApiPaperTradeCreated = components['schemas']['PaperTradeCreatedResponse'];
type _AssertSnapshotFields = keyof OpenApiPortfolioSnapshot;
type _AssertAccountFields = keyof OpenApiPortfolioAccountItem;
type _AssertPaperTradeFields = keyof OpenApiPaperTradeCreated;
const _snapshotFieldAnchor: _AssertSnapshotFields = 'total_equity';
const _accountFieldAnchor: _AssertAccountFields = 'base_currency';
const _paperTradeFieldAnchor: _AssertPaperTradeFields = 'price_source';
void _snapshotFieldAnchor;
void _accountFieldAnchor;
void _paperTradeFieldAnchor;

const portfolioAccountItemSchema = z.object({
  id: z.number(), name: z.string(), market: z.string(), baseCurrency: z.string(), isActive: z.boolean(),
  accountType: z.string().optional(), ownerId: z.string().nullable().optional(), broker: z.string().nullable().optional(),
  createdAt: z.string().nullable().optional(), updatedAt: z.string().nullable().optional(),
}).passthrough();
const portfolioAccountListResponseSchema = z.object({ accounts: z.array(portfolioAccountItemSchema).optional() }).passthrough();
const portfolioPositionItemSchema = z.object({
  symbol: z.string(), market: z.string(), currency: z.string(), quantity: z.number(), avgCost: z.number(),
  totalCost: z.number(), lastPrice: z.number(), marketValueBase: z.number(), unrealizedPnlBase: z.number(),
  valuationCurrency: z.string(), unrealizedPnlPct: z.number().nullable().optional(), priceSource: z.string().optional(),
  priceProvider: z.string().nullable().optional(), priceDate: z.string().nullable().optional(),
  priceStale: z.boolean().optional(), priceAvailable: z.boolean().optional(), dataQuality: z.string().optional(),
  limitations: z.array(z.string()).optional(),
}).passthrough();
const portfolioAccountSnapshotSchema = z.object({
  accountId: z.number(), accountName: z.string(), asOf: z.string(), baseCurrency: z.string(), costMethod: z.string(),
  market: z.string(), feeTotal: z.number(), fxStale: z.boolean(), realizedPnl: z.number(), taxTotal: z.number(),
  totalCash: z.number(), totalEquity: z.number(), totalMarketValue: z.number(), unrealizedPnl: z.number(),
  ownerId: z.string().nullable().optional(), broker: z.string().nullable().optional(), dataQuality: z.string().optional(),
  limitations: z.array(z.string()).optional(), positions: z.array(portfolioPositionItemSchema).optional(),
}).passthrough();
const portfolioSnapshotResponseSchema = z.object({
  asOf: z.string(), costMethod: z.string(), currency: z.string(), accountCount: z.number(),
  totalCash: z.number(), totalMarketValue: z.number(), totalEquity: z.number(), realizedPnl: z.number(),
  unrealizedPnl: z.number(), feeTotal: z.number(), taxTotal: z.number(), fxStale: z.boolean(),
  dataQuality: z.string().optional(), limitations: z.array(z.string()).optional(),
  accounts: z.array(portfolioAccountSnapshotSchema).optional(),
}).passthrough();
const portfolioDeleteResponseSchema = z.object({ deleted: z.number() }).passthrough();
const portfolioEventCreatedResponseSchema = z.object({ id: z.number() }).passthrough();
const paperTradeCreatedResponseSchema = z.object({ id: z.number(), price: z.number(), priceSource: z.string() }).passthrough();
const portfolioRiskResponseSchema = z.object({
  asOf: z.string(), costMethod: z.string(), currency: z.string(), accountId: z.number().nullable().optional(),
  concentration: z.record(z.string(), z.unknown()).optional(), sectorConcentration: z.record(z.string(), z.unknown()).optional(),
  drawdown: z.record(z.string(), z.unknown()).optional(), stopLoss: z.record(z.string(), z.unknown()).optional(),
  thresholds: z.record(z.string(), z.unknown()).optional(), decisionSignalRisk: z.unknown().optional(),
}).passthrough();
const portfolioFxRefreshResponseSchema = z.object({
  asOf: z.string(), accountCount: z.number(), refreshEnabled: z.boolean(), pairCount: z.number(),
  updatedCount: z.number(), staleCount: z.number(), errorCount: z.number(),
  disabledReason: z.string().nullable().optional(),
}).passthrough();
const portfolioTradeListItemSchema = z.object({
  id: z.number(), accountId: z.number(), symbol: z.string(), market: z.string(), currency: z.string(),
  tradeDate: z.string(), side: z.string(), quantity: z.number(), price: z.number(), fee: z.number(), tax: z.number(),
  tradeUid: z.string().nullable().optional(), note: z.string().nullable().optional(), createdAt: z.string().nullable().optional(),
}).passthrough();
const portfolioTradeListResponseSchema = z.object({
  total: z.number(), page: z.number(), pageSize: z.number(), items: z.array(portfolioTradeListItemSchema).optional(),
}).passthrough();
const portfolioCashLedgerListItemSchema = z.object({
  id: z.number(), accountId: z.number(), eventDate: z.string(), direction: z.string(), amount: z.number(),
  currency: z.string(), note: z.string().nullable().optional(), createdAt: z.string().nullable().optional(),
}).passthrough();
const portfolioCashLedgerListResponseSchema = z.object({
  total: z.number(), page: z.number(), pageSize: z.number(), items: z.array(portfolioCashLedgerListItemSchema).optional(),
}).passthrough();
const portfolioCorporateActionListItemSchema = z.object({
  id: z.number(), accountId: z.number(), symbol: z.string(), market: z.string(), currency: z.string(),
  effectiveDate: z.string(), actionType: z.string(), cashDividendPerShare: z.number().nullable().optional(),
  splitRatio: z.number().nullable().optional(), note: z.string().nullable().optional(), createdAt: z.string().nullable().optional(),
}).passthrough();
const portfolioCorporateActionListResponseSchema = z.object({
  total: z.number(), page: z.number(), pageSize: z.number(), items: z.array(portfolioCorporateActionListItemSchema).optional(),
}).passthrough();
const portfolioImportBrokerItemSchema = z.object({
  broker: z.string(), aliases: z.array(z.string()).optional(), displayName: z.string().nullable().optional(),
}).passthrough();
const portfolioImportBrokerListResponseSchema = z.object({ brokers: z.array(portfolioImportBrokerItemSchema).optional() }).passthrough();
const portfolioImportTradeItemSchema = z.object({
  tradeDate: z.string(), symbol: z.string(), side: z.string(), quantity: z.number(), price: z.number(),
  fee: z.number(), tax: z.number(), dedupHash: z.string(), tradeUid: z.string().nullable().optional(),
  currency: z.string().nullable().optional(),
}).passthrough();
const portfolioImportParseResponseSchema = z.object({
  broker: z.string(), recordCount: z.number(), skippedCount: z.number(), errorCount: z.number(),
  records: z.array(portfolioImportTradeItemSchema).optional(), errors: z.array(z.string()).optional(),
}).passthrough();
const portfolioImportCommitResponseSchema = z.object({
  accountId: z.number(), recordCount: z.number(), insertedCount: z.number(), duplicateCount: z.number(),
  failedCount: z.number(), dryRun: z.boolean(), errors: z.array(z.string()).optional(),
}).passthrough();
const taskAcceptedSchema = z.object({
  taskId: z.string(), status: z.string(), analysisPhase: z.string().optional(),
  message: z.string().nullable().optional(), messageCode: z.string().optional(),
  messageParams: z.record(z.string(), z.unknown()).optional(),
}).passthrough();

function parseCamelCasePayload<T>(
  data: unknown,
  schema: z.ZodTypeAny,
  label: string,
): T {
  const camel = toCamelCase<unknown>(data);
  const result = schema.safeParse(camel);
  if (!result.success) {
    const issueSummary = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
      .join('; ');
    if (import.meta.env.DEV) {
      console.error(`[portfolio] response validation failed (${label})`, result.error.issues);
    }
    throw createApiError(
      createParsedApiError({
        title: '响应校验失败',
        message: `接口响应未通过校验（${label}）。${issueSummary}`,
        rawMessage: result.error.message,
        category: 'unknown',
        code: 'api_response_validation_failed',
        params: { label, issues: issueSummary },
        details: result.error.issues,
      }),
    );
  }
  return camel as T;
}

function withDefaultArrayItems<T extends { items?: unknown[] }>(payload: T): T & { items: NonNullable<T['items']> } {
  if (!Array.isArray(payload.items)) return { ...payload, items: [] as NonNullable<T['items']> };
  return payload as T & { items: NonNullable<T['items']> };
}

type SnapshotQuery = {
  accountId?: number;
  asOf?: string;
  costMethod?: PortfolioCostMethod;
  includeRealtime?: boolean;
};

type FxRefreshQuery = {
  accountId?: number;
  asOf?: string;
};

type EventQuery = {
  accountId?: number;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
};

type TradeListQuery = EventQuery & {
  symbol?: string;
  side?: 'buy' | 'sell';
};

type CashListQuery = EventQuery & {
  direction?: 'in' | 'out';
};

type CorporateListQuery = EventQuery & {
  symbol?: string;
  actionType?: 'cash_dividend' | 'split_adjustment';
};

function buildSnapshotParams(query: SnapshotQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  if (query.costMethod) {
    params.cost_method = query.costMethod;
  }
  if (query.includeRealtime !== undefined) {
    params.include_realtime = query.includeRealtime ? 'true' : 'false';
  }
  return params;
}

function buildFxRefreshParams(query: FxRefreshQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.asOf) {
    params.as_of = query.asOf;
  }
  return params;
}

function buildEventParams(query: EventQuery): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (query.accountId != null) {
    params.account_id = query.accountId;
  }
  if (query.dateFrom) {
    params.date_from = query.dateFrom;
  }
  if (query.dateTo) {
    params.date_to = query.dateTo;
  }
  if (query.page != null) {
    params.page = query.page;
  }
  if (query.pageSize != null) {
    params.page_size = query.pageSize;
  }
  return params;
}

export const portfolioApi = {
  async getAccounts(includeInactive = false): Promise<PortfolioAccountListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/accounts', {
      params: { include_inactive: includeInactive },
    });
    const parsed = parseCamelCasePayload<PortfolioAccountListResponse>(response.data, portfolioAccountListResponseSchema, 'PortfolioAccountListResponse');
    if (!Array.isArray(parsed.accounts)) return { ...parsed, accounts: [] };
    return parsed;
  },

  async createAccount(payload: PortfolioAccountCreateRequest): Promise<PortfolioAccountItem> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/accounts', {
      name: payload.name,
      broker: payload.broker,
      market: payload.market,
      base_currency: payload.baseCurrency,
      owner_id: payload.ownerId,
      account_type: payload.accountType ?? 'real',
    });
    return parseCamelCasePayload<PortfolioAccountItem>(response.data, portfolioAccountItemSchema, 'PortfolioAccountItem');
  },

  async updateAccount(accountId: number, payload: PortfolioAccountUpdateRequest): Promise<PortfolioAccountItem> {
    const body: Record<string, unknown> = {};
    if (payload.name !== undefined) body.name = payload.name;
    if (payload.broker !== undefined) body.broker = payload.broker;
    if (payload.market !== undefined) body.market = payload.market;
    if (payload.baseCurrency !== undefined) body.base_currency = payload.baseCurrency;
    if (payload.ownerId !== undefined) body.owner_id = payload.ownerId;
    if (payload.isActive !== undefined) body.is_active = payload.isActive;
    const response = await apiClient.put<Record<string, unknown>>(
      `/api/v1/portfolio/accounts/${accountId}`,
      body,
    );
    return parseCamelCasePayload<PortfolioAccountItem>(response.data, portfolioAccountItemSchema, 'PortfolioAccountItem');
  },

  async deleteAccount(accountId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/accounts/${accountId}`);
    return parseCamelCasePayload<PortfolioDeleteResponse>(response.data, portfolioDeleteResponseSchema, 'PortfolioDeleteResponse');
  },

  async getSnapshot(query: SnapshotQuery = {}): Promise<PortfolioSnapshotResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/snapshot', {
      params: buildSnapshotParams(query),
    });
    const parsed = parseCamelCasePayload<PortfolioSnapshotResponse>(response.data, portfolioSnapshotResponseSchema, 'PortfolioSnapshotResponse');
    if (!Array.isArray(parsed.accounts)) return { ...parsed, accounts: [] };
    return parsed;
  },

  async analyzePosition(symbol: string, payload: PortfolioPositionAnalysisRequest = {}): Promise<TaskAccepted> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/portfolio/positions/${encodeURIComponent(symbol)}/analysis`,
      {
        account_id: payload.accountId,
        analysis_phase: payload.analysisPhase ?? 'auto',
        force: payload.force ?? false,
      },
    );
    return parseCamelCasePayload<TaskAccepted>(response.data, taskAcceptedSchema, 'TaskAccepted');
  },

  async getRisk(query: SnapshotQuery = {}): Promise<PortfolioRiskResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/risk', {
      params: buildSnapshotParams(query),
    });
    return parseCamelCasePayload<PortfolioRiskResponse>(response.data, portfolioRiskResponseSchema, 'PortfolioRiskResponse');
  },

  async refreshFx(query: FxRefreshQuery = {}): Promise<PortfolioFxRefreshResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/fx/refresh', undefined, {
      params: buildFxRefreshParams(query),
    });
    return parseCamelCasePayload<PortfolioFxRefreshResponse>(response.data, portfolioFxRefreshResponseSchema, 'PortfolioFxRefreshResponse');
  },

  async createTrade(payload: PortfolioTradeCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/trades', {
      operation_id: payload.operationId,
      account_id: payload.accountId,
      symbol: payload.symbol,
      trade_date: payload.tradeDate,
      side: payload.side,
      quantity: payload.quantity,
      price: payload.price,
      fee: payload.fee ?? 0,
      tax: payload.tax ?? 0,
      market: payload.market,
      currency: payload.currency,
      trade_uid: payload.tradeUid,
      note: payload.note,
    }, { headers: { 'Idempotency-Key': payload.operationId } });
    return parseCamelCasePayload<PortfolioEventCreatedResponse>(response.data, portfolioEventCreatedResponseSchema, 'PortfolioEventCreatedResponse');
  },

  async createPaperTrade(
    accountId: number,
    payload: PaperTradeCreateRequest,
  ): Promise<PaperTradeCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/portfolio/accounts/${accountId}/paper-trades`,
      {
        operation_id: payload.operationId,
        symbol: payload.symbol,
        trade_date: payload.tradeDate,
        side: payload.side,
        quantity: payload.quantity,
        ...(payload.price !== undefined ? { price: payload.price } : {}),
        ...(payload.note !== undefined ? { note: payload.note } : {}),
      },
      { headers: { 'Idempotency-Key': payload.operationId } },
    );
    return parseCamelCasePayload<PaperTradeCreatedResponse>(response.data, paperTradeCreatedResponseSchema, 'PaperTradeCreatedResponse');
  },

  async deleteTrade(tradeId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/trades/${tradeId}`);
    return parseCamelCasePayload<PortfolioDeleteResponse>(response.data, portfolioDeleteResponseSchema, 'PortfolioDeleteResponse');
  },

  async createCashLedger(payload: PortfolioCashLedgerCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/cash-ledger', {
      operation_id: payload.operationId,
      account_id: payload.accountId,
      event_date: payload.eventDate,
      direction: payload.direction,
      amount: payload.amount,
      currency: payload.currency,
      note: payload.note,
    }, { headers: { 'Idempotency-Key': payload.operationId } });
    return parseCamelCasePayload<PortfolioEventCreatedResponse>(response.data, portfolioEventCreatedResponseSchema, 'PortfolioEventCreatedResponse');
  },

  async deleteCashLedger(entryId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/cash-ledger/${entryId}`);
    return parseCamelCasePayload<PortfolioDeleteResponse>(response.data, portfolioDeleteResponseSchema, 'PortfolioDeleteResponse');
  },

  async createCorporateAction(payload: PortfolioCorporateActionCreateRequest): Promise<PortfolioEventCreatedResponse> {
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/corporate-actions', {
      operation_id: payload.operationId,
      account_id: payload.accountId,
      symbol: payload.symbol,
      effective_date: payload.effectiveDate,
      action_type: payload.actionType,
      market: payload.market,
      currency: payload.currency,
      cash_dividend_per_share: payload.cashDividendPerShare,
      split_ratio: payload.splitRatio,
      note: payload.note,
    }, { headers: { 'Idempotency-Key': payload.operationId } });
    return parseCamelCasePayload<PortfolioEventCreatedResponse>(response.data, portfolioEventCreatedResponseSchema, 'PortfolioEventCreatedResponse');
  },

  async deleteCorporateAction(actionId: number): Promise<PortfolioDeleteResponse> {
    const response = await apiClient.delete<Record<string, unknown>>(`/api/v1/portfolio/corporate-actions/${actionId}`);
    return parseCamelCasePayload<PortfolioDeleteResponse>(response.data, portfolioDeleteResponseSchema, 'PortfolioDeleteResponse');
  },

  async listTrades(query: TradeListQuery = {}): Promise<PortfolioTradeListResponse> {
    const params = buildEventParams(query);
    if (query.symbol) {
      params.symbol = query.symbol;
    }
    if (query.side) {
      params.side = query.side;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/trades', { params });
    return withDefaultArrayItems(parseCamelCasePayload<PortfolioTradeListResponse>(response.data, portfolioTradeListResponseSchema, 'PortfolioTradeListResponse'));
  },

  async listCashLedger(query: CashListQuery = {}): Promise<PortfolioCashLedgerListResponse> {
    const params = buildEventParams(query);
    if (query.direction) {
      params.direction = query.direction;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/cash-ledger', { params });
    return withDefaultArrayItems(parseCamelCasePayload<PortfolioCashLedgerListResponse>(response.data, portfolioCashLedgerListResponseSchema, 'PortfolioCashLedgerListResponse'));
  },

  async listCorporateActions(query: CorporateListQuery = {}): Promise<PortfolioCorporateActionListResponse> {
    const params = buildEventParams(query);
    if (query.symbol) {
      params.symbol = query.symbol;
    }
    if (query.actionType) {
      params.action_type = query.actionType;
    }
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/corporate-actions', { params });
    return withDefaultArrayItems(parseCamelCasePayload<PortfolioCorporateActionListResponse>(response.data, portfolioCorporateActionListResponseSchema, 'PortfolioCorporateActionListResponse'));
  },

  async listImportBrokers(): Promise<PortfolioImportBrokerListResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/portfolio/imports/csv/brokers');
    const parsed = parseCamelCasePayload<PortfolioImportBrokerListResponse>(response.data, portfolioImportBrokerListResponseSchema, 'PortfolioImportBrokerListResponse');
    if (!Array.isArray(parsed.brokers)) return { ...parsed, brokers: [] };
    return parsed;
  },

  async parseCsvImport(broker: string, file: File): Promise<PortfolioImportParseResponse> {
    const formData = new FormData();
    formData.append('broker', broker);
    formData.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/imports/csv/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    const parsed = parseCamelCasePayload<PortfolioImportParseResponse>(response.data, portfolioImportParseResponseSchema, 'PortfolioImportParseResponse');
    return { ...parsed, records: Array.isArray(parsed.records) ? parsed.records : [], errors: Array.isArray(parsed.errors) ? parsed.errors : [] };
  },

  async commitCsvImport(
    accountId: number,
    broker: string,
    file: File,
    operationId: string,
    dryRun = false,
  ): Promise<PortfolioImportCommitResponse> {
    const formData = new FormData();
    formData.append('account_id', String(accountId));
    formData.append('broker', broker);
    formData.append('dry_run', dryRun ? 'true' : 'false');
    formData.append('operation_id', operationId);
    formData.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/portfolio/imports/csv/commit', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        'Idempotency-Key': operationId,
      },
    });
    const parsed = parseCamelCasePayload<PortfolioImportCommitResponse>(response.data, portfolioImportCommitResponseSchema, 'PortfolioImportCommitResponse');
    if (!Array.isArray(parsed.errors)) return { ...parsed, errors: [] };
    return parsed;
  },
};
