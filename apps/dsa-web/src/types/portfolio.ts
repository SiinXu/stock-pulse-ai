// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';
import type { DecisionSignalItem } from './decisionSignals';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiAccount = components['schemas']['PortfolioAccountItem'];
type OpenApiAccountList = components['schemas']['PortfolioAccountListResponse'];
type OpenApiCreate = components['schemas']['PortfolioAccountCreateRequest'];
type OpenApiUpdate = components['schemas']['PortfolioAccountUpdateRequest'];
type OpenApiPosition = components['schemas']['PortfolioPositionItem'];
type OpenApiPositionAnalysis = components['schemas']['PortfolioPositionAnalysisRequest'];
type OpenApiAccountSnapshot = components['schemas']['PortfolioAccountSnapshot'];
type OpenApiSnapshot = components['schemas']['PortfolioSnapshotResponse'];
type OpenApiRisk = components['schemas']['PortfolioRiskResponse'];
type OpenApiSignalRisk = components['schemas']['PortfolioDecisionSignalRiskBlock'];
type OpenApiSignalRiskItem = components['schemas']['PortfolioDecisionSignalRiskItem'];
type OpenApiTrade = components['schemas']['PortfolioTradeCreateRequest'];
type OpenApiTradeListItem = components['schemas']['PortfolioTradeListItem'];
type OpenApiTradeList = components['schemas']['PortfolioTradeListResponse'];
type OpenApiCashCreate = components['schemas']['PortfolioCashLedgerCreateRequest'];
type OpenApiCashItem = components['schemas']['PortfolioCashLedgerListItem'];
type OpenApiCashList = components['schemas']['PortfolioCashLedgerListResponse'];
type OpenApiCorpCreate = components['schemas']['PortfolioCorporateActionCreateRequest'];
type OpenApiCorpItem = components['schemas']['PortfolioCorporateActionListItem'];
type OpenApiCorpList = components['schemas']['PortfolioCorporateActionListResponse'];
type OpenApiEventCreated = components['schemas']['PortfolioEventCreatedResponse'];
type OpenApiDelete = components['schemas']['PortfolioDeleteResponse'];
type OpenApiImportTrade = components['schemas']['PortfolioImportTradeItem'];
type OpenApiFailedRow = components['schemas']['PortfolioImportFailedRow'];
type OpenApiParse = components['schemas']['PortfolioImportParseResponse'];
type OpenApiFutuPreview = components['schemas']['PortfolioFutuImportPreviewResponse'];
type OpenApiFutuRequest = components['schemas']['PortfolioFutuImportRequest'];
type OpenApiCommit = components['schemas']['PortfolioImportCommitResponse'];
type OpenApiBrokerItem = components['schemas']['PortfolioImportBrokerItem'];
type OpenApiBrokerList = components['schemas']['PortfolioImportBrokerListResponse'];
type OpenApiFxRefresh = components['schemas']['PortfolioFxRefreshResponse'];
type OpenApiPaperTrade = components['schemas']['PaperTradeCreateRequest'];
type OpenApiPaperTradeCreated = components['schemas']['PaperTradeCreatedResponse'];
type OpenApiPaperQuality = components['schemas']['PaperDecisionQualityResponse'];
type OpenApiPaperQualityItem = components['schemas']['PaperDecisionQualityItem'];
type OpenApiPaperQualityDimension = components['schemas']['PaperDecisionQualityDimension'];
type OpenApiPaperQualityReason = components['schemas']['PaperDecisionQualityReason'];
type OpenApiPaperQualityAggregate = components['schemas']['PaperDecisionQualityAggregate'];

