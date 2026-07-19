import type React from 'react';

export function getFieldDescriptionIds(
  controlId: string,
  hint: React.ReactNode,
  error: React.ReactNode,
  ariaDescribedBy?: string,
) {
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [ariaDescribedBy, errorId ?? hintId].filter(Boolean).join(' ') || undefined;

  return { hintId, errorId, describedBy };
}
