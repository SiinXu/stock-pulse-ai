import type { UiLanguage } from '../../i18n/uiText';
import { SCREENING_TEXT } from '../../locales/screening';

export type ScreeningText = (typeof SCREENING_TEXT)[UiLanguage];
