// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GitCompareArrows, History, Loader2 } from 'lucide-react';
import {
  researchTimelineApi,
  type ResearchTimelineNode,
  type ResearchTimelineSources,
} from '../../api/researchTimeline';
import { getParsedApiError, type ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  Badge,
  Button,
  Card,
  EmptyState,
  InlineAlert,
  Loading,
} from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import {
  APP_ROUTE_PATHS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  buildAnalysisWorkbenchHref,
  buildSignalCenterHref,
} from '../../routing/routes';
import { CHAT_SESSION_QUERY_KEY } from '../chat/chatPageConstants';
import { formatDateTime } from '../../utils/format';

const PAGE_LIMIT = 20;

type ResearchTimelinePanelProps = {
  stockCode: string;
};

function kindLabelKey(kind: ResearchTimelineNode['kind']): UiTextKey {
  switch (kind) {
    case 'analysis_run':
      return 'stocks.workspace.timeline.kind.analysis';
    case 'chat':
      return 'stocks.workspace.timeline.kind.chat';
    case 'signal':
      return 'stocks.workspace.timeline.kind.signal';
    case 'hypothesis':
      return 'stocks.workspace.timeline.kind.hypothesis';
    default:
      return 'stocks.workspace.timeline.kind.analysis';
  }
}

function formatConfidence(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  const pct = value <= 1 ? value * 100 : value;
  return `${Math.round(pct)}%`;
}

function buildNodeHref(node: ResearchTimelineNode): string | null {
  const link = node.link;
  switch (link.type) {
    case 'analysis_history': {
      const recordId = link.recordId;
      if (typeof recordId !== 'number' || !Number.isSafeInteger(recordId) || recordId <= 0) {
        return null;
      }
      return buildAnalysisWorkbenchHref({
        stock: link.stockCode ?? undefined,
        recordId,
        segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
      });
    }
    case 'chat_session': {
      const sessionId = link.sessionId?.trim();
      if (!sessionId) return null;
      const params = new URLSearchParams();
      params.set(CHAT_SESSION_QUERY_KEY, sessionId);
      if (link.stockCode?.trim()) params.set('stock', link.stockCode.trim());
      return `${APP_ROUTE_PATHS.agent}?${params.toString()}`;
    }
    case 'decision_signal': {
      return buildSignalCenterHref({
        stock: link.stockCode ?? undefined,
      });
    }
    default:
      return null;
  }
}

function AnalysisDiffCard({
  left,
  right,
  t,
}: {
  left: ResearchTimelineNode;
  right: ResearchTimelineNode;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
}): React.ReactElement {
  const leftConf = formatConfidence(left.confidence);
  const rightConf = formatConfidence(right.confidence);
  return (
    <div
      className="rounded-lg border border-border bg-surface-secondary/40 p-3 text-sm"
      role="status"
      aria-label={t('stocks.workspace.timeline.diffTitle')}
    >
      <div className="mb-2 flex items-center gap-2 font-medium text-foreground">
        <GitCompareArrows className="h-4 w-4" aria-hidden="true" />
        {t('stocks.workspace.timeline.diffTitle')}
      </div>
      <dl className="grid gap-2 sm:grid-cols-2">
        <div>
          <dt className="text-xs text-secondary-text">{t('stocks.workspace.timeline.diffOlder')}</dt>
          <dd className="text-foreground">
            {left.direction || '—'}
            {leftConf ? ` · ${leftConf}` : ''}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-secondary-text">{t('stocks.workspace.timeline.diffNewer')}</dt>
          <dd className="text-foreground">
            {right.direction || '—'}
            {rightConf ? ` · ${rightConf}` : ''}
          </dd>
        </div>
      </dl>
    </div>
  );
}

