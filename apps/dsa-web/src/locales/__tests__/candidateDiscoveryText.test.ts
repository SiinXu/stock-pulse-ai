import { describe, expect, it } from 'vitest';
import { ADDITIONAL_UI_LANGUAGES } from '../../i18n/uiLanguages';
import {
  loadCandidateDiscoveryText,
  SOURCE_CANDIDATE_DISCOVERY_TEXT,
} from '../candidateDiscoveryText';

const SOURCE_KEYS = Object.keys(SOURCE_CANDIDATE_DISCOVERY_TEXT.en).sort();

describe('candidate discovery text inventory', () => {
  it('keeps the Chinese and English source inventories in parity', () => {
    expect(Object.keys(SOURCE_CANDIDATE_DISCOVERY_TEXT.zh).sort()).toEqual(SOURCE_KEYS);
  });

  it.each(ADDITIONAL_UI_LANGUAGES)(
    'lazy-loads complete, non-English candidate discovery copy for %s',
    async (language) => {
      const translated = await loadCandidateDiscoveryText(language);
      expect(Object.keys(translated).sort()).toEqual(SOURCE_KEYS);
      expect(Object.values(translated).every((value) => value.trim().length > 0)).toBe(true);
      expect(translated).not.toEqual(SOURCE_CANDIDATE_DISCOVERY_TEXT.en);
    },
  );
});
