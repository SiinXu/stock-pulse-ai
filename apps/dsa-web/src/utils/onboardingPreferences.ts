export type ExperienceMode = 'beginner' | 'professional';

export const EXPERIENCE_MODE_STORAGE_KEY = 'stockpulse.experienceMode.v1';
export const ONBOARDING_DISMISSED_STORAGE_KEY = 'stockpulse.onboarding.dismissed.v1';

function getLocalStorage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readExperienceMode(storage: Storage | null = getLocalStorage()): ExperienceMode | null {
  try {
    const value = storage?.getItem(EXPERIENCE_MODE_STORAGE_KEY);
    return value === 'beginner' || value === 'professional' ? value : null;
  } catch {
    return null;
  }
}

export function writeExperienceMode(
  mode: ExperienceMode,
  storage: Storage | null = getLocalStorage(),
): void {
  try {
    storage?.setItem(EXPERIENCE_MODE_STORAGE_KEY, mode);
  } catch {
    // The preference remains in memory when durable browser storage is unavailable.
  }
}

export function readOnboardingDismissed(storage: Storage | null = getLocalStorage()): boolean {
  try {
    return storage?.getItem(ONBOARDING_DISMISSED_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function dismissOnboarding(storage: Storage | null = getLocalStorage()): void {
  try {
    storage?.setItem(ONBOARDING_DISMISSED_STORAGE_KEY, 'true');
  } catch {
    // Dismissal remains in memory when durable browser storage is unavailable.
  }
}
