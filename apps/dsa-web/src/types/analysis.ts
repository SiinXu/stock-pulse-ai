// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type { components, operations, paths } from './api.generated';

type CamelCase<S extends string> = S extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : S;

type CamelizeKeys<T> = T extends readonly (infer U)[]
  ? CamelizeKeys<U>[]
  : T extends object
    ? { [K in keyof T as CamelCase<K & string>]: CamelizeKeys<T[K]> }
    : T;

type Override<T, U> = Omit<T, keyof U> & U;

type OpenApiAnalyze = components['schemas']['AnalyzeRequest'];
type OpenApiAccepted = components['schemas']['TaskAccepted'];
type OpenApiBatchItem = components['schemas']['BatchTaskAcceptedItem'];
type OpenApiBatchDup = components['schemas']['BatchDuplicateTaskItem'];
type OpenApiBatch = components['schemas']['BatchTaskAcceptedResponse'];
type OpenApiTaskStatus = components['schemas']['TaskStatus'];
type OpenApiTaskInfo = components['schemas']['TaskInfo'];
type OpenApiTaskList = components['schemas']['TaskListResponse'];
type OpenApiResult = components['schemas']['AnalysisResultResponse'];
type OpenApiReport = components['schemas']['AnalysisReport'];
type OpenApiReportMeta = components['schemas']['ReportMeta'];
type OpenApiReportSummary = components['schemas']['ReportSummary'];
type OpenApiReportStrategy = components['schemas']['ReportStrategy'];
type OpenApiReportDetails = components['schemas']['ReportDetails'];
type OpenApiPhase = components['schemas']['MarketPhaseSummary'];
type OpenApiReviewRequest = components['schemas']['MarketReviewRequest'];
type OpenApiReviewAccepted = components['schemas']['MarketReviewAccepted'];
type OpenApiPack = components['schemas']['AnalysisContextPackOverview'];
type OpenApiPackSubject = components['schemas']['AnalysisContextPackOverviewSubject'];
type OpenApiPackBlock = components['schemas']['AnalysisContextPackOverviewBlock'];
type OpenApiPackCounts = components['schemas']['AnalysisContextPackOverviewCounts'];
type OpenApiPackMetadata = components['schemas']['AnalysisContextPackOverviewMetadata'];
type OpenApiPackQuality = components['schemas']['AnalysisContextPackOverviewDataQuality'];
type OpenApiInsights = components['schemas']['ReportStructuredInsights'];
type OpenApiPhaseDecision = components['schemas']['ReportStructuredPhaseDecision'];
type OpenApiPhaseContext = components['schemas']['ReportStructuredPhaseContext'];
type OpenApiSignalAttribution = components['schemas']['ReportStructuredSignalAttribution'];
type OpenApiSynthesis = components['schemas']['ReportStructuredStrategySynthesis'];
type OpenApiSynthesisSkill = components['schemas']['ReportStructuredStrategySkill'];
type OpenApiSynthesisConflict = components['schemas']['ReportStructuredStrategyConflict'];
type OpenApiSynthesisSummary = components['schemas']['ReportStructuredStrategySummary'];
type OpenApiCommittee = components['schemas']['ReportStructuredCommitteeDeliberation'];
type OpenApiCommitteeMember = components['schemas']['ReportStructuredCommitteeMember'];
type OpenApiCommitteeConclusion = components['schemas']['ReportStructuredCommitteeConclusion'];
type OpenApiCommitteeOpinion = components['schemas']['ReportStructuredCommitteeOpinion'];
type OpenApiCommitteeDivergence = components['schemas']['ReportStructuredCommitteeDivergence'];
type OpenApiHistoryItem = components['schemas']['HistoryItem'];
type OpenApiHistoryList = components['schemas']['HistoryListResponse'];
type OpenApiHistorySearchItem = components['schemas']['HistorySearchItem'];
type OpenApiHistorySearch = components['schemas']['HistorySearchResponse'];
type OpenApiNewsItem = components['schemas']['NewsIntelItem'];
type OpenApiNews = components['schemas']['NewsIntelResponse'];
type OpenApiStockBarItem = components['schemas']['StockBarItem'];
type OpenApiStockBar = components['schemas']['StockBarResponse'];

