import type React from 'react';
import { cn } from '../../utils/cn';
import { resolveAiTaskMatrix, type AiTaskStatus, type UiLang } from './aiTaskMatrix';
import { SETTINGS_MISC_TEXT, SETTINGS_OVERVIEW_STATUS } from '../../locales/settingsMisc';

interface AiOverviewMatrixProps {
  /** Config value accessor (draft-applied), used to resolve effective routing. */
  getValue: (key: string) => string;
  language: UiLang;
  /** Jump to the Task Routing view to edit models. */
  onEditRouting?: () => void;
  /** Authoritative model routes declared by enabled connections (for Active state). */
  availableRoutes?: Set<string>;
  /** Render an opaque ModelRef as a user-facing model/Connection label. */
  formatModel?: (modelRef: string) => string;
}

const STATUS_META: Record<AiTaskStatus, { dot: string; text: string }> = {
  active: { dot: 'bg-success', text: 'text-foreground' },
  unavailable: { dot: 'bg-danger', text: 'text-danger' },
  unconfigured: { dot: 'bg-warning', text: 'text-warning' },
};

export const AiOverviewMatrix: React.FC<AiOverviewMatrixProps> = ({
  getValue,
  language,
  onEditRouting,
  availableRoutes,
  formatModel = (modelRef) => modelRef,
}) => {
  const rows = resolveAiTaskMatrix(getValue, { availableRoutes });
  const tx = (entry: { zh: string; en: string }) => entry[language];
  const text = SETTINGS_MISC_TEXT[language];

  return (
    <section aria-labelledby="ai-overview-title" className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="ai-overview-title" className="text-sm font-semibold text-foreground">{text.overviewTitle}</h2>
          <p className="mt-1 text-xs leading-5 text-secondary-text">{text.overviewDescription}</p>
        </div>
        {onEditRouting ? (
          <button
            type="button"
            className="inline-flex min-h-11 min-w-11 items-center justify-center whitespace-nowrap rounded-lg border border-[var(--settings-border)] px-3 py-1.5 text-xs text-secondary-text transition-colors hover:border-foreground hover:text-foreground"
            onClick={onEditRouting}
          >
            {text.editRouting}
          </button>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-xl border border-[var(--settings-border)]">
        <table className="w-full min-w-140 border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--settings-border)] text-xs uppercase tracking-wide text-muted-text">
              <th scope="col" className="px-3 py-2 font-medium">{text.colTask}</th>
              <th scope="col" className="px-3 py-2 font-medium">{text.colBackend}</th>
              <th scope="col" className="px-3 py-2 font-medium">{text.colPrimary}</th>
              <th scope="col" className="px-3 py-2 font-medium">{text.colFallback}</th>
              <th scope="col" className="px-3 py-2 font-medium">{text.colStatus}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-[var(--settings-border)] last:border-b-0" data-testid={`ai-task-${row.id}`}>
                <th scope="row" className="px-3 py-2.5 font-medium text-foreground">{tx(row.label)}</th>
                <td className="px-3 py-2.5 text-secondary-text">
                  {tx(row.backendLabel)}
                  {row.fallbackBackendId ? (
                    <span className="ml-1 text-xs text-muted-text">
                      · {text.failover}: {row.fallbackBackendId}
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2.5">
                  {row.primaryModel ? (
                    <span className="break-all text-foreground">{formatModel(row.primaryModel)}</span>
                  ) : (
                    <span className="text-muted-text">{text.none}</span>
                  )}
                  {row.primaryInherited && row.primaryModel ? (
                    <span className="ml-1 text-xs text-muted-text">({text.inherited})</span>
                  ) : null}
                </td>
                <td className="px-3 py-2.5 text-secondary-text">
                  {row.fallbackModels.length > 0 ? (
                    <span className="break-all">
                      {row.fallbackModels.map(formatModel).join(language === 'en' ? ', ' : '、')}
                    </span>
                  ) : (
                    <span className="text-muted-text">—</span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <span className="inline-flex items-center gap-1.5">
                    <span className={cn('h-2 w-2 rounded-full', STATUS_META[row.status].dot)} aria-hidden="true" />
                    <span className={STATUS_META[row.status].text}>
                      {SETTINGS_OVERVIEW_STATUS[language][row.status]}
                    </span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};
