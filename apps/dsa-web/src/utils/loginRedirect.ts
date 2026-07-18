// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
const REDIRECT_VALIDATION_ORIGIN = 'https://login-redirect.invalid';

function hasUnsafeRedirectCharacter(value: string): boolean {
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? 0;
    if (codePoint <= 0x20 || codePoint === 0x7f || character === '\\') {
      return true;
    }
  }
  return false;
}

// Only same-origin absolute paths are allowed; anything else (external URLs,
// protocol-relative hosts, control-character normalization, or backslash
// tricks) falls back to the home page.
export function resolveLoginRedirect(search: string | URLSearchParams): string {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search;
  const raw = params.get('redirect') ?? '';

  if (!raw.startsWith('/') || hasUnsafeRedirectCharacter(raw)) {
    return '/';
  }

  try {
    const validationOrigin = new URL(REDIRECT_VALIDATION_ORIGIN);
    const destination = new URL(raw, validationOrigin);
    if (destination.origin !== validationOrigin.origin) {
      return '/';
    }

    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return '/';
  }
}