type OpenApiAnalyzeOp = operations['trigger_analysis_api_v1_analysis_analyze_post'];
type OpenApiReviewOp = operations['trigger_market_review_api_v1_analysis_market_review_post'];
type OpenApiStatusOp = operations['get_analysis_status_api_v1_analysis_status__task_id__get'];
type OpenApiTaskListOp = operations['get_task_list_api_v1_analysis_tasks_get'];
type OpenApiCancelOp = operations['cancelAnalysisTask'];

type OpenApiAnalyzePathPost = paths['/api/v1/analysis/analyze']['post'];
type OpenApiReviewPathPost = paths['/api/v1/analysis/market-review']['post'];
type OpenApiStatusPathGet = paths['/api/v1/analysis/status/{task_id}']['get'];
type OpenApiTaskListPathGet = paths['/api/v1/analysis/tasks']['get'];
type OpenApiCancelPathPost = paths['/api/v1/analysis/tasks/{task_id}/cancel']['post'];

type OpenApiAnalyzePost200 = OpenApiAnalyzeOp['responses']['200']['content']['application/json'];
type OpenApiAnalyzePost202 = OpenApiAnalyzeOp['responses']['202']['content']['application/json'];
type OpenApiAnalyzeBody = OpenApiAnalyzeOp['requestBody']['content']['application/json'];
type OpenApiReviewPost202 = OpenApiReviewOp['responses']['202']['content']['application/json'];
type OpenApiStatusGet200 = OpenApiStatusOp['responses']['200']['content']['application/json'];
type OpenApiTaskListGet200 = OpenApiTaskListOp['responses']['200']['content']['application/json'];
type OpenApiCancelPost200 = OpenApiCancelOp['responses']['200']['content']['application/json'];

type _Assert<T extends true> = T;
type _Analyze200IsResult = _Assert<OpenApiAnalyzePost200 extends OpenApiResult ? true : false>;
type _ResultIsAnalyze200 = _Assert<OpenApiResult extends OpenApiAnalyzePost200 ? true : false>;
type _AnalyzeOpIsPath = _Assert<OpenApiAnalyzeOp extends OpenApiAnalyzePathPost ? true : false>;
type _PathIsAnalyzeOp = _Assert<OpenApiAnalyzePathPost extends OpenApiAnalyzeOp ? true : false>;
type _AnalyzeBodyIsRequest = _Assert<OpenApiAnalyzeBody extends OpenApiAnalyze ? true : false>;
type _RequestIsAnalyzeBody = _Assert<OpenApiAnalyze extends OpenApiAnalyzeBody ? true : false>;
type _AnalyzeHas200 = _Assert<200 extends keyof OpenApiAnalyzeOp['responses'] ? true : false>;
type _AnalyzeHas202 = _Assert<202 extends keyof OpenApiAnalyzeOp['responses'] ? true : false>;
type _AnalyzeLacks201 = _Assert<201 extends keyof OpenApiAnalyzeOp['responses'] ? false : true>;
type _Analyze202IsAcceptedOrBatch = _Assert<
  OpenApiAnalyzePost202 extends OpenApiAccepted | OpenApiBatch ? true : false
>;
type _AcceptedOrBatchIsAnalyze202 = _Assert<
  OpenApiAccepted | OpenApiBatch extends OpenApiAnalyzePost202 ? true : false
