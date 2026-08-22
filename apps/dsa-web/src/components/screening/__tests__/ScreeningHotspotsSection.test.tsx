// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AlphaSiftHotspot, AlphaSiftHotspotDetail } from '../../../api/alphasift';
import { SCREENING_TEXT } from '../../../locales/screening';
import { ScreeningHotspotsSection, type ScreeningHotspotsSectionProps } from '../ScreeningHotspotsSection';
import { getHotspotPanelKind, isLastGoodHotspotResponse } from '../hotspotModel';

const text = SCREENING_TEXT.en;
const dataSourcesName = `${text.openDataSources} · ${text.hotspots}`;
const mappedSourceError = text.hotspotUnavailableDetail.replace('{detail}', text.diagnosticNetwork);

const hotspot: AlphaSiftHotspot = {
  topic: 'ai-compute',
  name: 'AI Compute',
  rank: 1,
  heatScore: 92,
  changePct: 6.2,
  trendScore: 80,
  persistenceScore: 70,
  sampleStockCount: 8,
  leaders: ['Leader A'],
};

const degradedDetail: AlphaSiftHotspotDetail = {
  enabled: true,
  provider: 'akshare',
  topic: 'ai-compute',
  name: 'AI Compute',
  summary: 'Degraded theme detail.',
  qualityStatus: 'stale',
  stale: true,
  staleAgeHours: 2.5,
  fallbackUsed: true,
  missingFields: ['live_stocks'],
  sourceErrors: ['eastmoney_hotspot_unavailable', "RemoteDisconnected('Remote end closed connection without response')"],
  route: [{ title: 'Catalyst', description: 'Route item', publishedAt: '2026-08-05' }],
  stocks: [{ code: '000001', name: 'Demo Stock', changePct: 2.1, hotStockScore: 88 }],
  stockCount: 1,
};

function getHotspotSection() {
  const section = screen.getByRole('heading', { name: text.hotspots }).closest('section');
  expect(section).not.toBeNull();
  return section as HTMLElement;
}

function renderSection(overrides: Partial<ScreeningHotspotsSectionProps> = {}) {
  const onRefresh = vi.fn();
  const onOpenDataSources = vi.fn();
  const view = render(
    <ScreeningHotspotsSection
      text={text}
      language="en"
      isScreeningEnabled
      hotspots={[]}
      hotspotsUpdatedAt={null}
      hotspotsExpanded
      selectedHotspotTopic={null}
      hotspotDetail={null}
      loadingHotspots={false}
      loadingHotspotDetail={false}
      hotspotError=""
      hotspotDetailError=""
      onToggleExpanded={() => undefined}
      onRefresh={onRefresh}
      onSelectHotspot={() => undefined}
      onAnalyzeStock={() => undefined}
      onOpenDataSources={onOpenDataSources}
      {...overrides}
    />,
  );
  return { onRefresh, onOpenDataSources, ...view };
}

describe('getHotspotPanelKind', () => {
  const empty = text.noCachedHotspots;
  const unavailable = text.hotspotUnavailable;

  it('distinguishes genuine empty, degraded, cached, and healthy lists', () => {
    expect(getHotspotPanelKind(0, empty, empty, unavailable)).toBe('empty');
    expect(getHotspotPanelKind(0, unavailable, empty, unavailable)).toBe('empty');
    expect(getHotspotPanelKind(0, mappedSourceError, empty, unavailable)).toBe('degraded');
    expect(getHotspotPanelKind(0, text.hotspotLoadFailed, empty, unavailable)).toBe('degraded');
    expect(getHotspotPanelKind(1, text.hotspotLoadFailed, empty, unavailable)).toBe('cached');
    expect(getHotspotPanelKind(1, '', empty, unavailable)).toBe('healthy');
  });

  it('treats failure-serve-cache as last-good and does not treat a successful live fallback as last-good', () => {
    expect(isLastGoodHotspotResponse({
      enabled: true,
      provider: 'akshare',
      hotspotCount: 1,
      hotspots: [hotspot],
      cacheUsed: true,
      fallbackUsed: true,
      sourceErrors: ['alphasift_hotspot_source_error'],
    })).toBe(true);
    expect(isLastGoodHotspotResponse({
      enabled: true,
      provider: 'akshare',
      hotspotCount: 1,
      hotspots: [hotspot],
      cacheUsed: false,
      fallbackUsed: true,
      sourceErrors: ['alphasift_hotspot_source_error', 'alphasift_hotspot_direct_fallback_used'],
    })).toBe(false);
    expect(isLastGoodHotspotResponse({
      enabled: true,
      provider: 'akshare',
      hotspotCount: 1,
      hotspots: [hotspot],
      cacheUsed: true,
      fallbackUsed: false,
      sourceErrors: [],
    })).toBe(false);
  });
});

