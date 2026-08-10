import { InlineAlert } from '../common';
import type { ChatSendToast } from './useChatSendFeedback';

export function ChatSendFeedbackAlert({
  toast,
  successTitle,
  failureTitle,
}: {
  toast: ChatSendToast | null;
  successTitle: string;
  failureTitle: string;
}) {
  if (!toast) return null;
  return (
    <InlineAlert
      variant={toast.type === 'success' ? 'success' : 'danger'}
      size="compact"
      title={toast.type === 'success' ? successTitle : failureTitle}
      message={toast.message}
      className="max-w-md"
    />
  );
}
