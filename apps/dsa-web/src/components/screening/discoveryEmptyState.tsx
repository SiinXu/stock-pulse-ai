// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { Play, Settings2 } from 'lucide-react';
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
  if (kind === 'source_unavailable') {
    return {
      title: text.sourcesUnavailableTitle,
      description: text.sourcesUnavailableDescription,
      action: (
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button
            type="button"
            variant="primary"
            disabled={loading}
            aria-label={`${text.retry} · ${text.sourcesUnavailableTitle}`}
            onClick={onRetry}
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            {text.retry}
          </Button>
          <Button
            type="button"
            variant="secondary"
            aria-label={`${text.openDataSources} · ${text.sourcesUnavailableTitle}`}
            onClick={onOpenDataSources}
          >
            <Settings2 className="h-4 w-4" aria-hidden="true" />
            {text.openDataSources}
          </Button>
        </div>
      ),
    };
  }
  if (kind === 'unconfigured') {
    return {
      title: text.diagnosticEmpty,
      description: text.noHitsDescription,
      action: (
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button
            type="button"
            variant="primary"
            disabled={loading}
            aria-label={`${text.retry} · ${text.diagnosticEmpty}`}
            onClick={onRetry}
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            {text.retry}
          </Button>
          <Button
            type="button"
            variant="secondary"
            aria-label={`${text.openDataSources} · ${text.diagnosticEmpty}`}
            onClick={onOpenDataSources}
          >
            <Settings2 className="h-4 w-4" aria-hidden="true" />
            {text.openDataSources}
          </Button>
        </div>
      ),
    };
  }
  return {
    title: text.discoveryNoHits,
    description: text.noHitsDescription,
    action: (
      <Button
        type="button"
        variant="primary"
        disabled={loading}
        aria-label={`${text.retry} · ${text.discoveryNoHits}`}
        onClick={onRetry}
      >
        <Play className="h-4 w-4" aria-hidden="true" />
        {text.retry}
      </Button>
    ),
  };
}