type OpenApiListOp = operations['list_accounts_api_v1_portfolio_accounts_get'];
type OpenApiCreateOp = operations['create_account_api_v1_portfolio_accounts_post'];
type OpenApiUpdateOp = operations['update_account_api_v1_portfolio_accounts__account_id__put'];
type OpenApiSnapshotOp = operations['get_snapshot_api_v1_portfolio_snapshot_get'];
type OpenApiRiskOp = operations['get_risk_report_api_v1_portfolio_risk_get'];
type OpenApiTradeListOp = operations['list_trades_api_v1_portfolio_trades_get'];
type OpenApiTradeCreateOp = operations['create_trade_api_v1_portfolio_trades_post'];
type OpenApiTradeDeleteOp = operations['delete_trade_api_v1_portfolio_trades__trade_id__delete'];
type OpenApiCashListOp = operations['list_cash_ledger_api_v1_portfolio_cash_ledger_get'];
type OpenApiCashCreateOp = operations['create_cash_ledger_api_v1_portfolio_cash_ledger_post'];
type OpenApiCashDeleteOp = operations['delete_cash_ledger_api_v1_portfolio_cash_ledger__entry_id__delete'];
type OpenApiCorpListOp = operations['list_corporate_actions_api_v1_portfolio_corporate_actions_get'];
type OpenApiCorpCreateOp = operations['create_corporate_action_api_v1_portfolio_corporate_actions_post'];
type OpenApiCorpDeleteOp = operations['delete_corporate_action_api_v1_portfolio_corporate_actions__action_id__delete'];
type OpenApiFxOp = operations['refresh_fx_rates_api_v1_portfolio_fx_refresh_post'];
type OpenApiBrokersOp = operations['list_csv_brokers_api_v1_portfolio_imports_csv_brokers_get'];
type OpenApiParseOp = operations['parse_csv_import_api_v1_portfolio_imports_csv_parse_post'];
type OpenApiCommitOp = operations['commit_csv_import_api_v1_portfolio_imports_csv_commit_post'];
type OpenApiFutuCommitOp = operations['commit_futu_import_api_v1_portfolio_imports_futu_post'];
type OpenApiFutuPreviewOp = operations['preview_futu_import_api_v1_portfolio_imports_futu_preview_post'];
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
type OpenApiCashListPathGet = paths['/api/v1/portfolio/cash-ledger']['get'];
type OpenApiCashCreatePathPost = paths['/api/v1/portfolio/cash-ledger']['post'];
type OpenApiCashDeletePathDelete = paths['/api/v1/portfolio/cash-ledger/{entry_id}']['delete'];
type OpenApiCorpListPathGet = paths['/api/v1/portfolio/corporate-actions']['get'];
type OpenApiCorpCreatePathPost = paths['/api/v1/portfolio/corporate-actions']['post'];
type OpenApiCorpDeletePathDelete = paths['/api/v1/portfolio/corporate-actions/{action_id}']['delete'];
type OpenApiFxPathPost = paths['/api/v1/portfolio/fx/refresh']['post'];
type OpenApiBrokersPathGet = paths['/api/v1/portfolio/imports/csv/brokers']['get'];
type OpenApiParsePathPost = paths['/api/v1/portfolio/imports/csv/parse']['post'];
type OpenApiCommitPathPost = paths['/api/v1/portfolio/imports/csv/commit']['post'];
type OpenApiFutuCommitPathPost = paths['/api/v1/portfolio/imports/futu']['post'];
type OpenApiFutuPreviewPathPost = paths['/api/v1/portfolio/imports/futu/preview']['post'];
type OpenApiPaperTradePathPost = paths['/api/v1/portfolio/accounts/{account_id}/paper-trades']['post'];
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
type OpenApiCashListGet200 = OpenApiCashListOp['responses']['200']['content']['application/json'];
type OpenApiCashCreatePost200 = OpenApiCashCreateOp['responses']['200']['content']['application/json'];
type OpenApiCashCreateBody = OpenApiCashCreateOp['requestBody']['content']['application/json'];
type OpenApiCashDeleteDelete200 = OpenApiCashDeleteOp['responses']['200']['content']['application/json'];
type OpenApiCorpListGet200 = OpenApiCorpListOp['responses']['200']['content']['application/json'];
type OpenApiCorpCreatePost200 = OpenApiCorpCreateOp['responses']['200']['content']['application/json'];
type OpenApiCorpCreateBody = OpenApiCorpCreateOp['requestBody']['content']['application/json'];
type OpenApiCorpDeleteDelete200 = OpenApiCorpDeleteOp['responses']['200']['content']['application/json'];
type OpenApiFxPost200 = OpenApiFxOp['responses']['200']['content']['application/json'];
type OpenApiBrokersGet200 = OpenApiBrokersOp['responses']['200']['content']['application/json'];
type OpenApiParsePost200 = OpenApiParseOp['responses']['200']['content']['application/json'];
type OpenApiCommitPost200 = OpenApiCommitOp['responses']['200']['content']['application/json'];
type OpenApiFutuCommitPost200 = OpenApiFutuCommitOp['responses']['200']['content']['application/json'];
type OpenApiFutuCommitBody = OpenApiFutuCommitOp['requestBody']['content']['application/json'];
type OpenApiFutuPreviewPost200 = OpenApiFutuPreviewOp['responses']['200']['content']['application/json'];
type OpenApiPaperTradePost200 = OpenApiPaperTradeOp['responses']['200']['content']['application/json'];
type OpenApiPaperTradeBody = OpenApiPaperTradeOp['requestBody']['content']['application/json'];
type OpenApiPaperQualityGet200 = OpenApiPaperQualityOp['responses']['200']['content']['application/json'];

