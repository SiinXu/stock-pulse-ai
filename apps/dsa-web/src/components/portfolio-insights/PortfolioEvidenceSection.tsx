// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { sanitizeDiagnosticText } from '../../utils/dataQualityFormat/sanitizeDiagnostic';
import { Collapsible } from '../common';

type EvidenceValue = string | number | boolean | null | undefined | EvidenceValue[] | {
  [key: string]: EvidenceValue;
};

type PortfolioEvidenceSectionProps = {
  title: string;
  description?: string;
  values: unknown;
  testId?: string;
  emptyLabel: string;
  yesLabel: string;
  noLabel: string;
  keyLabels?: Record<string, string>;
  defaultOpen?: boolean;
};

function formatKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/^./, (value) => value.toUpperCase());
}

function formatScalar(
  value: string | number | boolean | null | undefined,
  labels: Pick<PortfolioEvidenceSectionProps, 'emptyLabel' | 'yesLabel' | 'noLabel'>,
): string {
  if (value == null || value === '') return labels.emptyLabel;
  if (typeof value === 'boolean') return value ? labels.yesLabel : labels.noLabel;
  if (typeof value === 'number') return String(value);
  return sanitizeDiagnosticText(String(value), 400);
}

function EvidenceValueView({
  value,
  labels,
  keyLabels,
}: {
  value: EvidenceValue;
  labels: Pick<PortfolioEvidenceSectionProps, 'emptyLabel' | 'yesLabel' | 'noLabel'>;
  keyLabels?: Record<string, string>;
}) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-text">{labels.emptyLabel}</span>;
    return (
      <ul className="space-y-1 text-sm text-secondary-text">
        {value.map((item, index) => (
          <li key={typeof item === 'string' ? item : index} className="break-words">
            {typeof item === 'object' && item !== null
              ? <EvidenceValueView value={item} labels={labels} keyLabels={keyLabels} />
              : formatScalar(item as string | number | boolean | null | undefined, labels)}
          </li>
        ))}
      </ul>
    );
  }
  if (value && typeof value === 'object') {
    return (
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
        {Object.entries(value).map(([key, item]) => (
          <div key={key} className="min-w-0 border-l-2 border-border pl-3">
            <dt className="text-xs font-medium text-secondary-text">
              {keyLabels?.[key] ?? formatKey(key)}
            </dt>
            <dd className="mt-1 break-words text-sm text-foreground">
              <EvidenceValueView value={item} labels={labels} keyLabels={keyLabels} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return (
    <span className="break-words text-sm text-foreground">
      {formatScalar(value, labels)}
    </span>
  );
}

const PortfolioEvidenceSection: React.FC<PortfolioEvidenceSectionProps> = ({
  title,
  description,
  values,
  testId,
  emptyLabel,
  yesLabel,
  noLabel,
  keyLabels,
  defaultOpen = false,
}) => {
  const labels = { emptyLabel, yesLabel, noLabel };
  return (
    <div data-testid={testId}>
      <Collapsible title={title} defaultOpen={defaultOpen}>
        {description ? <p className="mb-3 text-sm text-secondary-text">{description}</p> : null}
        <EvidenceValueView value={values as EvidenceValue} labels={labels} keyLabels={keyLabels} />
      </Collapsible>
    </div>
  );
};

export default PortfolioEvidenceSection;
