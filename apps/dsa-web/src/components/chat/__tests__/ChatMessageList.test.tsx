import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_TEXT, type UiTextKey } from '../../../i18n/uiText';
import type { Message, ProgressStep } from '../../../stores/agentChatStore';
import { ChatMessageList, type ChatMessageListProps } from '../ChatMessageList';

const t = (key: UiTextKey, params: Record<string, string | number> = {}) => {
  let value = UI_TEXT.en[key];
  Object.entries(params).forEach(([name, replacement]) => {
    value = value.replace(`{${name}}`, String(replacement));
  });
  return value;
};

const defaultProps: ChatMessageListProps = {
  language: 'en',
  t,
  text: { copied: 'Copied', copy: 'Copy' },
  messages: [],
  loading: false,
  progressSteps: [],
  agentUnavailable: false,
  quickQuestions: [],
  onQuickQuestion: vi.fn(),
  quickQuestionsDisabled: false,
  expandedThinking: new Set(),
  onToggleThinking: vi.fn(),
  copiedMessages: new Set(),
  onCopyMessage: vi.fn(),
  onDownloadMessage: vi.fn(),
  messagesViewportRef: createRef<HTMLDivElement>(),
  messagesEndRef: createRef<HTMLDivElement>(),
  onScroll: vi.fn(),
};

function renderList(overrides: Partial<ChatMessageListProps> = {}) {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <ChatMessageList {...defaultProps} {...overrides} />
    </UiLanguageProvider>,
  );
}

describe('ChatMessageList trace presentation', () => {
  it('keeps the live trace expanded and marks the newest event', () => {
    const progressSteps: ProgressStep[] = [
      { type: 'thinking', message: 'Planning' },
      { type: 'tool_start', tool: 'search', display_name: 'Search' },
    ];

    const { container } = renderList({ loading: true, progressSteps });

    expect(screen.getByTestId('chat-live-progress')).toBeInTheDocument();
    expect(container.querySelector('[data-trace-mode="live"]')).toBeInTheDocument();
    expect(container.querySelectorAll('[data-trace-step]')).toHaveLength(progressSteps.length);
    expect(container.querySelector('[data-trace-step="tool_start"]')).toHaveAttribute(
      'data-current',
      'true',
    );
    expect(screen.getByRole('progressbar', { name: 'Search...' })).toBeInTheDocument();
  });

  it('keeps a successful completed trace collapsed until requested', () => {
    const message: Message = {
      id: 'assistant-success',
      role: 'assistant',
      content: 'Finished response.',
      thinkingSteps: [
        { type: 'thinking', message: 'Planning' },
        { type: 'tool_done', tool: 'lookup', success: true, duration: 0.4 },
      ],
    };

    const onToggleThinking = vi.fn();
    const { container, rerender } = renderList({ messages: [message], onToggleThinking });

    const toggle = screen.getByRole('button', { name: /Reasoning.*1 tool call/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(container.querySelector('[data-trace-step]')).not.toBeInTheDocument();

    fireEvent.click(toggle);
    expect(onToggleThinking).toHaveBeenCalledWith('assistant-success');

    rerender(
      <UiLanguageProvider initialLanguage="en">
        <ChatMessageList
          {...defaultProps}
          messages={[message]}
          expandedThinking={new Set(['assistant-success'])}
        />
      </UiLanguageProvider>,
    );
    expect(container.querySelectorAll('[data-trace-step]')).toHaveLength(2);
  });

  it('keeps a real failed tool row visible while the rest of history is collapsed', () => {
    const message: Message = {
      id: 'assistant-failure',
      role: 'assistant',
      content: 'The available evidence is incomplete.',
      thinkingSteps: [
        { type: 'thinking', message: 'Planning' },
        { type: 'tool_done', tool: 'lookup', success: false, duration: 0.4 },
      ],
    };

    const { container } = renderList({ messages: [message] });

    expect(screen.getByRole('button', { name: /Reasoning/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(container.querySelectorAll('[data-trace-step]')).toHaveLength(1);
    expect(container.querySelector('[data-trace-step="tool_done"]')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toHaveAttribute('data-trace-status', 'danger');
    expect(screen.queryByText('Planning')).not.toBeInTheDocument();
  });
});
