import type React from 'react';
import { localizeParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { Alert } from './Alert';
import { Button } from './Button';

interface ApiErrorAlertProps {
  error: ParsedApiError;
  className?: string;
  actionLabel?: string;
  onAction?: () => void;
  dismissLabel?: string;
  onDismiss?: () => void;
}

export const ApiErrorAlert: React.FC<ApiErrorAlertProps> = ({
  error,
  className = '',
  actionLabel,
  onAction,
  dismissLabel,
  onDismiss,
}) => {
  const { language, t } = useUiLanguage();
  const localizedError = localizeParsedApiError(error, language);
  const showDetails = localizedError.rawMessage.trim() && localizedError.rawMessage.trim() !== localizedError.message.trim();

  const action = actionLabel && onAction ? (
    <Button type="button" variant="danger-subtle" size="compact" onClick={onAction}>
      {actionLabel}
    </Button>
  ) : undefined;
  const content = (
    <>
      <p>{localizedError.message}</p>
      {showDetails ? (
        <details className="mt-3 rounded-lg border border-subtle bg-surface-2 px-3 py-2">
          <summary className="flex min-h-11 cursor-pointer items-center text-xs text-[hsl(var(--color-danger-alert-text))] opacity-90">{t('common.details')}</summary>
          <pre className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-[hsl(var(--color-danger-alert-text))] opacity-85">
            {localizedError.rawMessage}
          </pre>
        </details>
      ) : null}
    </>
  );
  const alertProps = {
    tone: 'danger',
    urgent: true,
    title: localizedError.title,
    className,
    action,
  } as const;

  return onDismiss ? (
    <Alert
      {...alertProps}
      dismissLabel={dismissLabel ?? t('common.close')}
      onDismiss={onDismiss}
    >
      {content}
    </Alert>
  ) : (
    <Alert {...alertProps}>
      {content}
    </Alert>
  );
};
