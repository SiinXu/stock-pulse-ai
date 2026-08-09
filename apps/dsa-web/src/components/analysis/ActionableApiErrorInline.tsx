// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { localizeParsedApiError, type ParsedApiError } from '../../api/error';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey, UiTextParams } from '../../i18n/uiText';
import { APP_ROUTE_PATHS } from '../../routing/routes';
import {
  alignParsedApiErrorWithMapping,
  isUiTextActionableKey,
  mapApiErrorToActionable,
  toUiTextKey,
  type ActionableErrorClass,
} from '../../utils/apiReasonMapper';
import { Button, InlineAlert, type InlineAlertVariant } from '../common';

export interface ActionableApiErrorAction {
  label: string;
  onClick?: () => void;
  target?: string;
  reload?: boolean;
  disabled?: boolean;
  isLoading?: boolean;
}

export interface ActionableApiErrorInlineProps {
  error: ParsedApiError;
  onDismiss?: () => void;
  /** Operation-owned actions. The renderer never infers retry safety. */
  actions?: readonly ActionableApiErrorAction[];
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

const SAFE_DIAGNOSTIC_TOKEN = /^[A-Za-z0-9._:/-]{1,160}$/;
const SENSITIVE_DIAGNOSTIC_TOKEN = /^(?:sk-|bearer|basic|api[_-]?key|access[_-]?token|secret)/i;

function formatTechnicalPart(label: string, value: unknown): string | null {
  if (typeof value !== 'string' && typeof value !== 'number') return null;
  const token = String(value).trim();
  if (!token) return null;
  const safe = SAFE_DIAGNOSTIC_TOKEN.test(token)
    && !SENSITIVE_DIAGNOSTIC_TOKEN.test(token);
  return `${label}: ${safe ? token : '[redacted]'}`;
}

/**
 * Form-primary, toast-free rendering of a mapped API error for analysis launch paths.
 * Technical code/reason stay under a collapsed disclosure (#885 Phase 2).
 */
const ActionableApiErrorInline: React.FC<ActionableApiErrorInlineProps> = ({
  error,
  onDismiss,
  actions,
  titleOverride,
  messageOverride,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
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

  const runAction = (action: ActionableApiErrorAction) => {
    if (action.disabled || action.isLoading) return;
    if (action.onClick) {
      action.onClick();
      return;
    }
    if (action.reload) {
      if (typeof window !== 'undefined') window.location.reload();
      return;
    }
    if (action.target) {
      const target = action.target === APP_ROUTE_PATHS.login
        ? `${APP_ROUTE_PATHS.login}?${new URLSearchParams({
            redirect: `${location.pathname}${location.search}${location.hash}`,
          })}`
        : action.target;
      navigate(target);
    }
  };

  const action = actions?.length || onDismiss ? (
    <div className="flex flex-wrap items-center gap-2">
      {actions?.map((item, index) => (
        <Button
          key={`${item.label}-${index}`}
          type="button"
          variant="secondary"
          size="compact"
          onClick={() => runAction(item)}
          disabled={item.disabled || item.isLoading}
          isLoading={item.isLoading}
        >
          {item.label}
        </Button>
      ))}
      {onDismiss ? (
        <Button type="button" variant="ghost" size="compact" onClick={onDismiss}>
          {t('common.close')}
        </Button>
      ) : null}
    </div>
  ) : undefined;

  const technicalParts = [
    formatTechnicalPart('code', mapping.technicalCode),
    formatTechnicalPart('reason', mapping.technicalReason),
    formatTechnicalPart('trace', error.traceId),
    formatTechnicalPart('status', error.status),
  ].filter((part): part is string => Boolean(part));

  return (
    <InlineAlert
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