>;
type _Review202IsAccepted = _Assert<OpenApiReviewPost202 extends OpenApiReviewAccepted ? true : false>;
type _AcceptedIsReview202 = _Assert<OpenApiReviewAccepted extends OpenApiReviewPost202 ? true : false>;
type _ReviewOpIsPath = _Assert<OpenApiReviewOp extends OpenApiReviewPathPost ? true : false>;
type _PathIsReviewOp = _Assert<OpenApiReviewPathPost extends OpenApiReviewOp ? true : false>;
type _ReviewHas202 = _Assert<202 extends keyof OpenApiReviewOp['responses'] ? true : false>;
type _ReviewLacks200 = _Assert<200 extends keyof OpenApiReviewOp['responses'] ? false : true>;
type _ReviewLacks201 = _Assert<201 extends keyof OpenApiReviewOp['responses'] ? false : true>;
type _Status200IsStatus = _Assert<OpenApiStatusGet200 extends OpenApiTaskStatus ? true : false>;
type _StatusIsStatus200 = _Assert<OpenApiTaskStatus extends OpenApiStatusGet200 ? true : false>;
type _StatusOpIsPath = _Assert<OpenApiStatusOp extends OpenApiStatusPathGet ? true : false>;
type _PathIsStatusOp = _Assert<OpenApiStatusPathGet extends OpenApiStatusOp ? true : false>;
type _StatusGetNeverRequestBody = _Assert<OpenApiStatusOp extends { requestBody?: never } ? true : false>;
type _StatusHas200 = _Assert<200 extends keyof OpenApiStatusOp['responses'] ? true : false>;
type _StatusLacks201 = _Assert<201 extends keyof OpenApiStatusOp['responses'] ? false : true>;
type _TaskList200IsTaskList = _Assert<OpenApiTaskListGet200 extends OpenApiTaskList ? true : false>;
type _TaskListIsTaskList200 = _Assert<OpenApiTaskList extends OpenApiTaskListGet200 ? true : false>;
type _TaskListOpIsPath = _Assert<OpenApiTaskListOp extends OpenApiTaskListPathGet ? true : false>;
type _PathIsTaskListOp = _Assert<OpenApiTaskListPathGet extends OpenApiTaskListOp ? true : false>;
type _TaskListGetNeverRequestBody = _Assert<
  OpenApiTaskListOp extends { requestBody?: never } ? true : false
>;
type _TaskListHas200 = _Assert<200 extends keyof OpenApiTaskListOp['responses'] ? true : false>;
type _TaskListLacks201 = _Assert<201 extends keyof OpenApiTaskListOp['responses'] ? false : true>;
type _Cancel200IsStatus = _Assert<OpenApiCancelPost200 extends OpenApiTaskStatus ? true : false>;
type _StatusIsCancel200 = _Assert<OpenApiTaskStatus extends OpenApiCancelPost200 ? true : false>;
type _CancelOpIsPath = _Assert<OpenApiCancelOp extends OpenApiCancelPathPost ? true : false>;
type _PathIsCancelOp = _Assert<OpenApiCancelPathPost extends OpenApiCancelOp ? true : false>;
type _CancelNeverRequestBody = _Assert<OpenApiCancelOp extends { requestBody?: never } ? true : false>;
type _CancelHas200 = _Assert<200 extends keyof OpenApiCancelOp['responses'] ? true : false>;
type _CancelLacks201 = _Assert<201 extends keyof OpenApiCancelOp['responses'] ? false : true>;

type _OpenApiAnchors = [
  _Analyze200IsResult,
  _ResultIsAnalyze200,
  _AnalyzeOpIsPath,
  _PathIsAnalyzeOp,
  _AnalyzeBodyIsRequest,
  _RequestIsAnalyzeBody,
  _AnalyzeHas200,
  _AnalyzeHas202,
  _AnalyzeLacks201,
  _Analyze202IsAcceptedOrBatch,
  _AcceptedOrBatchIsAnalyze202,
  _Review202IsAccepted,
  _AcceptedIsReview202,
  _ReviewOpIsPath,
  _PathIsReviewOp,
  _ReviewHas202,
  _ReviewLacks200,
  _ReviewLacks201,
  _Status200IsStatus,
  _StatusIsStatus200,
  _StatusOpIsPath,
  _PathIsStatusOp,
  _StatusGetNeverRequestBody,
  _StatusHas200,
  _StatusLacks201,
  _TaskList200IsTaskList,
  _TaskListIsTaskList200,
  _TaskListOpIsPath,
  _PathIsTaskListOp,
  _TaskListGetNeverRequestBody,
  _TaskListHas200,
  _TaskListLacks201,
  _Cancel200IsStatus,
  _StatusIsCancel200,
  _CancelOpIsPath,
  _PathIsCancelOp,
  _CancelNeverRequestBody,
  _CancelHas200,
  _CancelLacks201,
];
type _BindOpenApiAnchors<T> = [_OpenApiAnchors] extends [unknown] ? T : T;

