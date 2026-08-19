// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { sanitizeDiagnosticCode } from '../approvalFormat';

/** Stable backend identity: snake_case / kebab-case / underscored channel ids. */
export const STABLE_MACHINE_CODE = /^[a-z_][a-z0-9_-]{0,63}$/i;

export function isStableMachineCode(value: string | null | undefined): boolean {
  return STABLE_MACHINE_CODE.test(String(value ?? '').trim());
}

/**
 * Keep a visible sanitized identity for unknown codes.
 * Stable machine tokens stay as-is. Prose/HTML is compacted through the T06
 * diagnostic sanitizer instead of collapsing every non-token to "unknown".
 */
export function sanitizeMachineCode(value: string | null | undefined): string {
  const raw = String(value ?? '').trim();
  if (!raw) return '—';
  if (STABLE_MACHINE_CODE.test(raw)) return raw;
  const withoutMarkup = sanitizeDiagnosticText(raw, 64);
  if (STABLE_MACHINE_CODE.test(withoutMarkup)) return withoutMarkup;
  const compact = withoutMarkup
    .replace(/[^a-zA-Z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64);
  return compact || sanitizeDiagnosticCode(raw);
}

export function sanitizeDiagnosticText(value: string, maxLength = 280): string {
  const withoutMarkup = value.replace(/<[^>]*>/g, '');
  const withoutControls = Array.from(withoutMarkup)
    .filter((character) => {
      const code = character.codePointAt(0) ?? 0;
      return code > 31 && code !== 127
        && !(code >= 0x202a && code <= 0x202e)
        && !(code >= 0x2066 && code <= 0x2069);
    })
    .join('');
  return withoutControls.replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

export function sanitizeUserAuthoredText(value: string, maxLength = 80): string {
  return sanitizeDiagnosticText(value, maxLength);
}

export function formatEmptyDisplay(): string {
  return '—';
}
