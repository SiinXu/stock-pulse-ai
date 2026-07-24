// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { DeepLinkGuard } from '../../components/routing/DeepLinkGuard';
import { ToastProvider } from '../../components/common';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import {
  LegacyHomeAnalysisRedirect,
} from '../LegacyHomeAnalysisRedirect';
import { resolveLegacyHomeAnalysisRedirect } from '../homeAnalysisRedirect';
import {
  ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS,
  ANALYSIS_WORKBENCH_SEGMENT_VALUES,
  APP_ROUTE_PATHS,
  HOME_ROUTE_QUERY_KEYS,
  HOME_WORKSPACE_VALUES,
  REPORT_ROUTE_QUERY_KEYS,
  RUN_FLOW_ROUTE_QUERY_VALUES,
} from '../routes';
import { SESSION_RESTORE_SUPPRESS_STATE_KEY } from '../../utils/sessionContinuity';

function LocationProbe() {
  const location = useLocation();
  return (
    <>
      <output data-testid="location">{`${location.pathname}${location.search}${location.hash}`}</output>
      <output data-testid="state">{JSON.stringify(location.state)}</output>
    </>
  );
}

describe('resolveLegacyHomeAnalysisRedirect', () => {
  it('maps report and history Run Flow state while preserving benign context and hash', () => {
    expect(resolveLegacyHomeAnalysisRedirect({
      search: `?ref=notification&${REPORT_ROUTE_QUERY_KEYS.recordId}=7&${REPORT_ROUTE_QUERY_KEYS.runFlow}=${RUN_FLOW_ROUTE_QUERY_VALUES.history}&${REPORT_ROUTE_QUERY_KEYS.runFlowRecordId}=7&${HOME_ROUTE_QUERY_KEYS.workspace}=${HOME_WORKSPACE_VALUES.history}`,
      hash: '#evidence',
    })).toEqual({
      pathname: APP_ROUTE_PATHS.researchAnalysis,
      search: `?ref=notification&${ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment}=${ANALYSIS_WORKBENCH_SEGMENT_VALUES.history}&${REPORT_ROUTE_QUERY_KEYS.recordId}=7&${REPORT_ROUTE_QUERY_KEYS.runFlow}=${RUN_FLOW_ROUTE_QUERY_VALUES.history}&${REPORT_ROUTE_QUERY_KEYS.runFlowRecordId}=7`,
      hash: '#evidence',
    });
  });

  it('maps task Run Flow and workspace-only bookmarks to their Workbench segments', () => {
    const task = resolveLegacyHomeAnalysisRedirect({
      search: `?${REPORT_ROUTE_QUERY_KEYS.runFlow}=${RUN_FLOW_ROUTE_QUERY_VALUES.task}&${REPORT_ROUTE_QUERY_KEYS.runFlowTaskId}=task-9`,
      hash: '',
    });
    expect(task?.search).toBe(
      `?${ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment}=${ANALYSIS_WORKBENCH_SEGMENT_VALUES.tasks}&${REPORT_ROUTE_QUERY_KEYS.runFlow}=${RUN_FLOW_ROUTE_QUERY_VALUES.task}&${REPORT_ROUTE_QUERY_KEYS.runFlowTaskId}=task-9`,
    );

    const today = resolveLegacyHomeAnalysisRedirect({
      search: `?${HOME_ROUTE_QUERY_KEYS.workspace}=${HOME_WORKSPACE_VALUES.today}`,
      hash: '',
    });
    expect(today?.search).toBe(
      `?${ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment}=${ANALYSIS_WORKBENCH_SEGMENT_VALUES.history}`,
    );
  });

  it('leaves the attention hub in place without legacy analysis intent', () => {
    expect(resolveLegacyHomeAnalysisRedirect({ search: '?from=nav', hash: '' })).toBeNull();
  });
});

describe('LegacyHomeAnalysisRedirect', () => {
  it('replaces Home with the Workbench and suppresses destination session restore', async () => {
    render(
      <MemoryRouter initialEntries={[{
        pathname: APP_ROUTE_PATHS.home,
        search: `?${REPORT_ROUTE_QUERY_KEYS.recordId}=9`,
        state: { source: 'bookmark' },
      }]}>
        <Routes>
          <Route
            path={APP_ROUTE_PATHS.home}
            element={(
              <LegacyHomeAnalysisRedirect>
                <div>Attention hub</div>
              </LegacyHomeAnalysisRedirect>
            )}
          />
          <Route path={APP_ROUTE_PATHS.researchAnalysis} element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId('location')).toHaveTextContent(
      `${APP_ROUTE_PATHS.researchAnalysis}?${ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment}=${ANALYSIS_WORKBENCH_SEGMENT_VALUES.history}&${REPORT_ROUTE_QUERY_KEYS.recordId}=9`,
    );
    expect(JSON.parse(screen.getByTestId('state').textContent ?? '{}')).toEqual({
      source: 'bookmark',
      [SESSION_RESTORE_SUPPRESS_STATE_KEY]: true,
    });
  });

  it('maps a workspace-only bookmark after the global deep-link guard runs', async () => {
    render(
      <UiLanguageProvider initialLanguage="en">
        <ToastProvider>
          <MemoryRouter initialEntries={[`${APP_ROUTE_PATHS.home}?${HOME_ROUTE_QUERY_KEYS.workspace}=${HOME_WORKSPACE_VALUES.history}`]}>
            <DeepLinkGuard>
              <Routes>
                <Route
                  path={APP_ROUTE_PATHS.home}
                  element={(
                    <LegacyHomeAnalysisRedirect>
                      <div>Attention hub</div>
                    </LegacyHomeAnalysisRedirect>
                  )}
                />
                <Route path={APP_ROUTE_PATHS.researchAnalysis} element={<LocationProbe />} />
              </Routes>
            </DeepLinkGuard>
          </MemoryRouter>
        </ToastProvider>
      </UiLanguageProvider>,
    );

    expect(await screen.findByTestId('location')).toHaveTextContent(
      `${APP_ROUTE_PATHS.researchAnalysis}?${ANALYSIS_WORKBENCH_ROUTE_QUERY_KEYS.segment}=${ANALYSIS_WORKBENCH_SEGMENT_VALUES.history}`,
    );
  });
});
