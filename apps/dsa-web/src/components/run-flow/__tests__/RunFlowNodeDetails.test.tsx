import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { RunFlowNode } from '../../../types/runFlow';
import { RunFlowNodeDetails } from '../RunFlowNodeDetails';

describe('RunFlowNodeDetails', () => {
  it('hides provider metrics that do not apply to queue nodes', () => {
    const node: RunFlowNode = {
      id: 'task_queue',
      lane: 'entry',
      kind: 'queue',
      label: '任务队列',
      status: 'success',
      startedAt: '2026-06-08T22:14:25',
      message: '任务进入运行队列',
    };

    render(<RunFlowNodeDetails node={node} onClose={() => undefined} />);

    expect(screen.getByText('任务队列')).toBeInTheDocument();
    expect(screen.getByText('类型')).toBeInTheDocument();
    expect(screen.getByText('队列')).toBeInTheDocument();
    expect(screen.getByText('开始时间')).toBeInTheDocument();
    expect(screen.queryByText('提供方')).not.toBeInTheDocument();
    expect(screen.queryByText('耗时')).not.toBeInTheDocument();
    expect(screen.queryByText('尝试次数')).not.toBeInTheDocument();
    expect(screen.queryByText('记录数')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '关闭节点详情' })).toHaveAttribute('data-size', 'default');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('renders provider attempts through the compact embedded table contract', () => {
    const node: RunFlowNode = {
      id: 'provider_attempts',
      lane: 'data_source',
      kind: 'data_source',
      label: '行情回退链',
      status: 'fallback',
      metadata: {
        attempts: [
          {
            id: 'attempt-1',
            label: '主数据源',
            provider: 'TushareFetcher',
            status: 'failed',
            durationMs: 320,
            recordCount: 0,
            startedAt: '2026-06-08T22:14:25',
          },
          {
            id: 'attempt-2',
            label: '备用数据源',
            provider: 'AkshareFetcher',
            status: 'success',
            durationMs: 410,
            recordCount: 39,
            startedAt: '2026-06-08T22:14:26',
          },
        ],
      },
    };

    render(<RunFlowNodeDetails node={node} />);

    const table = screen.getByRole('table', { name: '运行尝试' });
    expect(table).toHaveAttribute('data-density', 'compact');
    expect(table).toHaveClass('min-w-full', 'text-xs');
    expect(table.parentElement).toHaveAttribute('data-data-table', 'ready');
    expect(table.parentElement).not.toHaveAttribute('data-surface-level');
    expect(screen.getByRole('rowheader', { name: /主数据源/ })).toHaveTextContent('TushareFetcher');
    expect(screen.getByRole('rowheader', { name: /备用数据源/ })).toHaveTextContent('AkshareFetcher');
    expect(screen.getByText('320 ms')).toBeInTheDocument();
    expect(screen.getByText('39')).toBeInTheDocument();
  });

  it('renders ContextPack quality metadata as structured details instead of raw JSON', () => {
    const node: RunFlowNode = {
      id: 'context_pack',
      lane: 'analysis',
      kind: 'analysis',
      label: 'ContextPack',
      status: 'degraded',
      metadata: {
        topologyGroup: 'context_pack',
        packVersion: '1.0',
        counts: {
          available: 4,
          missing: 1,
          partial: 1,
          fallback: 0,
        },
        dataQuality: {
          overallScore: 91,
          level: 'good',
          blockScores: {
            quote: 100,
            dailyBars: 100,
            technical: 100,
            news: 35,
          },
        },
        context_status_counts: {
          success: 4,
          degraded: 1,
          skipped: 1,
        },
      },
    };

    render(<RunFlowNodeDetails node={node} />);

    expect(screen.getByText('上下文质量')).toBeInTheDocument();
    expect(screen.getByText('综合评分')).toBeInTheDocument();
    expect(screen.getByText('91')).toBeInTheDocument();
    expect(screen.getByText('数据块评分')).toBeInTheDocument();
    expect(screen.getByText('news')).toBeInTheDocument();
    expect(screen.getByText('35')).toBeInTheDocument();
    expect(screen.getByText('版本')).toBeInTheDocument();
    expect(screen.getByText('1.0')).toBeInTheDocument();
    expect(screen.queryByText('提供方')).not.toBeInTheDocument();
    expect(screen.queryByText('耗时')).not.toBeInTheDocument();
    expect(screen.queryByText('尝试次数')).not.toBeInTheDocument();
    expect(screen.queryByText('记录数')).not.toBeInTheDocument();
    expect(screen.queryByText('counts')).not.toBeInTheDocument();
    expect(screen.queryByText('dataQuality')).not.toBeInTheDocument();
    expect(screen.queryByText('context_status_counts')).not.toBeInTheDocument();
    expect(screen.queryByText(/overallScore/)).not.toBeInTheDocument();
  });

  it('keeps provider metrics visible for data source nodes', () => {
    const node: RunFlowNode = {
      id: 'topology_data_realtime_quote',
      lane: 'data_source',
      kind: 'data_source',
      label: '实时行情',
      provider: 'TushareFetcher -> AkshareFetcher',
      status: 'fallback',
      durationMs: 750,
      attempts: 2,
      recordCount: 39,
    };

    render(<RunFlowNodeDetails node={node} />);

    expect(screen.getByText('提供方')).toBeInTheDocument();
    expect(screen.getByText('TushareFetcher -> AkshareFetcher')).toBeInTheDocument();
    expect(screen.getByText('耗时')).toBeInTheDocument();
    expect(screen.getByText('750 ms')).toBeInTheDocument();
    expect(screen.getByText('尝试次数')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('记录数')).toBeInTheDocument();
    expect(screen.getByText('39')).toBeInTheDocument();
  });
});
