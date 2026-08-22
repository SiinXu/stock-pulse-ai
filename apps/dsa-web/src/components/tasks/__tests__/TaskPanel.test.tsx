import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analysisApi } from '../../../api/analysis';
import { TaskPanel } from '../TaskPanel';
import type { TaskInfo } from '../../../types/analysis';

vi.mock('../../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../../api/analysis')>('../../../api/analysis');
  return {
    ...actual,
    analysisApi: {
      ...actual.analysisApi,
      cancelTask: vi.fn(),
    },
  };
});

const baseTask: TaskInfo = {
  taskId: 'task-1',
  stockCode: '600519',
  stockName: '贵州茅台',
  status: 'processing',
  progress: 40,
  message: '正在抓取最新行情',
  reportType: 'detailed',
  createdAt: '2026-03-21T08:00:00Z',
};

describe('TaskPanel', () => {
  beforeEach(() => {
    vi.mocked(analysisApi.cancelTask).mockReset();
  });

  it('renders requested analysis phase badges for active tasks', () => {
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            analysisPhase: 'intraday',
          },
          {
            ...baseTask,
            taskId: 'task-2',
            stockCode: 'AAPL',
            stockName: 'Apple',
            status: 'pending',
            analysisPhase: 'auto',
          },
        ]}
      />,
    );

    expect(screen.getByLabelText('请求阶段: 盘中')).toBeInTheDocument();
    expect(screen.getByLabelText('请求阶段: 自动阶段')).toBeInTheDocument();
  });

  it('renders active tasks with preserved dashboard panel styling', () => {
    const { container } = render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            traceId: 'trace-task-1',
          },
          {
            ...baseTask,
            taskId: 'task-2',
            stockCode: 'AAPL',
            stockName: 'Apple',
            status: 'pending',
            message: '等待分析队列',
          },
        ]}
      />,
    );

    expect(screen.getByText('分析任务')).toBeInTheDocument();
    expect(screen.getByText('1 进行中')).toBeInTheDocument();
    expect(screen.getByText('1 等待中')).toBeInTheDocument();
    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByLabelText('任务状态：分析中')).toBeInTheDocument();
    expect(screen.getByText('运行诊断')).toBeInTheDocument();
    expect(screen.getAllByText('trace-task-1')).toHaveLength(2);
    expect(screen.queryByText(/请求阶段:/)).not.toBeInTheDocument();
    expect(container.querySelector('[data-surface-level="interactive"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="task-panel-item"]')).toHaveAttribute(
      'data-surface-level',
      'interactive',
    );
    expect(screen.getByRole('progressbar', { name: '分析中 40%' })).toHaveAttribute(
      'aria-valuenow',
      '40',
    );
  });

  it('keeps narrow sidebar task metadata in rows instead of squeezing diagnostics vertically', () => {
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            stockCode: '601869.SH',
            stockName: '长飞光纤',
            progress: 32,
            message: '长飞光纤: 请求阶段: 自动阶段',
            analysisPhase: 'auto',
            traceId: 'c5b9665a64e3b9f42ad9f',
          },
        ]}
        onOpenRunFlow={vi.fn()}
      />,
    );

    const item = screen.getByTestId('task-panel-item');
    expect(item).toHaveClass('grid');
    expect(item).not.toHaveClass('flex');
    expect(screen.getByText('长飞光纤')).toHaveClass('truncate');
    expect(screen.getByText('601869.SH')).toHaveClass('shrink-0');
    expect(screen.getByText('32%')).toBeInTheDocument();

    const diagnosticsSummary = screen.getByTestId('task-panel-diagnostics-summary');
    expect(diagnosticsSummary).toHaveClass('grid-cols-[auto_minmax(0,1fr)_auto]');
    expect(diagnosticsSummary).toHaveClass('min-h-11');
    expect(screen.getByText('运行诊断')).toHaveClass('whitespace-nowrap');
    expect(screen.getByText('c5b9665a64...')).toHaveClass('truncate');
    expect(screen.getByRole('button', { name: '查看 长飞光纤 运行流' })).toBeInTheDocument();
  });

  it('renders a cancel control for a running analysis task and posts cancel', async () => {
    const onDismiss = vi.fn();
    vi.mocked(analysisApi.cancelTask).mockResolvedValue({
      taskId: 'task-1',
      status: 'cancel_requested',
      messageCode: 'task.cancel_requested',
      progress: 40,
    });
    render(
      <TaskPanel
        tasks={[baseTask]}
        onOpenRunFlow={vi.fn()}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByLabelText('任务状态：分析中')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看 贵州茅台 运行流' })).toBeInTheDocument();
    const cancelButton = screen.getByRole('button', { name: '取消 贵州茅台 分析' });
    fireEvent.click(cancelButton);
    await waitFor(() => {
      expect(analysisApi.cancelTask).toHaveBeenCalledWith('task-1');
    });
    expect(screen.queryByRole('button', { name: '关闭 贵州茅台 任务' })).not.toBeInTheDocument();
    expect(onDismiss).not.toHaveBeenCalled();
  });

  it('shows a visible error when analysis cancel fails', async () => {
    vi.mocked(analysisApi.cancelTask).mockRejectedValue(new Error('offline'));
    render(<TaskPanel tasks={[baseTask]} />);

    fireEvent.click(screen.getByRole('button', { name: '取消 贵州茅台 分析' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(alert.textContent?.trim()).not.toHaveLength(0);
  });

  it('does not offer cancel for market-review tasks listed in the panel', () => {
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            stockCode: 'market_review',
            stockName: '大盘复盘',
            reportType: 'detailed',
          },
        ]}
      />,
    );

    expect(screen.queryByRole('button', { name: /取消|停止/ })).not.toBeInTheDocument();
  });

  it('does not offer cancel for local model pull tasks listed in the panel', () => {
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            stockCode: 'qwen2.5:7b',
            stockName: 'qwen2.5:7b',
            reportType: 'local_model_pull',
          },
        ]}
      />,
    );

    expect(screen.queryByRole('button', { name: /取消|停止/ })).not.toBeInTheDocument();
  });

  it('does not treat cancel-requested status as a clickable cancel action', () => {
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            status: 'cancel_requested',
            message: '正在请求取消',
          },
        ]}
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('任务状态：请求取消')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /取消|停止/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '关闭 贵州茅台 任务' })).not.toBeInTheDocument();
  });

  it('opens the run-flow view from an active task icon button', () => {
    const onOpenRunFlow = vi.fn();
    render(
      <TaskPanel
        tasks={[baseTask]}
        onOpenRunFlow={onOpenRunFlow}
      />,
    );

    const runFlowButton = screen.getByRole('button', { name: '查看 贵州茅台 运行流' });
    expect(runFlowButton).toHaveAttribute('data-size', 'compact');
    fireEvent.click(runFlowButton);

    expect(onOpenRunFlow).toHaveBeenCalledWith(baseTask);
  });

  it('keeps cancel-requested tasks visible without rendering them as failed', () => {
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            status: 'cancel_requested',
            message: '正在请求取消',
          },
        ]}
      />,
    );

    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
    expect(screen.getByLabelText('任务状态：请求取消')).toBeInTheDocument();
    expect(screen.queryByText('失败')).not.toBeInTheDocument();
  });

  it('briefly retains a completed terminal task and dismisses it on close', () => {
    const onDismiss = vi.fn();
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            status: 'completed',
          },
        ]}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
    expect(screen.getByLabelText('任务状态：已完成')).toBeInTheDocument();

    const dismissButton = screen.getByRole('button', { name: '关闭 贵州茅台 任务' });
    expect(dismissButton).toHaveAttribute('data-size', 'compact');
    fireEvent.click(dismissButton);
    expect(onDismiss).toHaveBeenCalledWith('task-1');
  });

  it('renders a failed terminal task with a failure status', () => {
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            status: 'failed',
          },
        ]}
      />,
    );

    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
    expect(screen.getByLabelText('任务状态：失败')).toBeInTheDocument();
  });

  it('renders an interrupted task as a dismissible warning terminal state', () => {
    const onDismiss = vi.fn();
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            status: 'interrupted',
            progress: 100,
            messageCode: 'task.interrupted',
          },
        ]}
        onDismiss={onDismiss}
      />,
    );

    const statusBadge = screen.getByLabelText('任务状态：已中断');
    expect(statusBadge).toHaveClass('text-warning');
    expect(screen.getByText('任务已中断')).toBeInTheDocument();
    expect(screen.queryByText('100%')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '关闭 贵州茅台 任务' }));
    expect(onDismiss).toHaveBeenCalledWith('task-1');
  });

  it('does not render when there are no tasks at all', () => {
    const { container } = render(<TaskPanel tasks={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