export type StockReportType = 'simple' | 'detailed' | 'full' | 'brief';
export type ReportType = StockReportType | 'market_review';
export type AnalysisPhase = 'auto' | 'premarket' | 'intraday' | 'postmarket';
export type MarketReviewRegion = 'cn' | 'hk' | 'us' | 'jp' | 'kr';
export type TaskLifecycleStatus =
  | 'pending'
  | 'processing'
  | 'cancel_requested'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'interrupted';
export type ReportLanguage = 'zh' | 'en' | 'ko';
export type MarketPhaseValue =
  | 'premarket'
  | 'intraday'
  | 'lunch_break'
  | 'closing_auction'
  | 'postmarket'
  | 'non_trading'
  | 'unknown';
export type DecisionAction = 'buy' | 'add' | 'hold' | 'reduce' | 'sell' | 'watch' | 'avoid' | 'alert';
export type SentimentLabel =
  | '极度悲观'
  | '悲观'
  | '中性'
  | '乐观'
  | '极度乐观'
  | 'Very Bearish'
  | 'Bearish'
  | 'Neutral'
  | 'Bullish'
  | 'Very Bullish'
  | '매우 비관'
  | '비관'
  | '중립'
  | '낙관'
  | '매우 낙관';
export type AnalysisContextPackBlockStatus =
  | 'available'
  | 'missing'
  | 'not_supported'
  | 'fallback'
  | 'stale'
  | 'estimated'
  | 'partial'
  | 'fetch_failed';
export type AnalysisContextPackDataQualityLevel = 'good' | 'usable' | 'limited' | 'poor';

export type AnalysisRequest = Omit<Override<CamelizeKeys<OpenApiAnalyze>, {
  analysisPhase?: AnalysisPhase;
  asyncMode?: boolean;
  forceRefresh?: boolean;
  notify?: boolean;
  reportType?: StockReportType;
  selectionSource?: 'manual' | 'autocomplete' | 'import' | 'image';
  reportLanguage?: ReportLanguage;
  stockCode?: string;
  stockCodes?: string[];
  stockName?: string;
  originalQuery?: string;
  skills?: string[];
}>, 'debateMaxRounds' | 'enableDebate' | 'useMemory'>;

export type MarketReviewRequest = Override<CamelizeKeys<OpenApiReviewRequest>, {
  sendNotification?: boolean;
  reportLanguage?: ReportLanguage;
  regions?: readonly MarketReviewRegion[];
}>;

export type MarketReviewAccepted = Override<CamelizeKeys<OpenApiReviewAccepted>, {
  status: 'accepted';
  messageCode?: string;
  messageParams?: Record<string, unknown>;
  taskId?: string;
  traceId?: string;
}>;

export type MarketPhaseSummary = Override<CamelizeKeys<OpenApiPhase>, {
  phase: MarketPhaseValue;
  warnings: string[];
}>;

export type ReportMeta = Override<CamelizeKeys<OpenApiReportMeta>, {
  stockName: string;
  createdAt: string;
  reportType: ReportType;
  reportLanguage?: ReportLanguage;
  id?: number;
  currentPrice?: number;
  changePct?: number;
  modelUsed?: string;
  marketPhaseSummary?: MarketPhaseSummary | null;
}>;

export type ReportSummary = Override<CamelizeKeys<OpenApiReportSummary>, {
  analysisSummary: string;
  operationAdvice: string;
  action?: DecisionAction | null;
  actionLabel?: string | null;
  trendPrediction: string;
  sentimentScore: number;
  sentimentLabel?: SentimentLabel;
  /**
   * Canonical Risk Manager gate payload (`risk-manager-result/v1`) projected by
   * the backend analysis service. Missing must present as not-evaluated on Web —
   * never implied pass.
   */
  riskManager?: Record<string, unknown> | null;
}>;

export type ReportStrategy = Override<CamelizeKeys<OpenApiReportStrategy>, {
  idealBuy?: string;
  secondaryBuy?: string;
  stopLoss?: string;
  takeProfit?: string;
}>;

export interface RelatedBoard {
  name: string;
  code?: string;
  type?: string;
}

export interface SectorRankingItem {
  name: string;
  code?: string;
  changePct?: number;
  source?: string;
  updatedAt?: string;
}

export interface SectorRankings {
  top?: SectorRankingItem[];
  bottom?: SectorRankingItem[];
}

