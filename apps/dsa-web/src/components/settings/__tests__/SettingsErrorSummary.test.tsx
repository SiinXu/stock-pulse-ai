import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SettingsErrorSummary, type ErrorSummaryEntry } from '../SettingsErrorSummary';

const entries: ErrorSummaryEntry[] = [
  { key: 'WECHAT_WEBHOOK_URL', label: '企业微信 Webhook', message: '地址格式不正确', section: 'notifications', view: 'channels' },
  { key: 'LITELLM_MODEL', label: '主模型', message: '缺少 provider 前缀', section: 'ai_models', view: 'task_routing' },
];

describe('SettingsErrorSummary', () => {
  it('renders nothing when there are no errors', () => {
    const { container } = render(<SettingsErrorSummary entries={[]} onJump={() => {}} language="zh" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('summarizes every errored field with its message', () => {
    render(<SettingsErrorSummary entries={entries} onJump={() => {}} language="zh" />);
    expect(screen.getByText('有 2 项配置需要修正')).toBeInTheDocument();
    expect(screen.getByText('企业微信 Webhook')).toBeInTheDocument();
    expect(screen.getByText('地址格式不正确')).toBeInTheDocument();
    expect(screen.getByText('主模型')).toBeInTheDocument();
  });

  it('invokes onJump with the full entry so the page can route + focus', () => {
    const onJump = vi.fn();
    render(<SettingsErrorSummary entries={entries} onJump={onJump} language="zh" />);
    fireEvent.click(screen.getByRole('button', { name: '前往修正: 主模型' }));
    expect(onJump).toHaveBeenCalledWith(entries[1]);
  });

  it('uses singular English copy for a single error', () => {
    render(<SettingsErrorSummary entries={[entries[0]]} onJump={() => {}} language="en" />);
    expect(screen.getByText('1 setting needs attention')).toBeInTheDocument();
  });
});
