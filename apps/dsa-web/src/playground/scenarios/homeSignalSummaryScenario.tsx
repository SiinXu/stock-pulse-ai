// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { HomeSignalSummary } from '../../components/home/HomeSignalSummary';
import { usePlaygroundScenario } from '../scenarioContext';
import type { PlaygroundScenarioRenderer } from '../types';

const HomeSignalSummaryStory: PlaygroundScenarioRenderer = () => {
  const { scenario } = usePlaygroundScenario();
  const isLoading = scenario === 'loading';
  const isError = scenario === 'error';
  const hasSnapshot = !isLoading && !isError;
  return (
    <div className="max-w-xl">
      <HomeSignalSummary
        isLoading={isLoading}
        availability={{
          activeSignals: hasSnapshot,
          reassessments: hasSnapshot,
          alerts: hasSnapshot,
        }}
        data={{
          activeSignalTotal: hasSnapshot ? 4 : null,
          triggeredAlertTotal: hasSnapshot ? 2 : null,
          dueReassessmentTotal: hasSnapshot ? 1 : null,
        }}
        stale={{
          activeSignals: false,
          reassessments: false,
          alerts: false,
        }}
        onRetry={() => undefined}
        onViewAll={() => undefined}
      />
    </div>
  );
};

export default HomeSignalSummaryStory;