export type MarketStructureStatus = 'ok' | 'partial' | 'unknown' | 'not_supported';
export type MarketStructureThemeSource = 'industry' | 'concept' | 'mixed' | 'unknown';
export type MarketStructureThemePhase = 'warming' | 'accelerating' | 'cooling' | 'unknown';
export type MarketStructureStockRole = 'leader' | 'follower' | 'edge' | 'unknown';

export interface MarketStructureSource {
  provider: string;
  dataset: string;
  status: string;
  message?: string | null;
}

export interface MarketStructureDataQuality {
  status: MarketStructureStatus;
  missingFields?: string[];
  sources?: MarketStructureSource[];
  errors?: string[];
}

export interface RankedThemeItem {
  name: string;
  changePct?: number | null;
  rank?: number | null;
  source?: MarketStructureThemeSource;
  code?: string | null;
  updatedAt?: string | null;
}

export interface MarketThemeItem extends RankedThemeItem {
  phase?: MarketStructureThemePhase;
  strengthScore?: number | null;
  reason?: string | null;
}

export interface ThemeBreadth {
  activeCount?: number;
  leadingIndustryCount?: number;
  leadingConceptCount?: number;
  laggingCount?: number;
}

export interface MarketThemeContext {
  schemaVersion: 'market-theme-v1';
  status: MarketStructureStatus;
  market: string;
  tradeDate?: string | null;
  activeThemes?: MarketThemeItem[];
  leadingIndustries?: RankedThemeItem[];
  leadingConcepts?: RankedThemeItem[];
  laggingThemes?: RankedThemeItem[];
  themeBreadth?: ThemeBreadth;
  dataQuality?: MarketStructureDataQuality;
}

export interface StockBoardPosition {
  name: string;
  type?: string | null;
  code?: string | null;
  rank?: number | null;
  changePct?: number | null;
  source?: MarketStructureThemeSource;
}

export interface PrimaryTheme {
  name: string;
  source?: MarketStructureThemeSource;
  phase?: MarketStructureThemePhase;
  rank?: number | null;
  changePct?: number | null;
}

export interface MarketStructureRiskTag {
  code: string;
  message: string;
}

export interface StockMarketPosition {
  schemaVersion: 'stock-market-position-v1';
  status: MarketStructureStatus;
  stockCode: string;
  stockName?: string | null;
  market: string;
  primaryTheme?: PrimaryTheme | null;
  relatedBoards?: StockBoardPosition[];
  stockRole?: MarketStructureStockRole;
  themePhase?: MarketStructureThemePhase;
  riskTags?: MarketStructureRiskTag[];
  missingFields?: string[];
}

export interface MarketStructureContext {
  schemaVersion: 'market-structure-v1';
  status: MarketStructureStatus;
  market: string;
  tradeDate?: string | null;
  marketThemeContext: MarketThemeContext;
  stockMarketPosition: StockMarketPosition;
}

export interface MarketReviewPayloadSection {
  key?: string;
  title: string;
  markdown: string;
}

export interface MarketReviewIndex {
  code: string;
  name: string;
  current?: number;
  change?: number;
  changePct?: number;
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
  amount?: number;
  amplitude?: number;
}

export interface MarketReviewBreadth {
  upCount?: number;
  downCount?: number;
  flatCount?: number;
  limitUpCount?: number;
  limitDownCount?: number;
  totalAmount?: number;
  turnoverUnit?: string;
}

export interface MarketReviewPayload {
  version?: number;
  kind?: 'market_review' | string;
  region?: string;
  language?: ReportLanguage | string;
  title?: string;
  rootTitle?: string;
  generatedAt?: string;
  date?: string;
  marketScope?: string;
  marketLight?: Record<string, unknown>;
  breadth?: MarketReviewBreadth;
  indices?: MarketReviewIndex[];
  sectors?: SectorRankings;
  concepts?: SectorRankings;
  news?: Array<Record<string, unknown>>;
  sections?: MarketReviewPayloadSection[];
  markets?: Record<string, MarketReviewPayload>;
  markdownReport?: string;
}

export type AnalysisContextPackOverviewSubject = CamelizeKeys<OpenApiPackSubject>;
export type AnalysisContextPackOverviewCounts = CamelizeKeys<OpenApiPackCounts>;
export type AnalysisContextPackOverviewMetadata = CamelizeKeys<OpenApiPackMetadata>;

