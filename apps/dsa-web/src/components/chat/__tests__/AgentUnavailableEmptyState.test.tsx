// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { AgentUnavailableEmptyState } from '../AgentUnavailableEmptyState';

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

describe('AgentUnavailableEmptyState', () => {
  it('offers cloud, local, and non-Agent paths through shared buttons', () => {
    render(
      <MemoryRouter initialEntries={['/agent']}>
        <UiLanguageProvider initialLanguage="en">
          <AgentUnavailableEmptyState
            title="Agent unavailable"
            description="Configure a model source first."
            actionLabel="Configure cloud model"
            localActionLabel="Use a local model"
            analysisActionLabel="Analysis workbench"
          />
          <LocationProbe />
        </UiLanguageProvider>
      </MemoryRouter>,
    );

    const cloudAction = screen.getByRole('button', { name: 'Configure cloud model' });
    const localAction = screen.getByRole('button', { name: 'Use a local model' });
    const analysisAction = screen.getByRole('button', { name: 'Analysis workbench' });
    [cloudAction, localAction, analysisAction].forEach((action) => {
      expect(action).toHaveAttribute('data-control', 'button');
    });
    expect(cloudAction.parentElement).toHaveClass('gap-x-2', 'gap-y-4');

    fireEvent.click(cloudAction);

    expect(screen.getByTestId('location')).toHaveTextContent(
      '/settings?section=ai_models&view=connections',
    );

    fireEvent.click(localAction);

    expect(screen.getByTestId('location')).toHaveTextContent(
      '/settings?section=ai_models&view=connections',
    );

    fireEvent.click(analysisAction);
    expect(screen.getByTestId('location')).toHaveTextContent('/research/analysis');
  });
});
