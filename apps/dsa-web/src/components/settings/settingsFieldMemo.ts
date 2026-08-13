import type React from 'react';
import type {
  ConfigValidationIssue,
  SystemConfigItem,
} from '../../types/systemConfig';

export interface SettingsFieldProps {
  item: SystemConfigItem;
  value: string;
  disabled?: boolean;
  onChange: (key: string, value: string) => void;
  issues?: ConfigValidationIssue[];
  /** Effective requirement from the field's schema contract. */
  requirement?: 'required' | 'optional' | 'inherited' | null;
  /** True when the field's enabledWhen conditions are not met (read-only). */
  dependencyLocked?: boolean;
  /** Fail-safe schema diagnostic that forces a field into read-only mode. */
  readOnlyDiagnostic?: string;
  /** Restricts multi-enum options to those passing the filter (already-selected values always stay visible). */
  enumOptionFilter?: (value: string) => boolean;
  /** Rendered instead of the multi-enum control when the filter leaves no option and nothing is selected. */
  enumEmptyState?: React.ReactNode;
}

export function areSettingsFieldPropsEqual(
  previous: SettingsFieldProps,
  next: SettingsFieldProps,
): boolean {
  if (previous.item.key !== next.item.key) return false;
  if (previous.item.value !== next.item.value) return false;
  if (previous.item.isMasked !== next.item.isMasked) return false;
  if (previous.item.rawValueExists !== next.item.rawValueExists) return false;
  if (previous.item.persistedValue !== next.item.persistedValue) return false;
  if (previous.item.schema !== next.item.schema) return false;
  if (previous.value !== next.value) return false;
  if (Boolean(previous.disabled) !== Boolean(next.disabled)) return false;
  if (previous.requirement !== next.requirement) return false;
  if (Boolean(previous.dependencyLocked) !== Boolean(next.dependencyLocked)) return false;
  if (previous.readOnlyDiagnostic !== next.readOnlyDiagnostic) return false;
  if (previous.onChange !== next.onChange) return false;
  if (previous.enumOptionFilter !== next.enumOptionFilter) return false;
  if (previous.enumEmptyState !== next.enumEmptyState) return false;

  const previousIssues = previous.issues ?? [];
  const nextIssues = next.issues ?? [];
  if (previousIssues.length !== nextIssues.length) return false;
  for (let index = 0; index < previousIssues.length; index += 1) {
    const left = previousIssues[index];
    const right = nextIssues[index];
    if (
      left.code !== right.code
      || left.key !== right.key
      || left.severity !== right.severity
      || left.message !== right.message
    ) {
      return false;
    }
  }
  return true;
}
