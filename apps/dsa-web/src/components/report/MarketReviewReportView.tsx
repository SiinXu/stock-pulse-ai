import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { BarChart3, Clipboard, FileText, Gauge, Layers, ShieldAlert, TrendingUp, WalletCards, Workflow } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import { historyApi } from '../../api/history';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText, UI_TEXT } from '../../i18n/uiText';
import { MARKET_REVIEW_CONTENT_TEXT } from '../../locales/reportContent';
import { REPORT_CHROME_TEXT } from '../../locales/reportChrome';
import type {
  AnalysisReport,
  MarketReviewIndex,
  MarketReviewPayload,
  MarketReviewPayloadSection,
  ReportLanguage,
} from '../../types/analysis';
import { markdownToPlainText } from '../../utils/markdown';
import {
  getMarketReviewSectionKind,
  isGenericMarketReviewTitle,
  normalizeMarketReviewHeading,
} from '../../utils/marketReview';
import { getReportText, normalizeReportLanguage } from '../../utils/reportLanguage';
import { getUiLocale } from '../../utils/uiLocale';
import { ApiErrorAlert, Card, DataTable, type DataTableColumn, InlineAlert, useClipboard } from '../common';
import { Tooltip } from '../common/Tooltip';
import { MarketStructureCard } from './MarketStructureCard';
import { ReportMarkdownBody } from './ReportMarkdownBody';

interface MarketReviewReportViewProps {
  report?: AnalysisReport;
  recordId?: number;
  content?: string;
  payload?: MarketReviewPayload | null;
  reportLanguage?: ReportLanguage;
  className?: string;
  onOpenRunFlow?: (recordId: number) => void;
}

type CopyType = 'markdown' | 'text';
type LoadedMarkdown = {
  recordId: number;
  content: string;
};
type LoadError = {
  recordId: number;
  error: ParsedApiError;
};
type MarketReviewSection = {
  id: string;
  title: string;
  content: string;
  icon: typeof FileText;
};
type StructuredMarketData = {
  id: string;
  title?: string;
  breadth?: MarketReviewPayload['breadth'];
  indices: NonNullable<MarketReviewPayload['indices']>;
  sectors?: MarketReviewPayload['sectors'];
  concepts?: MarketReviewPayload['concepts'];
};

const isMarketReviewPayload = (value: unknown): value is MarketReviewPayload =>
  Boolean(value && typeof value === 'object');

