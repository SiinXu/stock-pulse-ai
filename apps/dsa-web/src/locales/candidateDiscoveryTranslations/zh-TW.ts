// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// PENDING_NATIVE_REVIEW: High-risk financial discovery copy requires native-language review.
import type { CandidateDiscoveryText } from '../candidateDiscoveryText';

const translations: CandidateDiscoveryText = {
  documentTitle: "選股發現 - StockPulse",
  pageTitle: "選股發現",
  pageDescription: "在同一頁使用有界 AI 候選發現，或可選的 AlphaSift 策略選股；結果僅供研究，不是交易指令。",
  discoveryStatusReady: "AI 發現可用（有界）",
  modeStrategy: "策略選股",
  modeDiscovery: "AI 發現",
  discoveryTitle: "AI 候選發現（有界）",
  discoveryDescription: "用自然語言或條件在自選/持倉/指數分頁宇宙中發現候選。行情經 data_provider 限次獲取，禁止無界全市場掃描。",
  discoveryDisclaimer: "僅供研究篩選，不構成投資建議或交易指令。",
  discoveryQuery: "自然語言 / 條件",
  discoveryQueryPlaceholder: "例如：銀行 漲幅>2 成交額>1億",
  discoveryUniverse: "宇宙",
  discoveryUniverseWatchlist: "自選",
  discoveryUniversePortfolio: "持倉",
  discoveryUniverseIndex: "符號指數分頁",
  discoveryPage: "頁碼",
  discoveryPageSize: "每頁數量",
  discoveryMaxResults: "返回上限",
  discoveryProviderBudget: "行情調用預算",
  discoveryRun: "運行發現",
  discoveryRunning: "發現運行中…",
  discoverySubmitting: "正在提交發現任務…",
  discoveryCancel: "取消",
  discoveryCancelRequested: "已請求取消",
  discoveryCancelFailed: "取消失敗",
  discoveryFailed: "候選發現失敗",
  discoveryNoHits: "當前宇宙與條件沒有命中候選。",
  discoveryProgress: "進度 {progress}% · {message}",
  discoveryCostSummary: "成本：行情 {provider}/{maxProvider} · 候選 {candidates}",
  discoveryUniverseSummary: "宇宙 {source} · 解析 {resolved} · 評估 {evaluated}",
  discoveryAddWatchlist: "加入自選",
  discoveryWatchlistAdded: "已加入自選：{code}",
  discoveryWatchlistFailed: "加入自選失敗",
};

export default translations;
