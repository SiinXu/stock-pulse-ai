// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
export function createOperationId(scope: string): string {
  const normalizedScope = scope.replace(/[^a-zA-Z0-9_-]/g, '-');
  const randomUuid = globalThis.crypto?.randomUUID?.();
  if (randomUuid) {
    return `${normalizedScope}-${randomUuid}`;
  }

  const randomPart = Math.random().toString(36).slice(2);
  return `${normalizedScope}-${Date.now().toString(36)}-${randomPart}`;
}
