import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TaskPanel } from '../TaskPanel';
import type { TaskInfo } from '../../../types/analysis';
import { UiLanguageProvider, useUiLanguage } from '../../../contexts/UiLanguageContext';

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
  it('localizes stable task message codes on every render and keeps raw text in diagnostics', () => {
    const LanguageHarness = () => {
      const { setLanguage } = useUiLanguage();
      return (
        <>
          <button type="button" onClick={() => setLanguage('zh')}>中文</button>
          <button type="button" onClick={() => setLanguage('en')}>English</button>
          <TaskPanel
            tasks={[{
              ...baseTask,
              message: '仅供诊断的中文上游消息',
              messageCode: 'task_progress',
              messageParams: { progress: 40 },
              error: 'raw upstream failure',
              revision: 3,
              updatedAt: '2026-03-21T08:00:03Z',
              traceId: 'trace-task-1',
            }]}
          />
        </>
      );
    };

    render(
      <UiLanguageProvider>
        <LanguageHarness />
      </UiLanguageProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: '中文' }));
    expect(screen.getByText('分析进度 40%')).toBeInTheDocument();
    expect(screen.queryByText('仅供诊断的中文上游消息', { selector: 'p' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'English' }));

    expect(screen.getByText('Analysis progress: 40%')).toBeInTheDocument();
    expect(screen.queryByText('分析进度 40%')).not.toBeInTheDocument();
    expect(screen.getByText('仅供诊断的中文上游消息')).toBeInTheDocument();
    expect(screen.getByText('raw upstream failure')).toBeInTheDocument();
  });

  it('uses a localized generic message for unknown codes instead of raw server text', () => {
    const LanguageHarness = () => {
      const { setLanguage } = useUiLanguage();
      return (
        <>
          <button type="button" onClick={() => setLanguage('en')}>English</button>
          <TaskPanel tasks={[{
            ...baseTask,
            message: '不应成为英文界面主文案',
            messageCode: 'future_server_code',
            traceId: 'trace-unknown',
          }]} />
        </>
      );
    };

    render(
      <UiLanguageProvider>
        <LanguageHarness />
      </UiLanguageProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'English' }));

    expect(screen.getByText('Analysis is in progress')).toBeInTheDocument();
    expect(screen.queryByText('不应成为英文界面主文案', { selector: 'p' })).not.toBeInTheDocument();
    expect(screen.getByText('不应成为英文界面主文案', { selector: 'span' })).toBeInTheDocument();
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
    expect(screen.getAllByText('运行诊断')).toHaveLength(2);
    expect(screen.getAllByText('trace-task-1')).toHaveLength(2);
    expect(screen.queryByText(/请求阶段:/)).not.toBeInTheDocument();
    expect(container.querySelector('.home-panel-card')).toBeTruthy();
    expect(container.querySelector('.home-subpanel')).toBeTruthy();
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
    expect(screen.getByText('运行诊断')).toHaveClass('whitespace-nowrap');
    expect(screen.getByText('c5b9665a64...')).toHaveClass('truncate');
    expect(screen.getByRole('button', { name: '查看 长飞光纤 运行流' })).toBeInTheDocument();
  });

  it('opens the run-flow view from an active task icon button', () => {
    const onOpenRunFlow = vi.fn();
    render(
      <TaskPanel
        tasks={[baseTask]}
        onOpenRunFlow={onOpenRunFlow}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '查看 贵州茅台 运行流' }));

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
            revision: 7,
          },
        ]}
        onDismiss={onDismiss}
      />,
    );

    expect(screen.getByText('贵州茅台')).toBeInTheDocument();
    expect(screen.getByLabelText('任务状态：已完成')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '关闭 贵州茅台 任务' }));
    expect(onDismiss).toHaveBeenCalledWith('task-1', 7);
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

  it('does not render when there are no tasks at all', () => {
    const { container } = render(<TaskPanel tasks={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
