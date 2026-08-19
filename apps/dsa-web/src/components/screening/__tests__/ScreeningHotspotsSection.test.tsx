// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AlphaSiftHotspot, AlphaSiftHotspotDetail } from '../../../api/alphasift';
import { SCREENING_TEXT } from '../../../locales/screening';
import { Button } from '../../common';
import { ScreeningHotspotsSection, type ScreeningHotspotsSectionProps } from '../ScreeningHotspotsSection';

const text = SCREENING_TEXT.en;

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

function renderSection(overrides: Partial<ScreeningHotspotsSectionProps> = {}) {
  const onRefresh = vi.fn();
  const onOpenDataSources = vi.fn();
  const view = render(
    <>
      <Button
        size="default"
        variant="secondary"
        aria-label={`${text.openDataSources} · ${text.hotspots}`}
        onClick={onOpenDataSources}
      >
        {text.openDataSources}
      </Button>
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
        {...overrides}
      />
    </>,
  );
  return { onRefresh, onOpenDataSources, ...view };
}

describe('ScreeningHotspotsSection recovery contract', () => {
  afterEach(() => {
    cleanup();
  });

  it('offers Retry and Data Sources from an empty hotspot error instead of a raw source_errors-only UI', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspotsExpanded: false,
      hotspotError: text.hotspotUnavailable,
    });

    expect(screen.queryByText('eastmoney_hotspot_unavailable')).not.toBeInTheDocument();
    const retry = screen.getByRole('button', { name: text.refreshHotspots });
    const dataSources = screen.getByRole('button', { name: `${text.openDataSources} · ${text.hotspots}` });
    expect(retry).toHaveAttribute('data-control', 'button');
    expect(dataSources).toHaveAttribute('data-control', 'button');
    fireEvent.click(retry);
    fireEvent.click(dataSources);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('keeps the expanded refresh control as Retry and still offers Data Sources', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspotError: text.hotspotUnavailable,
    });

    expect(screen.getByText(text.refreshDescription)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: text.refreshHotspots }));
    fireEvent.click(screen.getByRole('button', { name: `${text.openDataSources} · ${text.hotspots}` }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('labels preserved last-good hotspots and still offers Retry plus Data Sources', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspots: [hotspot],
      hotspotsUpdatedAt: '2026-08-05T12:00:00Z',
      hotspotError: text.hotspotLoadFailed,
    });

    expect(screen.getByText(text.showingLastGoodTitle)).toBeInTheDocument();
    expect(screen.getByText('AI Compute')).toBeInTheDocument();
    expect(screen.getByText(text.hotspotLoadFailed)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: text.refreshHotspots }));
    fireEvent.click(screen.getByRole('button', { name: `${text.openDataSources} · ${text.hotspots}` }));
    expect(screen.getByText('AI Compute')).toBeInTheDocument();
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('adds Retry and Data Sources next to degraded hotspot details so source_errors are not the only recovery UI', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      hotspots: [hotspot],
      selectedHotspotTopic: 'ai-compute',
      hotspotDetail: degradedDetail,
    });

    expect(screen.getByText(text.degradedDetail).closest('details')).not.toBeNull();
    expect(screen.getByText(text.cacheFallbackHours.replace('{hours}', '2.5'))).toBeInTheDocument();
    expect(screen.getAllByText(text.diagnosticNetwork).length).toBeGreaterThan(0);
    expect(screen.queryByText(/RemoteDisconnected/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: text.refreshHotspots }));
    fireEvent.click(screen.getByRole('button', { name: `${text.openDataSources} · ${text.hotspots}` }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });

  it('keeps Data Sources reachable when screening is disabled and Retry is blocked', () => {
    const { onRefresh, onOpenDataSources } = renderSection({
      isScreeningEnabled: false,
      hotspotsExpanded: false,
      hotspotError: text.hotspotUnavailable,
    });

    expect(screen.getByRole('button', { name: text.refreshHotspots })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: `${text.openDataSources} · ${text.hotspots}` }));
    expect(onRefresh).not.toHaveBeenCalled();
    expect(onOpenDataSources).toHaveBeenCalledTimes(1);
  });
});
