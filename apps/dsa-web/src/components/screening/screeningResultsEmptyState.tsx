import { Play, Settings2, SlidersHorizontal } from 'lucide-react';
import { Button } from '../common';
import type { ScreeningResultsEmptyState } from './ScreeningResultsSection';
import type { ScreeningResultsEmptyKind } from './screeningPageState';
import type { ScreeningText } from './screeningText';

type Options = {
  text: ScreeningText;
  kind: ScreeningResultsEmptyKind | null;
  loading: boolean;
  onOpenConfiguration: () => void;
  onOpenDataSources: () => void;
  onRetry: () => void;
};

export default function createScreeningResultsEmptyState({
  text,
  kind,
  loading,
  onOpenConfiguration,
  onOpenDataSources,
  onRetry,
}: Options): ScreeningResultsEmptyState {
  if (kind === 'loading') {
    return { title: text.running, description: text.runningTask };
  }
  if (kind === 'blocked') {
    return { title: text.noResults };
  }
  if (kind === 'no_hits') {
    return {
      title: text.noHitsTitle,
      description: text.noHitsDescription,
      action: (
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button type="button" variant="primary" disabled={loading} aria-label={`${text.adjustParameters} · ${text.noHitsTitle}`} onClick={onOpenConfiguration}>
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
            {text.adjustParameters}
          </Button>
          <Button type="button" variant="secondary" disabled={loading} aria-label={`${text.retry} · ${text.noHitsTitle}`} onClick={onRetry}>
            <Play className="h-4 w-4" aria-hidden="true" />
            {text.retry}
          </Button>
        </div>
      ),
    };
  }
  if (kind === 'source_unavailable') {
    return {
      title: text.sourcesUnavailableTitle,
      description: text.sourcesUnavailableDescription,
      action: (
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button type="button" variant="primary" disabled={loading} aria-label={`${text.retry} · ${text.sourcesUnavailableTitle}`} onClick={onRetry}>
            <Play className="h-4 w-4" aria-hidden="true" />
            {text.retry}
          </Button>
          <Button type="button" variant="secondary" aria-label={`${text.openDataSources} · ${text.sourcesUnavailableTitle}`} onClick={onOpenDataSources}>
            <Settings2 className="h-4 w-4" aria-hidden="true" />
            {text.openDataSources}
          </Button>
        </div>
      ),
    };
  }
  return {
    title: text.neverRunTitle,
    description: text.neverRunDescription,
    action: (
      <Button type="button" variant="primary" disabled={loading} aria-label={`${text.run} · ${text.neverRunTitle}`} onClick={onOpenConfiguration}>
        <Play className="h-4 w-4" aria-hidden="true" />
        {text.run}
      </Button>
    ),
  };
}