export type AnalysisContextPackOverviewBlock = Override<CamelizeKeys<OpenApiPackBlock>, {
  status: AnalysisContextPackBlockStatus;
  warnings: string[];
  missingReasons: string[];
}>;

export type AnalysisContextPackOverviewDataQuality = Override<CamelizeKeys<OpenApiPackQuality>, {
  level?: AnalysisContextPackDataQualityLevel | null;
  blockScores: Record<string, number>;
  limitations: string[];
}>;

export type AnalysisContextPackOverview = Override<CamelizeKeys<OpenApiPack>, {
  subject: AnalysisContextPackOverviewSubject;
  blocks: AnalysisContextPackOverviewBlock[];
  counts: AnalysisContextPackOverviewCounts;
  dataQuality?: AnalysisContextPackOverviewDataQuality | null;
  warnings: string[];
  metadata: AnalysisContextPackOverviewMetadata;
}>;

export type ReportStrataFrameworkStatus =
  | 'aligned'
  | 'partial'
  | 'conflict'
  | 'not_configured';

export interface ReportStrataVerifiedFact {
  statement: string;
  sourceId?: string | null;
  asOf?: string | null;
}

export interface ReportStrataGapOrConflict {
  kind: 'missing' | 'conflict';
  description: string;
  sourceIds?: string[];
}

export interface ReportStrataFrameworkAlignment {
  status: ReportStrataFrameworkStatus;
  summary?: string;
  frameworkTitle?: string | null;
  frameworkVersion?: number | null;
  frameworkId?: string | null;
}

/** Issue #616 evidence strata for full-report presentation. */
export interface ReportStrata {
  schemaVersion?: string;
  verifiedFacts?: ReportStrataVerifiedFact[];
  missingOrConflicts?: ReportStrataGapOrConflict[];
  modelInference?: string[];
  risksCounterEvidence?: string[];
  frameworkAlignment?: ReportStrataFrameworkAlignment;
  disclaimer?: string;
}

export type ReportPhaseContext = CamelizeKeys<OpenApiPhaseContext>;

export type ReportPhaseDecision = Override<CamelizeKeys<OpenApiPhaseDecision>, {
  phaseContext?: ReportPhaseContext;
}>;

export type ReportSignalAttribution = CamelizeKeys<OpenApiSignalAttribution>;
export type ReportStrategySynthesisSkill = CamelizeKeys<OpenApiSynthesisSkill>;
export type ReportStrategySynthesisConflict = CamelizeKeys<OpenApiSynthesisConflict>;
export type ReportStrategySynthesisSummaryParams = CamelizeKeys<OpenApiSynthesisSummary>;

export type ReportStrategySynthesis = Override<CamelizeKeys<OpenApiSynthesis>, {
  conflicts?: ReportStrategySynthesisConflict[];
  supportingSkills?: ReportStrategySynthesisSkill[];
  opposingSkills?: ReportStrategySynthesisSkill[];
  summaryParams?: ReportStrategySynthesisSummaryParams;
}>;

export type ReportCommitteeMember = CamelizeKeys<OpenApiCommitteeMember>;
export type ReportCommitteeConclusion = CamelizeKeys<OpenApiCommitteeConclusion>;
export type ReportCommitteeOpinion = CamelizeKeys<OpenApiCommitteeOpinion>;

export type ReportCommitteeDivergence = Override<CamelizeKeys<OpenApiCommitteeDivergence>, {
  conflictType?: string;
  descriptionKey?: string;
}>;

export type ReportCommitteeDeliberation = Override<CamelizeKeys<OpenApiCommittee>, {
  members?: ReportCommitteeMember[];
  conclusion?: ReportCommitteeConclusion;
  supportingOpinions?: ReportCommitteeOpinion[];
  dissentingOpinions?: ReportCommitteeOpinion[];
  divergencePoints?: ReportCommitteeDivergence[];
}>;

export type ReportStructuredInsights = Override<CamelizeKeys<OpenApiInsights>, {
  schemaVersion: 'report-structured-insights-v1';
  phaseDecision?: ReportPhaseDecision;
  signalAttribution?: ReportSignalAttribution;
  strategySynthesis?: ReportStrategySynthesis;
  committeeDeliberation?: ReportCommitteeDeliberation;
}>;

