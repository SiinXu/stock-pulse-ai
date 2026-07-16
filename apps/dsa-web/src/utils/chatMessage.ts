import { getParsedApiError } from '../api/error';
import type { UiLanguage } from '../i18n/uiText';
import type { Message } from '../stores/agentChatStore';

/** Resolve persisted stable failures at render/export time so language switches stay live. */
export function getChatMessageDisplayContent(
  message: Message,
  language: UiLanguage,
): string {
  if (!message.error) {
    return message.content;
  }

  const localized = getParsedApiError({
    error: message.error,
    params: message.params ?? {},
    message: message.content,
  }, language);
  return `${localized.title}\n\n${localized.message}`;
}
