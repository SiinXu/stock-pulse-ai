// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type { ReportVersionSeverity } from '../../api/reportVersionCompare';

/**
 * Visual weight for field changes.
 * Major (buy→sell style reversals) uses danger emphasis.
 * Moderate uses warning; minor uses subtle info; none is neutral.
 */
export function severityRowClass(severity: ReportVersionSeverity, changed: boolean): string {
  if (!changed || severity === 'none') {
    return 'border-border/40 bg-elevated/40';
  }
  switch (severity) {
    case 'major':
      return 'border-danger/40 bg-danger/10 ring-1 ring-danger/25';
    case 'moderate':
      return 'border-warning/35 bg-warning/10';
    case 'minor':
      return 'border-primary/25 bg-primary/5';
    default:
      return 'border-border/50 bg-elevated/50';
  }
}

export function severityBadgeVariant(
  severity: ReportVersionSeverity,
): 'danger' | 'warning' | 'info' | 'default' | 'history' {
  switch (severity) {
    case 'major':
      return 'danger';
    case 'moderate':
      return 'warning';
    case 'minor':
      return 'info';
    case 'none':
      return 'history';
    default:
      return 'default';
  }
}
