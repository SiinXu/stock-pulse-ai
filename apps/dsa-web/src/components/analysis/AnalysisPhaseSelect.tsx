// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useId } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { AnalysisPhase } from '../../types/analysis';
import { cn } from '../../utils/cn';
import { getAnalysisPhaseOptions } from '../../utils/marketPhase';
import { Select } from '../common';

export interface AnalysisPhaseSelectProps {
  value: AnalysisPhase;
  onChange: (value: AnalysisPhase) => void;
  label: string;
  hint?: string;
  id?: string;
  disabled?: boolean;
  className?: string;
}

export function AnalysisPhaseSelect({
  value,
  onChange,
  label,
  hint,
  id,
  disabled = false,
  className,
}: AnalysisPhaseSelectProps) {
  const generatedId = useId();
  const { language } = useUiLanguage();
  const controlId = id ?? generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;

  return (
    <div className={cn('w-full', className)}>
      <Select
        id={controlId}
        value={value}
        onChange={(nextValue) => onChange(nextValue as AnalysisPhase)}
        options={getAnalysisPhaseOptions(language)}
        label={label}
        ariaDescribedBy={hintId}
        disabled={disabled}
        className="w-full"
        triggerClassName="w-full"
      />
      {hint ? (
        <p id={hintId} className="mt-1.5 text-xs text-secondary-text">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
