import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatThinkingDetails } from '../ChatThinkingDetails';
import { UI_TEXT, type UiTextKey } from '../../../i18n/uiText';
import type { ProgressStep } from '../../../stores/agentChatStore';
import {
  resetChatThinkingTraceStats,
  snapshotChatThinkingTraceStats,
} from '../chatThinkingTrace';

const t = (key: UiTextKey) => UI_TEXT.en[key];

describe('ChatThinkingDetails', () => {
  it('expands a completed tool call with an accessible disclosure', () => {
    render(
      <ChatThinkingDetails
        t={t}
        steps={[{
          type: 'tool_done',
          tool: 'get_daily_history',
          display_name: 'Daily history',
          success: true,
          duration: 0.5,
          meta: {
            arguments: { stock_code: '600519' },
            result_preview: '{"close":1500}',
            result_length: 14,
            cached: false,
          },
        }]}
      />,
    );

    const detailToggle = screen.getByRole('button', { name: /Daily history.*View details/ });
    expect(detailToggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/"stock_code": "600519"/)).not.toBeInTheDocument();

    fireEvent.click(detailToggle);

    expect(detailToggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/"stock_code": "600519"/)).toBeVisible();
    expect(screen.getByText(/"close":1500/)).toBeVisible();
    expect(screen.getByText(/"close":1500/)).toHaveClass('max-h-64', 'overflow-auto');
  });

  it('expands a stage using only public status, duration, and reason fields', () => {
    render(
      <ChatThinkingDetails
        t={t}
        steps={[{
          type: 'stage_done',
          stage: 'agent_loop',
          status: 'completed',
          duration: 1.2,
          reason: 'budget_guard',
          message: 'Stage done',
        }]}
      />,
    );

    const detailToggle = screen.getByRole('button', { name: /View details/ });
    expect(screen.queryByTestId('chat-stage-detail')).not.toBeInTheDocument();
    fireEvent.click(detailToggle);
    expect(screen.getByTestId('chat-stage-detail')).toHaveTextContent('"stage": "agent_loop"');
    expect(screen.getByTestId('chat-stage-detail')).toHaveTextContent('"status": "completed"');
    expect(screen.getByTestId('chat-stage-detail')).toHaveTextContent('"reason": "budget_guard"');
  });

  it('marks only the newest real live event as current without changing event order', () => {
    const { container } = render(
      <ChatThinkingDetails
        mode="live"
        t={t}
        steps={[
          { type: 'thinking', step: 1, message: 'Planning' },
          { type: 'tool_done', tool: 'lookup', success: true, duration: 0.3 },
          { type: 'tool_start', tool: 'search', display_name: 'Search' },
        ]}
      />,
    );

    const rows = container.querySelectorAll('[data-trace-step]');
    expect(rows).toHaveLength(3);
    expect([...rows].map((row) => row.getAttribute('data-trace-step'))).toEqual([
      'thinking',
      'tool_done',
      'tool_start',
    ]);
    expect(rows[0]).not.toHaveAttribute('data-current');
    expect(rows[1]).not.toHaveAttribute('data-current');
    expect(rows[2]).toHaveAttribute('data-current', 'true');
    expect(within(rows[2] as HTMLElement).getByText('Running')).toHaveAttribute(
      'data-trace-status',
      'info',
    );
  });

  it('keeps failures and budget skips semantically distinct from current activity', () => {
    const { container } = render(
      <ChatThinkingDetails
        mode="live"
        t={t}
        steps={[
          { type: 'tool_done', tool: 'lookup', success: false, duration: 0.2 },
          { type: 'pipeline_timeout', stage: 'agent_loop', timeout: 30 },
          { type: 'pipeline_budget_skipped', stage: 'critic', reason: 'insufficient_budget' },
        ]}
      />,
    );

    const failed = container.querySelector('[data-trace-step="tool_done"]');
    const timeout = container.querySelector('[data-trace-step="pipeline_timeout"]');
    const skipped = container.querySelector('[data-trace-step="pipeline_budget_skipped"]');
    expect(within(failed as HTMLElement).getByText('Failed')).toHaveAttribute('data-trace-status', 'danger');
    expect(within(timeout as HTMLElement).getByText('Timeout')).toHaveAttribute('data-trace-status', 'danger');
    expect(within(skipped as HTMLElement).getByText('Skipped')).toHaveAttribute('data-trace-status', 'warning');
    expect(skipped).toHaveAttribute('data-current', 'true');
    expect(within(skipped as HTMLElement).queryByText('Running')).not.toBeInTheDocument();
  });

  it('does not mark persisted history rows as current', () => {
    const { container } = render(
      <ChatThinkingDetails
        mode="history"
        t={t}
        steps={[{ type: 'tool_done', tool: 'lookup', success: true, duration: 0.2 }]}
      />,
    );

    expect(container.querySelector('[data-trace-step]')).not.toHaveAttribute('data-current');
    expect(screen.getByText('Completed')).toHaveAttribute('data-trace-status', 'success');
  });

  it('keeps disclosure state on the same event when the visible list grows from failures to the full trace', () => {
    const successStep = {
      type: 'tool_done',
      tool: 'lookup',
      display_name: 'Lookup',
      success: true,
      duration: 0.2,
      meta: { arguments: { q: 'ok' } },
    };
    const failedStep = {
      type: 'tool_done',
      tool: 'search',
      display_name: 'Search',
      success: false,
      duration: 0.4,
      meta: { arguments: { q: 'fail' } },
    };

    const { rerender } = render(
      <ChatThinkingDetails t={t} mode="history" steps={[failedStep]} />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Search.*View details/ }));
    expect(screen.getByText(/"q": "fail"/)).toBeVisible();
    expect(screen.queryByText(/"q": "ok"/)).not.toBeInTheDocument();

    rerender(
      <ChatThinkingDetails t={t} mode="history" steps={[successStep, failedStep]} />,
    );

    expect(screen.getByText(/"q": "fail"/)).toBeVisible();
    expect(screen.queryByText(/"q": "ok"/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Search.*View details/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByRole('button', { name: /Lookup.*View details/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });

  it('keeps a newest completed live event successful while marking it current', () => {
    const { container } = render(
      <ChatThinkingDetails
        mode="live"
        t={t}
        steps={[{ type: 'tool_done', tool: 'lookup', success: true, duration: 0.2 }]}
      />,
    );

    const row = container.querySelector('[data-trace-step="tool_done"]');
    expect(row).toHaveAttribute('data-current', 'true');
    expect(row).toHaveClass('border-success/30', 'bg-success/5');
    expect(within(row as HTMLElement).getByText('Completed')).toHaveAttribute(
      'data-trace-status',
      'success',
    );
    expect(within(row as HTMLElement).queryByText('Running')).not.toBeInTheDocument();
  });

  it('keeps per-append derivation and row work constant while streaming 200 live steps', () => {
    const streamed: ProgressStep[] = [];
    const { rerender } = render(
      <ChatThinkingDetails mode="live" t={t} steps={streamed} />,
    );

    const perAppendDerive: number[] = [];
    const perAppendIdentity: number[] = [];

    for (let index = 0; index < 200; index += 1) {
      streamed.push({
        type: 'thinking',
        step: index + 1,
        message: `Planning ${index + 1}`,
      });
      resetChatThinkingTraceStats();
      rerender(
        <ChatThinkingDetails mode="live" t={t} steps={[...streamed]} />,
      );
      const snapshot = snapshotChatThinkingTraceStats();
      perAppendDerive.push(snapshot.derive);
      perAppendIdentity.push(snapshot.identity);
    }

    const tailDerive = perAppendDerive.slice(1);
    const tailIdentity = perAppendIdentity.slice(1);

    expect(perAppendDerive[0]).toBe(1);
    expect(new Set(tailDerive)).toEqual(new Set([1]));
    expect(new Set(tailIdentity)).toEqual(new Set([1]));
    expect(screen.getAllByText(/Planning \d+/)).toHaveLength(200);
    expect(document.querySelectorAll('[data-current="true"]')).toHaveLength(1);
    expect(document.querySelector('[data-current="true"]')).toHaveTextContent('Planning 200');
  });

  it('renders the same live transcript HTML when steps arrive incrementally or all at once', () => {
    const steps: ProgressStep[] = [
      { type: 'thinking', step: 1, message: 'Planning' },
      { type: 'tool_start', tool: 'search', display_name: 'Search' },
      {
        type: 'tool_done',
        tool: 'search',
        display_name: 'Search',
        success: true,
        duration: 0.4,
        meta: { arguments: { q: '600519' }, result_preview: '{"ok":true}', result_length: 11 },
      },
      { type: 'stage_done', stage: 'agent_loop', status: 'completed', duration: 1.2, reason: 'budget_guard' },
      { type: 'pipeline_budget_skipped', stage: 'critic', reason: 'insufficient_budget' },
    ];

    const { container: batchContainer, unmount } = render(
      <ChatThinkingDetails mode="live" t={t} steps={steps} />,
    );
    const batchTrace = serializeTraceDom(batchContainer);
    unmount();

    const growing: ProgressStep[] = [];
    const { container, rerender } = render(
      <ChatThinkingDetails mode="live" t={t} steps={growing} />,
    );
    for (const step of steps) {
      growing.push(step);
      rerender(<ChatThinkingDetails mode="live" t={t} steps={[...growing]} />);
    }

    expect(serializeTraceDom(container)).toEqual(batchTrace);
  });
});

function serializeTraceDom(container: HTMLElement) {
  return [...container.querySelectorAll('[data-trace-step]')].map((row) => ({
    type: row.getAttribute('data-trace-step'),
    current: row.getAttribute('data-current'),
    className: row.className,
    text: row.textContent?.replace(/\s+/g, ' ').trim(),
    expanded: row.querySelector('button')?.getAttribute('aria-expanded') ?? null,
    label: row.querySelector('button')?.getAttribute('aria-label') ?? null,
    status: row.querySelector('[data-trace-status]')?.getAttribute('data-trace-status') ?? null,
    statusText: row.querySelector('[data-trace-status]')?.textContent ?? null,
  }));
}
