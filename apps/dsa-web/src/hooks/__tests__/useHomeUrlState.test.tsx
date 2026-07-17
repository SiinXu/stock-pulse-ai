import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useCallback, useState } from 'react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { ParsedApiError } from '../../api/error';
import { useHomeUrlState } from '../useHomeUrlState';

type HarnessProps = {
  defaultRecordId?: number | null;
  initialSelectedRecordId?: number | null;
  reportError?: ParsedApiError | null;
  onSelect?: (recordId: number, isUserInitiated?: boolean) => void;
  onClear?: (preserveError?: boolean) => void;
};

function Harness({
  defaultRecordId = null,
  initialSelectedRecordId = null,
  reportError = null,
  onSelect,
  onClear,
}: HarnessProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [selectedRecordId, setSelectedRecordId] = useState(initialSelectedRecordId);
  const selectHistoryItem = useCallback((recordId: number, isUserInitiated?: boolean) => {
    setSelectedRecordId(recordId);
    onSelect?.(recordId, isUserInitiated);
    return Promise.resolve();
  }, [onSelect]);
  const clearSelectedRecord = useCallback((preserveError?: boolean) => {
    setSelectedRecordId(null);
    onClear?.(preserveError);
  }, [onClear]);
  const homeUrl = useHomeUrlState({
    defaultRecordId,
    isHistoryLoading: false,
    selectedRecordId,
    isReportLoading: false,
    reportError,
    selectHistoryItem,
    clearSelectedRecord,
  });

  const source = homeUrl.runFlowSource?.type === 'task'
    ? `task:${homeUrl.runFlowSource.taskId}`
    : homeUrl.runFlowSource?.type === 'history'
      ? `history:${homeUrl.runFlowSource.recordId}`
      : 'none';

  return (
    <div>
      <output data-testid="search">{location.search}</output>
      <output data-testid="location-key">{location.key}</output>
      <output data-testid="source">{source}</output>
      <output data-testid="issue">{homeUrl.urlIssue ?? 'none'}</output>
      <button type="button" onClick={() => homeUrl.navigateToRecord(2)}>record 2</button>
      <button type="button" onClick={() => homeUrl.openTaskRunFlow('task-2')}>task flow</button>
      <button type="button" onClick={() => homeUrl.openHistoryRunFlow(2)}>history flow</button>
      <button type="button" onClick={() => homeUrl.closeRunFlow()}>close flow</button>
      <button type="button" onClick={() => navigate(-1)}>back</button>
      <button type="button" onClick={() => navigate(1)}>forward</button>
    </div>
  );
}

function renderHarness(initialEntry: string, props: HarnessProps = {}) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Harness {...props} />
    </MemoryRouter>,
  );
}