const ResearchTimelinePanel: React.FC<ResearchTimelinePanelProps> = ({ stockCode }) => {
  const { language, t } = useUiLanguage();
  const navigate = useNavigate();
  const requestIdRef = useRef(0);
  const [items, setItems] = useState<ResearchTimelineNode[]>([]);
  const [sources, setSources] = useState<ResearchTimelineSources | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const loadPage = useCallback(async (cursor: string | null, append: boolean) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (append) setLoadingMore(true);
    else {
      setLoading(true);
      setError(null);
    }
    try {
      const response = await researchTimelineApi.list(stockCode, {
        cursor,
        limit: PAGE_LIMIT,
      });
      if (requestIdRef.current !== requestId) return;
      setSources(response.sources);
      setNextCursor(response.nextCursor ?? null);
      setHasMore(Boolean(response.hasMore));
      setItems((current) => (append ? [...current, ...response.items] : response.items));
      if (!append) setSelectedIds([]);
      setError(null);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setError(getParsedApiError(err));
      if (!append) {
        setItems([]);
        setSources(null);
        setNextCursor(null);
        setHasMore(false);
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [stockCode]);

  useEffect(() => {
    requestIdRef.current += 1;
    void loadPage(null, false);
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadPage]);

  const selectedAnalysis = useMemo(() => {
    const selected = selectedIds
      .map((id) => items.find((item) => item.id === id))
      .filter((item): item is ResearchTimelineNode => item?.kind === 'analysis_run');
    if (selected.length !== 2) return null;
    const ordered = [...selected].sort((a, b) => a.occurredAt.localeCompare(b.occurredAt));
    return { left: ordered[0], right: ordered[1] };
  }, [items, selectedIds]);

  const toggleSelect = useCallback((node: ResearchTimelineNode) => {
    if (node.kind !== 'analysis_run') return;
    setSelectedIds((current) => {
      if (current.includes(node.id)) {
        return current.filter((id) => id !== node.id);
      }
      const analysisOnly = current.filter((id) => items.find((item) => item.id === id)?.kind === 'analysis_run');
      const next = [...analysisOnly, node.id];
      return next.slice(-2);
    });
  }, [items]);

  const handleOpen = useCallback((node: ResearchTimelineNode) => {
    const href = buildNodeHref(node);
    if (href) navigate(href);
  }, [navigate]);

  const hypothesisNote = sources?.hypothesis === 'unavailable'
    ? t('stocks.workspace.timeline.hypothesisUnavailable')
    : null;

  const emptyDescription = useMemo(() => {
    if (!sources) return t('stocks.workspace.timeline.emptyDescription');
    const parts = [
      sources.analysisRun === 'empty' ? t('stocks.workspace.timeline.sourceEmpty.analysis') : null,
      sources.chat === 'empty' ? t('stocks.workspace.timeline.sourceEmpty.chat') : null,
      sources.signal === 'empty' ? t('stocks.workspace.timeline.sourceEmpty.signal') : null,
      sources.hypothesis === 'unavailable'
        ? t('stocks.workspace.timeline.sourceEmpty.hypothesisUnavailable')
        : sources.hypothesis === 'empty'
          ? t('stocks.workspace.timeline.sourceEmpty.hypothesis')
          : null,
    ].filter(Boolean);
    return parts.length
      ? parts.join(' ')
      : t('stocks.workspace.timeline.emptyDescription');
  }, [sources, t]);

  return (
    <Card
      title={t('stocks.workspace.timeline.title')}
      padding="md"
    >
      <div className="space-y-3">
        <p className="text-sm text-secondary-text">
          {t('stocks.workspace.timeline.description')}
        </p>
        {hypothesisNote ? (
          <InlineAlert variant="info" message={hypothesisNote} />
        ) : null}

        {error ? (
          <ApiErrorAlert
            error={error}
            actionLabel={t('common.retry')}
            onAction={() => void loadPage(null, false)}
          />
        ) : null}

        {loading && items.length === 0 ? (
          <Loading />
        ) : items.length === 0 && !error ? (
          <EmptyState
            compact
            title={t('stocks.workspace.timeline.emptyTitle')}
            description={emptyDescription}
            icon={<History className="h-6 w-6" />}
          />
        ) : (
          <>
            {selectedAnalysis ? (
              <AnalysisDiffCard
                left={selectedAnalysis.left}
                right={selectedAnalysis.right}
                t={t}
              />
            ) : items.some((item) => item.kind === 'analysis_run') ? (
              <p className="text-xs text-secondary-text">
                {t('stocks.workspace.timeline.diffHint')}
              </p>
            ) : null}

            <ol className="space-y-2" aria-label={t('stocks.workspace.timeline.listLabel')}>
              {items.map((node) => {
                const href = buildNodeHref(node);
                const selected = selectedIds.includes(node.id);
                const conf = formatConfidence(node.confidence);
                return (
                  <li
                    key={node.id}
                    className={`rounded-lg border p-3 ${selected ? 'border-primary bg-primary/5' : 'border-border bg-surface'}`}
                    data-kind={node.kind}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="history">{t(kindLabelKey(node.kind))}</Badge>
                          {node.status ? (
                            <Badge variant="default">{node.status}</Badge>
                          ) : null}
                          <time
                            className="text-xs text-secondary-text"
                            dateTime={node.occurredAt}
                          >
                            {formatDateTime(node.occurredAt, language)}
                          </time>
                        </div>
                        <div className="font-medium text-foreground">{node.title}</div>
                        {node.summary ? (
                          <p className="text-sm text-secondary-text line-clamp-2">{node.summary}</p>
                        ) : null}
                        {(node.direction || conf) ? (
                          <p className="text-xs text-secondary-text">
                            {[node.direction, conf].filter(Boolean).join(' · ')}
                          </p>
                        ) : null}
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {node.kind === 'analysis_run' ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="compact"
                            onClick={() => toggleSelect(node)}
                            aria-pressed={selected}
                          >
                            {selected
                              ? t('stocks.workspace.timeline.deselect')
                              : t('stocks.workspace.timeline.selectForDiff')}
                          </Button>
                        ) : null}
                        {href ? (
                          <Button
                            type="button"
                            variant="secondary"
                            size="compact"
                            onClick={() => handleOpen(node)}
                            aria-label={`${t('stocks.workspace.timeline.open')}: ${node.title}`}
                          >
                            {t('stocks.workspace.timeline.open')}
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>

            {hasMore ? (
              <div className="flex justify-center pt-1">
                <Button
                  type="button"
                  variant="secondary"
                  size="comfortable"
                  disabled={loadingMore || !nextCursor}
                  onClick={() => void loadPage(nextCursor, true)}
                >
                  {loadingMore ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                      {t('common.loading')}
                    </>
                  ) : (
                    t('stocks.workspace.timeline.loadMore')
                  )}
                </Button>
              </div>
            ) : items.length > 0 ? (
              <p className="text-center text-xs text-secondary-text">
                {t('stocks.workspace.timeline.end')}
              </p>
            ) : null}
          </>
        )}
      </div>
    </Card>
  );
};

export default ResearchTimelinePanel;
