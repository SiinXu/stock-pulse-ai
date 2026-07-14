import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ConnectionServiceCards } from '../ConnectionServiceCards';
import type { ConnectionCard } from '../connectionModel';

const connections: ConnectionCard[] = [
  { name: 'deepseek', providerId: 'deepseek', providerLabel: 'DeepSeek 官方', protocol: 'deepseek', enabled: true, status: 'configured', modelCount: 2, models: ['a', 'b'], usedByTasks: ['报告', 'Vision'] },
  { name: 'proxy', providerId: 'proxy', providerLabel: '自定义兼容服务', protocol: 'openai', enabled: true, status: 'incomplete', modelCount: 0, models: [], usedByTasks: [] },
];

describe('ConnectionServiceCards', () => {
  it('renders one card per connection with provider, status, model count and usage', () => {
    render(<ConnectionServiceCards connections={connections} language="zh" onAddService={() => {}} />);
    expect(screen.getByTestId('model-access-card-deepseek')).toBeInTheDocument();
    expect(screen.getByText('DeepSeek 官方')).toBeInTheDocument();
    expect(screen.getByText('已配置')).toBeInTheDocument();
    expect(screen.getByText('未完成')).toBeInTheDocument();
    expect(screen.getByText('报告、Vision')).toBeInTheDocument();
  });

  it('shows an empty state and still offers "Add model service"', () => {
    const onAdd = vi.fn();
    render(<ConnectionServiceCards connections={[]} language="zh" onAddService={onAdd} />);
    expect(screen.getByText('尚未接入模型服务')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '添加模型服务' }));
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it('never uses "channel" wording in the user-facing labels', () => {
    const { container } = render(
      <ConnectionServiceCards connections={connections} language="en" onAddService={() => {}} />,
    );
    expect(container.textContent).toContain('Add model service');
    expect(container.textContent?.toLowerCase()).not.toContain('channel');
  });
});
