// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, expectTypeOf, it } from 'vitest';
import type { components, operations, paths } from '../api.generated';
import * as Portfolio from '../portfolio';
import type {
  PaperTradeCreateRequest,
  PortfolioAccountCreateRequest,
  PortfolioAccountItem,
  PortfolioAccountListResponse,
  PortfolioAccountSnapshot,
  PortfolioDeleteResponse,
  PortfolioEventCreatedResponse,
  PortfolioRiskResponse,
  PortfolioSnapshotResponse,
  PortfolioTradeCreateRequest,
} from '../portfolio';

type OpenApiAccount = components['schemas']['PortfolioAccountItem'];
type OpenApiAccountList = components['schemas']['PortfolioAccountListResponse'];
type OpenApiCreate = components['schemas']['PortfolioAccountCreateRequest'];
type OpenApiUpdate = components['schemas']['PortfolioAccountUpdateRequest'];
type OpenApiAccountSnapshot = components['schemas']['PortfolioAccountSnapshot'];
type OpenApiSnapshot = components['schemas']['PortfolioSnapshotResponse'];
type OpenApiRisk = components['schemas']['PortfolioRiskResponse'];
type OpenApiTrade = components['schemas']['PortfolioTradeCreateRequest'];
type OpenApiTradeList = components['schemas']['PortfolioTradeListResponse'];
type OpenApiEventCreated = components['schemas']['PortfolioEventCreatedResponse'];
type OpenApiDelete = components['schemas']['PortfolioDeleteResponse'];
type OpenApiPaperTrade = components['schemas']['PaperTradeCreateRequest'];
type OpenApiPaperQuality = components['schemas']['PaperDecisionQualityResponse'];

type OpenApiListOp = operations['list_accounts_api_v1_portfolio_accounts_get'];
type OpenApiCreateOp = operations['create_account_api_v1_portfolio_accounts_post'];
type OpenApiUpdateOp = operations['update_account_api_v1_portfolio_accounts__account_id__put'];
type OpenApiSnapshotOp = operations['get_snapshot_api_v1_portfolio_snapshot_get'];
type OpenApiRiskOp = operations['get_risk_report_api_v1_portfolio_risk_get'];
type OpenApiTradeListOp = operations['list_trades_api_v1_portfolio_trades_get'];
type OpenApiTradeCreateOp = operations['create_trade_api_v1_portfolio_trades_post'];
type OpenApiTradeDeleteOp = operations['delete_trade_api_v1_portfolio_trades__trade_id__delete'];
type OpenApiCashListOp = operations['list_cash_ledger_api_v1_portfolio_cash_ledger_get'];
type OpenApiBrokersOp = operations['list_csv_brokers_api_v1_portfolio_imports_csv_brokers_get'];
type OpenApiParseOp = operations['parse_csv_import_api_v1_portfolio_imports_csv_parse_post'];
type OpenApiCommitOp = operations['commit_csv_import_api_v1_portfolio_imports_csv_commit_post'];
type OpenApiFutuCommitOp = operations['commit_futu_import_api_v1_portfolio_imports_futu_post'];
type OpenApiPaperTradeOp = operations['create_paper_trade_api_v1_portfolio_accounts__account_id__paper_trades_post'];
type OpenApiPaperQualityOp = operations['getPaperDecisionQuality'];

type OpenApiListPathGet = paths['/api/v1/portfolio/accounts']['get'];
type OpenApiCreatePathPost = paths['/api/v1/portfolio/accounts']['post'];
type OpenApiUpdatePathPut = paths['/api/v1/portfolio/accounts/{account_id}']['put'];
type OpenApiSnapshotPathGet = paths['/api/v1/portfolio/snapshot']['get'];
type OpenApiRiskPathGet = paths['/api/v1/portfolio/risk']['get'];
type OpenApiTradeListPathGet = paths['/api/v1/portfolio/trades']['get'];
type OpenApiTradeCreatePathPost = paths['/api/v1/portfolio/trades']['post'];
type OpenApiTradeDeletePathDelete = paths['/api/v1/portfolio/trades/{trade_id}']['delete'];
type OpenApiPaperQualityPathGet = paths['/api/v1/portfolio/accounts/{account_id}/paper-decision-quality']['get'];

type OpenApiListGet200 = OpenApiListOp['responses']['200']['content']['application/json'];
type OpenApiCreatePost200 = OpenApiCreateOp['responses']['200']['content']['application/json'];
type OpenApiCreateBody = OpenApiCreateOp['requestBody']['content']['application/json'];
type OpenApiUpdatePut200 = OpenApiUpdateOp['responses']['200']['content']['application/json'];
type OpenApiUpdateBody = OpenApiUpdateOp['requestBody']['content']['application/json'];
type OpenApiSnapshotGet200 = OpenApiSnapshotOp['responses']['200']['content']['application/json'];
type OpenApiRiskGet200 = OpenApiRiskOp['responses']['200']['content']['application/json'];
type OpenApiTradeListGet200 = OpenApiTradeListOp['responses']['200']['content']['application/json'];
type OpenApiTradeCreatePost200 = OpenApiTradeCreateOp['responses']['200']['content']['application/json'];
type OpenApiTradeCreateBody = OpenApiTradeCreateOp['requestBody']['content']['application/json'];
type OpenApiTradeDeleteDelete200 = OpenApiTradeDeleteOp['responses']['200']['content']['application/json'];
type OpenApiParsePost200 = OpenApiParseOp['responses']['200']['content']['application/json'];
type OpenApiCommitPost200 = OpenApiCommitOp['responses']['200']['content']['application/json'];
type OpenApiFutuCommitPost200 = OpenApiFutuCommitOp['responses']['200']['content']['application/json'];
type OpenApiPaperTradePost200 = OpenApiPaperTradeOp['responses']['200']['content']['application/json'];
type OpenApiPaperQualityGet200 = OpenApiPaperQualityOp['responses']['200']['content']['application/json'];

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type _Assert<T extends true> = T;
type IsOptional<T, K extends keyof T> = Partial<Pick<T, K>> extends Pick<T, K> ? true : false;

