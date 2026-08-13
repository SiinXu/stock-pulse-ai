// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// PENDING_NATIVE_REVIEW: High-risk financial discovery copy requires native-language review.
import type { CandidateDiscoveryText } from '../candidateDiscoveryText';

const translations: CandidateDiscoveryText = {
  documentTitle: "発見 - StockPulse",
  pageTitle: "発見",
  pageDescription: "同一ページで有界 AI 候補発見、または任意の AlphaSift 戦略スクリーニング。研究用途のみで売買指示ではありません。",
  discoveryStatusReady: "AI 発見が利用可能（有界）",
  modeStrategy: "戦略スクリーニング",
  modeDiscovery: "AI 発見",
  discoveryTitle: "AI 候補発見（有界）",
  discoveryDescription: "ウォッチリスト／保有／ページ分割された銘柄索引で自然言語または条件から候補を発見。相場は data_provider の呼出予算内のみ。無制限の全市場スキャンはしません。",
  discoveryDisclaimer: "研究用スクリーニングのみ。投資助言や売買指示ではありません。",
  discoveryQuery: "自然言語 / 条件",
  discoveryQueryPlaceholder: "例: 銀行 騰落 > 2 売買代金 > 1億相当",
  discoveryUniverse: "ユニバース",
  discoveryUniverseWatchlist: "ウォッチリスト",
  discoveryUniversePortfolio: "ポートフォリオ",
  discoveryUniverseIndex: "銘柄索引ページ",
  discoveryPage: "ページ",
  discoveryPageSize: "ページサイズ",
  discoveryMaxResults: "最大件数",
  discoveryProviderBudget: "プロバイダ呼出予算",
  discoveryRun: "発見を実行",
  discoveryRunning: "発見を実行中…",
  discoverySubmitting: "発見タスクを送信中…",
  discoveryCancel: "キャンセル",
  discoveryCancelRequested: "キャンセル要求済み",
  discoveryCancelFailed: "キャンセルに失敗",
  discoveryFailed: "候補発見に失敗",
  discoveryNoHits: "このユニバースと条件に一致する候補がありません。",
  discoveryProgress: "進捗 {progress}% · {message}",
  discoveryCostSummary: "コスト: 相場 {provider}/{maxProvider} · 候補 {candidates}",
  discoveryUniverseSummary: "ユニバース {source} · 解決 {resolved} · 評価 {evaluated}",
  discoveryAddWatchlist: "ウォッチリストへ追加",
  discoveryWatchlistAdded: "ウォッチリストに追加済み: {code}",
  discoveryWatchlistFailed: "ウォッチリスト追加に失敗",
};

export default translations;
