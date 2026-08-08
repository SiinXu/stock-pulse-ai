import type React from 'react';
import {
  Bookmark,
  ChevronDown,
  Clock3,
  Flame,
  Play,
  RefreshCw,
} from 'lucide-react';
import type { AlphaSiftHotspot, AlphaSiftHotspotDetail } from '../../api/alphasift';
import { formatUiText, type UiLanguage } from '../../i18n/uiText';
import { getUiListSeparator } from '../../utils/uiLocale';
import { Button, InlineAlert, Surface } from '../common';
import { MiniSparkline } from './MiniSparkline';
import {
  formatHotspotMetric,
  formatHotspotUpdatedAt,
  formatStockChangeText,
  getHotspotIcon,
  getHotspotLeadersText,
  getHotspotRouteItems,
  getHotspotSampleText,
  getHotspotStrength,
  getRouteTimeLabel,
} from './hotspotModel';
import { formatNumber, formatPercent } from './screeningCandidateModel';
import { summarizeAlphaSiftDiagnostic } from './screeningMessages';
import type { ScreeningText } from './screeningText';

export type ScreeningHotspotsSectionProps = {
  text: ScreeningText;
  language: UiLanguage;
  isScreeningEnabled: boolean;
  hotspots: AlphaSiftHotspot[];
  hotspotsUpdatedAt: string | null;
  hotspotsExpanded: boolean;
  selectedHotspotTopic: string | null;
  hotspotDetail: AlphaSiftHotspotDetail | null;
  loadingHotspots: boolean;
  loadingHotspotDetail: boolean;
  hotspotError: string;
  hotspotDetailError: string;
  onToggleExpanded: () => void;
  onRefresh: () => void;
  onSelectHotspot: (topic: string) => void;
  onAnalyzeStock: (stock: AlphaSiftHotspotDetail['stocks'][number]) => void;
};