type _BoundComponents = _Assert<
  (
    | 'PortfolioAccountItem'
    | 'PortfolioAccountCreateRequest'
    | 'PortfolioAccountListResponse'
    | 'PortfolioAccountUpdateRequest'
    | 'PortfolioAccountSnapshot'
    | 'PortfolioSnapshotResponse'
    | 'PortfolioPositionItem'
    | 'PortfolioRiskResponse'
    | 'PortfolioDecisionSignalRiskBlock'
    | 'PortfolioDecisionSignalRiskItem'
    | 'PortfolioTradeCreateRequest'
    | 'PortfolioTradeListResponse'
    | 'PortfolioEventCreatedResponse'
    | 'PortfolioDeleteResponse'
    | 'PortfolioImportParseResponse'
    | 'PaperTradeCreateRequest'
    | 'PaperDecisionQualityResponse'
  ) extends keyof components['schemas'] ? true : false
>;

type _List200IsList = _Assert<OpenApiListGet200 extends OpenApiAccountList ? true : false>;
type _ListIsList200 = _Assert<OpenApiAccountList extends OpenApiListGet200 ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiListPathGet ? true : false>;
type _PathIsListOp = _Assert<OpenApiListPathGet extends OpenApiListOp ? true : false>;
type _ListGetNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _ListHas200 = _Assert<200 extends keyof OpenApiListOp['responses'] ? true : false>;
type _ListLacks201 = _Assert<201 extends keyof OpenApiListOp['responses'] ? false : true>;
type _Create200IsAccount = _Assert<OpenApiCreatePost200 extends OpenApiAccount ? true : false>;
type _AccountIsCreate200 = _Assert<OpenApiAccount extends OpenApiCreatePost200 ? true : false>;
type _CreateBodyIsRequest = _Assert<OpenApiCreateBody extends OpenApiCreate ? true : false>;
type _RequestIsCreateBody = _Assert<OpenApiCreate extends OpenApiCreateBody ? true : false>;
type _Update200IsAccount = _Assert<OpenApiUpdatePut200 extends OpenApiAccount ? true : false>;
type _UpdateBodyIsUpdate = _Assert<OpenApiUpdateBody extends OpenApiUpdate ? true : false>;
type _Snapshot200IsSnapshot = _Assert<OpenApiSnapshotGet200 extends OpenApiSnapshot ? true : false>;
type _SnapshotGetNeverRequestBody = _Assert<OpenApiSnapshotOp extends { requestBody?: never } ? true : false>;
type _Risk200IsRisk = _Assert<OpenApiRiskGet200 extends OpenApiRisk ? true : false>;
type _RiskGetNeverRequestBody = _Assert<OpenApiRiskOp extends { requestBody?: never } ? true : false>;
type _TradeList200IsTradeList = _Assert<OpenApiTradeListGet200 extends OpenApiTradeList ? true : false>;
type _TradeListGetNeverRequestBody = _Assert<OpenApiTradeListOp extends { requestBody?: never } ? true : false>;
type _TradeCreate200IsEvent = _Assert<OpenApiTradeCreatePost200 extends OpenApiEventCreated ? true : false>;
type _TradeCreateBodyIsTrade = _Assert<OpenApiTradeCreateBody extends OpenApiTrade ? true : false>;
type _TradeDelete200IsDelete = _Assert<OpenApiTradeDeleteDelete200 extends OpenApiDelete ? true : false>;
type _Parse200IsParse = _Assert<OpenApiParsePost200 extends components['schemas']['PortfolioImportParseResponse'] ? true : false>;
type _Commit200IsCommit = _Assert<OpenApiCommitPost200 extends components['schemas']['PortfolioImportCommitResponse'] ? true : false>;
type _FutuCommit200IsCommit = _Assert<OpenApiFutuCommitPost200 extends components['schemas']['PortfolioImportCommitResponse'] ? true : false>;
type _PaperTrade200IsCreated = _Assert<OpenApiPaperTradePost200 extends components['schemas']['PaperTradeCreatedResponse'] ? true : false>;
type _PaperQuality200IsQuality = _Assert<OpenApiPaperQualityGet200 extends OpenApiPaperQuality ? true : false>;
type _PaperQualityGetNeverRequestBody = _Assert<OpenApiPaperQualityOp extends { requestBody?: never } ? true : false>;
type _CashListGetNeverRequestBody = _Assert<OpenApiCashListOp extends { requestBody?: never } ? true : false>;
type _BrokersGetNeverRequestBody = _Assert<OpenApiBrokersOp extends { requestBody?: never } ? true : false>;

