import type React from 'react';
import { cn } from '../../utils/cn';
import { resolveAiTaskMatrix, type AiTaskStatus, type UiLang } from './aiTaskMatrix';

interface AiOverviewMatrixProps {
  /** Config value accessor (draft-applied), used to resolve effective routing. */
  getValue: (key: string) => string;
  language: UiLang;
  /** Jump to the Task Routing view to edit models. */
  onEditRouting?: () => void;
  /** Authoritative model routes declared by enabled connections (for Active state). */
  availableRoutes?: Set<string>;
}

const STATUS_META: Record<AiTaskStatus, { zh: string; en: string; dot: string; text: string }> = {
  active: { zh: '生效', en: 'Active', dot: 'bg-success', text: 'text-foreground' },
  unavailable: { zh: '当前配置不可用', en: 'Unavailable', dot: 'bg-danger', text: 'text-danger' },
  unconfigured: { zh: '待配置', en: 'Needs config', dot: 'bg-warning', text: 'text-warning' },
};

const T = {
  title: { zh: '任务路由总览', en: 'Task routing overview' },
  description: {
    zh: '每个任务当前的执行方式与生效模型，无需查看环境变量即可判断实际路径。',
    en: 'The execution backend and effective model for each task — no env vars needed.',
  },
  colTask: { zh: '任务', en: 'Task' },
  colBackend: { zh: '执行方式', en: 'Execution backend' },
  colPrimary: { zh: '主模型', en: 'Primary model' },
  colFallback: { zh: '备用模型', en: 'Fallback models' },
  colStatus: { zh: '状态', en: 'Status' },
  inherited: { zh: '继承报告模型', en: 'inherits report model' },
  none: { zh: '未配置', en: 'not configured' },
  failover: { zh: '失败切换', en: 'failover' },
  edit: { zh: '前往任务路由', en: 'Edit task routing' },
} as const;

export const AiOverviewMatrix: React.FC<AiOverviewMatrixProps> = ({ getValue, language, onEditRouting, availableRoutes }) => {
  const rows = resolveAiTaskMatrix(getValue, { availableRoutes });
  const tx = (entry: { zh: string; en: string }) => entry[language];

  return (
    <section aria-labelledby="ai-overview-title" className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="ai-overview-title" className="text-sm font-semibold text-foreground">{tx(T.title)}</h2>
          <p className="mt-1 text-xs leading-5 text-secondary-text">{tx(T.description)}</p>
        </div>
        {onEditRouting ? (
          <button
            type="button"
            className="whitespace-nowrap rounded-md border border-[var(--settings-border)] px-3 py-1.5 text-xs text-secondary-text transition-colors hover:border-foreground hover:text-foreground"
            onClick={onEditRouting}
          >
            {tx(T.edit)}
          </button>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-xl border border-[var(--settings-border)]">
        <table className="w-full min-w-[560px] border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-[var(--settings-border)] text-[11px] uppercase tracking-wide text-muted-text">
              <th scope="col" className="px-3 py-2 font-medium">{tx(T.colTask)}</th>
              <th scope="col" className="px-3 py-2 font-medium">{tx(T.colBackend)}</th>
              <th scope="col" className="px-3 py-2 font-medium">{tx(T.colPrimary)}</th>
              <th scope="col" className="px-3 py-2 font-medium">{tx(T.colFallback)}</th>
              <th scope="col" className="px-3 py-2 font-medium">{tx(T.colStatus)}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-[var(--settings-border)] last:border-b-0" data-testid={`ai-task-${row.id}`}>
                <th scope="row" className="px-3 py-2.5 font-medium text-foreground">{tx(row.label)}</th>
                <td className="px-3 py-2.5 text-secondary-text">
                  {tx(row.backendLabel)}
                  {row.fallbackBackendId ? (
                    <span className="ml-1 text-[11px] text-muted-text">
                      · {tx(T.failover)}: {row.fallbackBackendId}
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2.5">
                  {row.primaryModel ? (
                    <span className="break-all text-foreground">{row.primaryModel}</span>
                  ) : (
                    <span className="text-muted-text">{tx(T.none)}</span>
                  )}
                  {row.primaryInherited && row.primaryModel ? (
                    <span className="ml-1 text-[11px] text-muted-text">（{tx(T.inherited)}）</span>
                  ) : null}
                </td>
                <td className="px-3 py-2.5 text-secondary-text">
                  {row.fallbackModels.length > 0 ? (
                    <span className="break-all">{row.fallbackModels.join('、')}</span>
                  ) : (
                    <span className="text-muted-text">—</span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <span className="inline-flex items-center gap-1.5">
                    <span className={cn('h-2 w-2 rounded-full', STATUS_META[row.status].dot)} aria-hidden="true" />
                    <span className={STATUS_META[row.status].text}>
                      {tx(STATUS_META[row.status])}
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