export type ReportDetails = Override<CamelizeKeys<OpenApiReportDetails>, {
  newsContent?: string;
  rawResult?: Record<string, unknown>;
  contextSnapshot?: Record<string, unknown> & { marketReviewPayload?: MarketReviewPayload };
  analysisContextPackOverview?: AnalysisContextPackOverview | null;
  financialReport?: Record<string, unknown>;
  dividendMetrics?: Record<string, unknown>;
  belongBoards?: RelatedBoard[];
  sectorRankings?: SectorRankings;
  conceptRankings?: SectorRankings;
  marketStructure?: MarketStructureContext | null;
  reportStrata?: ReportStrata | null;
  structuredInsights?: ReportStructuredInsights | null;
}>;

export type AnalysisReport = Override<CamelizeKeys<OpenApiReport>, {
  meta: ReportMeta;
  summary: ReportSummary;
  strategy?: ReportStrategy;
  details?: ReportDetails;
}>;

export type RunDiagnosticStatus = 'normal' | 'degraded' | 'failed' | 'unknown';

export type RunDiagnosticComponentStatus =
  | 'ok'
  | 'degraded'
  | 'failed'
  | 'unknown'
  | 'not_configured'
  | 'skipped';

export interface RunDiagnosticComponent {
  key: string;
  label: string;
  status: RunDiagnosticComponentStatus;
  message: string;
  details?: Record<string, unknown>;
}

export interface RunDiagnosticSummary {
  traceId?: string;
  taskId?: string;
  queryId?: string;
  stockCode?: string;
  triggerSource?: string;
  status: RunDiagnosticStatus;
  statusLabel: string;
  reason: string;
  components: Record<string, RunDiagnosticComponent>;
  copyText: string;
}

export type AnalysisResult = Override<CamelizeKeys<OpenApiResult>, {
  stockName: string;
  report: AnalysisReport;
  diagnosticSummary?: RunDiagnosticSummary;
  traceId?: string;
}>;

export type TaskAccepted = Override<CamelizeKeys<OpenApiAccepted>, {
  status: Extract<TaskLifecycleStatus, 'pending' | 'processing'>;
  analysisPhase?: AnalysisPhase;
  message?: string;
  messageCode?: string;
  messageParams?: Record<string, unknown>;
  traceId?: string;
}>;

export type BatchTaskAcceptedItem = Override<CamelizeKeys<OpenApiBatchItem>, {
  status: Extract<TaskLifecycleStatus, 'pending' | 'processing'>;
  analysisPhase?: AnalysisPhase;
  message?: string;
  messageCode?: string;
  messageParams?: Record<string, unknown>;
  traceId?: string;
}>;

export type BatchDuplicateTaskItem = _BindOpenApiAnchors<CamelizeKeys<OpenApiBatchDup>>;

export type BatchTaskAcceptedResponse = Override<CamelizeKeys<OpenApiBatch>, {
  accepted: BatchTaskAcceptedItem[];
  duplicates: BatchDuplicateTaskItem[];
}>;

export type AnalyzeAsyncResponse = TaskAccepted | BatchTaskAcceptedResponse;

export type AnalyzeResponse = AnalysisResult | AnalyzeAsyncResponse;

export type TaskStatus = Override<CamelizeKeys<OpenApiTaskStatus>, {
  status: TaskLifecycleStatus;
  message?: string;
  messageCode?: string;
  messageParams?: Record<string, unknown>;
  result?: AnalysisResult;
  marketReviewReport?: string;
  marketReviewPayload?: MarketReviewPayload;
  region?: string;
  error?: string;
  stockName?: string;
  originalQuery?: string;
  selectionSource?: string;
  analysisPhase?: AnalysisPhase | null;
  skills?: string[];
  traceId?: string;
  progress?: number;
}>;

export type TaskInfo = Override<CamelizeKeys<OpenApiTaskInfo>, {
  status: TaskLifecycleStatus;
  analysisPhase?: AnalysisPhase;
  message?: string;
  messageCode?: string;
  messageParams?: Record<string, unknown>;
  traceId?: string;
  stockName?: string;
  startedAt?: string;
  completedAt?: string;
  error?: string;
  originalQuery?: string;
  selectionSource?: string;
  skills?: string[];
  region?: string;
}>;