type _PublicAccountNotPath200 = _Assert<PortfolioAccountItem extends OpenApiCreatePost200 ? false : true>;
type _Path200NotPublicAccount = _Assert<OpenApiCreatePost200 extends PortfolioAccountItem ? false : true>;
type _PublicListNotPath200 = _Assert<PortfolioAccountListResponse extends OpenApiListGet200 ? false : true>;
type _Path200NotPublicList = _Assert<OpenApiListGet200 extends PortfolioAccountListResponse ? false : true>;
type _PublicSnapshotNotPath200 = _Assert<PortfolioSnapshotResponse extends OpenApiSnapshotGet200 ? false : true>;
type _Path200NotPublicSnapshot = _Assert<OpenApiSnapshotGet200 extends PortfolioSnapshotResponse ? false : true>;
type _PublicRiskNotPath200 = _Assert<PortfolioRiskResponse extends OpenApiRiskGet200 ? false : true>;
type _Path200NotPublicRisk = _Assert<OpenApiRiskGet200 extends PortfolioRiskResponse ? false : true>;
type _PublicDeleteIsPath200 = _Assert<PortfolioDeleteResponse extends OpenApiTradeDeleteDelete200 ? true : false>;
type _Path200IsPublicDelete = _Assert<OpenApiTradeDeleteDelete200 extends PortfolioDeleteResponse ? true : false>;
type _PublicEventIsPath200 = _Assert<PortfolioEventCreatedResponse extends OpenApiTradeCreatePost200 ? true : false>;
type _Path200IsPublicEvent = _Assert<OpenApiTradeCreatePost200 extends PortfolioEventCreatedResponse ? true : false>;

type _UiHasAccountType = _Assert<'accountType' extends keyof PortfolioAccountItem ? true : false>;
type _UiHasBaseCurrency = _Assert<'baseCurrency' extends keyof PortfolioAccountItem ? true : false>;
type _UiHasCostMethod = _Assert<'costMethod' extends keyof PortfolioSnapshotResponse ? true : false>;
type _UiHasOperationId = _Assert<'operationId' extends keyof PortfolioTradeCreateRequest ? true : false>;
type _UiLacksAccountTypeSnake = _Assert<'account_type' extends keyof PortfolioAccountItem ? false : true>;
type _UiLacksBaseCurrencySnake = _Assert<'base_currency' extends keyof PortfolioAccountItem ? false : true>;
type _UiLacksCostMethodSnake = _Assert<'cost_method' extends keyof PortfolioSnapshotResponse ? false : true>;
type _UiLacksOperationIdSnake = _Assert<'operation_id' extends keyof PortfolioTradeCreateRequest ? false : true>;
type _GeneratedHasAccountTypeSnake = _Assert<'account_type' extends keyof OpenApiAccount ? true : false>;
type _GeneratedHasBaseCurrencySnake = _Assert<'base_currency' extends keyof OpenApiAccount ? true : false>;
type _GeneratedHasCostMethodSnake = _Assert<'cost_method' extends keyof OpenApiSnapshot ? true : false>;
type _GeneratedHasOperationIdSnake = _Assert<'operation_id' extends keyof OpenApiTrade ? true : false>;
type _GeneratedLacksAccountTypeCamel = _Assert<'accountType' extends keyof OpenApiAccount ? false : true>;
type _GeneratedLacksBaseCurrencyCamel = _Assert<'baseCurrency' extends keyof OpenApiAccount ? false : true>;
type _GeneratedLacksCostMethodCamel = _Assert<'costMethod' extends keyof OpenApiSnapshot ? false : true>;
type _GeneratedLacksOperationIdCamel = _Assert<'operationId' extends keyof OpenApiTrade ? false : true>;

type _UiAccountTypeOptional = _Assert<IsOptional<PortfolioAccountItem, 'accountType'>>;
type _UiCreateAccountTypeOptional = _Assert<IsOptional<PortfolioAccountCreateRequest, 'accountType'>>;
type _NaiveAccountTypeRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiAccount>, 'accountType'> extends false ? true : false
>;
type _NaiveCreateAccountTypeRequired = _Assert<
  IsOptional<CamelizeKeys<OpenApiCreate>, 'accountType'> extends false ? true : false
>;
type _UiFeeOptional = _Assert<IsOptional<PortfolioTradeCreateRequest, 'fee'>>;
type _UiTaxOptional = _Assert<IsOptional<PortfolioTradeCreateRequest, 'tax'>>;
type _NaiveFeeRequired = _Assert<IsOptional<CamelizeKeys<OpenApiTrade>, 'fee'> extends false ? true : false>;
type _NaiveTaxRequired = _Assert<IsOptional<CamelizeKeys<OpenApiTrade>, 'tax'> extends false ? true : false>;
type _UiOperationIdRequired = _Assert<
  IsOptional<PortfolioTradeCreateRequest, 'operationId'> extends false ? true : false
