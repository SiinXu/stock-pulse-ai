// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { createRef, useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import {
  AppPage,
  PageHeader,
  ResponsiveRail,
  SummaryStrip,
  TabPanel,
  Tabs,
  Toolbar,
  WorkspaceNavigation,
  WorkspacePage,
} from '..';

describe('page skeleton Patterns', () => {
  it('keeps AppPage inside the shell landmark and forwards native props and ref', () => {
    const ref = createRef<HTMLDivElement>();
    const { container } = render(
      <main>
        <AppPage ref={ref} aria-label="Workspace canvas">Content</AppPage>
      </main>,
    );

    const page = screen.getByLabelText('Workspace canvas');
    expect(page.tagName).toBe('DIV');
    expect(page).toHaveAttribute('data-pattern', 'app-page');
    expect(page).toHaveAttribute('data-page-width', 'full');
    expect(ref.current).toBe(page);
    expect(container.querySelectorAll('main')).toHaveLength(1);
  });

  it('provides one stable, programmatically focusable page heading', () => {
    const headingRef = createRef<HTMLHeadingElement>();
    render(
      <PageHeader
        ref={headingRef}
        eyebrow="Research"
        title="A deliberately long localized portfolio analysis heading"
        description="Current evidence and risk"
        actions={<button type="button">Export</button>}
      />,
    );

    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading).toHaveAttribute('tabindex', '-1');
    expect(headingRef.current).toBe(heading);
    expect(heading.closest('header')).toHaveAttribute('data-pattern', 'page-header');
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
  });

  it('names Toolbar semantics and omits unused slots', () => {
    const ref = createRef<HTMLDivElement>();
    render(
      <Toolbar ref={ref} aria-label="Report commands" left={<button type="button">Refresh</button>} />,
    );

    const toolbar = screen.getByRole('toolbar', { name: 'Report commands' });
    expect(toolbar).toHaveAttribute('data-pattern', 'toolbar');
    expect(within(toolbar).getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
    expect(toolbar.querySelector('[data-slot="end"]')).not.toBeInTheDocument();
    expect(ref.current).toBe(toolbar);
  });

  it('composes a full-width WorkspacePage with a disclosure rail', () => {
    render(
      <WorkspacePage
        aria-label="Run workspace"
        rail={(
          <ResponsiveRail
            title="Run context"
            expandLabel="Show run context"
            collapseLabel="Hide run context"
          >
            <p>Context details</p>
          </ResponsiveRail>
        )}
      >
        <p>Main workspace</p>
      </WorkspacePage>,
    );

    const workspace = screen.getByText('Main workspace').closest('[data-pattern="workspace-page"]');
    const rail = screen.getByRole('complementary', { name: 'Run context' });
    const toggle = screen.getByRole('button', { name: 'Show run context' });
    expect(workspace).not.toBeNull();
    expect(rail).toHaveAttribute('data-compact-state', 'collapsed');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(toggle);
    expect(rail).toHaveAttribute('data-compact-state', 'expanded');
    expect(screen.getByRole('button', { name: 'Hide run context' })).toHaveAttribute('aria-expanded', 'true');
  });

  it('implements roving Tabs and associated tab panels without using segmented controls', () => {
    const Harness = () => {
      const [value, setValue] = useState('overview');
      const items = [
        { id: 'overview', label: 'Overview' },
        { id: 'disabled', label: 'Unavailable', disabled: true },
        { id: 'risk', label: 'Risk' },
      ];
      return (
        <>
          <Tabs
            id="portfolio-tabs"
            aria-label="Portfolio sections"
            value={value}
            items={items}
            onValueChange={setValue}
          />
          {items.map((item) => (
            <TabPanel key={item.id} tabsId="portfolio-tabs" value={item.id} activeValue={value}>
              {item.label} panel
            </TabPanel>
          ))}
        </>
      );
    };

    render(<Harness />);
    const overview = screen.getByRole('tab', { name: 'Overview' });
    overview.focus();
    fireEvent.keyDown(overview, { key: 'ArrowRight' });
    const risk = screen.getByRole('tab', { name: 'Risk' });
    expect(risk).toHaveAttribute('aria-selected', 'true');
    expect(risk).toHaveFocus();
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Risk panel');

    fireEvent.keyDown(risk, { key: 'Home' });
    expect(overview).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Unavailable' })).toBeDisabled();
  });

  it('renders SummaryStrip as one labelled definition list', () => {
    const ref = createRef<HTMLDListElement>();
    render(
      <SummaryStrip
        ref={ref}
        aria-label="Portfolio summary"
        items={[
          { id: 'value', label: 'Market value', value: '$24,080' },
          { id: 'risk', label: 'Risk status', value: 'Review', tone: 'warning', detail: 'As of today' },
        ]}
      />,
    );

    const summary = screen.getByLabelText('Portfolio summary');
    expect(summary.tagName).toBe('DL');
    expect(summary).toHaveAttribute('data-pattern', 'summary-strip');
    expect(screen.getByText('Market value').tagName).toBe('DT');
    expect(screen.getByText('$24,080').tagName).toBe('DD');
    expect(ref.current).toBe(summary);
  });

  it('uses links for desktop workspace routes and a native select for compact navigation', () => {
    const onCompactNavigate = vi.fn();
    render(
      <MemoryRouter>
        <WorkspaceNavigation
          id="research-navigation"
          ariaLabel="Research views"
          current="report"
          items={[
            { id: 'asset', label: 'Asset overview', to: '/asset' },
            { id: 'report', label: 'Full report', to: '/report' },
          ]}
          onCompactNavigate={onCompactNavigate}
        />
      </MemoryRouter>,
    );

    const navigation = screen.getByRole('navigation', { name: 'Research views' });
    const current = within(navigation).getByRole('link', { name: 'Full report' });
    expect(current).toHaveAttribute('href', '/report');
    expect(current).toHaveAttribute('aria-current', 'page');
    expect(current).toHaveAttribute('data-route-focus-key', 'research-navigation:report');
    expect(within(navigation).queryByRole('tab')).not.toBeInTheDocument();

    fireEvent.change(within(navigation).getByRole('combobox', { name: 'Research views' }), {
      target: { value: 'asset' },
    });
    expect(onCompactNavigate).toHaveBeenCalledWith(expect.objectContaining({ id: 'asset', to: '/asset' }));
  });
});
