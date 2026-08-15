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
  it('uses the shared Button and opens the actionable Model Sources path', () => {
    render(
      <MemoryRouter initialEntries={['/agent']}>
        <UiLanguageProvider initialLanguage="en">
          <AgentUnavailableEmptyState
            title="Agent unavailable"
            description="Configure a model source first."
            actionLabel="Open model sources"
          />
          <LocationProbe />
        </UiLanguageProvider>
      </MemoryRouter>,
    );

    const action = screen.getByRole('button', { name: 'Open model sources' });
    expect(action).toHaveAttribute('data-control', 'button');
    fireEvent.click(action);

    expect(screen.getByTestId('location')).toHaveTextContent(
      '/settings?section=ai_models&view=connections',
    );
  });
});