describe('ScreeningHotspotsSection recovery contract', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders a genuine empty hotspot run with Retry and Data Sources, not as a source outage', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspotError: text.noCachedHotspots,
    });

    const hotspotSection = getHotspotSection();
    const alert = within(hotspotSection).getByRole('status');
    expect(within(alert).getByText(text.noCachedHotspots)).toBeInTheDocument();
    expect(within(alert).queryByText(text.sourcesUnavailableTitle)).not.toBeInTheDocument();
    expect(within(alert).queryByText(text.showingLastGoodTitle)).not.toBeInTheDocument();
    expect(within(hotspotSection).getByText(text.refreshDescription)).toBeInTheDocument();
    expect(within(hotspotSection).queryByText(text.sourcesUnavailableDescription)).not.toBeInTheDocument();
    expect(screen.queryByText('eastmoney_hotspot_unavailable')).not.toBeInTheDocument();
    const retry = within(hotspotSection).getByRole('button', { name: text.refreshHotspots });
    const dataSources = within(hotspotSection).getByRole('button', { name: dataSourcesName });
    expect(retry).toHaveAttribute('data-control', 'button');
    expect(dataSources).toHaveAttribute('data-control', 'button');
    fireEvent.click(retry);
    fireEvent.click(dataSources);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('renders a degraded empty hotspot run with mapped copy and Data Sources, not the idle empty hint', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspotError: mappedSourceError,
    });

    const hotspotSection = getHotspotSection();
    const alert = within(hotspotSection).getByRole('status');
    expect(within(alert).getByText(text.sourcesUnavailableTitle)).toBeInTheDocument();
    expect(within(alert).getByText(mappedSourceError)).toBeInTheDocument();
    expect(within(alert).queryByText(text.showingLastGoodTitle)).not.toBeInTheDocument();
    expect(within(hotspotSection).getByText(text.sourcesUnavailableDescription)).toBeInTheDocument();
    expect(within(hotspotSection).queryByText(text.refreshDescription)).not.toBeInTheDocument();
    expect(screen.queryByText('eastmoney_hotspot_unavailable')).not.toBeInTheDocument();
    expect(screen.queryByText(/RemoteDisconnected/)).not.toBeInTheDocument();
    fireEvent.click(within(hotspotSection).getByRole('button', { name: text.refreshHotspots }));
    fireEvent.click(within(hotspotSection).getByRole('button', { name: dataSourcesName }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('labels preserved last-good hotspots and keeps Retry plus Data Sources on that alert', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspots: [hotspot],
      hotspotsUpdatedAt: '2026-08-05T12:00:00Z',
      hotspotError: text.hotspotLoadFailed,
    });

    const hotspotSection = getHotspotSection();
    const alert = within(hotspotSection).getByRole('status');
    expect(within(alert).getByText(text.showingLastGoodTitle)).toBeInTheDocument();
    expect(within(alert).getByText(text.showingLastGoodMessage)).toBeInTheDocument();
    expect(within(alert).queryByText(text.hotspotLoadFailed)).not.toBeInTheDocument();
    expect(within(alert).queryByText(text.sourcesUnavailableTitle)).not.toBeInTheDocument();
    expect(within(alert).queryByText(text.refreshDescription)).not.toBeInTheDocument();
    expect(within(hotspotSection).getByText('AI Compute')).toBeInTheDocument();
    expect(within(hotspotSection).queryByText(text.refreshDescription)).not.toBeInTheDocument();
    fireEvent.click(within(hotspotSection).getByRole('button', { name: text.refreshHotspots }));
    fireEvent.click(within(hotspotSection).getByRole('button', { name: dataSourcesName }));
    expect(screen.getByText('AI Compute')).toBeInTheDocument();
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('places Data Sources on the empty hotspot alert instead of a page sibling, with Retry still in the section', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspotsExpanded: false,
      hotspotError: text.hotspotUnavailable,
    });

    const hotspotSection = getHotspotSection();
    expect(screen.queryByText('eastmoney_hotspot_unavailable')).not.toBeInTheDocument();
    const retry = within(hotspotSection).getByRole('button', { name: text.refreshHotspots });
    const alert = within(hotspotSection).getByRole('status');
    const dataSources = within(hotspotSection).getByRole('button', { name: dataSourcesName });
    expect(within(alert).getByText(text.hotspotUnavailable)).toBeInTheDocument();
    expect(within(alert).queryByText(text.sourcesUnavailableTitle)).not.toBeInTheDocument();
    expect(retry).toHaveAttribute('data-control', 'button');
    expect(dataSources).toHaveAttribute('data-control', 'button');
    expect(dataSources).toHaveAttribute('type', 'button');
    expect(hotspotSection.contains(dataSources)).toBe(true);
    expect(retry.closest('div')).toBe(dataSources.closest('div'));
    fireEvent.click(retry);
    fireEvent.click(dataSources);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('keeps Data Sources keyboard-focusable and associated with the empty hotspot alert', () => {
    const { onOpenDataSources } = renderSection({
      hotspotsExpanded: false,
      hotspotError: text.hotspotUnavailable,
    });

    const hotspotSection = getHotspotSection();
    const alert = within(hotspotSection).getByRole('status');
    const dataSources = within(hotspotSection).getByRole('button', { name: dataSourcesName });
    expect(within(alert).getByText(text.hotspotUnavailable)).toBeInTheDocument();
    expect(dataSources).toHaveAccessibleName(dataSourcesName);
    expect(dataSources).not.toBeDisabled();
    dataSources.focus();
    expect(dataSources).toHaveFocus();
    fireEvent.keyDown(dataSources, { key: 'Enter' });
    fireEvent.keyDown(dataSources, { key: ' ' });
    fireEvent.click(dataSources);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('places Data Sources on the degraded hotspot panel so mapped source_errors are not the only recovery UI', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspots: [hotspot],
      selectedHotspotTopic: 'ai-compute',
      hotspotDetail: degradedDetail,
    });

    const hotspotSection = getHotspotSection();
    expect(within(hotspotSection).getByText(text.degradedDetail).closest('details')).not.toBeNull();
    expect(screen.getByText(text.cacheFallbackHours.replace('{hours}', '2.5'))).toBeInTheDocument();
    expect(screen.getAllByText(text.diagnosticNetwork).length).toBeGreaterThan(0);
    expect(screen.queryByText(/RemoteDisconnected/)).not.toBeInTheDocument();
    fireEvent.click(within(hotspotSection).getByRole('button', { name: text.refreshHotspots }));
    fireEvent.click(within(hotspotSection).getByRole('button', { name: dataSourcesName }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('does not place Data Sources on healthy hotspot cards', () => {
    renderSection({
      hotspots: [hotspot],
      hotspotsUpdatedAt: '2026-08-05T12:00:00Z',
    });

    expect(screen.getByText('AI Compute')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: dataSourcesName })).not.toBeInTheDocument();
    expect(screen.queryByText(text.showingLastGoodTitle)).not.toBeInTheDocument();
    expect(screen.queryByText(text.sourcesUnavailableTitle)).not.toBeInTheDocument();
  });

  it('keeps Data Sources reachable when screening is disabled and Retry is blocked', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      isScreeningEnabled: false,
      hotspotsExpanded: false,
      hotspotError: text.hotspotUnavailable,
    });

    expect(within(getHotspotSection()).getByRole('button', { name: text.refreshHotspots })).toBeDisabled();
    const dataSources = within(getHotspotSection()).getByRole('button', { name: dataSourcesName });
    expect(dataSources).not.toBeDisabled();
    fireEvent.click(dataSources);
    expect(onRefresh).not.toHaveBeenCalled();
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });
});
