import { render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { describe, expect, it } from 'vitest';
import { AppPage } from '../AppPage';
import { PageHeader } from '../PageHeader';
import { Section } from '../Section';
import { SectionCard } from '../SectionCard';
import { StickyActionBar } from '../StickyActionBar';
import { Toolbar } from '../Toolbar';

describe('layout patterns', () => {
  it('keeps AppPage as a ref-forwarding non-landmark container', () => {
    const ref = createRef<HTMLDivElement>();
    const { container } = render(<AppPage ref={ref}>Content</AppPage>);

    expect(ref.current).toBe(container.firstElementChild);
    expect(container.querySelector('main')).toBeNull();
    expect(ref.current).toHaveClass('max-w-none', 'px-4', 'md:px-6', 'lg:px-8');
  });

  it('keeps PageHeader aligned to the AppPage content edge', () => {
    render(<PageHeader title="Overview" />);

    expect(screen.getByRole('banner')).not.toHaveClass('px-1');
  });

  it('labels a flat Section from its heading', () => {
    render(
      <Section title="Overview" description="Current account state" actions={<button type="button">Refresh</button>}>
        Section body
      </Section>,
    );

    const section = screen.getByRole('region', { name: 'Overview' });
    expect(section).not.toHaveClass('rounded-xl', 'border', 'shadow-soft-card');
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
  });

  it('keeps SectionCard as an explicit card container', () => {
    render(<SectionCard title="History" subtitle="Reports">Rows</SectionCard>);

    const heading = screen.getByRole('heading', { name: 'History' });
    const card = heading.parentElement?.parentElement?.parentElement;
    expect(card).toHaveTextContent('Reports');
    expect(card).toHaveClass('border');
  });

  it('renders Toolbar and StickyActionBar as flat bands', () => {
    render(
      <>
        <Toolbar aria-label="Filters" left={<button type="button">Market</button>} right={<button type="button">Apply</button>} />
        <StickyActionBar><button type="button">Save</button></StickyActionBar>
      </>,
    );

    const toolbar = screen.getByRole('toolbar', { name: 'Filters' });
    expect(toolbar).toHaveClass('border-y');
    expect(toolbar).not.toHaveClass('glass-panel', 'rounded-xl');
    expect(screen.getByRole('button', { name: 'Save' }).parentElement?.parentElement).toHaveClass('border-t');
  });
});
