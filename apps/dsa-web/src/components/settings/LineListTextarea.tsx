// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useState } from 'react';

type LineListTextareaProps = Omit<
  React.TextareaHTMLAttributes<HTMLTextAreaElement>,
  'defaultValue' | 'onChange' | 'value'
> & {
  values: readonly string[] | undefined;
  onValuesChange: (values: string[]) => void;
};

function linesToList(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function listToLines(values: readonly string[] | undefined): string {
  return (values ?? []).join('\n');
}

function listsEqual(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length
    && left.every((value, index) => value === right[index]);
}

const LineListTextarea: React.FC<LineListTextareaProps> = ({
  values,
  onValuesChange,
  onBlur,
  ...props
}) => {
  const serializedValues = listToLines(values);
  const [draft, setDraft] = useState(serializedValues);
  const [previousSerializedValues, setPreviousSerializedValues] = useState(
    serializedValues,
  );
  if (serializedValues !== previousSerializedValues) {
    setPreviousSerializedValues(serializedValues);
    if (!listsEqual(linesToList(draft), linesToList(serializedValues))) {
      setDraft(serializedValues);
    }
  }

  return (
    <textarea
      {...props}
      value={draft}
      onChange={(event) => {
        const nextDraft = event.target.value;
        const nextValues = linesToList(nextDraft);
        setDraft(nextDraft);
        if (!listsEqual(nextValues, linesToList(serializedValues))) {
          onValuesChange(nextValues);
        }
      }}
      onBlur={(event) => {
        setDraft(listToLines(linesToList(event.target.value)));
        onBlur?.(event);
      }}
    />
  );
};

export default LineListTextarea;
