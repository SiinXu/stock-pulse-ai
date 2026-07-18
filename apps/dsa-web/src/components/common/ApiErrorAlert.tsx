import type React from 'react';
import { ChevronDown, RefreshCw, X } from 'lucide-react';
import { localizeParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

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
          <button
            type="button"
            aria-label={dismissLabel ?? t('common.close')}
            className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-lg border-0 bg-transparent p-0 text-[hsl(var(--color-danger-alert-text))] transition hover:bg-[hsl(var(--color-danger-alert-bg)/0.15)]"
            onClick={onDismiss}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
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
        <button
          type="button"
          className="mt-1 inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-lg border-0 bg-transparent px-2 text-xs font-medium text-[hsl(var(--color-danger-alert-text))] transition hover:bg-[hsl(var(--color-danger-alert-bg)/0.15)]"
          onClick={onAction}
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
};
