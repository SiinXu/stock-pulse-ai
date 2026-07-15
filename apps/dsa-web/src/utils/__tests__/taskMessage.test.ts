import { describe, expect, it } from 'vitest';
import { formatTaskMessage } from '../taskMessage';

describe('formatTaskMessage', () => {
  it('renders the same task payload in the current UI language', () => {
    const task = {
      status: 'processing',
      message: '服务端 legacy 文案',
      messageCode: 'task.analysis.news',
      messageParams: { subject: 'AAPL' },
    };

    expect(formatTaskMessage(task, 'zh')).toBe('AAPL：正在检索新闻与舆情');
    expect(formatTaskMessage(task, 'en')).toBe('Searching news and sentiment for AAPL');
  });

  it('does not expose unknown legacy task copy as primary UI text', () => {
    const task = { status: 'processing', message: 'raw provider diagnostic' };

    expect(formatTaskMessage(task, 'zh')).toBe('任务执行中');
    expect(formatTaskMessage(task, 'en')).toBe('Task in progress');
  });
});
