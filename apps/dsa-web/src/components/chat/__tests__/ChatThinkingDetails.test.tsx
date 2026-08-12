import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatThinkingDetails } from '../ChatThinkingDetails';
import { UI_TEXT, type UiTextKey } from '../../../i18n/uiText';

describe('ChatThinkingDetails', () => {
  it('expands a completed tool call to show its persisted public details', () => {
    const t = (key: UiTextKey) => UI_TEXT.zh[key];
    render(
      <ChatThinkingDetails
        t={t}
        steps={[{
          type: 'tool_done',
          tool: 'get_daily_history',
          display_name: '获取历史K线',
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

    const detailToggle = screen.getByRole('button', { name: /获取历史K线.*查看详情/ });
    expect(screen.getByText(/"stock_code": "600519"/)).not.toBeVisible();

    fireEvent.click(detailToggle);

    expect(screen.getByText(/"stock_code": "600519"/)).toBeVisible();
    expect(screen.getByText(/"close":1500/)).toBeVisible();
  });

  it('expands a completed stage to show real status/duration/reason fields only', () => {
    const t = (key: UiTextKey) => UI_TEXT.zh[key];
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

    const detailToggle = screen.getByRole('button', { name: /查看详情/ });
    expect(screen.getByTestId('chat-stage-detail')).not.toBeVisible();
    fireEvent.click(detailToggle);
    expect(screen.getByTestId('chat-stage-detail')).toBeVisible();
    expect(screen.getByText(/stage: agent_loop/)).toBeVisible();
    expect(screen.getByText(/status: completed/)).toBeVisible();
    expect(screen.getByText(/reason: budget_guard/)).toBeVisible();
  });

});
