// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { CandidateDiscoveryResponse } from '../../api/candidateDiscovery';
import { Button } from '../common';
import type { ScreeningResultsEmptyState } from './ScreeningResultsSection';
import type { DiscoveryScreeningText } from './screeningText';

export type DiscoveryResultsEmptyKind = 'no_hits' | 'source_unavailable' | 'unconfigured';

type EmptyStateOptions = {
  text: DiscoveryScreeningText;
  kind: DiscoveryResultsEmptyKind | null;
  loading: boolean;
  onOpenDataSources: () => void;
  onRetry: () => void;
};

export function getDiscoveryResultsEmptyKind(
  result: Pick<CandidateDiscoveryResponse, 'status' | 'emptyReason' | 'candidateCount' | 'candidates'> | null,
): DiscoveryResultsEmptyKind | null {
  if (!result) return null;
  const candidateCount = Array.isArray(result.candidates)
    ? result.candidates.length
    : Number(result.candidateCount ?? 0);
  if (Number.isFinite(candidateCount) && candidateCount > 0) return null;

  const reason = result.emptyReason ?? '';
  const status = result.status ?? '';
  if (status === 'degraded_empty' || reason === 'provider_unavailable') {
    return 'source_unavailable';
  }
  // Backend empty_universe means the selected watchlist/portfolio/index page
  // has no symbols. That is an unconfigured universe, not a quote-source outage.
  if (reason === 'empty_universe') return 'unconfigured';
  return 'no_hits';
}

export function createDiscoveryResultsEmptyState({
  text,
  kind,
  loading,
  onOpenDataSources,
  onRetry,
}: EmptyStateOptions): ScreeningResultsEmptyState {
  const degraded = kind === 'source_unavailable';
  const title = degraded
    ? text.sourcesUnavailableTitle
    : kind === 'unconfigured'
      ? text.diagnosticEmpty
      : text.discoveryNoHits;
  const retry = (
    <Button variant="primary" disabled={loading} aria-label={`${text.retry} · ${title}`} onClick={onRetry}>
      {text.retry}
    </Button>
  );
  if (!degraded && kind !== 'unconfigured') {
    return { title, description: text.noHitsDescription, action: retry };
  }
  return {
    title,
    description: degraded ? text.sourcesUnavailableDescription : text.noHitsDescription,
    action: (
      <div className="flex flex-wrap items-center gap-2">
        {retry}
        <Button variant="secondary" aria-label={`${text.openDataSources} · ${title}`} onClick={onOpenDataSources}>
          {text.openDataSources}
        </Button>
      </div>
    ),
  };
}
