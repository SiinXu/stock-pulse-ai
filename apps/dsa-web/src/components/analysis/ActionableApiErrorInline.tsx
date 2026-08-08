// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { localizeParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey, UiTextParams } from '../../i18n/uiText';
import {
  alignParsedApiErrorWithMapping,
  isUiTextActionableKey,
  mapApiErrorToActionable,
  toUiTextKey,
  type ActionableErrorClass,
  type ActionableErrorCta,
  type ActionableErrorMapping,
} from '../../utils/apiReasonMapper';
import { Button, InlineAlert, type InlineAlertVariant } from '../common';

export interface ActionableApiErrorInlineProps {
  error: ParsedApiError;
  className?: string;
  onDismiss?: () => void;
  /** Override default CTA handler (after mapping resolves). */
  onRetry?: () => void;
  /** Optional extra navigate target for busy/duplicate “view tasks”. */
  onViewTasks?: () => void;
  /** Prefer tasks CTA over generic retry when class is busy and handler is set. */
  preferTasksCta?: boolean;
  /** Optional title override (e.g. home.duplicateTask). */
  titleOverride?: string;
  /** Optional message override after localization. */
  messageOverride?: string;
}

const CLASS_VARIANT: Record<ActionableErrorClass, InlineAlertVariant> = {
  config_conflict: 'warning',
  busy: 'warning',
  llm_not_configured: 'danger',
  outbound_policy: 'danger',
  local_only_mode: 'warning',
  credential: 'danger',
  network: 'danger',
  capability: 'warning',
  hitl_pending: 'warning',
  rate_quota: 'warning',
  notification: 'warning',
  auth: 'danger',
  validation: 'danger',
  not_found: 'warning',
  generic: 'danger',
};

function ctaLabel(
  cta: ActionableErrorCta,
  mapping: ActionableErrorMapping,
  t: (key: UiTextKey, params?: UiTextParams) => string,
  preferTasksCta: boolean,
): string {
  if (preferTasksCta && mapping.class === 'busy') {
    return t('analysisWorkbench.tasks');
  }
  if (cta.kind === 'navigate') {
    if (cta.target?.startsWith('/settings') || mapping.class === 'llm_not_configured') {
      return t('home.goSettings');
    }
    if (cta.target?.startsWith('/login')) {
      return t('layout.nav.settings');
    }
    return t('common.details');
  }
  if (cta.kind === 'reload') {
    return t('routeError.reload');
  }
  return t('common.retry');
}

/**
 * Form-primary, toast-free rendering of a mapped API error for analysis launch paths.
 * Technical code/reason stay under a collapsed disclosure (#885 Phase 2).
 */
export const ActionableApiErrorInline: React.FC<ActionableApiErrorInlineProps> = ({
  error,
  className,
  onDismiss,
  onRetry,
  onViewTasks,
  preferTasksCta = false,
  titleOverride,
  messageOverride,
}) => {
  const navigate = useNavigate();
  const { language, t } = useUiLanguage();
  const [detailsOpen, setDetailsOpen] = useState(false);

  const mapping = useMemo(() => mapApiErrorToActionable(error), [error]);
  const { title, message } = useMemo(() => {
    if (isUiTextActionableKey(mapping.titleKey)) {
      const titleKey = toUiTextKey(mapping.titleKey) as UiTextKey | null;
      const messageKey = toUiTextKey(mapping.messageKey) as UiTextKey | null;
      const params: UiTextParams = {
        reason: mapping.technicalReason ?? mapping.technicalCode ?? '',
        ...(error.params as UiTextParams | undefined),
      };
      return {
        title: titleOverride
          ?? (titleKey ? t(titleKey, params) : error.title),
        message: messageOverride
          ?? (messageKey ? t(messageKey, params) : error.message),
      };
    }

    const aligned = alignParsedApiErrorWithMapping(error, mapping);
    const localized = localizeParsedApiError(aligned, language);
    return {
      title: titleOverride ?? localized.title,
      message: messageOverride ?? localized.message,
    };
  }, [error, language, mapping, messageOverride, t, titleOverride]);

  const handleCta = () => {
    const cta = mapping.cta;
    if (preferTasksCta && mapping.class === 'busy' && onViewTasks) {
      onViewTasks();
      return;
    }
    if (!cta) {
      onRetry?.();
      return;
    }
    if (cta.kind === 'retry') {
      onRetry?.();
      return;
    }
    if (cta.kind === 'reload') {
      if (typeof window !== 'undefined') {
        window.location.reload();
      }
      return;
    }
    if (cta.kind === 'navigate' && cta.target) {
      navigate(cta.target);
    }
  };

  const showPrimaryCta = Boolean(
    mapping.cta || onRetry || (preferTasksCta && mapping.class === 'busy' && onViewTasks),
  );

  const action = showPrimaryCta || onDismiss ? (
    <div className="flex flex-wrap items-center gap-2">
      {showPrimaryCta ? (
        <Button
          type="button"
          variant="secondary"
          size="compact"
          onClick={handleCta}
        >
          {mapping.cta
            ? ctaLabel(mapping.cta, mapping, t, preferTasksCta && Boolean(onViewTasks))
            : preferTasksCta && mapping.class === 'busy' && onViewTasks
              ? t('analysisWorkbench.tasks')
              : t('common.retry')}
        </Button>
      ) : null}
      {onDismiss ? (
        <Button type="button" variant="ghost" size="compact" onClick={onDismiss}>
          {t('common.close')}
        </Button>
      ) : null}
    </div>
  ) : undefined;

  const technicalParts = [
    mapping.technicalCode ? `code: ${mapping.technicalCode}` : null,
    mapping.technicalReason ? `reason: ${mapping.technicalReason}` : null,
    error.traceId ? `trace: ${error.traceId}` : null,
    error.status ? `status: ${error.status}` : null,
  ].filter((part): part is string => Boolean(part));

  return (
    <InlineAlert
      className={className}
      variant={CLASS_VARIANT[mapping.class]}
      title={title}
      action={action}
      data-testid="actionable-api-error-inline"
      data-error-class={mapping.class}
      message={(
        <div className="space-y-2">
          <p>{message}</p>
          {technicalParts.length > 0 ? (
            <div>
              <button
                type="button"
                className="text-xs font-medium underline-offset-2 hover:underline"
                aria-expanded={detailsOpen}
                onClick={() => setDetailsOpen((open) => !open)}
              >
                {t('common.details')}
              </button>
              {detailsOpen ? (
                <pre
                  data-testid="actionable-error-technical"
                  className="mt-1 overflow-x-auto rounded-md border border-border/60 bg-background/40 px-2 py-1.5 font-mono text-xs text-secondary-text"
                >
                  {technicalParts.join('\n')}
                </pre>
              ) : null}
            </div>
          ) : null}
        </div>
      )}
    />
  );
};

export default ActionableApiErrorInline;