>;
type _NaiveOperationIdOptional = _Assert<IsOptional<CamelizeKeys<OpenApiTrade>, 'operationId'>>;
type _UiPaperOperationIdRequired = _Assert<
  IsOptional<PaperTradeCreateRequest, 'operationId'> extends false ? true : false
>;
type _NaivePaperOperationIdOptional = _Assert<IsOptional<CamelizeKeys<OpenApiPaperTrade>, 'operationId'>>;
type _UiListAccountsRequired = _Assert<
  IsOptional<PortfolioAccountListResponse, 'accounts'> extends false ? true : false
>;
type _NaiveListAccountsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiAccountList>, 'accounts'>>;
type _UiSnapshotAccountsRequired = _Assert<
  IsOptional<PortfolioSnapshotResponse, 'accounts'> extends false ? true : false
>;
type _NaiveSnapshotAccountsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiSnapshot>, 'accounts'>>;
type _UiPositionsRequired = _Assert<
  IsOptional<PortfolioAccountSnapshot, 'positions'> extends false ? true : false
>;
type _NaivePositionsOptional = _Assert<IsOptional<CamelizeKeys<OpenApiAccountSnapshot>, 'positions'>>;
type _UiConcentrationRequired = _Assert<
  IsOptional<PortfolioRiskResponse, 'concentration'> extends false ? true : false
>;
type _UiDrawdownRequired = _Assert<IsOptional<PortfolioRiskResponse, 'drawdown'> extends false ? true : false>;
type _UiStopLossRequired = _Assert<IsOptional<PortfolioRiskResponse, 'stopLoss'> extends false ? true : false>;
type _NaiveConcentrationOptional = _Assert<IsOptional<CamelizeKeys<OpenApiRisk>, 'concentration'>>;
type _NaiveDrawdownOptional = _Assert<IsOptional<CamelizeKeys<OpenApiRisk>, 'drawdown'>>;
type _NaiveStopLossOptional = _Assert<IsOptional<CamelizeKeys<OpenApiRisk>, 'stopLoss'>>;

type _CompileTimePins = [
  _BoundComponents,
  _List200IsList,
  _ListIsList200,
  _ListOpIsPath,
  _PathIsListOp,
  _ListGetNeverRequestBody,
  _ListHas200,
  _ListLacks201,
  _Create200IsAccount,
  _AccountIsCreate200,
  _CreateBodyIsRequest,
  _RequestIsCreateBody,
  _Update200IsAccount,
  _UpdateBodyIsUpdate,
  _Snapshot200IsSnapshot,
  _SnapshotGetNeverRequestBody,
  _Risk200IsRisk,
  _RiskGetNeverRequestBody,
  _TradeList200IsTradeList,
  _TradeListGetNeverRequestBody,
  _TradeCreate200IsEvent,
  _TradeCreateBodyIsTrade,
  _TradeDelete200IsDelete,
  _Parse200IsParse,
  _Commit200IsCommit,
  _FutuCommit200IsCommit,
  _PaperTrade200IsCreated,
  _PaperQuality200IsQuality,
  _PaperQualityGetNeverRequestBody,
  _CashListGetNeverRequestBody,
  _BrokersGetNeverRequestBody,
  _PublicAccountNotPath200,
  _Path200NotPublicAccount,
  _PublicListNotPath200,
  _Path200NotPublicList,
  _PublicSnapshotNotPath200,
  _Path200NotPublicSnapshot,
  _PublicRiskNotPath200,
  _Path200NotPublicRisk,
  _PublicDeleteIsPath200,
  _Path200IsPublicDelete,
  _PublicEventIsPath200,
  _Path200IsPublicEvent,
  _UiHasAccountType,
  _UiHasBaseCurrency,
  _UiHasCostMethod,
  _UiHasOperationId,
  _UiLacksAccountTypeSnake,
  _UiLacksBaseCurrencySnake,
  _UiLacksCostMethodSnake,
  _UiLacksOperationIdSnake,
  _GeneratedHasAccountTypeSnake,
  _GeneratedHasBaseCurrencySnake,
  _GeneratedHasCostMethodSnake,
  _GeneratedHasOperationIdSnake,
  _GeneratedLacksAccountTypeCamel,
  _GeneratedLacksBaseCurrencyCamel,
  _GeneratedLacksCostMethodCamel,
  _GeneratedLacksOperationIdCamel,
  _UiAccountTypeOptional,
  _UiCreateAccountTypeOptional,
  _NaiveAccountTypeRequired,
  _NaiveCreateAccountTypeRequired,
  _UiFeeOptional,
  _UiTaxOptional,
  _NaiveFeeRequired,
  _NaiveTaxRequired,
  _UiOperationIdRequired,
  _NaiveOperationIdOptional,
  _UiPaperOperationIdRequired,
  _NaivePaperOperationIdOptional,
  _UiListAccountsRequired,
  _NaiveListAccountsOptional,
  _UiSnapshotAccountsRequired,
  _NaiveSnapshotAccountsOptional,
  _UiPositionsRequired,
  _NaivePositionsOptional,
  _UiConcentrationRequired,
  _UiDrawdownRequired,
  _UiStopLossRequired,
  _NaiveConcentrationOptional,
  _NaiveDrawdownOptional,
  _NaiveStopLossOptional,
];

