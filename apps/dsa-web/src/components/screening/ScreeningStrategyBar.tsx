import type React from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { Button, Select, Surface } from '../common';
import type { ScreeningText } from './screeningText';

export type ScreeningStrategyBarProps = {
  text: ScreeningText;
  strategy: string;
  strategyOptions: Array<{ value: string; label: string }>;
  selectedStrategyTag: string;
  strategyDescription: string;
  strategyLoadError: string;
  loading: boolean;
  loadingStrategies: boolean;
  onStrategyChange: (nextStrategy: string) => void;
  onOpenConfiguration: () => void;
};

export const ScreeningStrategyBar: React.FC<ScreeningStrategyBarProps> = ({
  text,
  strategy,
  strategyOptions,
  selectedStrategyTag,
  strategyDescription,
  strategyLoadError,
  loading,
  loadingStrategies,
  onStrategyChange,
  onOpenConfiguration,
}) => (
      <Surface as="section" level="interactive" padding="none" className="p-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">{text.selectStrategy}</h2>
            <p className="mt-1 text-xs text-secondary-text">
              {strategyDescription}
            </p>
          </div>
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:flex-nowrap">
            <Select
              value={strategy}
              onChange={onStrategyChange}
              options={strategyOptions}
              ariaLabel={text.selectStrategy}
              placeholder={loadingStrategies ? text.loadingStrategies : text.strategiesUnavailable}
              disabled={loading || loadingStrategies || strategyOptions.length === 0}
              className="w-full sm:w-72 [&>div]:w-full"
            />
            <span className="shrink-0 rounded-lg border border-primary/30 bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">
              {selectedStrategyTag}
            </span>
            <Button
              type="button"
              variant="secondary"
              size="compact"
              onClick={onOpenConfiguration}
            >
              <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
              {text.parameters}
            </Button>
          </div>
        </div>
        {strategyLoadError ? <p role="alert" className="mt-2 text-xs text-danger">{strategyLoadError}</p> : null}
      </Surface>

);
