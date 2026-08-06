import type React from 'react';
import { Play } from 'lucide-react';
import { RESEARCH_DISCOVER_LIMITS } from '../../routing/routes';
import { Button, InlineAlert, Input, Modal, Select } from '../common';
import type { ScreeningText } from './screeningText';

export type ScreeningConfigurationModalProps = {
  text: ScreeningText;
  cancelLabel: string;
  isOpen: boolean;
  onClose: () => void;
  formId: string;
  description: string;
  loading: boolean;
  isScreeningEnabled: boolean;
  configurationError: string;
  market: string;
  markets: Array<{ id: string; label: string }>;
  strategy: string;
  maxResultsDraft: string;
  maxResultsError: string;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onMarketChange: (nextMarket: string) => void;
  onStrategyChange: (nextStrategy: string) => void;
  onMaxResultsChange: (nextMaxResults: string) => void;
};

export const ScreeningConfigurationModal: React.FC<ScreeningConfigurationModalProps> = ({
  text,
  cancelLabel,
  isOpen,
  onClose,
  formId,
  description,
  loading,
  isScreeningEnabled,
  configurationError,
  market,
  markets,
  strategy,
  maxResultsDraft,
  maxResultsError,
  onSubmit,
  onMarketChange,
  onStrategyChange,
  onMaxResultsChange,
}) => (
      <Modal
        isOpen={isOpen}
        onClose={onClose}
        title={text.parameters}
        description={description}
        closeDisabled={loading}
        showBorder={false}
        showHeaderDivider={false}
        showFooterDivider={false}
        footer={(
          <>
            <Button
              type="button"
              variant="ghost"
              size="compact"
              disabled={loading}
              onClick={onClose}
            >
              {cancelLabel}
            </Button>
            <Button
              type="submit"
              form={formId}
              variant="primary"
              size="compact"
              disabled={!isScreeningEnabled || loading}
              isLoading={loading}
              loadingText={text.screening}
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" />
              {text.run}
            </Button>
          </>
        )}
      >
        {configurationError ? (
          <InlineAlert
            variant="danger"
            title={text.callFailed}
            message={configurationError}
            className="mb-3"
          />
        ) : null}
        <form id={formId} onSubmit={onSubmit} noValidate>
          <div className="grid gap-3 sm:grid-cols-2">
            <Select
              label={text.market}
              value={market}
              disabled={loading}
              onChange={onMarketChange}
              options={markets.map((item) => ({ value: item.id, label: item.label }))}
              className="w-full flex-row items-center gap-3 [&>label]:mb-0 [&>label]:shrink-0 [&>div]:min-w-0 [&>div]:flex-1"
            />

            <Input
              label={text.strategyParameter}
              value={strategy}
              disabled={loading}
              onChange={(event) => onStrategyChange(event.target.value)}
              fieldClassName="w-full flex-row flex-wrap items-center gap-x-3 gap-y-1 [&>label]:mb-0 [&>label]:shrink-0 [&>.control-input-target]:min-w-0 [&>.control-input-target]:flex-1 [&>p]:basis-full"
            />

            <Input
              id="screening-max-results"
              label={text.resultCount}
              type="number"
              min={1}
              max={RESEARCH_DISCOVER_LIMITS.maxCount}
              step={1}
              value={maxResultsDraft}
              error={maxResultsError}
              disabled={loading}
              onChange={(event) => onMaxResultsChange(event.target.value)}
              fieldClassName="w-full flex-row flex-wrap items-center gap-x-3 gap-y-1 [&>label]:mb-0 [&>label]:shrink-0 [&>.control-input-target]:min-w-0 [&>.control-input-target]:flex-1 [&>p]:basis-full"
            />
          </div>
        </form>
      </Modal>

);
