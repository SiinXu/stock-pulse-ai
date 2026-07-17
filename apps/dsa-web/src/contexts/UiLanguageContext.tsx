import type React from 'react';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { formatUiText, UI_TEXT, type UiLanguage, type UiTextKey, type UiTextParams } from '../i18n/uiText';
import { isUiLanguageTranslationsLoaded, loadUiLanguageTranslations } from '../i18n/translations';
import {
  applyUiLanguageToDocument,
  getRuntimeInitialLanguage,
  getUiLanguageStorage,
  persistUiLanguage,
  recoverFailedUiLanguageSwitch,
} from '../utils/uiLanguage';

type UiLanguageContextValue = {
  language: UiLanguage;
  setLanguage: (language: UiLanguage) => void;
  t: (key: UiTextKey, params?: UiTextParams) => string;
};

const fallbackContext: UiLanguageContextValue = {
  language: 'zh',
  setLanguage: () => undefined,
  t: (key, params) => formatUiText(UI_TEXT.zh[key], params),
};

const UiLanguageContext = createContext<UiLanguageContextValue | null>(null);

export const UiLanguageProvider: React.FC<{ children: React.ReactNode; initialLanguage?: UiLanguage }> = ({
  children,
  initialLanguage,
}) => {
  const [language, setLanguageState] = useState<UiLanguage>(() => initialLanguage ?? getRuntimeInitialLanguage());
  const languageRequestRef = useRef(0);

  const setLanguage = useCallback((nextLanguage: UiLanguage) => {
    const requestId = languageRequestRef.current + 1;
    languageRequestRef.current = requestId;
    const commit = () => {
      if (languageRequestRef.current !== requestId) return;
      setLanguageState(nextLanguage);
      persistUiLanguage(getUiLanguageStorage(), nextLanguage);
    };
    if (isUiLanguageTranslationsLoaded(nextLanguage)) {
      commit();
      return;
    }
    void loadUiLanguageTranslations(nextLanguage).then(commit).catch(() => {
      if (languageRequestRef.current !== requestId) return;
      recoverFailedUiLanguageSwitch(nextLanguage);
    });
  }, []);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      applyUiLanguageToDocument(language);
    }
  }, [language]);

  const value = useMemo<UiLanguageContextValue>(() => ({
    language,
    setLanguage,
    t: (key, params) => formatUiText(UI_TEXT[language][key], params),
  }), [language, setLanguage]);

  return (
    <UiLanguageContext.Provider value={value}>
      {children}
    </UiLanguageContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components -- useUiLanguage is a hook, co-located for context access
export function useUiLanguage(): UiLanguageContextValue {
  return useContext(UiLanguageContext) ?? fallbackContext;
}
