import type { Message } from '../stores/agentChatStore';
import type { UiLanguage } from '../i18n/uiText';
import { getChatMessageDisplayContent } from './chatMessage';
import { formatUiDateTime } from './uiLocale';

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

  const lines: string[] = [
    language === 'en' ? '# Ask Stock Session' : '# 问股会话',
    '',
    language === 'en' ? `Generated: ${timeStr}` : `生成时间: ${timeStr}`,
    '',
  ];

  for (const msg of messages) {
    const heading = msg.role === 'user' ? (language === 'en' ? '## User' : '## 用户') : '## AI';
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
  const filename = `${language === 'en' ? 'ask_stock_session' : '问股会话'}_${dateStr}_${timeStr}.md`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
