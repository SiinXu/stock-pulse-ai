import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UiLanguageProvider } from '../../../contexts/UiLanguageContext';
import { UI_LANGUAGE_STORAGE_KEY } from '../../../utils/uiLanguage';
import { ReportDetails } from '../ReportDetails';

const TRACE_DETAILS = {
  rawResult: { score: 82 },
  contextSnapshot: { window: '30d' },
};

function getDisclosurePanel(toggle: HTMLElement): HTMLElement {
  const panelId = toggle.getAttribute('aria-controls');
  expect(panelId).toBeTruthy();
  const panel = document.getElementById(panelId!);
  expect(panel).toBeInstanceOf(HTMLElement);
  return panel as HTMLElement;
}

/**
 * jsdom does not synthesize a click from Enter/Space on a focused native
 * button. Real browsers do; Collapsible relies on that native activation.
 */
function activateDisclosureWithKey(toggle: HTMLElement, key: 'Enter' | ' ') {
  toggle.focus();
  expect(toggle).toHaveFocus();
  fireEvent.keyDown(toggle, { key });
  if (key === ' ') {
    fireEvent.keyUp(toggle, { key });
  }
  fireEvent.click(toggle);
}

describe('ReportDetails', () => {
  const writeTextMock = vi.fn().mockResolvedValue(undefined);
  let originalClipboard: Navigator['clipboard'] | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    writeTextMock.mockClear();
    originalClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: writeTextMock,
      },
    });
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: originalClipboard,
    });
    vi.useRealTimers();
  });

  it('keeps raw result and snapshot collapsed by default with independent aria and keyboard toggles', () => {
    render(
      <ReportDetails
        recordId={7}
        details={TRACE_DETAILS}
      />,
    );

    const rawToggle = screen.getByRole('button', { name: '原始分析结果' });
    const snapshotToggle = screen.getByRole('button', { name: '分析快照' });

    expect(rawToggle.tagName).toBe('BUTTON');
    expect(rawToggle).toHaveAttribute('type', 'button');
    expect(rawToggle).not.toHaveAttribute('data-control');
    expect(snapshotToggle).not.toHaveAttribute('data-control');
    expect(rawToggle).toHaveAttribute('aria-expanded', 'false');
    expect(snapshotToggle).toHaveAttribute('aria-expanded', 'false');

    const rawPanel = getDisclosurePanel(rawToggle);
    const snapshotPanel = getDisclosurePanel(snapshotToggle);
    expect(rawPanel.id).not.toBe(snapshotPanel.id);
    expect(rawPanel).toHaveClass('grid-rows-[0fr]');
    expect(snapshotPanel).toHaveClass('grid-rows-[0fr]');
    expect(rawPanel).toHaveTextContent('"score": 82');
    expect(snapshotPanel).toHaveTextContent('"window": "30d"');

    fireEvent.click(rawToggle);
    expect(rawToggle).toHaveAttribute('aria-expanded', 'true');
    expect(snapshotToggle).toHaveAttribute('aria-expanded', 'false');
    expect(rawPanel).toHaveClass('grid-rows-[1fr]');
    expect(snapshotPanel).toHaveClass('grid-rows-[0fr]');

    fireEvent.click(rawToggle);
    expect(rawToggle).toHaveAttribute('aria-expanded', 'false');
    expect(rawPanel).toHaveClass('grid-rows-[0fr]');

    activateDisclosureWithKey(rawToggle, 'Enter');
    expect(rawToggle).toHaveAttribute('aria-expanded', 'true');
    expect(snapshotToggle).toHaveAttribute('aria-expanded', 'false');

    activateDisclosureWithKey(rawToggle, 'Enter');
    expect(rawToggle).toHaveAttribute('aria-expanded', 'false');

    activateDisclosureWithKey(snapshotToggle, ' ');
    expect(snapshotToggle).toHaveAttribute('aria-expanded', 'true');
    expect(rawToggle).toHaveAttribute('aria-expanded', 'false');
    expect(snapshotPanel).toHaveClass('grid-rows-[1fr]');
    expect(rawPanel).toHaveClass('grid-rows-[0fr]');
  });

  it('keeps copied feedback scoped to the panel that was copied', async () => {
    render(
      <ReportDetails
        recordId={7}
        details={TRACE_DETAILS}
      />,
    );

    const rawToggle = screen.getByRole('button', { name: '原始分析结果' });
    const snapshotToggle = screen.getByRole('button', { name: '分析快照' });
    expect(rawToggle).toHaveAttribute('aria-expanded', 'false');
    expect(snapshotToggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(rawToggle);
    fireEvent.click(snapshotToggle);
    expect(rawToggle).toHaveAttribute('aria-expanded', 'true');
    expect(snapshotToggle).toHaveAttribute('aria-expanded', 'true');

    const [rawCopyButton, snapshotCopyButton] = screen.getAllByRole('button', { name: '复制' });
    expect(rawCopyButton).toHaveAttribute('data-control', 'button');
    expect(rawCopyButton).toHaveClass('control-hit-target');
    expect(snapshotCopyButton).toHaveAttribute('data-control', 'button');

    await act(async () => {
      fireEvent.click(rawCopyButton);
      await Promise.resolve();
    });

    expect(writeTextMock).toHaveBeenNthCalledWith(1, JSON.stringify(TRACE_DETAILS.rawResult, null, 2));
    expect(screen.getByRole('button', { name: '已复制' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '复制' })).toHaveLength(1);

    await act(async () => {
      fireEvent.click(snapshotCopyButton);
      await Promise.resolve();
    });

    expect(writeTextMock).toHaveBeenNthCalledWith(2, JSON.stringify(TRACE_DETAILS.contextSnapshot, null, 2));
    expect(screen.getAllByRole('button', { name: '已复制' })).toHaveLength(2);

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(screen.getAllByRole('button', { name: '复制' })).toHaveLength(2);
  });

  it('does not render when details and record id are both absent', () => {
    const { container } = render(<ReportDetails />);
    expect(container).toBeEmptyDOMElement();
  });

  it('keeps traceability controls in the UI language instead of the report language', () => {
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'en');

    render(
      <UiLanguageProvider>
        <ReportDetails
          language="zh"
          recordId={7}
          details={{ rawResult: { score: 82 } }}
        />
      </UiLanguageProvider>,
    );

    expect(screen.getByRole('heading', { name: 'Data Traceability' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Raw Analysis Result' })).toBeInTheDocument();
  });
});