const TOP_HEADING_PATTERN = /^\s*#\s+(.+?)\s*(?:\n+|$)/;
const SECTION_HEADING_PATTERN = /^(#{2,3})\s+(.+?)\s*$/gm;

const stripTopHeading = (markdown: string, title?: string): string => {
  const match = markdown.match(TOP_HEADING_PATTERN);
  if (!match) {
    return markdown.trim();
  }

  const heading = normalizeMarketReviewHeading(match[1]);
  const reportTitle = normalizeMarketReviewHeading(title || '');

  if (heading === reportTitle || isGenericMarketReviewTitle(heading)) {
    return markdown.slice(match[0].length).trim();
  }

  return markdown.trim();
};

const getSectionIcon = (title: string): typeof FileText => {
  const kind = getMarketReviewSectionKind(title);
  if (kind === 'index') {
    return BarChart3;
  }
  if (kind === 'sentiment') {
    return Gauge;
  }
  if (kind === 'rotation') {
    return TrendingUp;
  }
  if (kind === 'capital') {
    return WalletCards;
  }
  if (kind === 'risk') {
    return ShieldAlert;
  }
  return FileText;
};

const splitMarketReviewSections = (
  markdown: string,
  language: ReportLanguage,
): MarketReviewSection[] => {
  const text = MARKET_REVIEW_CONTENT_TEXT[language];
  const matches = Array.from(markdown.matchAll(SECTION_HEADING_PATTERN));
  if (matches.length === 0) {
    return [{
      id: 'full-review',
      title: text.fullReview,
      content: markdown,
      icon: FileText,
    }];
  }

  const intro = markdown.slice(0, matches[0].index).trim();
  const sections: MarketReviewSection[] = intro
    ? [{
        id: 'overview',
        title: text.overview,
        content: intro,
        icon: FileText,
      }]
    : [];

  matches.forEach((match, index) => {
    const start = (match.index ?? 0) + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index ?? markdown.length : markdown.length;
    const title = match[2].trim();
    const content = markdown.slice(start, end).trim();
    if (!content) {
      return;
    }
    sections.push({
      id: `${index}-${normalizeMarketReviewHeading(title).replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-').replace(/^-|-$/g, '') || 'section'}`,
      title,
      content,
      icon: getSectionIcon(title),
    });
  });

  return sections;
};

const getPayloadSections = (
  payload: MarketReviewPayload | null | undefined,
  language: ReportLanguage,
): MarketReviewSection[] => {
  if (!payload) {
    return [];
  }

  if (payload.markets) {
    return Object.entries(payload.markets).flatMap(([region, marketPayload]) => {
      const marketTitle = marketPayload.title || region.toUpperCase();
      return getPayloadSections(marketPayload, language).map((section) => ({
        ...section,
        id: `${region}-${section.id}`,
        title: `${marketTitle} / ${section.title}`,
      }));
    });
  }

  const payloadTitle = normalizeMarketReviewHeading(payload.title || '');
  return (payload.sections || [])
    .filter((section: MarketReviewPayloadSection) => section.markdown?.trim())
    .filter((section: MarketReviewPayloadSection) => normalizeMarketReviewHeading(section.title || '') !== payloadTitle)
    .map((section, index) => ({
      id: `${section.key || index}-${normalizeMarketReviewHeading(section.title).replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-') || 'section'}`,
      title: section.title || MARKET_REVIEW_CONTENT_TEXT[language].defaultSectionTitle,
      content: section.markdown,
      icon: getSectionIcon(section.title || ''),
    }));
};

const hasRankingRows = (rankings?: MarketReviewPayload['sectors']): boolean =>
  Boolean(rankings?.top?.length || rankings?.bottom?.length);

const hasStructuredMarketData = (payload?: MarketReviewPayload | null): boolean =>
  Boolean(payload?.breadth || payload?.indices?.length || hasRankingRows(payload?.sectors) || hasRankingRows(payload?.concepts));

const getStructuredMarketData = (payload?: MarketReviewPayload | null): StructuredMarketData[] => {
  if (!payload) {
    return [];
  }

  if (payload.markets) {
    return Object.entries(payload.markets)
      .filter(([, marketPayload]) => hasStructuredMarketData(marketPayload))
      .map(([region, marketPayload]) => ({
        id: region,
        title: marketPayload.title || region.toUpperCase(),
        breadth: marketPayload.breadth,
        indices: marketPayload.indices || [],
        sectors: marketPayload.sectors,
        concepts: marketPayload.concepts,
      }));
  }

  if (!hasStructuredMarketData(payload)) {
    return [];
  }

  return [{
    id: payload.region || 'market',
    title: payload.title,
    breadth: payload.breadth,
    indices: payload.indices || [],
    sectors: payload.sectors,
    concepts: payload.concepts,
  }];
};

const coerceFiniteNumber = (value: unknown): number | null => {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value === 'string' && value.trim()) {
    const normalizedValue = value.trim().replace(/,/g, '');
    const numericText = normalizedValue.endsWith('%')
      ? normalizedValue.slice(0, -1).trim()
      : normalizedValue;
    const parsed = Number(numericText);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
};

const formatMarketNumber = (value: unknown, options?: { zeroAsMissing?: boolean }): string => {
  const numericValue = coerceFiniteNumber(value);
  if (numericValue === null || (options?.zeroAsMissing && numericValue === 0)) {
    return '-';
  }
  return numericValue.toFixed(2);
};

const formatMarketCount = (value: unknown): string => {
  const numericValue = coerceFiniteNumber(value);
  return numericValue === null ? '-' : numericValue.toFixed(0);
};

const formatMarketAmount = (value: unknown, unit?: string): string => {
  const formattedValue = formatMarketNumber(value);
  if (formattedValue === '-') {
    return '-';
  }
  return unit ? `${formattedValue} ${unit}` : formattedValue;
};

const formatMarketPercent = (value: unknown): string => {
  const formattedValue = formatMarketNumber(value);
  return formattedValue === '-' ? '-' : `${formattedValue}%`;
};

const formatMarketHighLow = (high: unknown, low: unknown): string => {
  const highText = formatMarketNumber(high, { zeroAsMissing: true });
  const lowText = formatMarketNumber(low, { zeroAsMissing: true });
  return highText === '-' && lowText === '-' ? '-' : `${highText} / ${lowText}`;
};

const formatRankingChange = (value: unknown): string => {
  const numeric = typeof value === 'number' ? value : Number(String(value ?? '').replace(/%$/, ''));
  if (!Number.isFinite(numeric)) {
    return '-';
  }
  const sign = numeric > 0 ? '+' : '';
  return `${sign}${numeric.toFixed(2)}%`;
};

export const MarketReviewReportView: React.FC<MarketReviewReportViewProps> = ({
  report,
  recordId,
  content: providedContent,
  payload: providedPayload,
  reportLanguage = 'zh',
  className = '',
  onOpenRunFlow,
}) => {
  const { language: uiLanguage } = useUiLanguage();
  const normalizedReportLanguage = normalizeReportLanguage(reportLanguage);
  const reportText = getReportText(normalizedReportLanguage);
  const chromeText = REPORT_CHROME_TEXT[uiLanguage];
  const runFlowText = UI_TEXT[uiLanguage];
  const marketReviewText = MARKET_REVIEW_CONTENT_TEXT[normalizedReportLanguage];
  const [loadedMarkdown, setLoadedMarkdown] = useState<LoadedMarkdown | null>(null);
  const [loadError, setLoadError] = useState<LoadError | null>(null);
  const [copiedType, setCopiedType] = useState<CopyType | null>(null);
  const { copyText, copyError } = useClipboard();
  const summary = report?.summary;
  const meta = report?.meta;
  const contextPayload = report?.details?.contextSnapshot?.marketReviewPayload;
  const marketReviewPayload = providedPayload ?? (isMarketReviewPayload(contextPayload) ? contextPayload : null);
  const loadedContent = loadedMarkdown && loadedMarkdown.recordId === recordId ? loadedMarkdown.content : '';
  const content = providedContent ?? marketReviewPayload?.markdownReport ?? loadedContent;
  const error = loadError && loadError.recordId === recordId ? loadError.error : null;
  const hasStructuredContent = Boolean(marketReviewPayload?.sections?.length || marketReviewPayload?.markets);
  const isLoading = Boolean(recordId && !providedContent && !hasStructuredContent && loadedMarkdown?.recordId !== recordId && !error);
  const displayTitle = marketReviewPayload?.rootTitle
    || marketReviewPayload?.title
    || meta?.stockName
    || marketReviewText.defaultTitle;
  const structuredContent = useMemo(
    () => stripTopHeading(content, displayTitle),
    [content, displayTitle],
  );
  const sections = useMemo(
    () => {
      const payloadSections = getPayloadSections(marketReviewPayload, normalizedReportLanguage);
      return payloadSections.length > 0
        ? payloadSections
        : splitMarketReviewSections(structuredContent, normalizedReportLanguage);
    },
    [marketReviewPayload, normalizedReportLanguage, structuredContent],
  );
  const structuredMarketData = useMemo(
    () => getStructuredMarketData(marketReviewPayload),
    [marketReviewPayload],
  );
  const showStructuredMarketTitles = Boolean(marketReviewPayload?.markets);
  const canOpenRunFlow = recordId !== undefined && onOpenRunFlow;

  useEffect(() => {
    if (!recordId || providedContent || hasStructuredContent) {
      return undefined;
    }

    let isMounted = true;

    historyApi.getMarkdown(recordId)
      .then((markdownContent) => {
        if (isMounted) {
          setLoadedMarkdown({ recordId, content: markdownContent });
          setLoadError(null);
        }
      })
      .catch((err: unknown) => {
        if (isMounted) {
          setLoadError({
            recordId,
            error: getParsedApiError(err, uiLanguage),
          });
        }
      });

    return () => {
      isMounted = false;
    };
  }, [hasStructuredContent, providedContent, recordId, uiLanguage]);

  const handleCopy = useCallback(async (type: CopyType) => {
    if (!content) {
      return;
    }
    const value = type === 'markdown' ? content : markdownToPlainText(content);
    if (await copyText(value)) {
      setCopiedType(type);
      window.setTimeout(() => setCopiedType(null), 2000);
    }
  }, [content, copyText]);

  const insightCards = useMemo(() => [
    {
      icon: FileText,
      label: marketReviewText.reviewSummary,
      value: summary?.analysisSummary || marketReviewText.noReviewSummary,
    },
    {
      icon: Gauge,
      label: reportText.marketSentiment,
      value: summary?.sentimentScore !== undefined
        ? `${summary.sentimentScore} / 100`
        : marketReviewText.noSentimentScore,
    },
    {
      icon: Layers,
      label: marketReviewText.rotationAndFunds,
      value: summary?.operationAdvice || marketReviewText.noRotationView,
    },
    {
      icon: ShieldAlert,
      label: marketReviewText.riskAndWatch,
      value: summary?.trendPrediction || marketReviewText.noRiskWatch,
    },
  ], [marketReviewText, reportText.marketSentiment, summary]);
  const indexColumns: readonly DataTableColumn<MarketReviewIndex>[] = [
    {
      id: 'index',
      header: marketReviewText.index,
      rowHeader: true,
      cell: (index) => <span className="font-medium text-foreground">{index.name}</span>,
    },
    {
      id: 'last',
      header: marketReviewText.last,
      nowrap: true,
      cell: (index) => formatMarketNumber(index.current),
    },
    {
      id: 'change',
      header: marketReviewText.change,
      nowrap: true,
      cell: (index) => formatMarketPercent(index.changePct),
    },
    {
      id: 'high-low',
      header: marketReviewText.highLow,
      nowrap: true,
      cell: (index) => formatMarketHighLow(index.high, index.low),
    },
  ];

  return (
    <div className={`animate-fade-in space-y-4 pb-8 ${className}`}>
      <Card variant="gradient" padding="md" className="home-report-hero text-left">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="mb-2 inline-flex items-center gap-2 text-xs font-semibold text-secondary-text">
              <BarChart3 className="h-4 w-4" aria-hidden="true" />
              <span>{marketReviewText.eyebrow}</span>
            </div>
            <h2 className="text-heading-2 font-bold leading-tight text-foreground">
              {displayTitle}
            </h2>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-text">
              {meta?.stockCode ? (
                <span className="home-accent-chip px-2 py-0.5 font-mono">{meta.stockCode}</span>
              ) : null}
              {meta?.createdAt ? <span>{new Date(meta.createdAt).toLocaleString(getUiLocale(uiLanguage))}</span> : null}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {canOpenRunFlow ? (
              <Tooltip content={runFlowText['runFlow.open']}>
                <span className="inline-flex">
                  <button
                    type="button"
                    onClick={() => onOpenRunFlow(recordId)}
                    className="home-surface-button flex h-11 w-11 items-center justify-center rounded-lg text-secondary-text hover:text-foreground"
                    aria-label={formatUiText(runFlowText['runFlow.openHistoryAria'], { recordId })}
                  >
                    <Workflow className="h-5 w-5" aria-hidden="true" />
                  </button>
                </span>
              </Tooltip>
            ) : null}
            <Tooltip content={chromeText.copyMarkdownSource}>
              <span className="inline-flex">
                <button
                  type="button"
                  onClick={() => void handleCopy('markdown')}
                  disabled={isLoading || !content || copiedType !== null}
                  className="home-surface-button flex h-11 w-11 items-center justify-center rounded-lg text-secondary-text hover:text-foreground disabled:opacity-50"
                  aria-label={chromeText.copyMarkdownSource}
                >
                  {copiedType === 'markdown' ? (
                    <svg className="h-5 w-5 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <Clipboard className="h-5 w-5" aria-hidden="true" />
                  )}
                </button>
              </span>
            </Tooltip>
            <Tooltip content={chromeText.copyPlainText}>
              <span className="inline-flex">
                <button
                  type="button"
                  onClick={() => void handleCopy('text')}
                  disabled={isLoading || !content || copiedType !== null}
                  className="home-surface-button flex h-11 w-11 items-center justify-center rounded-lg text-secondary-text hover:text-foreground disabled:opacity-50"
                  aria-label={chromeText.copyPlainText}
                >
                  {copiedType === 'text' ? (
                    <svg className="h-5 w-5 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <FileText className="h-5 w-5" aria-hidden="true" />
                  )}
                </button>
              </span>
            </Tooltip>
          </div>
        </div>
      </Card>

      {copyError ? <InlineAlert variant="danger" message={copyError} /> : null}

      {summary ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {insightCards.map(({ icon: Icon, label, value }) => (
            <Card key={label} variant="bordered" padding="sm" className="text-left">
              <div className="flex items-start gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <p className="label-uppercase">{label}</p>
                  <p className="mt-2 line-clamp-4 text-sm leading-6 text-foreground">{value}</p>
                </div>
              </div>
            </Card>
          ))}
        </div>
      ) : null}

      {structuredMarketData.length > 0 ? (
        <Card variant="bordered" padding="md" className="text-left">
          <div className="mb-3 flex items-center gap-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <BarChart3 className="h-4 w-4" aria-hidden="true" />
            </span>
            <h3 className="text-base font-semibold text-foreground">{marketReviewText.structuredMarketData}</h3>
          </div>
          <div className="space-y-5">
            {structuredMarketData.map((marketData) => (
              <div key={marketData.id} className="space-y-3">
                {showStructuredMarketTitles ? (
                  <h4 className="text-sm font-semibold text-foreground">{marketData.title}</h4>
                ) : null}
                {marketData.breadth ? (
                  <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
                    <div className="rounded-lg border border-subtle p-3">
                      <p className="label-uppercase">{marketReviewText.advancers}</p>
                      <p className="mt-1 font-semibold text-foreground">
                        {formatMarketCount(marketData.breadth.upCount)}
                      </p>
                    </div>
                    <div className="rounded-lg border border-subtle p-3">
                      <p className="label-uppercase">{marketReviewText.decliners}</p>
                      <p className="mt-1 font-semibold text-foreground">
                        {formatMarketCount(marketData.breadth.downCount)}
                      </p>
                    </div>
                    <div className="rounded-lg border border-subtle p-3">
                      <p className="label-uppercase">{marketReviewText.limitUpDown}</p>
                      <p className="mt-1 font-semibold text-foreground">
                        {formatMarketCount(marketData.breadth.limitUpCount)} /{' '}
                        {formatMarketCount(marketData.breadth.limitDownCount)}
                      </p>
                    </div>
                    <div className="rounded-lg border border-subtle p-3">
                      <p className="label-uppercase">{marketReviewText.turnover}</p>
                      <p className="mt-1 font-semibold text-foreground">
                        {formatMarketAmount(marketData.breadth.totalAmount, marketData.breadth.turnoverUnit)}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-secondary-text">{marketReviewText.noBreadthData}</p>
                )}
                {marketData.indices.length > 0 ? (
                  <DataTable
                    caption={`${marketData.title || displayTitle}: ${marketReviewText.index}`}
                    columns={indexColumns}
                    rows={marketData.indices}
                    getRowKey={(index) => index.code || index.name}
                    emptyState={{ title: marketReviewText.noBreadthData }}
                    density="compact"
                    frame="embedded"
                    minWidth="container"
                    separatorTone="subtle"
                  />
                ) : null}
                {(() => {
                  const boardTypes = [{
                    key: 'sectors' as const,
                    title: marketReviewText.industryBoards,
                    rankings: marketData.sectors,
                  }, {
                    key: 'concepts' as const,
                    title: marketReviewText.conceptBoards,
                    rankings: marketData.concepts,
                  }].filter(({ rankings }) => hasRankingRows(rankings));
                  if (boardTypes.length === 0) {
                    return null;
                  }
                  const renderPanels = (
                    key: string,
                    title: string,
                    rankings: MarketReviewPayload['sectors'],
                  ) => (['top', 'bottom'] as const).map((side) => {
                    const rows = rankings?.[side] || [];
                    if (rows.length === 0) {
                      return null;
                    }
                    return (
                      <div key={`${key}-${side}`} className="rounded-lg border border-subtle p-3">
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <p className="label-uppercase">{title}</p>
                          <span className="text-xs text-secondary-text">
                            {side === 'top' ? marketReviewText.leading : marketReviewText.lagging}
                          </span>
                        </div>
                        <div className="space-y-1.5">
                          {rows.slice(0, 5).map((item, index) => (
                            <div key={`${item.name}-${index}`} className="flex items-center justify-between gap-3 text-sm">
                              <span className="min-w-0 truncate text-foreground">{item.name}</span>
                              <span className="shrink-0 font-mono text-secondary-text">
                                {formatRankingChange(item.changePct)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  });
                  // When both types of sectors exist, align them by industry | concept horizontally to save vertical space; when only one type exists, retain lead | lag layout horizontally.
                  if (boardTypes.length >= 2) {
                    return (
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        {boardTypes.map(({ key, title, rankings }) => (
                          <div key={key} className="space-y-3">
                            {renderPanels(key, title, rankings)}
                          </div>
                        ))}
                      </div>
                    );
                  }
                  const { key, title, rankings } = boardTypes[0];
                  return (
                    <div key={key} className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      {renderPanels(key, title, rankings)}
                    </div>
                  );
                })()}
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {/* Render market structure context only when the persisted report includes it; legacy reports omit the section. */}
      {report?.details?.marketStructure ? (
        <MarketStructureCard
          context={report.details.marketStructure}
          language={normalizedReportLanguage}
        />
      ) : null}

      {isLoading ? (
        <Card variant="bordered" padding="md" className="text-left">
          <div className="flex h-64 flex-col items-center justify-center">
            <div className="home-spinner h-10 w-10 animate-spin border-[3px]" />
            <p className="mt-4 text-sm text-secondary-text">{chromeText.loadingReport}</p>
          </div>
        </Card>
      ) : error ? (
        <Card variant="bordered" padding="md" className="text-left">
          <div className="flex h-64 flex-col items-center justify-center">
            <ApiErrorAlert error={error} className="w-full max-w-lg" />
          </div>
        </Card>
      ) : (
        <div data-testid="market-review-report" className="space-y-4">
          {sections.map(({ id, title, content: sectionContent, icon: Icon }) => (
            <Card key={id} variant="bordered" padding="md" className="text-left">
              <div className="mb-3 flex items-center gap-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <h3 className="text-base font-semibold text-foreground">{title}</h3>
              </div>
              <ReportMarkdownBody
                content={sectionContent}
                className="market-review-markdown"
              />
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
