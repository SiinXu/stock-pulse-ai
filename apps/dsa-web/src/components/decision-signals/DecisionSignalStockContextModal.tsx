// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { Search, X } from 'lucide-react';
import {
  Button,
  IconButton,
  Modal,
  SelectionChip,
} from '../common';
import { StockAutocomplete } from '../StockAutocomplete';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { Market } from '../../types/stockIndex';
import {
  getCandidateKey,
  type StockCandidate,
  type StockContext,
} from './decisionSignalsPageModel';

export type DecisionSignalStockContextModalProps = {
  isOpen: boolean;
  onClose: () => void;
  stockDraft: string;
  onStockDraftChange: (value: string) => void;
  onSubmit: (code: string) => void;
  onAutocompleteSubmit: (
    code: string,
    name?: string,
    source?: 'manual' | 'autocomplete',
    metadata?: { market?: Market; displayCode?: string },
  ) => void;
  onClear: () => void;
  activeStockContext: StockContext | null;
  activeStockLabel: string | null;
  stockCandidates: StockCandidate[];
  stockCandidateMode: 'history' | 'popular' | 'empty';
  historyCandidatesLoaded: boolean;
  onCandidateSelect: (candidate: StockCandidate) => void;
};

const DecisionSignalStockContextModal: React.FC<DecisionSignalStockContextModalProps> = ({
  isOpen,
  onClose,
  stockDraft,
  onStockDraftChange,
  onSubmit,
  onAutocompleteSubmit,
  onClear,
  activeStockContext,
  activeStockLabel,
  stockCandidates,
  stockCandidateMode,
  historyCandidatesLoaded,
  onCandidateSelect,
}) => {
  const { t } = useUiLanguage();

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t('decisionSignals.stockContextTitle')}
    >
      <p className="mb-3 text-sm text-muted-text">{t('decisionSignals.stockContextDescription')}</p>
      <form
        className="flex flex-col gap-3 md:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(stockDraft);
          onClose();
        }}
      >
        <div className="min-w-0 flex-1">
          <StockAutocomplete
            value={stockDraft}
            onChange={onStockDraftChange}
            onSubmit={onAutocompleteSubmit}
            placeholder={t('decisionSignals.stockContextPlaceholder')}
            ariaLabel={t('decisionSignals.stockContextInput')}
          />
        </div>
        <Button
          type="submit"
          variant="primary"
          size="comfortable"
          disabled={!stockDraft.trim()}
        >
          <Search className="h-4 w-4" />
          {t('decisionSignals.stockContextApply')}
        </Button>
        <IconButton
          variant="ghost"
          size="comfortable"
          aria-label={t('decisionSignals.stockContextClear')}
          onClick={onClear}
          disabled={!activeStockContext && !stockDraft}
        >
          <X aria-hidden="true" />
        </IconButton>
      </form>

      {activeStockLabel ? (
        <p className="mt-3 text-sm text-secondary-text">
          {t('decisionSignals.stockContextCurrent', { stock: activeStockLabel })}
        </p>
      ) : (
        <p className="mt-3 text-sm text-secondary-text">{t('decisionSignals.stockContextEmpty')}</p>
      )}

      {historyCandidatesLoaded && stockCandidates.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-medium uppercase text-muted-text">
            {stockCandidateMode === 'history'
              ? t('decisionSignals.stockContextRecent')
              : t('decisionSignals.stockContextPopular')}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {stockCandidates.map((candidate) => (
              <SelectionChip
                key={`${candidate.source}:${getCandidateKey(candidate)}`}
                label={<span className="font-mono">{candidate.displayCode ?? candidate.code}</span>}
                description={candidate.name || undefined}
                metadata={candidate.market ? `/ ${candidate.market}` : undefined}
                onClick={() => {
                  onCandidateSelect(candidate);
                  onClose();
                }}
              />
            ))}
          </div>
        </div>
      ) : historyCandidatesLoaded ? (
        <p className="mt-4 text-sm text-secondary-text">{t('decisionSignals.stockContextNoCandidates')}</p>
      ) : null}
    </Modal>
  );
};

export default DecisionSignalStockContextModal;