type _Assert<T extends true> = T;
type _List200IsList = _Assert<OpenApiListGet200 extends OpenApiAccountList ? true : false>;
type _ListIsList200 = _Assert<OpenApiAccountList extends OpenApiListGet200 ? true : false>;
type _ListOpIsPath = _Assert<OpenApiListOp extends OpenApiListPathGet ? true : false>;
type _PathIsListOp = _Assert<OpenApiListPathGet extends OpenApiListOp ? true : false>;
type _ListGetNeverRequestBody = _Assert<OpenApiListOp extends { requestBody?: never } ? true : false>;
type _ListHas200 = _Assert<200 extends keyof OpenApiListOp['responses'] ? true : false>;
type _ListLacks201 = _Assert<201 extends keyof OpenApiListOp['responses'] ? false : true>;
type _Create200IsAccount = _Assert<OpenApiCreatePost200 extends OpenApiAccount ? true : false>;
type _AccountIsCreate200 = _Assert<OpenApiAccount extends OpenApiCreatePost200 ? true : false>;
type _CreateOpIsPath = _Assert<OpenApiCreateOp extends OpenApiCreatePathPost ? true : false>;
type _PathIsCreateOp = _Assert<OpenApiCreatePathPost extends OpenApiCreateOp ? true : false>;
type _CreateBodyIsRequest = _Assert<OpenApiCreateBody extends OpenApiCreate ? true : false>;
type _RequestIsCreateBody = _Assert<OpenApiCreate extends OpenApiCreateBody ? true : false>;
type _CreateHas200 = _Assert<200 extends keyof OpenApiCreateOp['responses'] ? true : false>;
type _CreateLacks201 = _Assert<201 extends keyof OpenApiCreateOp['responses'] ? false : true>;
type _Update200IsAccount = _Assert<OpenApiUpdatePut200 extends OpenApiAccount ? true : false>;
type _AccountIsUpdate200 = _Assert<OpenApiAccount extends OpenApiUpdatePut200 ? true : false>;
type _UpdateOpIsPath = _Assert<OpenApiUpdateOp extends OpenApiUpdatePathPut ? true : false>;
type _PathIsUpdateOp = _Assert<OpenApiUpdatePathPut extends OpenApiUpdateOp ? true : false>;
type _UpdateBodyIsUpdate = _Assert<OpenApiUpdateBody extends OpenApiUpdate ? true : false>;
type _UpdateIsUpdateBody = _Assert<OpenApiUpdate extends OpenApiUpdateBody ? true : false>;
type _UpdateHas200 = _Assert<200 extends keyof OpenApiUpdateOp['responses'] ? true : false>;
type _UpdateLacks201 = _Assert<201 extends keyof OpenApiUpdateOp['responses'] ? false : true>;
type _Snapshot200IsSnapshot = _Assert<OpenApiSnapshotGet200 extends OpenApiSnapshot ? true : false>;
type _SnapshotIsSnapshot200 = _Assert<OpenApiSnapshot extends OpenApiSnapshotGet200 ? true : false>;
type _SnapshotOpIsPath = _Assert<OpenApiSnapshotOp extends OpenApiSnapshotPathGet ? true : false>;
type _PathIsSnapshotOp = _Assert<OpenApiSnapshotPathGet extends OpenApiSnapshotOp ? true : false>;
type _SnapshotGetNeverRequestBody = _Assert<OpenApiSnapshotOp extends { requestBody?: never } ? true : false>;
type _SnapshotHas200 = _Assert<200 extends keyof OpenApiSnapshotOp['responses'] ? true : false>;
type _SnapshotLacks201 = _Assert<201 extends keyof OpenApiSnapshotOp['responses'] ? false : true>;
type _Risk200IsRisk = _Assert<OpenApiRiskGet200 extends OpenApiRisk ? true : false>;
type _RiskIsRisk200 = _Assert<OpenApiRisk extends OpenApiRiskGet200 ? true : false>;
type _RiskOpIsPath = _Assert<OpenApiRiskOp extends OpenApiRiskPathGet ? true : false>;
type _PathIsRiskOp = _Assert<OpenApiRiskPathGet extends OpenApiRiskOp ? true : false>;
type _RiskGetNeverRequestBody = _Assert<OpenApiRiskOp extends { requestBody?: never } ? true : false>;
type _RiskHas200 = _Assert<200 extends keyof OpenApiRiskOp['responses'] ? true : false>;
type _RiskLacks201 = _Assert<201 extends keyof OpenApiRiskOp['responses'] ? false : true>;
type _TradeList200IsTradeList = _Assert<OpenApiTradeListGet200 extends OpenApiTradeList ? true : false>;
type _TradeListIsTradeList200 = _Assert<OpenApiTradeList extends OpenApiTradeListGet200 ? true : false>;
type _TradeListOpIsPath = _Assert<OpenApiTradeListOp extends OpenApiTradeListPathGet ? true : false>;
type _PathIsTradeListOp = _Assert<OpenApiTradeListPathGet extends OpenApiTradeListOp ? true : false>;
type _TradeListGetNeverRequestBody = _Assert<OpenApiTradeListOp extends { requestBody?: never } ? true : false>;
type _TradeListHas200 = _Assert<200 extends keyof OpenApiTradeListOp['responses'] ? true : false>;
type _TradeListLacks201 = _Assert<201 extends keyof OpenApiTradeListOp['responses'] ? false : true>;
type _TradeCreate200IsEvent = _Assert<OpenApiTradeCreatePost200 extends OpenApiEventCreated ? true : false>;
type _EventIsTradeCreate200 = _Assert<OpenApiEventCreated extends OpenApiTradeCreatePost200 ? true : false>;
type _TradeCreateOpIsPath = _Assert<OpenApiTradeCreateOp extends OpenApiTradeCreatePathPost ? true : false>;
type _PathIsTradeCreateOp = _Assert<OpenApiTradeCreatePathPost extends OpenApiTradeCreateOp ? true : false>;
type _TradeCreateBodyIsTrade = _Assert<OpenApiTradeCreateBody extends OpenApiTrade ? true : false>;
type _TradeIsTradeCreateBody = _Assert<OpenApiTrade extends OpenApiTradeCreateBody ? true : false>;
type _TradeCreateHas200 = _Assert<200 extends keyof OpenApiTradeCreateOp['responses'] ? true : false>;
type _TradeCreateLacks201 = _Assert<201 extends keyof OpenApiTradeCreateOp['responses'] ? false : true>;
type _TradeDelete200IsDelete = _Assert<OpenApiTradeDeleteDelete200 extends OpenApiDelete ? true : false>;
type _DeleteIsTradeDelete200 = _Assert<OpenApiDelete extends OpenApiTradeDeleteDelete200 ? true : false>;
type _TradeDeleteOpIsPath = _Assert<OpenApiTradeDeleteOp extends OpenApiTradeDeletePathDelete ? true : false>;
type _PathIsTradeDeleteOp = _Assert<OpenApiTradeDeletePathDelete extends OpenApiTradeDeleteOp ? true : false>;
type _TradeDeleteNeverRequestBody = _Assert<OpenApiTradeDeleteOp extends { requestBody?: never } ? true : false>;
type _TradeDeleteHas200 = _Assert<200 extends keyof OpenApiTradeDeleteOp['responses'] ? true : false>;
type _TradeDeleteLacks201 = _Assert<201 extends keyof OpenApiTradeDeleteOp['responses'] ? false : true>;
type _CashList200IsCashList = _Assert<OpenApiCashListGet200 extends OpenApiCashList ? true : false>;
type _CashListIsCashList200 = _Assert<OpenApiCashList extends OpenApiCashListGet200 ? true : false>;
type _CashListOpIsPath = _Assert<OpenApiCashListOp extends OpenApiCashListPathGet ? true : false>;
type _PathIsCashListOp = _Assert<OpenApiCashListPathGet extends OpenApiCashListOp ? true : false>;
type _CashListGetNeverRequestBody = _Assert<OpenApiCashListOp extends { requestBody?: never } ? true : false>;
type _CashCreate200IsEvent = _Assert<OpenApiCashCreatePost200 extends OpenApiEventCreated ? true : false>;
type _EventIsCashCreate200 = _Assert<OpenApiEventCreated extends OpenApiCashCreatePost200 ? true : false>;
type _CashCreateOpIsPath = _Assert<OpenApiCashCreateOp extends OpenApiCashCreatePathPost ? true : false>;
type _PathIsCashCreateOp = _Assert<OpenApiCashCreatePathPost extends OpenApiCashCreateOp ? true : false>;
type _CashCreateBodyIsCash = _Assert<OpenApiCashCreateBody extends OpenApiCashCreate ? true : false>;
type _CashIsCashCreateBody = _Assert<OpenApiCashCreate extends OpenApiCashCreateBody ? true : false>;
type _CashDelete200IsDelete = _Assert<OpenApiCashDeleteDelete200 extends OpenApiDelete ? true : false>;
type _DeleteIsCashDelete200 = _Assert<OpenApiDelete extends OpenApiCashDeleteDelete200 ? true : false>;
type _CashDeleteOpIsPath = _Assert<OpenApiCashDeleteOp extends OpenApiCashDeletePathDelete ? true : false>;
type _PathIsCashDeleteOp = _Assert<OpenApiCashDeletePathDelete extends OpenApiCashDeleteOp ? true : false>;
type _CashDeleteNeverRequestBody = _Assert<OpenApiCashDeleteOp extends { requestBody?: never } ? true : false>;
type _CorpList200IsCorpList = _Assert<OpenApiCorpListGet200 extends OpenApiCorpList ? true : false>;
type _CorpListIsCorpList200 = _Assert<OpenApiCorpList extends OpenApiCorpListGet200 ? true : false>;
type _CorpListOpIsPath = _Assert<OpenApiCorpListOp extends OpenApiCorpListPathGet ? true : false>;
type _PathIsCorpListOp = _Assert<OpenApiCorpListPathGet extends OpenApiCorpListOp ? true : false>;
type _CorpListGetNeverRequestBody = _Assert<OpenApiCorpListOp extends { requestBody?: never } ? true : false>;
type _CorpCreate200IsEvent = _Assert<OpenApiCorpCreatePost200 extends OpenApiEventCreated ? true : false>;
type _EventIsCorpCreate200 = _Assert<OpenApiEventCreated extends OpenApiCorpCreatePost200 ? true : false>;
type _CorpCreateOpIsPath = _Assert<OpenApiCorpCreateOp extends OpenApiCorpCreatePathPost ? true : false>;
type _PathIsCorpCreateOp = _Assert<OpenApiCorpCreatePathPost extends OpenApiCorpCreateOp ? true : false>;
type _CorpCreateBodyIsCorp = _Assert<OpenApiCorpCreateBody extends OpenApiCorpCreate ? true : false>;
type _CorpIsCorpCreateBody = _Assert<OpenApiCorpCreate extends OpenApiCorpCreateBody ? true : false>;
type _CorpDelete200IsDelete = _Assert<OpenApiCorpDeleteDelete200 extends OpenApiDelete ? true : false>;
type _DeleteIsCorpDelete200 = _Assert<OpenApiDelete extends OpenApiCorpDeleteDelete200 ? true : false>;
type _CorpDeleteOpIsPath = _Assert<OpenApiCorpDeleteOp extends OpenApiCorpDeletePathDelete ? true : false>;
type _PathIsCorpDeleteOp = _Assert<OpenApiCorpDeletePathDelete extends OpenApiCorpDeleteOp ? true : false>;
type _CorpDeleteNeverRequestBody = _Assert<OpenApiCorpDeleteOp extends { requestBody?: never } ? true : false>;
type _Fx200IsFx = _Assert<OpenApiFxPost200 extends OpenApiFxRefresh ? true : false>;
type _FxIsFx200 = _Assert<OpenApiFxRefresh extends OpenApiFxPost200 ? true : false>;
type _FxOpIsPath = _Assert<OpenApiFxOp extends OpenApiFxPathPost ? true : false>;
type _PathIsFxOp = _Assert<OpenApiFxPathPost extends OpenApiFxOp ? true : false>;
type _FxNeverRequestBody = _Assert<OpenApiFxOp extends { requestBody?: never } ? true : false>;
type _FxHas200 = _Assert<200 extends keyof OpenApiFxOp['responses'] ? true : false>;
type _FxLacks201 = _Assert<201 extends keyof OpenApiFxOp['responses'] ? false : true>;
type _Brokers200IsBrokers = _Assert<OpenApiBrokersGet200 extends OpenApiBrokerList ? true : false>;
type _BrokersIsBrokers200 = _Assert<OpenApiBrokerList extends OpenApiBrokersGet200 ? true : false>;
type _BrokersOpIsPath = _Assert<OpenApiBrokersOp extends OpenApiBrokersPathGet ? true : false>;
type _PathIsBrokersOp = _Assert<OpenApiBrokersPathGet extends OpenApiBrokersOp ? true : false>;
type _BrokersGetNeverRequestBody = _Assert<OpenApiBrokersOp extends { requestBody?: never } ? true : false>;
type _Parse200IsParse = _Assert<OpenApiParsePost200 extends OpenApiParse ? true : false>;
type _ParseIsParse200 = _Assert<OpenApiParse extends OpenApiParsePost200 ? true : false>;
type _ParseOpIsPath = _Assert<OpenApiParseOp extends OpenApiParsePathPost ? true : false>;
type _PathIsParseOp = _Assert<OpenApiParsePathPost extends OpenApiParseOp ? true : false>;
type _Commit200IsCommit = _Assert<OpenApiCommitPost200 extends OpenApiCommit ? true : false>;
type _CommitIsCommit200 = _Assert<OpenApiCommit extends OpenApiCommitPost200 ? true : false>;
type _CommitOpIsPath = _Assert<OpenApiCommitOp extends OpenApiCommitPathPost ? true : false>;
type _PathIsCommitOp = _Assert<OpenApiCommitPathPost extends OpenApiCommitOp ? true : false>;
type _FutuCommit200IsCommit = _Assert<OpenApiFutuCommitPost200 extends OpenApiCommit ? true : false>;
type _CommitIsFutuCommit200 = _Assert<OpenApiCommit extends OpenApiFutuCommitPost200 ? true : false>;
type _FutuCommitOpIsPath = _Assert<OpenApiFutuCommitOp extends OpenApiFutuCommitPathPost ? true : false>;
type _PathIsFutuCommitOp = _Assert<OpenApiFutuCommitPathPost extends OpenApiFutuCommitOp ? true : false>;
type _FutuCommitBodyIsRequest = _Assert<OpenApiFutuCommitBody extends OpenApiFutuRequest ? true : false>;
type _RequestIsFutuCommitBody = _Assert<OpenApiFutuRequest extends OpenApiFutuCommitBody ? true : false>;
type _FutuPreview200IsPreview = _Assert<OpenApiFutuPreviewPost200 extends OpenApiFutuPreview ? true : false>;
type _PreviewIsFutuPreview200 = _Assert<OpenApiFutuPreview extends OpenApiFutuPreviewPost200 ? true : false>;
type _FutuPreviewOpIsPath = _Assert<OpenApiFutuPreviewOp extends OpenApiFutuPreviewPathPost ? true : false>;
type _PathIsFutuPreviewOp = _Assert<OpenApiFutuPreviewPathPost extends OpenApiFutuPreviewOp ? true : false>;
type _FutuPreviewNeverRequestBody = _Assert<OpenApiFutuPreviewOp extends { requestBody?: never } ? true : false>;
type _PaperTrade200IsCreated = _Assert<OpenApiPaperTradePost200 extends OpenApiPaperTradeCreated ? true : false>;
type _CreatedIsPaperTrade200 = _Assert<OpenApiPaperTradeCreated extends OpenApiPaperTradePost200 ? true : false>;
type _PaperTradeOpIsPath = _Assert<OpenApiPaperTradeOp extends OpenApiPaperTradePathPost ? true : false>;
type _PathIsPaperTradeOp = _Assert<OpenApiPaperTradePathPost extends OpenApiPaperTradeOp ? true : false>;
type _PaperTradeBodyIsRequest = _Assert<OpenApiPaperTradeBody extends OpenApiPaperTrade ? true : false>;
type _RequestIsPaperTradeBody = _Assert<OpenApiPaperTrade extends OpenApiPaperTradeBody ? true : false>;
type _PaperQuality200IsQuality = _Assert<OpenApiPaperQualityGet200 extends OpenApiPaperQuality ? true : false>;
type _QualityIsPaperQuality200 = _Assert<OpenApiPaperQuality extends OpenApiPaperQualityGet200 ? true : false>;
type _PaperQualityOpIsPath = _Assert<OpenApiPaperQualityOp extends OpenApiPaperQualityPathGet ? true : false>;
type _PathIsPaperQualityOp = _Assert<OpenApiPaperQualityPathGet extends OpenApiPaperQualityOp ? true : false>;
type _PaperQualityGetNeverRequestBody = _Assert<OpenApiPaperQualityOp extends { requestBody?: never } ? true : false>;
type _PaperQualityHas200 = _Assert<200 extends keyof OpenApiPaperQualityOp['responses'] ? true : false>;
type _PaperQualityLacks201 = _Assert<201 extends keyof OpenApiPaperQualityOp['responses'] ? false : true>;

