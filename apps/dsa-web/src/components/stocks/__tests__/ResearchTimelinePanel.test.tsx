// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ResearchTimelinePanel from '../ResearchTimelinePanel';
import { researchTimelineApi } from '../../../api/researchTimeline';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import type { ResearchTimelineResponse } from '../../../api/researchTimeline';

vi.mock('../../../api/researchTimeline', () => ({
  researchTimelineApi: {
    list: vi.fn(),
  },
}));

const listMock = vi.mocked(researchTimelineApi.list);

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function makeResponse(overrides: Partial<ResearchTimelineResponse> = {}): ResearchTimelineResponse {
  return {
    stockCode: '600519',
    items: [],
    nextCursor: null,
    hasMore: false,
    limit: 20,
    sources: {
      analysisRun: 'empty',
      chat: 'empty',
      signal: 'empty',
      hypothesis: 'unavailable',
    },
    ...overrides,
  };
}

function renderPanel() {
  return render(
    <UiLanguageProvider>
      <MemoryRouter initialEntries={['/stocks/600519']}>
        <Routes>
          <Route
            path="/stocks/:stockCode"
            element={(
              <>
                <ResearchTimelinePanel stockCode="600519" />
                <LocationProbe />
              </>
            )}
          />
          <Route path="/research/analysis" element={<LocationProbe />} />
          <Route path="/chat" element={<LocationProbe />} />
          <Route path="/signals" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </UiLanguageProvider>,
  );
}

describe('ResearchTimelinePanel', () => {
  beforeEach(() => {
    listMock.mockReset();
  });

  it('shows an honest empty state when all sources are empty/unavailable', async () => {
    listMock.mockResolvedValue(makeResponse());
    renderPanel();
    expect(await screen.findByTestId('stock-details-research-timeline')).toBeInTheDocument();
    expect(await screen.findByText(/No research activity yet|暂无研究活动/)).toBeInTheDocument();
    expect(screen.getByText(/Hypothesis source unavailable|假设源不可用/)).toBeInTheDocument();
    expect(listMock).toHaveBeenCalledWith('600519', expect.objectContaining({ limit: 20 }));
  });

  it('orders multi-day nodes and opens analysis deep links', async () => {
    listMock.mockResolvedValue(makeResponse({
      sources: {
        analysisRun: 'ok',
        chat: 'ok',
        signal: 'ok',
        hypothesis: 'unavailable',
      },
      items: [
        {
          id: 'signal:9',
          kind: 'signal',
          occurredAt: '2026-08-03T12:00:00+00:00',
          title: 'Signal · Buy',
          direction: 'Buy',
          confidence: 0.8,
          link: { type: 'decision_signal', signalId: 9, stockCode: '600519' },
        },
        {
          id: 'chat:3',
          kind: 'chat',
          occurredAt: '2026-08-02T11:00:00+00:00',
          title: 'Deep research chat',
          summary: 'Follow-up on valuation?',
          link: {
            type: 'chat_session',
            sessionId: 'sess-1',
            messageId: 3,
            turnId: 'turn-day2',
            stockCode: '600519',
          },
        },
        {
          id: 'analysis_run:1',
          kind: 'analysis_run',
          occurredAt: '2026-08-01T10:00:00+00:00',
          title: 'Buy',
          direction: 'Bullish',
          confidence: 0.72,
          link: {
            type: 'analysis_history',
            recordId: 1,
            stockCode: '600519',
          },
        },
      ],
    }));

    renderPanel();
    expect(await screen.findByTestId('research-timeline-node-signal:9')).toBeInTheDocument();
    expect(screen.getByTestId('research-timeline-node-chat:3')).toBeInTheDocument();
    expect(screen.getByTestId('research-timeline-node-analysis_run:1')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('research-timeline-open-analysis_run:1'));
    await waitFor(() => {
      expect(screen.getByTestId('location').textContent).toContain('/research/analysis');
      expect(screen.getByTestId('location').textContent).toContain('recordId=1');
    });
  });

  it('paginates with cursor and never implies full-history load', async () => {
    listMock
      .mockResolvedValueOnce(makeResponse({
        sources: {
          analysisRun: 'ok',
          chat: 'empty',
          signal: 'empty',
          hypothesis: 'unavailable',
        },
        items: [
          {
            id: 'analysis_run:2',
            kind: 'analysis_run',
            occurredAt: '2026-08-02T10:00:00+00:00',
            title: 'Hold',
            direction: 'Neutral',
            confidence: 0.5,
            link: { type: 'analysis_history', recordId: 2, stockCode: '600519' },
          },
        ],
        hasMore: true,
        nextCursor: 'cursor-page-1',
      }))
      .mockResolvedValueOnce(makeResponse({
        sources: {
          analysisRun: 'ok',
          chat: 'empty',
          signal: 'empty',
          hypothesis: 'unavailable',
        },
        items: [
          {
            id: 'analysis_run:1',
            kind: 'analysis_run',
            occurredAt: '2026-08-01T10:00:00+00:00',
            title: 'Buy',
            direction: 'Bullish',
            confidence: 0.7,
            link: { type: 'analysis_history', recordId: 1, stockCode: '600519' },
          },
        ],
        hasMore: false,
        nextCursor: null,
      }));

    renderPanel();
    expect(await screen.findByTestId('research-timeline-node-analysis_run:2')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('research-timeline-load-more'));
    await waitFor(() => {
      expect(listMock).toHaveBeenLastCalledWith(
        '600519',
        expect.objectContaining({ cursor: 'cursor-page-1', limit: 20 }),
      );
    });
    expect(await screen.findByTestId('research-timeline-node-analysis_run:1')).toBeInTheDocument();
  });

  it('compares direction and confidence for two selected analysis nodes', async () => {
    listMock.mockResolvedValue(makeResponse({
      sources: {
        analysisRun: 'ok',
        chat: 'empty',
        signal: 'empty',
        hypothesis: 'unavailable',
      },
      items: [
        {
          id: 'analysis_run:2',
          kind: 'analysis_run',
          occurredAt: '2026-08-02T10:00:00+00:00',
          title: 'Sell',
          direction: 'Bearish',
          confidence: 0.4,
          link: { type: 'analysis_history', recordId: 2, stockCode: '600519' },
        },
        {
          id: 'analysis_run:1',
          kind: 'analysis_run',
          occurredAt: '2026-08-01T10:00:00+00:00',
          title: 'Buy',
          direction: 'Bullish',
          confidence: 0.8,
          link: { type: 'analysis_history', recordId: 1, stockCode: '600519' },
        },
      ],
    }));

    renderPanel();
    const selectButtons = await screen.findAllByRole('button', {
      name: /Select for compare|选择对比/,
    });
    fireEvent.click(selectButtons[0]);
    fireEvent.click(selectButtons[1]);
    const diff = await screen.findByTestId('research-timeline-analysis-diff');
    expect(diff).toBeInTheDocument();
    expect(diff.textContent).toMatch(/Bullish/);
    expect(diff.textContent).toMatch(/Bearish/);
    expect(diff.textContent).toMatch(/80%/);
    expect(diff.textContent).toMatch(/40%/);
  });
});
