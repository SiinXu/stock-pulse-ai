// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Shrink-only ratchet: non-English UI bundles must not introduce NEW keys whose
 * value is byte-identical to English. Existing identical pairs are frozen in
 * `identicalToEnglish.baseline.json` and may only shrink.
 *
 * Escape hatch (false-positive / intentional English): add the `locale\tkey`
 * pair to the baseline with a PR note justifying why the English value is the
 * correct product copy for that locale (proper nouns, codes, brand strings).
 */
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import fs from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { fileURLToPath } from 'node:url';
import { beforeAll, describe, expect, it } from 'vitest';
import { ADDITIONAL_UI_LANGUAGES } from '../uiLanguages';
import {
  getLoadedUiLanguageTranslations,
  loadAllUiLanguageTranslations,
  SOURCE_UI_TRANSLATIONS,
  type AdditionalUiLanguage,
} from '../translations';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASELINE_PATH = path.join(__dirname, 'identicalToEnglish.baseline.json');

type IdenticalPair = `${AdditionalUiLanguage}\t${string}`;

function pairKey(locale: AdditionalUiLanguage, key: string): IdenticalPair {
  return `${locale}\t${key}`;
}

function collectIdenticalPairs(): IdenticalPair[] {
  const pairs: IdenticalPair[] = [];
  for (const locale of ADDITIONAL_UI_LANGUAGES) {
    const bundle = getLoadedUiLanguageTranslations(locale);
    if (!bundle) {
      throw new Error(`UI translation bundle not loaded: ${locale}`);
    }
    for (const [key, english] of Object.entries(SOURCE_UI_TRANSLATIONS)) {
      const localized = bundle[key as keyof typeof bundle];
      if (typeof localized !== 'string' || typeof english !== 'string') {
        continue;
      }
      if (localized === english) {
        pairs.push(pairKey(locale, key));
      }
    }
  }
  pairs.sort();
  return pairs;
}

function loadBaseline(): IdenticalPair[] {
  const raw = fs.readFileSync(BASELINE_PATH, 'utf8');
  const parsed = JSON.parse(raw) as { pairs: string[]; count: number };
  if (!Array.isArray(parsed.pairs)) {
    throw new Error('identicalToEnglish.baseline.json must contain a pairs array');
  }
  return [...parsed.pairs].sort() as IdenticalPair[];
}

describe('identical-to-English ratchet', () => {
  beforeAll(async () => {
    await loadAllUiLanguageTranslations();
  });

  it('only allows known identical-to-English pairs and shrinks when pairs are fixed', () => {
    const current = collectIdenticalPairs();
    const baseline = loadBaseline();
    const baselineSet = new Set(baseline);
    const currentSet = new Set(current);

    const unexpected = current.filter((pair) => !baselineSet.has(pair));
    const stale = baseline.filter((pair) => !currentSet.has(pair));

    expect(
      unexpected,
      [
        'New keys are byte-identical to English in a non-English bundle.',
        'Translate them, or add to identicalToEnglish.baseline.json with PR justification.',
        ...unexpected.slice(0, 20),
        unexpected.length > 20 ? `…and ${unexpected.length - 20} more` : '',
      ].filter(Boolean).join('\n'),
    ).toEqual([]);

    expect(
      stale,
      [
        'Baseline pairs are no longer identical to English (shrink-only).',
        'Remove them from identicalToEnglish.baseline.json.',
        ...stale.slice(0, 20),
        stale.length > 20 ? `…and ${stale.length - 20} more` : '',
      ].filter(Boolean).join('\n'),
    ).toEqual([]);

    expect(current.length).toBe(baseline.length);
    expect(current.length).toBeLessThanOrEqual(baseline.length);
  });

  it('keeps the baseline count metadata honest', () => {
    const raw = JSON.parse(fs.readFileSync(BASELINE_PATH, 'utf8')) as {
      pairs: string[];
      count: number;
    };
    expect(raw.count).toBe(raw.pairs.length);
    expect(raw.pairs).toEqual([...raw.pairs].sort());
  });
});
