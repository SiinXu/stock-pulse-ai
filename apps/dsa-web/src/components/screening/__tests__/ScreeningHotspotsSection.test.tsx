// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AlphaSiftHotspot, AlphaSiftHotspotDetail } from '../../../api/alphasift';
import { SCREENING_TEXT } from '../../../locales/screening';
import { Button } from '../../common';
import { ScreeningHotspotsSection, type ScreeningHotspotsSectionProps } from '../ScreeningHotspotsSection';

const text = SCREENING_TEXT.en;
const dataSourcesName = `${text.openDataSources} · ${text.hotspots}`;

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

function dataSourcesSlot(onOpenDataSources: () => void) {
  return (
    <Button
      size="default"
      variant="secondary"
      aria-label={dataSourcesName}
      onClick={onOpenDataSources}
    >
      {text.openDataSources}
    </Button>
  );
}

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
      dataSourcesAction={dataSourcesSlot(onOpenDataSources)}
      {...overrides}
    />,
  );
  return { onRefresh, onOpenDataSources, ...view };
}

describe('ScreeningHotspotsSection recovery contract', () => {
  afterEach(() => {
    cleanup();
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

  it('keeps Retry and Data Sources on the expanded empty-error surface, not as a page sibling', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspotError: text.hotspotUnavailable,
    });

    const hotspotSection = getHotspotSection();
    expect(within(hotspotSection).getByText(text.refreshDescription)).toBeInTheDocument();
    expect(within(hotspotSection).getByRole('status')).toHaveTextContent(text.hotspotUnavailable);
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
    expect(within(alert).getByText(text.hotspotLoadFailed)).toBeInTheDocument();
    expect(within(hotspotSection).getByText('AI Compute')).toBeInTheDocument();
    fireEvent.click(within(hotspotSection).getByRole('button', { name: text.refreshHotspots }));
    fireEvent.click(within(hotspotSection).getByRole('button', { name: dataSourcesName }));
    expect(screen.getByText('AI Compute')).toBeInTheDocument();
    expect(onRefresh).toHaveBeenCalledTimes(1);
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
      dataSourcesAction: undefined,
    });

    expect(screen.getByText('AI Compute')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: dataSourcesName })).not.toBeInTheDocument();
    expect(screen.queryByText(text.showingLastGoodTitle)).not.toBeInTheDocument();
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
