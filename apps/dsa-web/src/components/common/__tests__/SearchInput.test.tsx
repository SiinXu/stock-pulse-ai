import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SearchInput } from '../SearchInput';

describe('SearchInput', () => {
  it('renders the compact search field and optional shortcut', () => {
    render(<SearchInput aria-label="Search stocks" shortcut="/" />);

    expect(screen.getByRole('searchbox', { name: 'Search stocks' }).parentElement).toHaveClass('h-11', 'sm:h-7', 'rounded-lg');
    expect(screen.getByText('/').tagName).toBe('KBD');
  });
});
