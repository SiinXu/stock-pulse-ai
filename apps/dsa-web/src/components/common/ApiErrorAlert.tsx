import type React from 'react';
import { useContext, useEffect, useRef } from 'react';
import { localizeParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { ToastProvider } from './ToastProvider';
import { ToastContext, useToast } from './toastContext';

interface ApiErrorAlertProps {
  error: ParsedApiError;
  className?: string;
  actionLabel?: string;
  onAction?: () => void;
  dismissLabel?: string;
  onDismiss?: () => void;
}

const ApiErrorToast: React.FC<ApiErrorAlertProps> = ({
  error,
  actionLabel,
  onAction,
  dismissLabel,
  onDismiss,
}) => {
  const { language, t } = useUiLanguage();
  const { showToast, dismissToast } = useToast();
  const localizedError = localizeParsedApiError(error, language);
  const onActionRef = useRef(onAction);
  const onDismissRef = useRef(onDismiss);
  const hasAction = Boolean(actionLabel && onAction);
  const hasDismiss = Boolean(onDismiss);

  useEffect(() => {
    onActionRef.current = onAction;
  }, [onAction]);

  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => {
    const toastId = showToast({
      title: localizedError.title,
      message: localizedError.message,
      tone: 'danger',
      durationMs: 0,
      closeLabel: dismissLabel ?? t('common.close'),
      action: hasAction ? {
        label: actionLabel as string,
        onClick: () => onActionRef.current?.(),
        dismissOnClick: false,
      } : undefined,
      onDismiss: hasDismiss ? () => onDismissRef.current?.() : undefined,
    });

    return () => dismissToast(toastId);
  }, [
    actionLabel,
    dismissLabel,
    dismissToast,
    hasAction,
    hasDismiss,
    localizedError.message,
    localizedError.title,
    showToast,
    t,
  ]);

  return null;
};

export const ApiErrorAlert: React.FC<ApiErrorAlertProps> = (props) => {
  const toastContext = useContext(ToastContext);
  return toastContext ? (
    <ApiErrorToast {...props} />
  ) : (
    <ToastProvider>
      <ApiErrorToast {...props} />
    </ToastProvider>
  );
};
