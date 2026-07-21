import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { ThemeProvider } from 'next-themes';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import ComponentPlaygroundPage from '../ComponentPlaygroundPage';

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="location-search">{location.search}</output>;
};

function renderPage(initialEntry = '/playground') {
  return render(
    <ThemeProvider attribute="class" defaultTheme="dark">
      <UiLanguageProvider initialLanguage="en">
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/playground" element={<><ComponentPlaygroundPage /><LocationProbe /></>} />
          </Routes>
        </MemoryRouter>
      </UiLanguageProvider>
    </ThemeProvider>,
  );
}

describe('ComponentPlaygroundPage', () => {
  it('canonicalizes invalid deep-link state and renders the fallback entry', async () => {
    renderPage('/playground?component=missing&scenario=missing&profile=unknown&viewport=huge');

    expect(await screen.findByRole('heading', { name: 'Button' })).toBeInTheDocument();
    await waitFor(() => {
      const params = new URLSearchParams(screen.getByTestId('location-search').textContent || '');
      expect(Object.fromEntries(params)).toMatchObject({
        component: 'button',
        scenario: 'variants',
        profile: 'ready',
        viewport: 'auto',
      });
    });
    expect(screen.getByTitle('Button - Variants')).toHaveAttribute('src', expect.stringContaining('/playground/render/button/variants'));
  });

  it('filters the catalog by search text and category', async () => {
    renderPage('/playground?component=button&scenario=variants&profile=ready&viewport=auto');

    const catalog = screen.getByRole('navigation', { name: 'Component catalog' });
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search components' }), {
      target: { value: 'markdown body' },
    });
    expect(within(catalog).getByRole('button', { name: /ReportMarkdownBody/ })).toBeInTheDocument();
    expect(within(catalog).queryByRole('button', { name: /Button Shared components/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search components' }), { target: { value: '' } });
    const categorySelect = screen.getByRole('combobox', { name: 'Component catalog' });
    fireEvent.click(categorySelect);
    fireEvent.click(screen.getByRole('option', { name: 'Reports' }));

    expect(within(catalog).getByRole('button', { name: /ReportSummary/ })).toBeInTheDocument();
    expect(within(catalog).queryByRole('button', { name: /AlertRuleForm/ })).not.toBeInTheDocument();
  });

  it('persists component, scenario, profile, and viewport selection in the URL', async () => {
    renderPage('/playground?component=modal&scenario=interactive&profile=slow&viewport=phone');

    expect(await screen.findByRole('heading', { name: 'Modal' })).toBeInTheDocument();
    const params = new URLSearchParams(screen.getByTestId('location-search').textContent || '');
    expect(Object.fromEntries(params)).toMatchObject({
      component: 'modal',
      scenario: 'interactive',
      profile: 'slow',
      viewport: 'phone',
    });
    expect(screen.getByTitle('Modal - Interactive')).toHaveAttribute('src', expect.stringContaining('profile=slow'));
  });
});