const accountBase = {
  id: 1,
  name: 'Main',
  market: 'us' as const,
  baseCurrency: 'USD',
  isActive: true,
};

const createBase = {
  name: 'Main',
  market: 'us' as const,
  baseCurrency: 'USD',
};

const tradeBase = {
  operationId: 'op-1',
  accountId: 1,
  symbol: 'AAPL',
  tradeDate: '2026-07-15',
  side: 'buy' as const,
  quantity: 10,
  price: 200,
};

const tradeMissingOp = {
  accountId: 1,
  symbol: 'AAPL',
  tradeDate: '2026-07-15',
  side: 'buy' as const,
  quantity: 10,
  price: 200,
  fee: 0,
  tax: 0,
};

const snapshotMissingAccounts = {
  asOf: '2026-07-15',
  costMethod: 'avg' as const,
  currency: 'USD',
  accountCount: 0,
  totalCash: 0,
  totalMarketValue: 0,
  totalEquity: 0,
  realizedPnl: 0,
  unrealizedPnl: 0,
  feeTotal: 0,
  taxTotal: 0,
  fxStale: false,
  dataQuality: 'ok',
};

const accountSnapshotMissingPositions = {
  accountId: 1,
  accountName: 'Main',
  market: 'us',
  baseCurrency: 'USD',
  asOf: '2026-07-15',
  costMethod: 'avg' as const,
  totalCash: 0,
  totalMarketValue: 0,
  totalEquity: 0,
  realizedPnl: 0,
  unrealizedPnl: 0,
  feeTotal: 0,
  taxTotal: 0,
  fxStale: false,
  dataQuality: 'ok',
};

const riskMissingNested = {
  asOf: '2026-07-15',
  costMethod: 'avg' as const,
  currency: 'USD',
  thresholds: {},
};

const riskBase = {
  asOf: '2026-07-15',
  costMethod: 'avg' as const,
  currency: 'USD',
  thresholds: {},
  concentration: {
    totalMarketValue: 1,
    topWeightPct: 1,
    alert: false,
    topPositions: [] as PortfolioRiskResponse['concentration']['topPositions'],
  },
  sectorConcentration: {
    totalMarketValue: 1,
    topWeightPct: 1,
    alert: false,
    topSectors: [] as PortfolioRiskResponse['sectorConcentration']['topSectors'],
    coverage: {},
    errors: [] as string[],
  },
  drawdown: {
    seriesPoints: 0,
    maxDrawdownPct: 0,
    currentDrawdownPct: 0,
    alert: false,
    fxStale: false,
  },
  stopLoss: {
    nearAlert: false,
    triggeredCount: 0,
    nearCount: 0,
    items: [] as PortfolioRiskResponse['stopLoss']['items'],
  },
};

const uiAccount: PortfolioAccountItem = accountBase;
void uiAccount;
const uiCreate: PortfolioAccountCreateRequest = createBase;
void uiCreate;
const uiTrade: PortfolioTradeCreateRequest = tradeBase;
void uiTrade;
const uiPaperTrade: PaperTradeCreateRequest = {
  operationId: 'op-1',
  symbol: 'AAPL',
  tradeDate: '2026-07-15',
  side: 'buy',
  quantity: 10,
};
void uiPaperTrade;
const uiRisk: PortfolioRiskResponse = riskBase;
void uiRisk;
const uiDelete: PortfolioDeleteResponse = { deleted: 1 };
void uiDelete;
const uiEvent: PortfolioEventCreatedResponse = { id: 1 };
void uiEvent;

// @ts-expect-error naive account requires generated-default accountType
const naiveAccount: CamelizeKeys<OpenApiAccount> = accountBase;
void naiveAccount;

// @ts-expect-error naive create requires generated-default accountType
const naiveCreate: CamelizeKeys<OpenApiCreate> = createBase;
void naiveCreate;

// @ts-expect-error naive trade requires generated-default fee and tax
const naiveTrade: CamelizeKeys<OpenApiTrade> = tradeBase;
void naiveTrade;

const naiveTradeMissingOp: CamelizeKeys<OpenApiTrade> = tradeMissingOp;
void naiveTradeMissingOp;
// @ts-expect-error public trade operationId is required
const publicTradeMissingOp: PortfolioTradeCreateRequest = tradeMissingOp;
void publicTradeMissingOp;

const naiveListMissing: CamelizeKeys<OpenApiAccountList> = {};
void naiveListMissing;
// @ts-expect-error public account list accounts is required
const publicListMissing: PortfolioAccountListResponse = {};
void publicListMissing;

const naiveSnapshotMissing: CamelizeKeys<OpenApiSnapshot> = snapshotMissingAccounts;
void naiveSnapshotMissing;
// @ts-expect-error public snapshot accounts is required
const publicSnapshotMissing: PortfolioSnapshotResponse = snapshotMissingAccounts;
void publicSnapshotMissing;

const naivePositionsMissing: CamelizeKeys<OpenApiAccountSnapshot> = accountSnapshotMissingPositions;
void naivePositionsMissing;
// @ts-expect-error public account snapshot positions is required
const publicPositionsMissing: PortfolioAccountSnapshot = accountSnapshotMissingPositions;
void publicPositionsMissing;

