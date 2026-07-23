import { beforeEach, describe, expect, it } from 'vitest';
import {
  dismissOnboarding,
  EXPERIENCE_MODE_STORAGE_KEY,
  ONBOARDING_DISMISSED_STORAGE_KEY,
  readExperienceMode,
  readOnboardingDismissed,
  writeExperienceMode,
} from '../onboardingPreferences';

describe('onboardingPreferences', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('persists only supported experience modes', () => {
    expect(readExperienceMode()).toBeNull();
    writeExperienceMode('beginner');
    expect(readExperienceMode()).toBe('beginner');
    writeExperienceMode('professional');
    expect(readExperienceMode()).toBe('professional');

    window.localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, 'unexpected');
    expect(readExperienceMode()).toBeNull();
  });

  it('persists onboarding dismissal separately from experience mode', () => {
    writeExperienceMode('beginner');
    expect(readOnboardingDismissed()).toBe(false);
    dismissOnboarding();

    expect(readOnboardingDismissed()).toBe(true);
    expect(window.localStorage.getItem(ONBOARDING_DISMISSED_STORAGE_KEY)).toBe('true');
    expect(readExperienceMode()).toBe('beginner');
  });
});
