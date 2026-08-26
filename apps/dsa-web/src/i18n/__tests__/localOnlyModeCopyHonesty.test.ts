// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { describe, expect, it } from 'vitest';
import settingsHelpEn from '../../locales/settingsHelp.en';
import settingsHelpZh from '../../locales/settingsHelp.zh';
import { ADDITIONAL_UI_LANGUAGES } from '../uiLanguages';
import { en } from '../uiTextEn';
import { zh } from '../uiTextZh';
import {
  getLoadedUiLanguageTranslations,
  SOURCE_UI_TRANSLATIONS,
} from '../translations';

const HINT_KEY = 'i18n.uiText.UI_TEXT.settings.outboundActivityModeHint' as const;
const HELP_USAGE_KEY = 'locales.settingsHelp.SETTINGS_HELP_MAPS.settings.system.LOCAL_ONLY_MODE.usage' as const;

const AIR_GAP_OVERCLAIMS = [
  /only pure loopback egress is allowed/i,
  /仅回环地址可出站/,
  /僅回環位址可出站/,
  /nur reiner Loopback-Ausgangsverkehr erlaubt/i,
  /solo se permite salida loopback pura/i,
  /seul le trafic loopback pur est autorisé/i,
  /hanya egress loopback murni yang diizinkan/i,
  /純粋なループバック送信のみ許可/,
  /순수 루프백만 허용/,
  /hanya egress loopback tulen dibenarkan/i,
];

function assertNoAirGapOverclaim(label: string, value: string): void {
  expect(value, label).toBeTruthy();
  for (const pattern of AIR_GAP_OVERCLAIMS) {
    expect(value, `${label} still overclaims ${pattern}`).not.toMatch(pattern);
  }
}

function assertHonestHint(label: string, value: string): void {
  expect(value, label).toContain('{reason}');
  assertNoAirGapOverclaim(label, value);
}

describe('Local Only Mode copy honesty (Refs #218)', () => {
  it('keeps the Outbound Activity badge from claiming only loopback egress', () => {
    assertHonestHint('en source', en['settings.outboundActivityModeHint']);
    assertHonestHint('zh source', zh['settings.outboundActivityModeHint']);
    assertHonestHint('English inventory', SOURCE_UI_TRANSLATIONS[HINT_KEY]);

    expect(en['settings.outboundActivityModeHint']).toMatch(/policy-owned HTTP/i);
    expect(en['settings.outboundActivityModeHint']).toMatch(/not a sandbox/i);
    expect(zh['settings.outboundActivityModeHint']).toMatch(/策略管辖 HTTP/);
    expect(zh['settings.outboundActivityModeHint']).toMatch(/不是沙箱/);

    for (const locale of ADDITIONAL_UI_LANGUAGES) {
      const bundle = getLoadedUiLanguageTranslations(locale);
      expect(bundle, locale).toBeTruthy();
      assertHonestHint(locale, bundle![HINT_KEY]);
    }
  });

  it('keeps Settings field help from claiming an air-gap', () => {
    const englishUsage = settingsHelpEn['settings.system.LOCAL_ONLY_MODE'].usage ?? '';
    const chineseUsage = settingsHelpZh['settings.system.LOCAL_ONLY_MODE'].usage ?? '';
    assertNoAirGapOverclaim('en help usage', englishUsage);
    assertNoAirGapOverclaim('zh help usage', chineseUsage);
    expect(englishUsage).toMatch(/plugin_safe_\*/);
    expect(englishUsage).toMatch(/not a sandbox/i);
    expect(chineseUsage).toMatch(/plugin_safe_\*/);
    expect(chineseUsage).toMatch(/不是沙箱/);
    expect(SOURCE_UI_TRANSLATIONS[HELP_USAGE_KEY]).toBe(englishUsage);

    for (const locale of ADDITIONAL_UI_LANGUAGES) {
      const bundle = getLoadedUiLanguageTranslations(locale);
      assertNoAirGapOverclaim(`${locale} help usage`, bundle![HELP_USAGE_KEY]);
    }
  });
});
