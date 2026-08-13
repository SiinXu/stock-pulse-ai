import { useEffect, useState } from 'react';
import type { UiLanguage } from '../../i18n/uiText';
import {
  getCandidateDiscoveryText,
  loadCandidateDiscoveryText,
  SOURCE_CANDIDATE_DISCOVERY_TEXT,
  type CandidateDiscoveryText,
} from '../../locales/candidateDiscoveryText';

type LoadedText = {
  language: UiLanguage;
  text: CandidateDiscoveryText;
};

export function useCandidateDiscoveryText(language: UiLanguage): CandidateDiscoveryText {
  const synchronous = getCandidateDiscoveryText(language);
  const [loaded, setLoaded] = useState<LoadedText | null>(null);

  useEffect(() => {
    if (synchronous) return undefined;
    let active = true;
    void loadCandidateDiscoveryText(language).then((text) => {
      if (active) setLoaded({ language, text });
    });
    return () => {
      active = false;
    };
  }, [language, synchronous]);

  if (synchronous) return synchronous;
  if (loaded?.language === language) return loaded.text;
  return SOURCE_CANDIDATE_DISCOVERY_TEXT.en;
}
