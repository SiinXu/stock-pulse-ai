// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createUiLanguageRecord } from '../../i18n/createUiLanguageRecord';
import type { UiLanguage } from '../../i18n/uiText';

export const PROVIDER_QUICK_LINKS_TEXT: Record<UiLanguage, { opensInNewTab: string }> = createUiLanguageRecord("components.settings.providerQuickLinksText.PROVIDER_QUICK_LINKS_TEXT", {
  zh: { opensInNewTab: '将在新标签页打开' },
  en: { opensInNewTab: 'opens in a new tab' },
});
