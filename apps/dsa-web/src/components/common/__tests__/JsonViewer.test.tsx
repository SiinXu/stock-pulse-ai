import { fireEvent, render, screen } from '@testing-library/react';
import type React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { JsonViewer } from '../JsonViewer';

function renderJsonViewer(data: React.ComponentProps<typeof JsonViewer>['data']) {
  return render(
    <UiLanguageProvider>
      <JsonViewer data={data} />
    </UiLanguageProvider>,
  );
}

describe('JsonViewer', () => {
  it('renders html-like JSON strings as inert text', () => {
    const { container } = renderJsonViewer({
      payload: '<img src=x onerror="window.__jsonViewerXss = true">',
      nested: {
        script: '<script>window.__jsonViewerScript = true</script>',
      },
    });

    expect(container.textContent).toContain('<img src=x onerror=\\"window.__jsonViewerXss = true\\">');
    expect(container.textContent).toContain('<script>window.__jsonViewerScript = true</script>');
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('[onerror]')).toBeNull();
  });

  it('keeps keys and values visually tokenized without injecting html', () => {
    renderJsonViewer({
      status: true,
      score: 82,
      note: 'ok',
    });

    expect(screen.getByText('"status"')).toHaveClass('text-primary');
    expect(screen.getByText('true')).toHaveClass('text-secondary-text');
    expect(screen.getByText('82')).toHaveClass('text-warning');
    expect(screen.getByText('"ok"')).toHaveClass('text-success');
    expect(screen.getByRole('button', { name: /^(?:复制|Copy)$/ })).toHaveClass('ui-touch-target', 'h-9', 'min-w-9');
  });

  it('supports an icon-only copy action without changing its accessible name', () => {
    render(
      <UiLanguageProvider>
        <JsonViewer data={{ status: 'ready' }} copyIconOnly />
      </UiLanguageProvider>,
    );

    const copyButton = screen.getByRole('button', { name: /^(?:复制|Copy)$/ });
    expect(copyButton).toHaveTextContent('');
    expect(copyButton.querySelector('svg')).toBeInTheDocument();
  });

  it('announces clipboard failures without showing false success', async () => {
    const originalClipboard = navigator.clipboard;
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
    });

    renderJsonViewer({ status: 'ready' });
    fireEvent.click(screen.getByRole('button', { name: /^(?:复制|Copy)$/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/复制失败，请重试|Copy failed\. Try again\./);
    expect(screen.queryByText(/已复制!|Copied!/)).not.toBeInTheDocument();

    consoleError.mockRestore();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: originalClipboard,
    });
  });
});