export type TaskListResponse = Override<CamelizeKeys<OpenApiTaskList>, {
  tasks: TaskInfo[];
}>;

export interface DuplicateTaskError {
  error: 'duplicate_task';
  message: string;
  params?: {
    stockCode?: string;
    existingTaskId?: string;
  };
  /** Legacy pre-envelope fields retained for rolling-upgrade compatibility. */
  stockCode?: string;
  existingTaskId?: string;
  details?: unknown;
  traceId?: string;
}

export type HistoryItem = Override<CamelizeKeys<OpenApiHistoryItem>, {
  id: number;
  createdAt: string;
  action?: DecisionAction | null;
  actionLabel?: string | null;
  reportType?: ReportType;
  stockName?: string;
  region?: string;
  trendPrediction?: string;
  analysisSummary?: string;
  sentimentScore?: number;
  operationAdvice?: string;
  currentPrice?: number;
  changePct?: number;
  volumeRatio?: number;
  turnoverRate?: number;
  modelUsed?: string;
  marketPhaseSummary?: MarketPhaseSummary | null;
}>;

export type StockHistoryRange = 'all' | '30d' | '90d';

export interface StockHistoryFilters {
  range: StockHistoryRange;
  model: string;
  sort: 'desc' | 'asc';
}

export type HistoryListResponse = Override<CamelizeKeys<OpenApiHistoryList>, {
  items: HistoryItem[];
}>;

export type HistorySearchItem = Override<CamelizeKeys<OpenApiHistorySearchItem>, {
  stockName?: string;
  reportType?: string;
  summary?: string;
  createdAt?: string;
}>;

export type HistorySearchResponse = Override<CamelizeKeys<OpenApiHistorySearch>, {
  items: HistorySearchItem[];
}>;

export type NewsIntelItem = CamelizeKeys<OpenApiNewsItem>;

export type NewsIntelResponse = Override<CamelizeKeys<OpenApiNews>, {
  items: NewsIntelItem[];
}>;

export interface HistoryFilters {
  stockCode?: string;
  reportType?: ReportType;
  startDate?: string;
  endDate?: string;
}

export interface HistoryPagination {
  page: number;
  limit: number;
}

export type StockBarItem = Override<CamelizeKeys<OpenApiStockBarItem>, {
  action?: DecisionAction | null;
  actionLabel?: string | null;
  stockName?: string;
  reportType?: string;
  sentimentScore?: number;
  operationAdvice?: string;
  lastAnalysisTime?: string;
  modelUsed?: string;
  marketPhaseSummary?: MarketPhaseSummary | null;
}>;

export type StockBarResponse = Override<CamelizeKeys<OpenApiStockBar>, {
  items: StockBarItem[];
}>;

export interface ApiError {
  error: string;
  message: string;
  details?: unknown;
  /** @deprecated Read-only server alias of details during the compatibility window. */
  detail?: unknown;
  traceId?: string | null;
}

/** Get sentiment label by score */
export const getSentimentLabel = (score: number, language: ReportLanguage = 'zh'): SentimentLabel => {
  if (language === 'en') {
    if (score <= 20) return 'Very Bearish';
    if (score <= 40) return 'Bearish';
    if (score <= 60) return 'Neutral';
    if (score <= 80) return 'Bullish';
    return 'Very Bullish';
  }
  if (language === 'ko') {
    if (score <= 20) return '매우 비관';
    if (score <= 40) return '비관';
    if (score <= 60) return '중립';
    if (score <= 80) return '낙관';
    return '매우 낙관';
  }
  if (score <= 20) return '极度悲观';
  if (score <= 40) return '悲观';
  if (score <= 60) return '中性';
  if (score <= 80) return '乐观';
  return '极度乐观';
};

/** Get sentiment color by score */
export const getSentimentColor = (score: number): string => {
  if (score <= 20) return '#ef4444'; // red-500
  if (score <= 40) return '#f97316'; // orange-500
  if (score <= 60) return '#eab308'; // yellow-500
  if (score <= 80) return '#22c55e'; // green-500
  return '#10b981'; // emerald-500
};
