// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useLayoutEffect, useMemo, useRef } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { parseDeepLink } from '../../utils/deepLink';
import { useToast } from '../common/toastContext';

type DeepLinkGuardProps = {
  children: React.ReactNode;
};

export const DeepLinkGuard: React.FC<DeepLinkGuardProps> = ({ children }) => {
  const location = useLocation();
  const { t } = useUiLanguage();
  const { showToast } = useToast();
  const lastWarningRef = useRef<string | null>(null);
  const currentHref = `${location.pathname}${location.search}${location.hash}`;
  const parsed = useMemo(
    () => parseDeepLink(currentHref, window.location.origin),
    [currentHref],
  );
  const normalizationRequired = parsed.normalizedHref !== currentHref;
  const reportableIssues = parsed.issues.filter((issue) => issue.code !== 'unsupported_route');
  const warningKey = reportableIssues.length > 0
    ? `${currentHref}:${reportableIssues.map(({ code, parameter }) => `${code}:${parameter ?? ''}`).join(',')}`
    : null;

  useLayoutEffect(() => {
    if (!warningKey) {
      lastWarningRef.current = null;
      return;
    }
    if (warningKey && lastWarningRef.current !== warningKey) {
      lastWarningRef.current = warningKey;
      showToast({
        title: t('deepLink.invalidTitle'),
        message: t('deepLink.invalidMessage'),
        tone: 'warning',
      });
    }
  }, [
    showToast,
    t,
    warningKey,
  ]);

  return normalizationRequired
    ? <Navigate to={parsed.normalizedHref} replace state={location.state} />
    : children;
};
