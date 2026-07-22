// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { ToastProvider } from '../../common';
import { DeepLinkGuard } from '../DeepLinkGuard';

function LocationProbe({ onRender }: { onRender?: (pathname: string) => void }) {
  const location = useLocation();
  onRender?.(location.pathname);
  return <output aria-label="Current route">{`${location.pathname}${location.search}${location.hash}`}</output>;
}

function renderGuard(initialEntry: string, onRender?: (pathname: string) => void) {
  return render(
    <UiLanguageProvider initialLanguage="en">
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <DeepLinkGuard>
            <LocationProbe onRender={onRender} />
          </DeepLinkGuard>
        </MemoryRouter>
      </ToastProvider>
    </UiLanguageProvider>,
  );
}

describe('DeepLinkGuard', () => {
  it('normalizes a major route before its page renders and reports the fallback', async () => {
    renderGuard('/chat?session=bad%20id&api_key=secret&keep=yes');

    await waitFor(() => expect(screen.getByLabelText('Current route')).toHaveTextContent('/chat?keep=yes'));
    expect(screen.getByText('Invalid link')).toBeInTheDocument();
    expect(screen.getByText(/invalid or sensitive state parameters/)).toBeInTheDocument();
  });

  it('leaves benign state on an unsupported route for the not-found page', () => {
    renderGuard('/missing?ref=notification');

    expect(screen.getByLabelText('Current route')).toHaveTextContent('/missing?ref=notification');
    expect(screen.queryByText('Invalid link')).not.toBeInTheDocument();
  });

  it('redirects an invalid stock path before the product page renders', async () => {
    const renderedPaths: string[] = [];
    renderGuard('/stocks/%3Cscript%3E?days=30', (pathname) => renderedPaths.push(pathname));

    await waitFor(() => expect(screen.getByLabelText('Current route')).toHaveTextContent('/'));
    expect(screen.getByText('Invalid link')).toBeInTheDocument();
    expect(renderedPaths).not.toContain('/stocks/%3Cscript%3E');
  });
});
