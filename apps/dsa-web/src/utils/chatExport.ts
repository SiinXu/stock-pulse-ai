import type { Message } from '../stores/agentChatStore';
import type { UiLanguage } from '../i18n/uiText';
import { createUiLanguageRecord } from '../i18n/createUiLanguageRecord';
import { getChatMessageDisplayContent } from './chatMessage';
import { formatUiDateTime } from './uiLocale';

const CHAT_EXPORT_TEXT = createUiLanguageRecord('utils.chatExport.CHAT_EXPORT_TEXT', {
  zh: { title: '问股会话', generated: '生成时间：{time}', user: '用户', filename: '问股会话' },
  en: { title: 'Ask Stock Session', generated: 'Generated: {time}', user: 'User', filename: 'ask_stock_session' },
});

/**
 * Format chat messages as Markdown for export.
 */
export function formatSessionAsMarkdown(messages: Message[], language: UiLanguage = 'zh'): string {
  const now = new Date();
  const timeStr = formatUiDateTime(now, language, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
  const text = CHAT_EXPORT_TEXT[language];

  const lines: string[] = [
    `# ${text.title}`,
    '',
    text.generated.replace('{time}', timeStr),
    '',
  ];

  for (const msg of messages) {
    const heading = msg.role === 'user' ? `## ${text.user}` : '## AI';
    if (msg.role === 'assistant' && msg.skillName) {
      lines.push(`${heading} (${msg.skillName})`);
    } else {
      lines.push(heading);
    }
    lines.push('');
    lines.push(getChatMessageDisplayContent(msg, language));
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * Trigger browser download of session as .md file.
 * Revokes object URL after download to prevent memory leak.
 */
export function downloadSession(messages: Message[], language: UiLanguage = 'zh'): void {
  const content = formatSessionAsMarkdown(messages, language);
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const now = new Date();
  const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
  const pad = (n: number) => n.toString().padStart(2, '0');
  const timeStr = pad(now.getHours()) + pad(now.getMinutes());
  const filename = `${CHAT_EXPORT_TEXT[language].filename}_${dateStr}_${timeStr}.md`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
