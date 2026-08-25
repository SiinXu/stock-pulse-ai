// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useEffect, useState } from 'react';
import { ApiErrorAlert, ToastViewport } from '../../common';
import {
  SettingsAlert,
  SettingsErrorSummary,
  type ErrorSummaryEntry,
} from '..';
import { SETTINGS_SECTION_IDS } from '../../../routing/routes';
import type { ParsedApiError } from '../../../api/error';
import type { UiLanguage, UiTextKey } from '../../../i18n/uiText';
import { SETTINGS_PAGE_TEXT } from '../../../locales/settingsPage';

type SettingsToast =
  | { type: 'success'; message: string }
  | { type: 'error'; error: ParsedApiError }
  | null;

type SettingsPageToastsProps = {
  showErrorSummary: boolean;
  hasValidationSummary: boolean;
  saveError: ParsedApiError | null;
  loadError: ParsedApiError | null;
  activeSection: string;
  toast: SettingsToast;
  errorSummaryEntries: ErrorSummaryEntry[];
  jumpToErrorField: (entry: ErrorSummaryEntry) => void;
  uiLanguage: UiLanguage;
  errorSummaryFingerprint: string;
  setDismissedErrorSummaryFingerprint: (fingerprint: string) => void;
  retryAction: 'load' | 'save' | null;
  lastSaveGroupRef: React.MutableRefObject<string | null>;
  retryAutosaveGroup: (group: string) => void;
  retry: () => void;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
  clearToast: () => void;
};

const SettingsPageToasts: React.FC<SettingsPageToastsProps> = (props) => {
  const settingsText = SETTINGS_PAGE_TEXT[props.uiLanguage];
  const [isToastPaused, setIsToastPaused] = useState(false);

  useEffect(() => {
    if (!props.toast || props.toast.type !== 'success' || isToastPaused) {
      return;
    }

    const timer = window.setTimeout(() => {
      props.clearToast();
    }, 3200);

    return () => {
      window.clearTimeout(timer);
    };
  }, [props.clearToast, isToastPaused, props.toast]);

  if (!(
    props.showErrorSummary
    || (!props.hasValidationSummary && (
      props.saveError
      || (props.loadError && props.activeSection !== SETTINGS_SECTION_IDS.usage)
      || props.toast
    ))
  )) {
    return null;
  }

  return (
    <ToastViewport>
      <div
        className="pointer-events-auto max-h-[calc(100dvh-2rem)] overflow-y-auto"
        onMouseEnter={() => setIsToastPaused(true)}
        onMouseLeave={() => setIsToastPaused(false)}
        onFocusCapture={() => setIsToastPaused(true)}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            setIsToastPaused(false);
          }
        }}
      >
        {props.showErrorSummary ? (
          <SettingsErrorSummary
            entries={props.errorSummaryEntries}
            onJump={props.jumpToErrorField}
            language={props.uiLanguage}
            dismissLabel={props.t('common.close')}
            onDismiss={() => props.setDismissedErrorSummaryFingerprint(props.errorSummaryFingerprint)}
          />
        ) : !props.hasValidationSummary && props.saveError ? (
          <ApiErrorAlert
            error={props.saveError}
            actionLabel={props.retryAction === 'save' && props.lastSaveGroupRef.current ? settingsText.autosaveRetry : undefined}
            onAction={props.retryAction === 'save' && props.lastSaveGroupRef.current
              ? () => props.retryAutosaveGroup(props.lastSaveGroupRef.current!)
              : undefined}
          />
        ) : props.loadError && props.activeSection !== SETTINGS_SECTION_IDS.usage ? (
          <ApiErrorAlert
            error={props.loadError}
            actionLabel={props.retryAction === 'load' ? props.t('common.retry') : props.t('settings.reload')}
            onAction={() => void props.retry()}
          />
        ) : props.toast?.type === 'success' ? (
          <SettingsAlert
            title={props.t('settings.actionSuccess')}
            message={props.toast.message}
            variant="success"
          />
        ) : props.toast ? (
          <ApiErrorAlert error={props.toast.error} />
        ) : null}
      </div>
    </ToastViewport>
  );
};

export default SettingsPageToasts;