export const ScreeningHotspotsSection: React.FC<ScreeningHotspotsSectionProps> = ({
  text,
  language,
  isScreeningEnabled,
  hotspots,
  hotspotsUpdatedAt,
  hotspotsExpanded,
  selectedHotspotTopic,
  hotspotDetail,
  loadingHotspots,
  loadingHotspotDetail,
  hotspotError,
  hotspotDetailError,
  onToggleExpanded,
  onRefresh,
  onSelectHotspot,
  onAnalyzeStock,
}) => (
      <Surface as="section" level="interactive" padding="md">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-warning/10 text-warning shadow-soft-card">
              <Flame className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-lg font-bold tracking-normal text-foreground">{text.hotspots}</h2>
              <p className="mt-1 text-xs leading-5 text-secondary-text">
                {text.hotspotsDescription}
              </p>
            </div>
          </div>
          <div className="flex flex-col items-start gap-2 lg:items-end">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="default"
                variant="secondary"
                disabled={!isScreeningEnabled}
                onClick={onToggleExpanded}
              >
                <Bookmark className="h-4 w-4" />
                {hotspotsExpanded ? text.collapseHotspots : `${text.expandHotspots}${hotspots.length ? ` (${hotspots.length})` : ''}`}
                <ChevronDown className={`h-4 w-4 transition-transform ${hotspotsExpanded ? 'rotate-180' : ''}`} />
              </Button>
              {hotspotsExpanded ? (
              <Button
                size="default"
                variant="secondary"
                isLoading={loadingHotspots}
                loadingText={text.refreshing}
                disabled={!isScreeningEnabled || loadingHotspots}
                onClick={onRefresh}
              >
                <RefreshCw className="h-4 w-4" />
                {text.refreshHotspots}
              </Button>
              ) : null}
            </div>
            <p className="text-xs text-secondary-text">{formatUiText(text.updatedAt, { time: formatHotspotUpdatedAt(hotspotsUpdatedAt, language, text) })}</p>
          </div>
        </div>

        {hotspotError ? (
          <InlineAlert variant="warning" className="mb-3" message={hotspotError} />
        ) : null}

        {!hotspotsExpanded ? (
          <Surface level="interactive" padding="sm" className="flex flex-col gap-2 text-sm text-secondary-text sm:flex-row sm:items-center sm:justify-between">
            <span>
              {hotspots.length > 0
                ? formatUiText(text.cachedHotspots, { count: hotspots.length })
                : text.hotspotsCollapsed}
            </span>
            <span className="text-xs">{text.liveDetailHint}</span>
          </Surface>
        ) : hotspots.length === 0 ? (
          <Surface level="interactive" padding="sm" className="text-sm text-secondary-text">
            {text.refreshDescription}
          </Surface>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {hotspots.map((item, index) => {
              const selected = selectedHotspotTopic === item.topic;
              const strength = getHotspotStrength(item, index, text);
              const iconMeta = getHotspotIcon(item.name || item.topic);
              const Icon = iconMeta.icon;
              return (
              <button
                key={`${item.topic}-${item.rank ?? ''}`}
                className={`group relative min-h-28 overflow-hidden rounded-lg border px-3 py-3 text-left transition-all ${
                  selected
                    ? 'border-warning/50 bg-gradient-to-br from-warning/10 via-card to-card shadow-soft-card ring-1 ring-warning/20'
                    : 'border-border/80 bg-card hover:-translate-y-0.5 hover:border-warning/40 hover:shadow-soft-card'
                }`}
                type="button"
                onClick={() => onSelectHotspot(item.topic)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span
                      className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold ${
                        index < 3 ? 'bg-warning/15 text-warning shadow-soft-card' : 'bg-subtle-soft text-secondary-text'
                      }`}
                    >
                      {index + 1}
                    </span>
                    <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${iconMeta.className}`}>
                      <Icon className="h-5 w-5" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold text-foreground">{item.name || item.topic}</p>
                      <span className={`mt-1 inline-flex rounded-md px-1.5 py-0.5 text-xs font-semibold ${strength.className}`}>
                        {strength.label}
                      </span>
                    </div>
                  </div>
                  <span className="shrink-0 text-2xl font-black leading-none text-orange-500">
                    {formatNumber(item.heatScore, 0)}
                  </span>
                </div>
                <div className="relative z-10 mt-4 grid min-w-0 flex-1 gap-1 pr-24 text-xs text-secondary-text">
                  <span>{text.change} <strong className="font-semibold text-foreground">{formatHotspotMetric(item.changePct, text)}%</strong></span>
                  <span>{text.trend} <strong className="font-semibold text-foreground">{formatHotspotMetric(item.trendScore, text)}</strong> · {text.persistence} <strong className="font-semibold text-foreground">{formatHotspotMetric(item.persistenceScore, text)}</strong></span>
                  <span>{getHotspotSampleText(item, text)} · {text.leader} {getHotspotLeadersText(item, language, text)}</span>
                </div>
                <div className="absolute bottom-3 right-3 opacity-95 transition-transform group-hover:scale-105">
                  <MiniSparkline score={item.heatScore} selected={selected} />
                </div>
              </button>
              );
            })}
          </div>
        )}

        {hotspotsExpanded && selectedHotspotTopic ? (
          <Surface level="interactive" padding="sm" className="mt-4">
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  {hotspotDetail?.name || selectedHotspotTopic}
                </h3>
                <p className="mt-1 text-xs leading-5 text-secondary-text">
                  {loadingHotspotDetail ? text.loadingHotspotDetail : hotspotDetail?.summary || text.selectHotspot}
                </p>
                {hotspotDetail?.canonicalTopic && hotspotDetail.canonicalTopic !== selectedHotspotTopic ? (
                  <p className="mt-1 text-xs text-secondary-text">{formatUiText(text.canonicalTopic, { topic: hotspotDetail.canonicalTopic })}</p>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {hotspotDetail?.qualityStatus ? (
                  <span className="w-fit rounded-full bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">
                    {formatUiText(text.quality, { status: hotspotDetail.qualityStatus })}
                  </span>
                ) : null}
                {hotspotDetail?.fallbackUsed || hotspotDetail?.stale ? (
                  <span className="w-fit rounded-full bg-warning/10 px-3 py-1 text-xs font-semibold text-warning">
                    {hotspotDetail.staleAgeHours != null ? formatUiText(text.cacheFallbackHours, { hours: formatNumber(hotspotDetail.staleAgeHours, 1) }) : text.cacheFallback}
                  </span>
                ) : null}
                {hotspotDetail?.stockCount != null ? (
                  <span className="w-fit rounded-full bg-orange-500/10 px-3 py-1 text-xs font-semibold text-orange-500">
                    {formatUiText(text.conceptStocksCount, { count: hotspotDetail.stockCount })}
                  </span>
                ) : null}
              </div>
            </div>

            {hotspotDetailError ? (
              <InlineAlert variant="warning" className="mb-3" message={hotspotDetailError} />
            ) : null}

            {hotspotDetail && ((hotspotDetail.missingFields || []).length > 0 || (hotspotDetail.sourceErrors || []).length > 0) ? (
              <details className="mb-3 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
                <summary className="min-h-11 cursor-pointer font-semibold">
                  <span className="inline-flex min-h-11 items-center">{text.degradedDetail}</span>
                </summary>
                <div className="mt-2 space-y-1 leading-5">
                  {(hotspotDetail.missingFields || []).length > 0 ? (
                    <p>{formatUiText(text.missingFields, { fields: (hotspotDetail.missingFields || []).join(getUiListSeparator(language)) })}</p>
                  ) : null}
                  {(hotspotDetail.sourceErrors || []).slice(0, 4).map((message, index) => (
                    <p key={`${message}-${index}`}>{summarizeAlphaSiftDiagnostic(message, text)}</p>
                  ))}
                </div>
              </details>
            ) : null}

            {hotspotDetail ? (
              <div className="grid gap-4 lg:grid-cols-[1fr_1.3fr]">
                <div>
                  <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-secondary-text">
                    <Clock3 className="h-3.5 w-3.5 text-orange-500" />
                    {text.routeTimeline}
                  </p>
                  <div className="relative space-y-0 pl-4 before:absolute before:bottom-3 before:left-[5px] before:top-2 before:w-px before:bg-border">
                    {getHotspotRouteItems(hotspotDetail).map((item, index) => (
                      <div key={`${item.title}-${index}`} className="relative pb-4 last:pb-0">
                        <span className="absolute -left-4 top-1 h-2.5 w-2.5 rounded-full border border-orange-400 bg-card" />
                        <Surface level="interactive" padding="sm">
                          <p className="text-xs font-semibold text-orange-500">{getRouteTimeLabel(item, language, text)}</p>
                          <p className="mt-1 text-xs font-semibold text-foreground">{item.title}</p>
                          <p className="mt-1 text-xs leading-5 text-secondary-text">{item.description}</p>
                          {item.source ? <p className="mt-2 text-xs text-secondary-text">{formatUiText(text.source, { source: item.source })}</p> : null}
                        </Surface>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-xs font-semibold text-secondary-text">{text.conceptStocks}</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {(hotspotDetail.stocks || []).slice(0, 10).map((stock) => (
                      <Surface key={`${stock.code || stock.name}`} level="interactive" padding="sm">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-xs font-semibold text-foreground">{stock.name || stock.code || '-'}</p>
                            <p className="mt-1 text-xs text-secondary-text">{stock.code || '-'}</p>
                          </div>
                          <div className="flex shrink-0 items-center gap-1">
                            <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">
                              {stock.role || text.conceptStock}
                            </span>
                            {stock.code ? (
                              <button
                                type="button"
                                aria-label={formatUiText(text.analyzeStock, { stock: stock.name || stock.code })}
                                className="inline-flex min-h-11 min-w-11 items-center justify-center text-xs font-semibold text-primary"
                                onClick={() => onAnalyzeStock(stock)}
                              >
                                <span className="inline-flex h-7 items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2 transition-colors hover:border-primary hover:bg-primary/15 hover:text-foreground">
                                  <Play className="h-3 w-3" />
                                  {text.analyze}
                                </span>
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <p className="mt-2 text-xs text-secondary-text">
                          {text.change} {formatStockChangeText(stock.changePct, text)} · {text.heat} {formatNumber(stock.hotStockScore, 0)}
                        </p>
                        {stock.source || stock.sourceConfidence != null || stock.fallbackUsed ? (
                          <p className="mt-1 text-xs text-secondary-text">
                            {formatUiText(text.source, { source: stock.source || '-' })}
                            {stock.sourceConfidence != null ? ` · ${formatUiText(text.confidence, { value: formatPercent(stock.sourceConfidence) })}` : ''}
                            {stock.fallbackUsed ? ` · ${text.fallback}` : ''}
                          </p>
                        ) : null}
                      </Surface>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </Surface>
        ) : null}
      </Surface>

);
