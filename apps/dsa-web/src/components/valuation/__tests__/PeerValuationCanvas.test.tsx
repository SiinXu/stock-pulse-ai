// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ReactElement } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PeerValuationCanvas as PeerCanvasPayload } from '../../../api/valuation';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { PeerValuationCanvas } from '../PeerValuationCanvas';

const sampleCanvas: PeerCanvasPayload = {
  schemaVersion: 'peer-valuation-canvas-v1',
  status: 'partial',
  stockCode: '600519',
  baseCurrency: 'CNY',
  fxStale: false,
  peerSet: {
    source: 'custom',
    sourceLabel: 'custom',
    explanation: 'Caller-supplied peer codes (manual set).',
    requestedCodes: ['000858', '000799'],
    missingDataCodes: ['000799'],
  },
  metrics: ['peRatio', 'pbRatio'],
  rows: [
    {
      stockCode: '600519',
      role: 'target',
      dataStatus: 'partial',
      missingMetrics: [],
      metrics: {
        peRatio: { value: 30, status: 'ok' },
        pbRatio: { value: 8, status: 'ok' },
        marketCap: { value: 2000000, status: 'ok', currency: 'CNY' },
        currentPrice: { value: 1600, status: 'ok', currency: 'CNY' },
      },
    },
    {
      stockCode: '000858',
      role: 'peer',
      dataStatus: 'ok',
      missingMetrics: [],
      metrics: {
        peRatio: { value: 20, status: 'ok' },
        pbRatio: { value: 5, status: 'ok' },
        marketCap: { value: 800000, status: 'ok', currency: 'CNY' },
        currentPrice: { value: 120, status: 'ok', currency: 'CNY' },
      },
    },
    {
      stockCode: '000799',
      role: 'peer',
      dataStatus: 'missing',
      missingMetrics: ['peRatio', 'pbRatio'],
      metrics: {
        peRatio: { value: null, status: 'missing', missingReason: 'unavailable' },
        pbRatio: { value: null, status: 'missing', missingReason: 'unavailable' },
        marketCap: { value: null, status: 'missing' },
        currentPrice: { value: 50, status: 'ok', currency: 'CNY' },
      },
    },
  ],
  medians: { peMedian: 20, pbMedian: 5 },
  heatmapCells: [
    { rowId: '600519', rowLabel: '600519 *', columnId: 'pe_ratio', columnLabel: 'PE/RATIO', score: 60 },
    { rowId: '000858', rowLabel: '000858', columnId: 'pe_ratio', columnLabel: 'PE/RATIO', score: 40 },
  ],
  disclaimer: 'Model estimate for research support only. Not investment advice.',
};

const renderPanel = (ui: ReactElement) =>
  render(<UiLanguageProvider initialLanguage="en">{ui}</UiLanguageProvider>);

describe('PeerValuationCanvas', () => {
  it('renders peer grid with missing data annotated', () => {
    renderPanel(<PeerValuationCanvas canvas={sampleCanvas} stockCode="600519" readOnly />);
    expect(screen.getByTestId('peer-valuation-canvas')).toBeInTheDocument();
    expect(screen.getByTestId('peer-canvas-source-explanation')).toHaveTextContent(/Caller-supplied/i);
    expect(screen.getByText('600519')).toBeInTheDocument();
    expect(screen.getByText('000799')).toBeInTheDocument();
    expect(screen.getAllByText(/Missing data|Missing annotated/i).length).toBeGreaterThan(0);
  });

  it('builds canvas via injected fetcher', async () => {
    const fetchCanvas = vi.fn().mockResolvedValue(sampleCanvas);
    renderPanel(
      <PeerValuationCanvas stockCode="600519" fetchCanvas={fetchCanvas} />,
    );
    fireEvent.change(screen.getByTestId('peer-canvas-peer-codes'), {
      target: { value: '000858,000799' },
    });
    fireEvent.click(screen.getByTestId('peer-canvas-build'));
    await waitFor(() => expect(fetchCanvas).toHaveBeenCalled());
    expect(fetchCanvas).toHaveBeenCalledWith(
      expect.objectContaining({
        stockCode: '600519',
        peerCodes: ['000858', '000799'],
        peerSource: 'custom',
      }),
    );
    expect(screen.getByTestId('peer-canvas-result')).toBeInTheDocument();
  });
});
