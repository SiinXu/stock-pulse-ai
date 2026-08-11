// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import type React from 'react';
import { useCallback, useEffect } from 'react';
import { Link, useNavigate, type SetURLSearchParams } from 'react-router-dom';
import { TaskPanel } from '../tasks/TaskPanel';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { PORTFOLIO_TEXT } from '../../locales/portfolio';
import {
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  RUN_FLOW_ROUTE_QUERY_VALUES,
  buildAnalysisWorkbenchHref,
} from '../../routing/routes';
import type { AnalysisPhase, TaskAccepted, TaskInfo } from '../../types/analysis';
import { usePortfolioAnalysisTasks } from './usePortfolioAnalysisTasks';

export interface PortfolioAnalysisTaskPanelController {
  acceptTask: (accepted: TaskAccepted, stockCode: string, analysisPhase: AnalysisPhase) => void;
  attachExistingTask: (
    taskId: string,
    stockCode: string,
    analysisPhase?: AnalysisPhase,
    resultRecordId?: number,
  ) => Promise<void>;
}

interface PortfolioAnalysisTaskPanelProps {
  searchParams: URLSearchParams;
  setSearchParams: SetURLSearchParams;
  visible: boolean;
  onControllerReady: (controller: PortfolioAnalysisTaskPanelController | null) => void;
}

const PortfolioAnalysisTaskPanel: React.FC<PortfolioAnalysisTaskPanelProps> = ({
  searchParams,
  setSearchParams,
  visible,
  onControllerReady,
}) => {
  const navigate = useNavigate();
  const { language, t } = useUiLanguage();
  const text = PORTFOLIO_TEXT[language];
  const {
    tasks,
    acceptTask,
    attachExistingTask,
    dismissTask,
  } = usePortfolioAnalysisTasks({ searchParams, setSearchParams });

  useEffect(() => {
    onControllerReady({ acceptTask, attachExistingTask });
    return () => onControllerReady(null);
  }, [acceptTask, attachExistingTask, onControllerReady]);

  const openRunFlow = useCallback((task: TaskInfo) => {
    void navigate(buildAnalysisWorkbenchHref({
      segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks,
      runFlow: RUN_FLOW_ROUTE_QUERY_VALUES.task,
      runFlowTaskId: task.taskId,
      stock: task.stockCode,
    }));
  }, [navigate]);

  if (!visible || tasks.length === 0) return null;

  return (
    <div className="space-y-2" data-testid="portfolio-analysis-task-panel">
      <TaskPanel
        tasks={tasks}
        title={text.analysisTask}
        onOpenRunFlow={openRunFlow}
        onDismiss={dismissTask}
      />
      {tasks.some((task) => task.status === 'completed') ? (
        <div className="flex flex-wrap gap-2">
          {tasks
            .filter((task) => task.status === 'completed')
            .map((task) => (
              <Link
                key={`result-${task.taskId}`}
                to={buildAnalysisWorkbenchHref({
                  segment: ANALYSIS_WORKBENCH_SEGMENT_VALUES.history,
                  recordId: task.resultRecordId,
                  stock: task.stockCode,
                })}
                data-control="navigation-link"
                className="control-hit-target inline-flex min-h-9 items-center rounded-md border border-subtle bg-elevated px-3 text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
              >
                {t('analysisWorkbench.viewReport')}: {task.stockName || task.stockCode}
              </Link>
            ))}
        </div>
      ) : null}
    </div>
  );
};

export default PortfolioAnalysisTaskPanel;
