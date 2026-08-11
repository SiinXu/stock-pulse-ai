import { useCallback, useEffect, useRef, useState } from 'react';

export type ChatSendToast = {
  type: 'success' | 'error';
  message: string;
};

export function useChatSendFeedback() {
  const [sendToast, setSendToast] = useState<ChatSendToast | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  const showSendFeedback = useCallback((nextToast: ChatSendToast, durationMs: number) => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    setSendToast(nextToast);
    timerRef.current = window.setTimeout(() => {
      setSendToast(null);
      timerRef.current = null;
    }, durationMs);
  }, []);
  const clearSendFeedback = useCallback(() => setSendToast(null), []);

  return { sendToast, showSendFeedback, clearSendFeedback };
}