describe('useHomeUrlState', () => {
  it('loads a report deep link through the URL-owned selection path', async () => {
    const onSelect = vi.fn();
    renderHarness('/?recordId=42&keep=yes', { onSelect });

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(42, true));
    expect(screen.getByTestId('search')).toHaveTextContent('?recordId=42&keep=yes');
  });

  it('replaces invalid core parameters without dropping unrelated query state', async () => {
    renderHarness('/?keep=yes&recordId=0&runFlow=task&runFlowTaskId=%20');

    await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('?keep=yes'));
    expect(screen.getByTestId('source')).toHaveTextContent('none');
    expect(screen.getByTestId('issue')).toHaveTextContent('invalid_record');
  });

  it('canonicalizes the initial default report once history is available', async () => {
    const onSelect = vi.fn();
    renderHarness('/?keep=yes', { defaultRecordId: 1, onSelect });

    await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('?keep=yes&recordId=1'));
    expect(onSelect).toHaveBeenCalledWith(1, false);
  });

  it('pushes user report selections and restores them with Back and Forward', async () => {
    const onSelect = vi.fn();
    renderHarness('/?recordId=1', { initialSelectedRecordId: 1, onSelect });

    fireEvent.click(screen.getByRole('button', { name: 'record 2' }));
    await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('?recordId=2'));
    await waitFor(() => expect(onSelect.mock.calls.map(([recordId]) => recordId)).toEqual([2]));

    fireEvent.click(screen.getByRole('button', { name: 'back' }));
    await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('?recordId=1'));
    await waitFor(() => expect(onSelect.mock.calls.at(-1)?.[0]).toBe(1));
    expect(onSelect.mock.calls.map(([recordId]) => recordId)).toEqual([2, 1]);

    fireEvent.click(screen.getByRole('button', { name: 'forward' }));
    await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('?recordId=2'));
    await waitFor(() => expect(onSelect.mock.calls.at(-1)?.[0]).toBe(2));
    expect(onSelect.mock.calls.map(([recordId]) => recordId)).toEqual([2, 1, 2]);
  });

  it('does not let a repeated current-record navigation block Back restoration', async () => {
    const onSelect = vi.fn();
    renderHarness('/?recordId=1', { initialSelectedRecordId: 1, onSelect });

    fireEvent.click(screen.getByRole('button', { name: 'record 2' }));
    await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('?recordId=2'));
    await waitFor(() => expect(onSelect.mock.calls.map(([recordId]) => recordId)).toEqual([2]));
    const firstRecordTwoKey = screen.getByTestId('location-key').textContent;
    expect(firstRecordTwoKey).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'record 2' }));
    await waitFor(() => expect(screen.getByTestId('location-key').textContent).not.toBe(firstRecordTwoKey));
    const repeatedRecordTwoKey = screen.getByTestId('location-key').textContent;
    expect(repeatedRecordTwoKey).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'back' }));
    await waitFor(() => expect(screen.getByTestId('location-key').textContent).toBe(firstRecordTwoKey));
    expect(screen.getByTestId('location-key').textContent).not.toBe(repeatedRecordTwoKey);

    fireEvent.click(screen.getByRole('button', { name: 'back' }));

    await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('?recordId=1'));
    await waitFor(() => expect(onSelect.mock.calls.map(([recordId]) => recordId)).toEqual([2, 1]));
  });

  it('restores task and history Run Flow state and preserves the report when closing', async () => {
    renderHarness('/?recordId=1&keep=yes', { initialSelectedRecordId: 1 });

    fireEvent.click(screen.getByRole('button', { name: 'task flow' }));
    await waitFor(() => expect(screen.getByTestId('source')).toHaveTextContent('task:task-2'));
    expect(screen.getByTestId('search')).toHaveTextContent(
      '?recordId=1&keep=yes&runFlow=task&runFlowTaskId=task-2',
    );

    fireEvent.click(screen.getByRole('button', { name: 'history flow' }));
    await waitFor(() => expect(screen.getByTestId('source')).toHaveTextContent('history:2'));

    fireEvent.click(screen.getByRole('button', { name: 'close flow' }));
    await waitFor(() => expect(screen.getByTestId('source')).toHaveTextContent('none'));
    expect(screen.getByTestId('search')).toHaveTextContent('?recordId=1&keep=yes');

    fireEvent.click(screen.getByRole('button', { name: 'back' }));
    await waitFor(() => expect(screen.getByTestId('source')).toHaveTextContent('history:2'));
  });

  it('removes a permanent failed report identity but keeps the localized error visible', async () => {
    const onClear = vi.fn();
    const reportError = {
      title: 'Requested content not found',
      message: 'It may have been removed.',
      rawMessage: 'not found',
      status: 404,
      category: 'http_error',
      code: 'not_found',
    } satisfies ParsedApiError;

    await act(async () => {
      renderHarness('/?recordId=404&keep=yes', {
        initialSelectedRecordId: 404,
        reportError,
        onClear,
      });
    });

    await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('?keep=yes'));
    expect(onClear).toHaveBeenCalledWith(true);
  });
});
