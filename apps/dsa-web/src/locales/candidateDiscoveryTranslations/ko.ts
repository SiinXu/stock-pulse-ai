// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
// PENDING_NATIVE_REVIEW: High-risk financial discovery copy requires native-language review.
import type { CandidateDiscoveryText } from '../candidateDiscoveryText';

const translations: CandidateDiscoveryText = {
  documentTitle: "발견 - StockPulse",
  pageTitle: "발견",
  pageDescription: "같은 페이지에서 제한된 AI 후보 발견 또는 선택적 AlphaSift 전략 스크리닝. 연구 전용이며 매매 지시가 아닙니다.",
  discoveryStatusReady: "AI 발견 준비됨(제한됨)",
  modeStrategy: "전략 스크리닝",
  modeDiscovery: "AI 발견",
  discoveryTitle: "AI 후보 발견(제한됨)",
  discoveryDescription: "관심목록/포트폴리오/페이지된 심볼 지수에서 자연어 또는 조건으로 후보를 찾습니다. 시세는 data_provider 호출 예산 내에서만 조회하며 무제한 전시장 스캔은 하지 않습니다.",
  discoveryDisclaimer: "연구용 스크리닝만 해당합니다. 투자 자문이나 매매 지시가 아닙니다.",
  discoveryQuery: "자연어 / 조건",
  discoveryQueryPlaceholder: "예: 은행 변동 > 2 거래대금 > 100m",
  discoveryUniverse: "유니버스",
  discoveryUniverseWatchlist: "관심목록",
  discoveryUniversePortfolio: "포트폴리오",
  discoveryUniverseIndex: "심볼 지수 페이지",
  discoveryPage: "페이지",
  discoveryPageSize: "페이지 크기",
  discoveryMaxResults: "최대 결과",
  discoveryProviderBudget: "공급자 호출 예산",
  discoveryRun: "발견 실행",
  discoveryRunning: "발견 실행 중…",
  discoverySubmitting: "발견 작업 제출 중…",
  discoveryCancel: "취소",
  discoveryCancelRequested: "취소 요청됨",
  discoveryCancelFailed: "취소 실패",
  discoveryFailed: "후보 발견 실패",
  discoveryNoHits: "이 유니버스와 조건에 맞는 후보가 없습니다.",
  discoveryProgress: "진행 {progress}% · {message}",
  discoveryCostSummary: "비용: 시세 {provider}/{maxProvider} · 후보 {candidates}",
  discoveryUniverseSummary: "유니버스 {source} · 해석 {resolved} · 평가 {evaluated}",
  discoveryAddWatchlist: "관심목록에 추가",
  discoveryWatchlistAdded: "관심목록에 추가됨: {code}",
  discoveryWatchlistFailed: "관심목록 추가 실패",
};

export default translations;