const naiveRiskMissing: CamelizeKeys<OpenApiRisk> = riskMissingNested;
void naiveRiskMissing;
// @ts-expect-error public risk nested blocks are required
const publicRiskMissing: PortfolioRiskResponse = riskMissingNested;
void publicRiskMissing;

// @ts-expect-error futureAccountFlag is not a public account field
const extraAccount: PortfolioAccountItem = { ...accountBase, futureAccountFlag: true };

// @ts-expect-error futureTradeFlag is not a public trade field
const extraTrade: PortfolioTradeCreateRequest = { ...tradeBase, futureTradeFlag: true };

const publicConcExtra: PortfolioRiskResponse['concentration'] = {
  totalMarketValue: 1,
  topWeightPct: 1,
  alert: false,
  topPositions: [],
  // @ts-expect-error futureConcentrationFlag is not a public concentration field
  futureConcentrationFlag: true,
};
void publicConcExtra;

const naiveConcExtra: NonNullable<CamelizeKeys<OpenApiRisk>['concentration']> = {
  totalMarketValue: 1,
  topWeightPct: 1,
  alert: false,
  topPositions: [],
  futureConcentrationFlag: true,
};
void naiveConcExtra;

const actionsExtra: PortfolioRiskResponse['decisionSignalRisk'] = {
  available: true,
  total: 1,
  actions: { sell: 1, futureAction: 2 },
  items: [],
};
void actionsExtra;

// @ts-expect-error account_type is not a public camelCase field
const publicSnake: PortfolioAccountItem = { ...accountBase, account_type: 'real' };

void extraAccount;
void extraTrade;
void publicSnake;

