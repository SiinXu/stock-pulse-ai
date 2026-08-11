import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ScrollArea } from '../ScrollArea';

describe('ScrollArea', () => {
  it('renders a scrollable viewport and forwards custom classes', () => {
    render(
      <ScrollArea
        className="outer-shell"
        viewportClassName="inner-viewport"
        testId="scroll-area-viewport"
      >
        <div>scroll content</div>
      </ScrollArea>
    );

    const viewport = screen.getByTestId('scroll-area-viewport');
    expect(viewport).toBeInTheDocument();
    expect(viewport).toHaveClass('inner-viewport');
    expect(viewport).toHaveTextContent('scroll content');
    expect(viewport.parentElement).toHaveClass('outer-shell');
  });

  it('keeps a flex-bounded height chain so nested lists can scroll', () => {
    render(
      <ScrollArea testId="scroll-area-viewport">
        <div>scroll content</div>
      </ScrollArea>,
    );

    const viewport = screen.getByTestId('scroll-area-viewport');
    const shell = viewport.parentElement;
    expect(shell).toHaveClass('min-h-0', 'flex-1', 'overflow-hidden');
    expect(viewport).toHaveClass('min-h-0', 'flex-1', 'overflow-y-auto', 'overscroll-contain');
    // touch-pan-y maps to touch-action: pan-y and blocks pinch-zoom; keep it off by default
    expect(viewport.className.split(/\s+/)).not.toContain('touch-pan-y');
  });
});
