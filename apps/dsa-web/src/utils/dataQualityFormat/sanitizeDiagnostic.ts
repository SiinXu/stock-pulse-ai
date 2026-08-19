// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

/** Stable backend identity: snake_case / kebab-case / underscored channel ids. */
export const STABLE_MACHINE_CODE = /^[a-z_][a-z0-9_-]{0,63}$/i;

export function isStableMachineCode(value: string | null | undefined): boolean {
  return STABLE_MACHINE_CODE.test(String(value ?? '').trim());
}

export function sanitizeMachineCode(value: string | null | undefined): string {
  const raw = String(value ?? '').trim();
  if (!raw) return 'unknown';
  return STABLE_MACHINE_CODE.test(raw) ? raw : 'unknown';
}

export function sanitizeDiagnosticText(value: string, maxLength = 280): string {
  const withoutMarkup = value.replace(/<[^>]*>/g, '');
  const withoutControls = Array.from(withoutMarkup)
    .filter((character) => {
      const code = character.codePointAt(0) ?? 0;
      return code > 31 && code !== 127;
    })
    .join('');
  return withoutControls.replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

export function formatEmptyDisplay(): string {
  return '—';
}