describe('portfolio OpenAPI type bind', () => {
  it('keeps the types module runtime-empty', () => {
    expect({ ...Portfolio }).toEqual({});
    expect(Object.keys(Portfolio)).toEqual([]);
    expect(Object.getOwnPropertyNames(Portfolio)).toEqual([]);
  });

  it('holds compile-time OpenAPI pins that tsc -b enforces', () => {
    type Held = _CompileTimePins[number];
    expectTypeOf<Held>().toEqualTypeOf<true>();
  });

  it('equates path JSON to named generated components, keeps GET requestBody never, and uses 200 not 201', () => {
    expectTypeOf<OpenApiListGet200>().toEqualTypeOf<OpenApiAccountList>();
    expectTypeOf<OpenApiCreatePost200>().toEqualTypeOf<OpenApiAccount>();
    expectTypeOf<OpenApiCreateBody>().toEqualTypeOf<OpenApiCreate>();
    expectTypeOf<OpenApiUpdatePut200>().toEqualTypeOf<OpenApiAccount>();
    expectTypeOf<OpenApiUpdateBody>().toEqualTypeOf<OpenApiUpdate>();
    expectTypeOf<OpenApiSnapshotGet200>().toEqualTypeOf<OpenApiSnapshot>();
    expectTypeOf<OpenApiRiskGet200>().toEqualTypeOf<OpenApiRisk>();
    expectTypeOf<OpenApiTradeListGet200>().toEqualTypeOf<OpenApiTradeList>();
    expectTypeOf<OpenApiTradeCreatePost200>().toEqualTypeOf<OpenApiEventCreated>();
    expectTypeOf<OpenApiTradeCreateBody>().toEqualTypeOf<OpenApiTrade>();
    expectTypeOf<OpenApiTradeDeleteDelete200>().toEqualTypeOf<OpenApiDelete>();
    expectTypeOf<OpenApiParsePost200>().toEqualTypeOf<components['schemas']['PortfolioImportParseResponse']>();
    expectTypeOf<OpenApiPaperQualityGet200>().toEqualTypeOf<OpenApiPaperQuality>();
    expectTypeOf<OpenApiListOp>().toEqualTypeOf<OpenApiListPathGet>();
    expectTypeOf<OpenApiCreateOp>().toEqualTypeOf<OpenApiCreatePathPost>();
    expectTypeOf<OpenApiUpdateOp>().toEqualTypeOf<OpenApiUpdatePathPut>();
    expectTypeOf<OpenApiSnapshotOp>().toEqualTypeOf<OpenApiSnapshotPathGet>();
    expectTypeOf<OpenApiRiskOp>().toEqualTypeOf<OpenApiRiskPathGet>();
    expectTypeOf<OpenApiTradeListOp>().toEqualTypeOf<OpenApiTradeListPathGet>();
    expectTypeOf<OpenApiTradeCreateOp>().toEqualTypeOf<OpenApiTradeCreatePathPost>();
    expectTypeOf<OpenApiTradeDeleteOp>().toEqualTypeOf<OpenApiTradeDeletePathDelete>();
    expectTypeOf<OpenApiPaperQualityOp>().toEqualTypeOf<OpenApiPaperQualityPathGet>();
    type ListNeverBody = OpenApiListOp extends { requestBody?: never } ? true : false;
    type SnapshotNeverBody = OpenApiSnapshotOp extends { requestBody?: never } ? true : false;
    type RiskNeverBody = OpenApiRiskOp extends { requestBody?: never } ? true : false;
    type TradeListNeverBody = OpenApiTradeListOp extends { requestBody?: never } ? true : false;
    type CashListNeverBody = OpenApiCashListOp extends { requestBody?: never } ? true : false;
    type BrokersNeverBody = OpenApiBrokersOp extends { requestBody?: never } ? true : false;
    type PaperQualityNeverBody = OpenApiPaperQualityOp extends { requestBody?: never } ? true : false;
    type ListHas201 = 201 extends keyof OpenApiListOp['responses'] ? true : false;
    type CreateHas201 = 201 extends keyof OpenApiCreateOp['responses'] ? true : false;
    type SnapshotHas201 = 201 extends keyof OpenApiSnapshotOp['responses'] ? true : false;
    type RiskHas201 = 201 extends keyof OpenApiRiskOp['responses'] ? true : false;
    expectTypeOf<ListNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<SnapshotNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<RiskNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<TradeListNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<CashListNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<BrokersNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<PaperQualityNeverBody>().toEqualTypeOf<true>();
    expectTypeOf<ListHas201>().toEqualTypeOf<false>();
    expectTypeOf<CreateHas201>().toEqualTypeOf<false>();
    expectTypeOf<SnapshotHas201>().toEqualTypeOf<false>();
    expectTypeOf<RiskHas201>().toEqualTypeOf<false>();
  });

  it('does not claim public Override types equal path 200 JSON except 1:1 delete and event-created', () => {
    type PublicAccountExtendsPath = PortfolioAccountItem extends OpenApiCreatePost200 ? true : false;
    type PathExtendsPublicAccount = OpenApiCreatePost200 extends PortfolioAccountItem ? true : false;
    type PublicListExtendsPath = PortfolioAccountListResponse extends OpenApiListGet200 ? true : false;
    type PathExtendsPublicList = OpenApiListGet200 extends PortfolioAccountListResponse ? true : false;
    type PublicSnapshotExtendsPath = PortfolioSnapshotResponse extends OpenApiSnapshotGet200 ? true : false;
    type PathExtendsPublicSnapshot = OpenApiSnapshotGet200 extends PortfolioSnapshotResponse ? true : false;
    type PublicRiskExtendsPath = PortfolioRiskResponse extends OpenApiRiskGet200 ? true : false;
    type PathExtendsPublicRisk = OpenApiRiskGet200 extends PortfolioRiskResponse ? true : false;
    type PublicDeleteExtendsPath = PortfolioDeleteResponse extends OpenApiTradeDeleteDelete200 ? true : false;
    type PathExtendsPublicDelete = OpenApiTradeDeleteDelete200 extends PortfolioDeleteResponse ? true : false;
    type PublicEventExtendsPath = PortfolioEventCreatedResponse extends OpenApiTradeCreatePost200 ? true : false;
    type PathExtendsPublicEvent = OpenApiTradeCreatePost200 extends PortfolioEventCreatedResponse ? true : false;
    expectTypeOf<PublicAccountExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicAccount>().toEqualTypeOf<false>();
    expectTypeOf<PublicListExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicList>().toEqualTypeOf<false>();
    expectTypeOf<PublicSnapshotExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicSnapshot>().toEqualTypeOf<false>();
    expectTypeOf<PublicRiskExtendsPath>().toEqualTypeOf<false>();
    expectTypeOf<PathExtendsPublicRisk>().toEqualTypeOf<false>();
    expectTypeOf<PublicDeleteExtendsPath>().toEqualTypeOf<true>();
    expectTypeOf<PathExtendsPublicDelete>().toEqualTypeOf<true>();
    expectTypeOf<PublicEventExtendsPath>().toEqualTypeOf<true>();
    expectTypeOf<PathExtendsPublicEvent>().toEqualTypeOf<true>();
  });

  it('keeps snake_case keys off the UI types and on the generated components', () => {
    expectTypeOf<keyof PortfolioAccountItem>().not.toMatchTypeOf<'account_type' | 'base_currency'>();
    expectTypeOf<keyof PortfolioSnapshotResponse>().not.toMatchTypeOf<'cost_method'>();
    expectTypeOf<keyof PortfolioTradeCreateRequest>().not.toMatchTypeOf<'operation_id'>();
    expectTypeOf<keyof OpenApiAccount>().not.toMatchTypeOf<'accountType' | 'baseCurrency'>();
    expectTypeOf<keyof OpenApiSnapshot>().not.toMatchTypeOf<'costMethod'>();
    expectTypeOf<keyof OpenApiTrade>().not.toMatchTypeOf<'operationId'>();
  });

  it('keeps UI accountType and trade fee/tax optional so short fixtures assign', () => {
    type UiAccountTypeOptional = IsOptional<PortfolioAccountItem, 'accountType'>;
    type NaiveAccountTypeOptional = IsOptional<CamelizeKeys<OpenApiAccount>, 'accountType'>;
    type UiFeeOptional = IsOptional<PortfolioTradeCreateRequest, 'fee'>;
    type UiTaxOptional = IsOptional<PortfolioTradeCreateRequest, 'tax'>;
    type NaiveFeeOptional = IsOptional<CamelizeKeys<OpenApiTrade>, 'fee'>;
    type NaiveTaxOptional = IsOptional<CamelizeKeys<OpenApiTrade>, 'tax'>;
    expectTypeOf<UiAccountTypeOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveAccountTypeOptional>().toEqualTypeOf<false>();
    expectTypeOf<UiFeeOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiTaxOptional>().toEqualTypeOf<true>();
    expectTypeOf<NaiveFeeOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveTaxOptional>().toEqualTypeOf<false>();
    expectTypeOf(accountBase).toMatchTypeOf<PortfolioAccountItem>();
    expectTypeOf(accountBase).not.toMatchTypeOf<CamelizeKeys<OpenApiAccount>>();
    expectTypeOf(createBase).toMatchTypeOf<PortfolioAccountCreateRequest>();
    expectTypeOf(createBase).not.toMatchTypeOf<CamelizeKeys<OpenApiCreate>>();
    expectTypeOf(tradeBase).toMatchTypeOf<PortfolioTradeCreateRequest>();
    expectTypeOf(tradeBase).not.toMatchTypeOf<CamelizeKeys<OpenApiTrade>>();
  });

  it('keeps UI operationId required while naive CamelizeKeys leaves it optional', () => {
    type UiOperationIdOptional = IsOptional<PortfolioTradeCreateRequest, 'operationId'>;
    type NaiveOperationIdOptional = IsOptional<CamelizeKeys<OpenApiTrade>, 'operationId'>;
    type UiPaperOperationIdOptional = IsOptional<PaperTradeCreateRequest, 'operationId'>;
    type NaivePaperOperationIdOptional = IsOptional<CamelizeKeys<OpenApiPaperTrade>, 'operationId'>;
    expectTypeOf<UiOperationIdOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveOperationIdOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiPaperOperationIdOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaivePaperOperationIdOptional>().toEqualTypeOf<true>();
    expectTypeOf(tradeMissingOp).not.toMatchTypeOf<PortfolioTradeCreateRequest>();
    expectTypeOf(tradeMissingOp).toMatchTypeOf<CamelizeKeys<OpenApiTrade>>();
  });

  it('keeps UI list/snapshot accounts and snapshot positions required', () => {
    const emptyList = {};
    expectTypeOf(emptyList).not.toMatchTypeOf<PortfolioAccountListResponse>();
    expectTypeOf(emptyList).toMatchTypeOf<CamelizeKeys<OpenApiAccountList>>();
    expectTypeOf(snapshotMissingAccounts).not.toMatchTypeOf<PortfolioSnapshotResponse>();
    expectTypeOf(snapshotMissingAccounts).toMatchTypeOf<CamelizeKeys<OpenApiSnapshot>>();
    expectTypeOf(accountSnapshotMissingPositions).not.toMatchTypeOf<PortfolioAccountSnapshot>();
    expectTypeOf(accountSnapshotMissingPositions).toMatchTypeOf<CamelizeKeys<OpenApiAccountSnapshot>>();
    type UiListAccountsOptional = IsOptional<PortfolioAccountListResponse, 'accounts'>;
    type NaiveListAccountsOptional = IsOptional<CamelizeKeys<OpenApiAccountList>, 'accounts'>;
    type UiSnapshotAccountsOptional = IsOptional<PortfolioSnapshotResponse, 'accounts'>;
    type UiPositionsOptional = IsOptional<PortfolioAccountSnapshot, 'positions'>;
    expectTypeOf<UiListAccountsOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveListAccountsOptional>().toEqualTypeOf<true>();
    expectTypeOf<UiSnapshotAccountsOptional>().toEqualTypeOf<false>();
    expectTypeOf<UiPositionsOptional>().toEqualTypeOf<false>();
  });

  it('keeps UI risk nested blocks required and closed while naive bags stay optional', () => {
    expectTypeOf(riskMissingNested).not.toMatchTypeOf<PortfolioRiskResponse>();
    expectTypeOf(riskMissingNested).toMatchTypeOf<CamelizeKeys<OpenApiRisk>>();
    expectTypeOf(riskBase).toMatchTypeOf<PortfolioRiskResponse>();
    type UiConcentrationOptional = IsOptional<PortfolioRiskResponse, 'concentration'>;
    type NaiveConcentrationOptional = IsOptional<CamelizeKeys<OpenApiRisk>, 'concentration'>;
    expectTypeOf<UiConcentrationOptional>().toEqualTypeOf<false>();
    expectTypeOf<NaiveConcentrationOptional>().toEqualTypeOf<true>();
    expectTypeOf(naiveConcExtra).toMatchTypeOf<NonNullable<CamelizeKeys<OpenApiRisk>['concentration']>>();
    type PublicConcentration = PortfolioRiskResponse['concentration'];
    type NaiveConcentration = NonNullable<CamelizeKeys<OpenApiRisk>['concentration']>;
    type PublicRejectsExtra = { futureConcentrationFlag: true } extends PublicConcentration ? true : false;
    type NaiveAcceptsExtra = { futureConcentrationFlag: true } extends NaiveConcentration ? true : false;
    expectTypeOf<PublicRejectsExtra>().toEqualTypeOf<false>();
    expectTypeOf<NaiveAcceptsExtra>().toEqualTypeOf<true>();
  });
});
