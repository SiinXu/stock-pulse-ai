import type React from 'react';
import { useCallback, useMemo } from 'react';
import { Play, Search } from 'lucide-react';
import type { AlphaSiftCandidate } from '../../api/alphasift';
import { formatUiText, type UiLanguage } from '../../i18n/uiText';
import { getUiListSeparator } from '../../utils/uiLocale';
import { Button, DataTable, type DataTableColumn, Surface } from '../common';
import {
  formatAmount,
  formatNumber,
  formatPercent,
  formatScore,
  getCandidateDetailId,
  getCandidateReason,
  getFactorEntries,
  getSignal,
  hasLlmInsight,
} from './screeningCandidateModel';
import { summarizeAlphaSiftDiagnostic } from './screeningMessages';
import type { ScreeningText } from './screeningText';

export type ScreeningResultsSectionProps = {
  text: ScreeningText;
  language: UiLanguage;
  candidates: AlphaSiftCandidate[];
  expandedCode: string | null;
  llmDegraded: boolean;
  loading: boolean;
  onExpandedCodeChange: (code: string | null) => void;
  onOpenConfiguration: () => void;
};

export const ScreeningResultsSection: React.FC<ScreeningResultsSectionProps> = ({
  text,
  language,
  candidates,
  expandedCode,
  llmDegraded,
  loading,
  onExpandedCodeChange,
  onOpenConfiguration,
}) => {
  const candidateColumns = useMemo<DataTableColumn<AlphaSiftCandidate>[]>(() => [
    {
      id: 'rank',
      header: '#',
      width: 'compact',
      nowrap: true,
      cell: (item) => item.rank,
    },
    {
      id: 'code',
      header: text.code,
      rowHeader: true,
      nowrap: true,
      cell: (item) => <span className="font-mono font-semibold text-foreground">{item.code}</span>,
    },
    {
      id: 'name',
      header: text.name,
      cell: (item) => <span className="font-semibold text-foreground">{item.name || '-'}</span>,
    },
    {
      id: 'industry',
      header: text.industry,
      cell: (item) => item.industry || '-',
    },
    {
      id: 'price',
      header: text.price,
      nowrap: true,
      cell: (item) => formatNumber(item.price),
    },
    {
      id: 'change',
      header: text.change,
      nowrap: true,
      cell: (item) => `${formatNumber(item.changePct)}%`,
    },
    {
      id: 'score',
      header: text.score,
      nowrap: true,
      cell: (item) => <span className="font-bold text-primary">{formatScore(item.score)}</span>,
    },
    {
      id: 'llm',
      header: <span>LLM</span>,
      nowrap: true,
      cell: (item) => llmDegraded ? text.notReranked : formatScore(item.llmScore),
    },
    {
      id: 'risk',
      header: text.risk,
      nowrap: true,
      cell: (item) => (
        <span className="rounded-lg bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
          {item.riskLevel || text.unknown}
        </span>
      ),
    },
    {
      id: 'details',
      header: text.details,
      nowrap: true,
      cell: (item) => {
        const expanded = expandedCode === item.code;
        return (
          <Button
            type="button"
            variant="ghost"
            size="default"
            aria-expanded={expanded}
            aria-controls={getCandidateDetailId(item)}
            onClick={() => onExpandedCodeChange(expanded ? null : item.code)}
          >
            {expanded ? text.collapse : text.expand}
          </Button>
        );
      },
    },
  ], [expandedCode, llmDegraded, onExpandedCodeChange, text]);

  const renderCandidateDetail = useCallback((item: AlphaSiftCandidate) => {
    const factors = getFactorEntries(item);
    const llmInsightAvailable = hasLlmInsight(item);
    const llmFallbackText = llmDegraded && !llmInsightAvailable
      ? text.llmFallbackRow
      : text.noLlmJudgement;
    const dsaWarnings = item.dsaContext?.warnings || [];
    const dsaNews = item.dsaNews || [];
    return (
      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.summary}</p>
            <p className="mt-1 text-sm leading-6 text-foreground">{getCandidateReason(item, text)}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.signal}</p>
            <p className="mt-1 text-sm text-foreground">{getSignal(item, text)}</p>
          </div>
          {item.dsaAnalysisSummary ? (
            <div>
              <p className="text-xs font-semibold text-secondary-text">{text.dsaSummary}</p>
              <p className="mt-1 text-sm leading-6 text-foreground">{item.dsaAnalysisSummary}</p>
            </div>
          ) : null}
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.llmJudgement}</p>
            <p className="mt-1 text-sm leading-6 text-foreground">
              {item.llmThesis || llmFallbackText}
            </p>
            {llmInsightAvailable ? (
              <p className="mt-1 text-xs text-secondary-text">
                {formatUiText(text.sectorThemeConfidence, { sector: item.llmSector || '-', theme: item.llmTheme || '-', confidence: formatPercent(item.llmConfidence) })}
              </p>
            ) : (
              <p className="mt-1 text-xs text-secondary-text">{text.noLlmMetadata}</p>
            )}
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.riskTags}</p>
            <p className="mt-1 text-sm text-foreground">
              {[...(item.riskFlags || []), ...(item.llmRisks || [])].length
                ? [...(item.riskFlags || []), ...(item.llmRisks || [])].join('，')
                : text.none}
            </p>
          </div>
        </div>
        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.mainFactors}</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {factors.length > 0 ? (
                factors.map(([key, value]) => (
                  <Surface key={key} level="interactive" padding="sm">
                    <span className="block text-xs text-secondary-text">{key}</span>
                    <span className="text-sm font-semibold text-foreground">{formatNumber(value)}</span>
                  </Surface>
                ))
              ) : (
                <span className="text-sm text-secondary-text">{text.noFactors}</span>
              )}
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.turnover}</p>
            <p className="mt-1 text-sm text-foreground">{formatAmount(item.amount, language, text)}</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.watchItems}</p>
            <p className="mt-1 text-sm text-foreground">
              {item.llmWatchItems?.length ? item.llmWatchItems.join(getUiListSeparator(language)) : llmDegraded ? text.degradedNoValue : text.none}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.catalysts}</p>
            <p className="mt-1 text-sm text-foreground">
              {item.llmCatalysts?.length ? item.llmCatalysts.join(getUiListSeparator(language)) : llmDegraded ? text.degradedNoValue : text.none}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold text-secondary-text">{text.dsaNews}</p>
            {dsaNews.length > 0 ? (
              <ul className="mt-1 space-y-1 text-sm text-foreground">
                {dsaNews.slice(0, 3).map((newsItem, newsIndex) => (
                  <li key={`${item.code}-dsa-news-${newsIndex}`}>
                    {newsItem.title || newsItem.snippet || '-'}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-sm text-secondary-text">{text.none}</p>
            )}
          </div>
          {dsaWarnings.length > 0 ? (
            <div>
              <p className="text-xs font-semibold text-secondary-text">{text.dsaHints}</p>
              <p className="mt-1 text-sm text-secondary-text">
                {dsaWarnings.map((warning) => summarizeAlphaSiftDiagnostic(warning, text)).join('，')}
              </p>
            </div>
          ) : null}
        </div>
      </div>
    );
  }, [language, llmDegraded, text]);

  return (
    <Surface as="section" level="interactive" padding="md">
      <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-foreground">{text.results}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary-text">
            {text.resultsDescription}
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-border bg-subtle-soft px-3 py-2 text-xs text-secondary-text">
          <Search className="h-4 w-4 text-primary" />
          {formatUiText(text.candidateCount, { count: candidates.length })}
        </div>
      </div>

      <DataTable
        caption={text.results}
        scrollAreaLabel={text.results}
        columns={candidateColumns}
        rows={candidates}
        getRowKey={(item) => `${item.rank}-${item.code}`}
        emptyState={{
          title: text.noResults,
          description: text.noResultsDescription,
          action: (
            <Button
              type="button"
              variant="primary"
              size="default"
              disabled={loading}
              aria-label={`${text.run} · ${text.noResults}`}
              onClick={onOpenConfiguration}
            >
              <Play className="h-4 w-4" aria-hidden="true" />
              {text.run}
            </Button>
          ),
        }}
        minWidth="wide"
        isRowDetailVisible={(item) => expandedCode === item.code}
        renderRowDetail={renderCandidateDetail}
        getRowDetailId={getCandidateDetailId}
        getRowDetailAriaLabel={(item) => `${item.name || item.code} ${text.details}`}
      />
    </Surface>
  );
};
