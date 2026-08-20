// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useEffect, useState } from 'react';
import type { InitialUiLanguageShell } from './prepareUiLanguage';
import type { UiLanguage } from './uiLanguages';

type InitialUiLanguageGateProps = {
  shell: InitialUiLanguageShell;
  catalog: Promise<UiLanguage>;
  onLanguage?: (language: UiLanguage) => void;
  children: (language: UiLanguage) => React.ReactNode;
};

export const LocaleNeutralShell: React.FC = () => (
  <div
    data-locale-neutral-shell=""
    aria-busy="true"
    className="min-h-dvh bg-base"
  />
);

export const InitialUiLanguageGate: React.FC<InitialUiLanguageGateProps> = ({
  shell,
  catalog,
  onLanguage,
  children,
}) => {
  const readyLanguage = shell.status === 'app-ready' ? shell.language : null;
  const [language, setLanguage] = useState<UiLanguage | null>(readyLanguage);

  useEffect(() => {
    if (readyLanguage) {
      onLanguage?.(readyLanguage);
      return;
    }
    let cancelled = false;
    void catalog.then((resolved) => {
      if (cancelled) return;
      onLanguage?.(resolved);
      setLanguage(resolved);
    });
    return () => {
      cancelled = true;
    };
  }, [catalog, onLanguage, readyLanguage]);

  if (language === null) {
    return <LocaleNeutralShell />;
  }
  return <>{children(language)}</>;
};