type _OpenApiAnchors = [
  _List200IsList,
  _ListIsList200,
  _ListOpIsPath,
  _PathIsListOp,
  _ListGetNeverRequestBody,
  _ListHas200,
  _ListLacks201,
  _Create200IsAccount,
  _AccountIsCreate200,
  _CreateOpIsPath,
  _PathIsCreateOp,
  _CreateBodyIsRequest,
  _RequestIsCreateBody,
  _CreateHas200,
  _CreateLacks201,
  _Update200IsAccount,
  _AccountIsUpdate200,
  _UpdateOpIsPath,
  _PathIsUpdateOp,
  _UpdateBodyIsUpdate,
  _UpdateIsUpdateBody,
  _UpdateHas200,
  _UpdateLacks201,
  _Snapshot200IsSnapshot,
  _SnapshotIsSnapshot200,
  _SnapshotOpIsPath,
  _PathIsSnapshotOp,
  _SnapshotGetNeverRequestBody,
  _SnapshotHas200,
  _SnapshotLacks201,
  _Risk200IsRisk,
  _RiskIsRisk200,
  _RiskOpIsPath,
  _PathIsRiskOp,
  _RiskGetNeverRequestBody,
  _RiskHas200,
  _RiskLacks201,
  _TradeList200IsTradeList,
  _TradeListIsTradeList200,
  _TradeListOpIsPath,
  _PathIsTradeListOp,
  _TradeListGetNeverRequestBody,
  _TradeListHas200,
  _TradeListLacks201,
  _TradeCreate200IsEvent,
  _EventIsTradeCreate200,
  _TradeCreateOpIsPath,
  _PathIsTradeCreateOp,
  _TradeCreateBodyIsTrade,
  _TradeIsTradeCreateBody,
  _TradeCreateHas200,
  _TradeCreateLacks201,
  _TradeDelete200IsDelete,
  _DeleteIsTradeDelete200,
  _TradeDeleteOpIsPath,
  _PathIsTradeDeleteOp,
  _TradeDeleteNeverRequestBody,
  _TradeDeleteHas200,
  _TradeDeleteLacks201,
  _CashList200IsCashList,
  _CashListIsCashList200,
  _CashListOpIsPath,
  _PathIsCashListOp,
  _CashListGetNeverRequestBody,
  _CashCreate200IsEvent,
  _EventIsCashCreate200,
  _CashCreateOpIsPath,
  _PathIsCashCreateOp,
  _CashCreateBodyIsCash,
  _CashIsCashCreateBody,
  _CashDelete200IsDelete,
  _DeleteIsCashDelete200,
  _CashDeleteOpIsPath,
  _PathIsCashDeleteOp,
  _CashDeleteNeverRequestBody,
  _CorpList200IsCorpList,
  _CorpListIsCorpList200,
  _CorpListOpIsPath,
  _PathIsCorpListOp,
  _CorpListGetNeverRequestBody,
  _CorpCreate200IsEvent,
  _EventIsCorpCreate200,
  _CorpCreateOpIsPath,
  _PathIsCorpCreateOp,
  _CorpCreateBodyIsCorp,
  _CorpIsCorpCreateBody,
  _CorpDelete200IsDelete,
  _DeleteIsCorpDelete200,
  _CorpDeleteOpIsPath,
  _PathIsCorpDeleteOp,
  _CorpDeleteNeverRequestBody,
  _Fx200IsFx,
  _FxIsFx200,
  _FxOpIsPath,
  _PathIsFxOp,
  _FxNeverRequestBody,
  _FxHas200,
  _FxLacks201,
  _Brokers200IsBrokers,
  _BrokersIsBrokers200,
  _BrokersOpIsPath,
  _PathIsBrokersOp,
  _BrokersGetNeverRequestBody,
  _Parse200IsParse,
  _ParseIsParse200,
  _ParseOpIsPath,
  _PathIsParseOp,
  _Commit200IsCommit,
  _CommitIsCommit200,
  _CommitOpIsPath,
  _PathIsCommitOp,
  _FutuCommit200IsCommit,
  _CommitIsFutuCommit200,
  _FutuCommitOpIsPath,
  _PathIsFutuCommitOp,
  _FutuCommitBodyIsRequest,
  _RequestIsFutuCommitBody,
  _FutuPreview200IsPreview,
  _PreviewIsFutuPreview200,
  _FutuPreviewOpIsPath,
  _PathIsFutuPreviewOp,
  _FutuPreviewNeverRequestBody,
  _PaperTrade200IsCreated,
  _CreatedIsPaperTrade200,
  _PaperTradeOpIsPath,
  _PathIsPaperTradeOp,
  _PaperTradeBodyIsRequest,
  _RequestIsPaperTradeBody,
  _PaperQuality200IsQuality,
  _QualityIsPaperQuality200,
  _PaperQualityOpIsPath,
  _PathIsPaperQualityOp,
  _PaperQualityGetNeverRequestBody,
  _PaperQualityHas200,
  _PaperQualityLacks201,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type PortfolioCostMethod = 'fifo' | 'avg';
export type PortfolioSide = 'buy' | 'sell';
export type PortfolioAccountType = 'real' | 'paper';
export type PortfolioCashDirection = 'in' | 'out';
export type PortfolioCorporateActionType = 'cash_dividend' | 'split_adjustment';
export type PortfolioImportSource = 'file' | 'futu';

export type PortfolioAccountItem = Override<CamelizeKeys<OpenApiAccount>, {
  market: 'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw';
  accountType?: PortfolioAccountType;
}>;

export type PortfolioAccountListResponse = Override<CamelizeKeys<OpenApiAccountList>, {
  accounts: PortfolioAccountItem[];
}>;

export type PortfolioAccountCreateRequest = Override<CamelizeKeys<OpenApiCreate>, {
  accountType?: PortfolioAccountType;
  broker?: string;
  ownerId?: string;
}>;

export type PortfolioAccountUpdateRequest = Override<CamelizeKeys<OpenApiUpdate>, {
  name?: string;
  broker?: string | null;
  market?: 'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw';
  baseCurrency?: string;
  ownerId?: string | null;
  isActive?: boolean;
}>;

export type PortfolioPositionItem = Override<CamelizeKeys<OpenApiPosition>, {
  priceSource?: 'realtime_quote' | 'history_close' | 'missing' | string;
  priceStale?: boolean;
  priceAvailable?: boolean;
  dataQuality?: 'ok' | 'partial' | string;
}>;

export type PortfolioPositionAnalysisRequest = Override<CamelizeKeys<OpenApiPositionAnalysis>, {
  accountId?: number;
  analysisPhase?: 'auto' | 'premarket' | 'intraday' | 'postmarket';
  force?: boolean;
}>;

export type PortfolioAccountSnapshot = Override<CamelizeKeys<OpenApiAccountSnapshot>, {
  costMethod: PortfolioCostMethod;
  dataQuality?: 'ok' | 'partial' | string;
  positions: PortfolioPositionItem[];
}>;

export type PortfolioSnapshotResponse = Override<CamelizeKeys<OpenApiSnapshot>, {
  costMethod: PortfolioCostMethod;
  dataQuality?: 'ok' | 'partial' | string;
  accounts: PortfolioAccountSnapshot[];
}>;

export interface PortfolioConcentrationItem {
  symbol: string;
  marketValueBase: number;
  weightPct: number;
  isAlert: boolean;
}

export interface PortfolioSectorConcentrationItem {
  sector: string;
  marketValueBase: number;
  weightPct: number;
  symbolCount: number;
  isAlert: boolean;
}

export interface PortfolioDrawdownBlock {
  seriesPoints: number;
  maxDrawdownPct: number;
  currentDrawdownPct: number;
  alert: boolean;
  fxStale: boolean;
}

export interface PortfolioStopLossItem {
  accountId: number;
  symbol: string;
  avgCost: number;
  lastPrice: number;
  lossPct: number;
  nearThresholdPct: number;
  isTriggered: boolean;
}

export type PortfolioDecisionSignalRiskItem = Override<CamelizeKeys<OpenApiSignalRiskItem>, {
  signal: Pick<DecisionSignalItem, 'action'> & Partial<DecisionSignalItem>;
}>;

export type PortfolioDecisionSignalRiskBlock = Override<CamelizeKeys<OpenApiSignalRisk>, {
  actions: {
    sell?: number;
    reduce?: number;
    alert?: number;
    [key: string]: number | undefined;
  };
  items: PortfolioDecisionSignalRiskItem[];
}>;

export type PortfolioRiskResponse = Override<CamelizeKeys<OpenApiRisk>, {
  costMethod: PortfolioCostMethod;
  thresholds: Record<string, number>;
  concentration: {
    totalMarketValue: number;
    topWeightPct: number;
    alert: boolean;
    topPositions: PortfolioConcentrationItem[];
  };
  sectorConcentration: {
    totalMarketValue: number;
    topWeightPct: number;
    alert: boolean;
    topSectors: PortfolioSectorConcentrationItem[];
    coverage: Record<string, number>;
    errors: string[];
  };
  drawdown: PortfolioDrawdownBlock;
  stopLoss: {
    nearAlert: boolean;
    triggeredCount: number;
    nearCount: number;
    items: PortfolioStopLossItem[];
  };
  decisionSignalRisk?: PortfolioDecisionSignalRiskBlock;
}>;

export type PortfolioTradeCreateRequest = Override<CamelizeKeys<OpenApiTrade>, {
  operationId: string;
  fee?: number;
  tax?: number;
  market?: 'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw';
  currency?: string;
  tradeUid?: string;
  note?: string;
}>;

export type PaperTradeCreateRequest = Override<CamelizeKeys<OpenApiPaperTrade>, {
  operationId: string;
  price?: number;
  note?: string;
}>;

export type PaperTradeCreatedResponse = Override<CamelizeKeys<OpenApiPaperTradeCreated>, {
  priceSource: 'manual' | 'latest_close' | string;
}>;

export type PaperDecisionQualityReason = CamelizeKeys<OpenApiPaperQualityReason>;

export type PaperDecisionQualityDimension = Override<CamelizeKeys<OpenApiPaperQualityDimension>, {
  status: 'ok' | 'unavailable';
  reasons?: PaperDecisionQualityReason[];
  inputs?: Record<string, number>;
}>;

export type PaperDecisionQualityItem = Override<CamelizeKeys<OpenApiPaperQualityItem>, {
  processScore: number;
  dimensions: Record<string, PaperDecisionQualityDimension>;
  effectiveWeights?: Record<string, number>;
  reasons?: PaperDecisionQualityReason[];
  evidence?: Record<string, unknown>;
  scoreKind?: 'process';
}>;

export type PaperDecisionQualityAggregate = Override<CamelizeKeys<OpenApiPaperQualityAggregate>, {
  dimensions?: Record<string, { score?: number | null; status?: string; sampleSize?: number | null }>;
}>;

export type PaperDecisionQualityResponse = Override<CamelizeKeys<OpenApiPaperQuality>, {
  aggregate: PaperDecisionQualityAggregate;
  items: PaperDecisionQualityItem[];
}>;

export type PortfolioCashLedgerCreateRequest = Override<CamelizeKeys<OpenApiCashCreate>, {
  operationId: string;
  currency?: string;
  note?: string;
}>;

export type PortfolioCorporateActionCreateRequest = Override<CamelizeKeys<OpenApiCorpCreate>, {
  operationId: string;
  market?: 'cn' | 'hk' | 'us' | 'jp' | 'kr' | 'tw';
  currency?: string;
  cashDividendPerShare?: number;
  splitRatio?: number;
  note?: string;
}>;

export type PortfolioEventCreatedResponse = CamelizeKeys<OpenApiEventCreated>;

export type PortfolioDeleteResponse = _BindOpenApiAnchors<CamelizeKeys<OpenApiDelete>>;

export type PortfolioTradeListItem = Override<CamelizeKeys<OpenApiTradeListItem>, {
  side: PortfolioSide;
}>;

export type PortfolioTradeListResponse = Override<CamelizeKeys<OpenApiTradeList>, {
  items: PortfolioTradeListItem[];
}>;

export type PortfolioCashLedgerListItem = Override<CamelizeKeys<OpenApiCashItem>, {
  direction: PortfolioCashDirection;
}>;

export type PortfolioCashLedgerListResponse = Override<CamelizeKeys<OpenApiCashList>, {
  items: PortfolioCashLedgerListItem[];
}>;

export type PortfolioCorporateActionListItem = Override<CamelizeKeys<OpenApiCorpItem>, {
  actionType: PortfolioCorporateActionType;
}>;

export type PortfolioCorporateActionListResponse = Override<CamelizeKeys<OpenApiCorpList>, {
  items: PortfolioCorporateActionListItem[];
}>;

export type PortfolioImportTradeItem = Override<CamelizeKeys<OpenApiImportTrade>, {
  side: PortfolioSide;
}>;

export type PortfolioImportFailedRow = Override<CamelizeKeys<OpenApiFailedRow>, {
  source: Record<string, string>;
}>;

export type PortfolioImportParseResponse = Override<CamelizeKeys<OpenApiParse>, {
  records: PortfolioImportTradeItem[];
  errors: string[];
  failedRows?: PortfolioImportFailedRow[];
}>;

export type PortfolioFutuImportPreviewResponse = Override<CamelizeKeys<OpenApiFutuPreview>, {
  records: PortfolioImportTradeItem[];
  errors: string[];
  failedRows?: PortfolioImportFailedRow[];
}>;

export type PortfolioImportCommitResponse = Override<CamelizeKeys<OpenApiCommit>, {
  errors: string[];
}>;

export type PortfolioFutuImportRequest = Override<CamelizeKeys<OpenApiFutuRequest>, {
  operationId: string;
  asOf?: string;
  expectedSnapshotId: string;
}>;

export type PortfolioImportBrokerItem = Override<CamelizeKeys<OpenApiBrokerItem>, {
  aliases: string[];
  displayName?: string;
}>;

export type PortfolioImportBrokerListResponse = Override<CamelizeKeys<OpenApiBrokerList>, {
  brokers: PortfolioImportBrokerItem[];
}>;

export type PortfolioFxRefreshResponse = CamelizeKeys<OpenApiFxRefresh>;
