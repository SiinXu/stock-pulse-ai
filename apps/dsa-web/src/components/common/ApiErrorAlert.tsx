import type React from 'react';
import { ChevronDown, RefreshCw, X } from 'lucide-react';
import { localizeParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { Button } from './Button';
import { IconButton } from './IconButton';

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

  return (
    <div
      className={`rounded-lg border border-[hsl(var(--color-danger-alert-border)/0.3)] bg-[hsl(var(--color-danger-alert-bg)/0.1)] px-3 py-2.5 text-[hsl(var(--color-danger-alert-text))] ${className}`}
      role="alert"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold">{localizedError.title}</p>
          <p className="mt-1 text-xs opacity-90">{localizedError.message}</p>
        </div>
        {onDismiss ? (
          <IconButton
            aria-label={dismissLabel ?? t('common.close')}
            visualSize="sm"
            tone="danger"
            tooltip={false}
            className="text-[hsl(var(--color-danger-alert-text))]"
            visualClassName="group-hover:bg-[hsl(var(--color-danger-alert-bg)/0.15)]"
            onClick={onDismiss}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </IconButton>
        ) : null}
      </div>
      {showDetails ? (
        <details className="group mt-1">
          <summary className="flex min-h-11 w-fit cursor-pointer list-none items-center gap-1.5 rounded-lg px-1 text-xs text-[hsl(var(--color-danger-alert-text))] opacity-90 transition hover:opacity-100">
            <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" aria-hidden="true" />
            {t('common.details')}
          </summary>
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words border-l-2 border-[hsl(var(--color-danger-alert-border)/0.3)] py-1 pl-3 text-xs leading-5 text-[hsl(var(--color-danger-alert-text))] opacity-85">
            {localizedError.rawMessage}
          </pre>
        </details>
      ) : null}
      {actionLabel && onAction ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="mt-1 !min-h-11 !min-w-11 border-0 text-[hsl(var(--color-danger-alert-text))] hover:bg-[hsl(var(--color-danger-alert-bg)/0.15)] hover:text-[hsl(var(--color-danger-alert-text))]"
          onClick={onAction}
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
};
