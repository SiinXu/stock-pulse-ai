import type { UiLanguage } from '../../i18n/uiText';
import type { CandidateDiscoveryText } from '../../locales/candidateDiscoveryText';
import { SCREENING_TEXT } from '../../locales/screening';

export type ScreeningText = (typeof SCREENING_TEXT)[UiLanguage];
export type DiscoveryScreeningText = ScreeningText & CandidateDiscoveryText;
