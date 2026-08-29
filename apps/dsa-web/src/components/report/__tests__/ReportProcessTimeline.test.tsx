// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import type { RunFlowEvent, RunFlowSnapshot } from '../../../types/runFlow';
import { ReportProcessTimeline } from '../ReportProcessTimeline';

const useRunFlowSnapshotMock = vi.fn();

vi.mock('../../../hooks/useRunFlowSnapshot', () => ({
  useRunFlowSnapshot: (...args: unknown[]) => useRunFlowSnapshotMock(...args),
}));

const agentEvent = (
  id: string,
  sequence: number,
  type: string,
  title: string,
): RunFlowEvent => ({
  id,
  timestamp: '2026-08-12T10:00:00Z',
  severity: 'success',
  type,
  nodeId: `node-${id}`,
  title,
  message: `${title} · step=${sequence}`,
  metadata: {
    schemaVersion: 1,
    sequence,
    eventType: type.replaceAll('_', '.'),
    status: 'success',
    duration_ms: 250,
    step: sequence,
    detailIntegrity: 'valid',
    attrs: { reason: 'ok' },
  },
});

const snapshot = (events: RunFlowEvent[]): RunFlowSnapshot => ({
  taskId: 'task-timeline',
  traceId: 'trace-timeline',
  stockCode: '600519',
  status: 'success',
  generatedAt: '2026-08-12T10:01:00Z',
  summary: {
    failedAttempts: 0,
    fallbackCount: 0,
    dataSourceCount: 0,
    eventCount: events.length,
  },
  lanes: [],
  nodes: [],
  edges: [],
  events,
});

describe('ReportProcessTimeline', () => {
  beforeEach(() => {
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');
    useRunFlowSnapshotMock.mockReset();
  });

  it('stays hidden when there are no agent events', () => {
    useRunFlowSnapshotMock.mockReturnValue({
      snapshot: snapshot([]),
      isLoading: false,
      error: null,
    });
    const { container } = render(
      <UiLanguageProvider>
        <ReportProcessTimeline recordId={12} />
      </UiLanguageProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('wires Collapsible aria-expanded / aria-controls and stays collapsed by default', () => {
    const flow = snapshot([
      agentEvent('phase', 1, 'agent_phase_end', 'Phase end: plan_execution'),
    ]);
    useRunFlowSnapshotMock.mockReturnValue({
      snapshot: flow,
      isLoading: false,
      error: null,
    });
    const onOpenRunFlow = vi.fn();
    render(
      <UiLanguageProvider>
        <ReportProcessTimeline recordId={12} onOpenRunFlow={onOpenRunFlow} />
      </UiLanguageProvider>,
    );

    const chrome = screen.getByTestId('report-process-timeline');
    const toggle = within(chrome).getByRole('button', { name: 'Reasoning' });
    expect(toggle).toHaveAttribute('type', 'button');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    const panelId = toggle.getAttribute('aria-controls');
    expect(panelId).toBeTruthy();
    const panel = document.getElementById(panelId!);
    expect(panel).toHaveAttribute('hidden');
    expect(panel).toHaveAttribute('inert');
    expect(within(toggle).getByText('1 events')).toBeVisible();
    expect(screen.queryByTestId('process-timeline')).not.toBeVisible();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(panel).not.toHaveAttribute('hidden');
    expect(screen.getByTestId('process-timeline')).toBeVisible();

    const innerToggle = screen.getByRole('button', { name: /View details/ });
    expect(innerToggle).toHaveAttribute('type', 'button');
    expect(innerToggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('process-timeline-why')).not.toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'View run flow' }));
    expect(onOpenRunFlow).toHaveBeenCalledWith(12);
  });
});
