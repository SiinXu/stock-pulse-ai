// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import {
  localizeParsedApiError,
  resolveErrorRemediation,
  type ParsedApiError,
} from '../../api/error';
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
  const remediation = resolveErrorRemediation(localizedError, language);
  const showDetails = localizedError.rawMessage.trim() && localizedError.rawMessage.trim() !== localizedError.message.trim();

  const resolvedActionLabel = actionLabel ?? remediation?.actionLabel;
  const remediationHref = !onAction ? remediation?.href : undefined;
  const resolvedOnAction = onAction ?? (
    remediationHref
      ? () => {
          // Avoid useNavigate so ApiErrorAlert remains usable outside a Router
          // (unit tests, isolated panels). Deep links still resolve correctly.
          window.location.assign(remediationHref);
        }
      : undefined
  );

  const action = resolvedActionLabel && resolvedOnAction ? (
    <Button type="button" variant="danger-subtle" size="compact" onClick={resolvedOnAction}>
      {resolvedActionLabel}
    </Button>
  ) : undefined;
  const content = (
    <>
      <p>{localizedError.message}</p>
      {remediation?.hint ? (
        <p className="mt-2 text-sm leading-5 text-[hsl(var(--color-danger-alert-text))] opacity-90">
          {remediation.hint}
        </p>
      ) : null}
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
  return onDismiss ? (
    <Alert
      tone="danger"
      urgent
      title={localizedError.title}
      className={className}
      action={action}
      dismissLabel={dismissLabel ?? t('common.close')}
      onDismiss={onDismiss}
    >
      {content}
    </Alert>
  ) : (
    <Alert
      tone="danger"
      urgent
      title={localizedError.title}
      className={className}
      action={action}
    >
      {content}
    </Alert>
  );
};
