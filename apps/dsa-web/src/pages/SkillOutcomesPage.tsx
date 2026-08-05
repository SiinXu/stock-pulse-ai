// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, RefreshCw, Settings2 } from 'lucide-react';
import {
  skillOutcomesApi,
  type SkillOutcomeItem,
  type SkillOutcomePerformanceBucket,
  type SkillOutcomePerformanceStats,
  type SkillOutcomeSampleItem,
} from '../api/skillOutcomes';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  ApiErrorAlert,
  AppPage,
  Badge,
  Button,
  EmptyState,
  IconButton,
  PageHeader,
  StatePanel,
  Surface,
} from '../components/common';
import { useRouteFocusTarget } from '../components/routing';
import {
  SkillOutcomePerformanceTable,
  SkillOutcomeRecentLists,
  SkillOutcomeRunPanel,
} from '../components/skill-outcomes';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { formatUiText } from '../i18n/uiText';
import { SKILL_OUTCOMES_TEXT } from '../locales/skillOutcomes';
import {
  APP_ROUTE_PATHS,
  buildSettingsHref,
} from '../routing/routes';

const RECENT_LIMIT = 20;

const agentBehaviorSettingsHref = buildSettingsHref({
  section: 'agent_behavior',
  view: 'execution',
});

const SkillOutcomesPage: React.FC = () => {
  const { language } = useUiLanguage();
  const text = SKILL_OUTCOMES_TEXT[language];
  const pageHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const requestIdRef = useRef(0);

  const [stats, setStats] = useState<SkillOutcomePerformanceStats | null>(null);
  const [outcomes, setOutcomes] = useState<SkillOutcomeItem[]>([]);
  const [samples, setSamples] = useState<SkillOutcomeSampleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useRouteFocusTarget({
    routeId: APP_ROUTE_PATHS.researchSkillOutcomes,
    headingRef: pageHeadingRef,
    ready: !loading,
  });

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  const load = useCallback(async (mode: 'initial' | 'refresh' = 'initial') => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (mode === 'initial') {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);
    try {
      const [statsResponse, outcomesResponse, samplesResponse] = await Promise.all([
        skillOutcomesApi.getStats(),
        skillOutcomesApi.listOutcomes({ limit: RECENT_LIMIT, offset: 0 }),
        skillOutcomesApi.listSamples({ limit: RECENT_LIMIT, offset: 0 }),
      ]);
      if (requestIdRef.current !== requestId) return;
      setStats(statsResponse);
      setOutcomes(outcomesResponse.items ?? []);
      setSamples(samplesResponse.items ?? []);
    } catch (cause) {
      if (requestIdRef.current !== requestId) return;
      setStats(null);
      setOutcomes([]);
      setSamples([]);
      setError(getParsedApiError(cause));
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void load('initial');
    return () => {
      requestIdRef.current += 1;
    };
  }, [load, reloadToken]);

  const buckets: SkillOutcomePerformanceBucket[] = useMemo(
    () => stats?.buckets ?? [],
    [stats],
  );

  const hasAnyData = buckets.length > 0 || outcomes.length > 0 || samples.length > 0;
  const isEmpty = !loading && !error && !hasAnyData;

  const handleRefresh = () => {
    setReloadToken((current) => current + 1);
  };

  return (
    <AppPage data-testid="skill-outcomes-page" className="space-y-6">
      <PageHeader
        ref={pageHeadingRef}
        title={text.title}
        description={text.description}
        actions={(
          <IconButton
            type="button"
            variant="ghost"
            size="compact"
            aria-label={text.refreshAria}
            disabled={loading || refreshing}
            onClick={() => void load('refresh')}
          >
            <RefreshCw
              className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`}
              aria-hidden="true"
            />
          </IconButton>
        )}
      />

      {loading ? (
        <StatePanel
          state="loading"
          title={text.loading}
          data-testid="skill-outcomes-loading"
        />
      ) : null}

      {!loading && error ? (
        <div className="space-y-3" data-testid="skill-outcomes-error">
          <StatePanel
            state="error"
            title={text.loadErrorTitle}
            description={<ApiErrorAlert error={error} />}
            action={(
              <Button type="button" variant="secondary" size="comfortable" onClick={handleRefresh}>
                {text.retry}
              </Button>
            )}
          />
        </div>
      ) : null}

      {!loading && !error ? (
        <>
          <Surface
            level="interactive"
            className="flex flex-col gap-2 px-4 py-3"
            data-testid="skill-outcomes-threshold-strip"
          >
            <div className="flex flex-wrap items-center gap-2">
              <BarChart3 className="h-4 w-4 text-primary" aria-hidden="true" />
              {stats?.engineVersion ? (
                <Badge variant="default" size="sm">
                  {formatUiText(text.engineVersion, { version: stats.engineVersion })}
                </Badge>
              ) : null}
              {stats?.minimumEvaluatedSampleSize !== undefined ? (
                <Badge variant="history" size="sm">
                  {formatUiText(text.minSamples, {
                    count: stats.minimumEvaluatedSampleSize,
                  })}
                </Badge>
              ) : null}
            </div>
            <p className="text-xs leading-5 text-muted-text">{text.thresholdNote}</p>
          </Surface>

          <SkillOutcomeRunPanel
            disabled={refreshing}
            onCompleted={() => {
              setReloadToken((current) => current + 1);
            }}
          />

          {isEmpty ? (
            <EmptyState
              data-testid="skill-outcomes-empty"
              title={text.emptyTitle}
              description={text.emptyDescription}
              action={(
                <Link
                  to={agentBehaviorSettingsHref}
                  data-testid="skill-outcomes-settings-link"
                  className="control-hit-target inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border bg-hover px-3 text-sm font-medium text-foreground shadow-soft-card transition-colors hover:bg-subtle-hover focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary/25"
                >
                  <Settings2 className="h-4 w-4" aria-hidden="true" />
                  {text.emptySettingsAction}
                </Link>
              )}
            />
          ) : (
            <div className="space-y-6">
              <Surface as="section" level="section" padding="md" className="space-y-3">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">{text.statsTitle}</h2>
                  <p className="mt-1 text-xs text-secondary-text">{text.statsDescription}</p>
                </div>
                {buckets.length === 0 ? (
                  <EmptyState compact title={text.emptyTitle} description={text.statsDescription} />
                ) : (
                  <SkillOutcomePerformanceTable buckets={buckets} />
                )}
              </Surface>

              <SkillOutcomeRecentLists outcomes={outcomes} samples={samples} />
            </div>
          )}
        </>
      ) : null}
    </AppPage>
  );
};

export default SkillOutcomesPage;
