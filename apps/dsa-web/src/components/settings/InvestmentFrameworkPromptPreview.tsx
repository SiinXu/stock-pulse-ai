// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import { Eye } from 'lucide-react';
import type { InvestmentFrameworkContent } from '../../types/investmentFramework';
import {
  formatInvestmentFrameworkPromptPreview,
  hasFrameworkPromptPreviewContent,
  type FrameworkPromptPreviewLanguage,
} from './investmentFrameworkPromptPreviewModel';

type InvestmentFrameworkPromptPreviewProps = {
  content: InvestmentFrameworkContent;
  frameworkId?: number | null;
  frameworkVersion?: number | null;
  /** True when the preview reflects unsaved draft content. */
  draft?: boolean;
  reportLanguage: FrameworkPromptPreviewLanguage;
  title: string;
  description: string;
  emptyLabel: string;
};

/**
 * Live preview of how the current framework draft is phrased into the
 * stock-analysis read-only prompt section (mirrors backend formatting).
 */
export const InvestmentFrameworkPromptPreview: React.FC<
  InvestmentFrameworkPromptPreviewProps
> = ({
  content,
  frameworkId = null,
  frameworkVersion = null,
  draft = true,
  reportLanguage,
  title,
  description,
  emptyLabel,
}) => {
  const preview = useMemo(
    () => formatInvestmentFrameworkPromptPreview(content, {
      frameworkId,
      frameworkVersion,
      draft,
      reportLanguage,
    }),
    [content, draft, frameworkId, frameworkVersion, reportLanguage],
  );
  const hasContent = hasFrameworkPromptPreviewContent(content);

  return (
    <section
      className="space-y-3 rounded-xl border settings-border bg-background/20 p-4"
      data-testid="investment-framework-prompt-preview"
      aria-labelledby="investment-framework-prompt-preview-title"
    >
      <div className="flex items-start gap-2">
        <Eye className="mt-0.5 h-4 w-4 shrink-0 text-secondary-text" aria-hidden="true" />
        <div className="min-w-0 space-y-1">
          <h3
            id="investment-framework-prompt-preview-title"
            className="text-base font-semibold text-foreground"
          >
            {title}
          </h3>
          <p className="text-xs leading-5 text-muted-text">
            {description}
          </p>
        </div>
      </div>

      {hasContent && preview ? (
        <pre
          className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3 font-mono text-xs leading-5 text-secondary-text"
          data-testid="investment-framework-prompt-preview-body"
        >
          {preview}
        </pre>
      ) : (
        <p
          className="rounded-lg border border-dashed border-[var(--settings-border)] bg-[var(--settings-surface)]/60 px-3 py-4 text-xs leading-5 text-muted-text"
          data-testid="investment-framework-prompt-preview-empty"
        >
          {emptyLabel}
        </p>
      )}
    </section>
  );
};

export default InvestmentFrameworkPromptPreview;
