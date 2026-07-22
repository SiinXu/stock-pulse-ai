// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';
import { recordSessionLocation } from '../../../utils/sessionContinuity';
import { SessionContinuityGuard } from '../SessionContinuityGuard';

function Probe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output aria-label="Current route">{`${location.pathname}${location.search}`}</output>
      <button type="button" onClick={() => navigate('/portfolio')}>Clear route state</button>
    </>
  );
}

function renderGuard(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <SessionContinuityGuard>
        <Probe />
      </SessionContinuityGuard>
    </MemoryRouter>,
  );
}

describe('SessionContinuityGuard', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('restores the prior route snapshot once on a fresh mount', async () => {
    recordSessionLocation('/portfolio?account=8');

    renderGuard('/portfolio');

    await waitFor(() => expect(screen.getByLabelText('Current route')).toHaveTextContent('/portfolio?account=8'));
  });

  it('does not fight a later in-app navigation that clears route state', async () => {
    recordSessionLocation('/portfolio?account=8');
    renderGuard('/portfolio');
    await screen.findByText('/portfolio?account=8');

    fireEvent.click(screen.getByRole('button', { name: 'Clear route state' }));

    await waitFor(() => expect(screen.getByLabelText('Current route')).toHaveTextContent('/portfolio'));
    expect(screen.getByLabelText('Current route')).not.toHaveTextContent('account=8');
  });
});
