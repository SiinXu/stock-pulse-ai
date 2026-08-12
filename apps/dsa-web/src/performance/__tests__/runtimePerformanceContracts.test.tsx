/**
 * Runtime performance contract measurements for Issue #883.
 * Full declared input sizes — do not shrink item/field/event counts to pass.
 * When DSA_RUNTIME_PERF_REPORT is set, measured values are written for the soft gate.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import { writeFileSync, mkdirSync } from 'node:fs';
// @ts-expect-error Node types are intentionally excluded from the browser tsconfig.
import path from 'node:path';
import type { ReactElement } from 'react';
import { memo, useCallback, useState } from 'react';
import { HistoryList } from '../../components/history/HistoryList';
import {
  SettingsField,
  areSettingsFieldPropsEqual,
} from '../../components/settings/SettingsField';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import type { HistoryItem } from '../../types/analysis';
import type { SystemConfigFieldSchema, SystemConfigItem } from '../../types/systemConfig';
import { useAgentChatStore } from '../../stores/agentChatStore';
import {
  HISTORY_LIST_MAX_MOUNTED_ROWS_BUDGET,
  HISTORY_LIST_MEASUREMENT_ITEM_COUNT,
  HISTORY_LIST_MEASUREMENT_VIEWPORT_PX,
  SETTINGS_FIELD_MEASUREMENT_COUNT,
  SETTINGS_FIELD_SIBLING_RERENDER_BUDGET,
  SSE_PROGRESS_COMMIT_BUDGET,
  SSE_PROGRESS_MEASUREMENT_EVENT_COUNT,
} from '../runtimeBudgets';

type Measurement = { id: string; value: number; unit: string };
const measurements: Measurement[] = [];

function record(id: string, value: number, unit: string) {
  const existing = measurements.findIndex((entry) => entry.id === id);
  if (existing >= 0) measurements[existing] = { id, value, unit };
  else measurements.push({ id, value, unit });
}

afterEach(() => {
  // process is available under Vitest; browser tsconfig omits Node types.
  const reportPath = (globalThis as { process?: { env?: Record<string, string | undefined> } })
    .process
    ?.env
    ?.DSA_RUNTIME_PERF_REPORT;
  if (reportPath && measurements.length > 0) {
    mkdirSync(path.dirname(reportPath), { recursive: true });
    writeFileSync(
      reportPath,
      JSON.stringify({ measuredAt: new Date().toISOString(), measurements }, null, 2),
    );
  }
});

function buildHistoryItems(count: number): HistoryItem[] {
  return Array.from({ length: count }, (_, index) => ({
    id: index + 1,
    queryId: `q-${index + 1}`,
    stockCode: `${600000 + (index % 900)}`,
    stockName: `Stock ${index + 1}`,
    sentimentScore: 50 + (index % 40),
    operationAdvice: '持有',
    createdAt: `2026-03-${String((index % 28) + 1).padStart(2, '0')}T08:00:00Z`,
  }));
}

const historyBaseProps = {
  isLoading: false,
  isLoadingMore: false,
  hasMore: false,
  selectedIds: new Set<number>(),
  onItemClick: vi.fn(),
  onLoadMore: vi.fn(),
  onToggleItemSelection: vi.fn(),
  onToggleSelectAll: vi.fn(),
  onDeleteSelected: vi.fn(),
};

describe('runtime performance contracts (#883)', () => {
  describe('history-list-virtualization', () => {
    it(`mounts at most ${HISTORY_LIST_MAX_MOUNTED_ROWS_BUDGET} rows for ${HISTORY_LIST_MEASUREMENT_ITEM_COUNT} items`, () => {
      const items = buildHistoryItems(HISTORY_LIST_MEASUREMENT_ITEM_COUNT);
      const { container } = render(
        <div style={{ height: HISTORY_LIST_MEASUREMENT_VIEWPORT_PX }}>
          <HistoryList {...historyBaseProps} items={items} />
        </div>,
      );

      // Window math uses estimated row height when the viewport has not yet
      // reported a clientHeight (jsdom). Virtualization still bounds mounts.
      const windowNode = screen.getByTestId('history-list-window');
      expect(windowNode).toHaveAttribute('data-virtualized', 'true');
      expect(windowNode).toHaveAttribute('data-total-count', String(HISTORY_LIST_MEASUREMENT_ITEM_COUNT));

      const mounted = container.querySelectorAll('[data-history-list-item]').length;
      record('history-list-virtualization', mounted, 'rows');
      expect(mounted).toBeGreaterThan(0);
      expect(mounted).toBeLessThan(HISTORY_LIST_MEASUREMENT_ITEM_COUNT);
      expect(mounted).toBeLessThanOrEqual(HISTORY_LIST_MAX_MOUNTED_ROWS_BUDGET);
    });
  });

  describe('settings-field-isolation', () => {
    it(`re-renders 0 siblings when one of ${SETTINGS_FIELD_MEASUREMENT_COUNT} fields changes`, { timeout: 20_000 }, () => {
      const fieldKeys = Array.from(
        { length: SETTINGS_FIELD_MEASUREMENT_COUNT },
        (_, index) => `FIELD_${index}`,
      );
      // Build stable schema objects once; identity must stay fixed so memo can work.
      const schemas: Record<string, SystemConfigFieldSchema> = {};
      for (let index = 0; index < fieldKeys.length; index += 1) {
        const key = fieldKeys[index];
        schemas[key] = {
          key,
          title: `Field ${index}`,
          category: 'base',
          isSensitive: false,
          isRequired: false,
          isEditable: true,
          validation: {},
          displayOrder: index + 1,
          dataType: 'string',
          uiControl: 'text',
          options: [],
        };
      }
      const onChange = vi.fn();
      const bodyRenderCounts = Object.fromEntries(fieldKeys.map((key) => [key, 0])) as Record<string, number>;

      // Count renders of a memo boundary that uses the same equality as SettingsField.
      // React.Profiler is not used: it can fire when the Profiler host re-renders even
      // if the memoized child bails out.
      type CountedProps = {
        item: SystemConfigItem;
        value: string;
        onChange: (key: string, value: string) => void;
      };
      const CountedSettingsField = memo(function CountedSettingsField(props: CountedProps) {
        bodyRenderCounts[props.item.key] += 1;
        return (
          <SettingsField
            item={props.item}
            value={props.value}
            onChange={props.onChange}
          />
        );
      }, (previous, next) => areSettingsFieldPropsEqual(previous, next));

      function Host(): ReactElement {
        const [values, setValues] = useState(() =>
          Object.fromEntries(fieldKeys.map((key, index) => [key, `value-${index}`])),
        );
        const handleEdit = useCallback(() => {
          setValues((current) => ({ ...current, FIELD_0: 'edited-0' }));
        }, []);
        return (
          <UiLanguageProvider initialLanguage="en">
            <button type="button" onClick={handleEdit}>edit-field-0</button>
            {fieldKeys.map((key) => {
              const item: SystemConfigItem = {
                key,
                value: values[key],
                rawValueExists: true,
                isMasked: false,
                schema: schemas[key],
              };
              return (
                <CountedSettingsField
                  key={key}
                  item={item}
                  value={values[key]}
                  onChange={onChange}
                />
              );
            })}
          </UiLanguageProvider>
        );
      }

      render(<Host />);
      for (const key of fieldKeys) {
        expect(bodyRenderCounts[key]).toBe(1);
      }
      const baseline = { ...bodyRenderCounts };

      fireEvent.click(screen.getByRole('button', { name: 'edit-field-0' }));

      expect(screen.getByRole('textbox', { name: 'Field 0' })).toHaveValue('edited-0');
      expect(screen.getByRole('textbox', { name: 'Field 1' })).toHaveValue('value-1');
      expect(
        screen.getByRole('textbox', { name: `Field ${SETTINGS_FIELD_MEASUREMENT_COUNT - 1}` }),
      ).toHaveValue(`value-${SETTINGS_FIELD_MEASUREMENT_COUNT - 1}`);

      const siblingRerenders = fieldKeys
        .filter((key) => key !== 'FIELD_0')
        .reduce((sum, key) => sum + (bodyRenderCounts[key] - baseline[key]), 0);
      const editedRerenders = bodyRenderCounts.FIELD_0 - baseline.FIELD_0;

      record('settings-field-isolation', siblingRerenders, 'renders');
      expect(editedRerenders).toBeGreaterThan(0);
      expect(siblingRerenders).toBeLessThanOrEqual(SETTINGS_FIELD_SIBLING_RERENDER_BUDGET);
      expect(fieldKeys.length).toBe(SETTINGS_FIELD_MEASUREMENT_COUNT);
      expect(SETTINGS_FIELD_MEASUREMENT_COUNT).toBeGreaterThanOrEqual(40);
    });
  });

  describe('sse-progress-batching', () => {
    const encoder = new TextEncoder();

    beforeEach(() => {
      localStorage.clear();
      sessionStorage.clear();
      useAgentChatStore.setState({
        messages: [],
        selectedSkillIds: null,
        loading: false,
        progressSteps: [],
        sessionId: 'session-perf',
        sessions: [],
        sessionsLoading: false,
        chatError: null,
        currentRoute: '/chat',
        completionBadge: false,
        hasInitialLoad: true,
        abortController: null,
        lastFailedRequest: null,
      });
      vi.clearAllMocks();
    });

    it(`batches ${SSE_PROGRESS_MEASUREMENT_EVENT_COUNT} progress events into <= ${SSE_PROGRESS_COMMIT_BUDGET} commits`, async () => {
      const rafCallbacks: FrameRequestCallback[] = [];
      vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
        rafCallbacks.push(cb);
        return rafCallbacks.length;
      });
      vi.stubGlobal('cancelAnimationFrame', (id: number) => {
        rafCallbacks[id - 1] = () => {};
      });

      const progressLines = Array.from(
        { length: SSE_PROGRESS_MEASUREMENT_EVENT_COUNT },
        (_, index) => `data: ${JSON.stringify({ type: 'stage_start', stage: `s${index}` })}`,
      );
      progressLines.push(`data: ${JSON.stringify({ type: 'done', success: true, content: 'ok' })}`);

      const { agentApi } = await import('../../api/agent');
      vi.spyOn(agentApi, 'chatStream').mockResolvedValue(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode(`${progressLines.join('\n')}\n`));
              controller.close();
            },
          }),
          { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
        ),
      );
      vi.spyOn(agentApi, 'getChatSessions').mockResolvedValue([]);
      vi.spyOn(agentApi, 'getChatSessionMessages').mockResolvedValue({
        session_id: 'session-perf',
        messages: [],
        session_state: { selected_skill_ids: null },
        turn_identity_supported: true,
      });

      let progressCommits = 0;
      const unsubscribe = useAgentChatStore.subscribe((state, previous) => {
        if (state.progressSteps !== previous.progressSteps) {
          progressCommits += 1;
        }
      });

      const streamPromise = useAgentChatStore.getState().startStream({
        message: 'measure batching',
        session_id: 'session-perf',
      });

      await act(async () => {
        while (rafCallbacks.length > 0) {
          const batch = rafCallbacks.splice(0, rafCallbacks.length);
          for (const callback of batch) callback(performance.now());
        }
        await streamPromise;
        while (rafCallbacks.length > 0) {
          const batch = rafCallbacks.splice(0, rafCallbacks.length);
          for (const callback of batch) callback(performance.now());
        }
      });

      unsubscribe();
      record('sse-progress-batching', progressCommits, 'commits');
      expect(progressCommits).toBeGreaterThan(0);
      expect(progressCommits).toBeLessThan(SSE_PROGRESS_MEASUREMENT_EVENT_COUNT);
      expect(progressCommits).toBeLessThanOrEqual(SSE_PROGRESS_COMMIT_BUDGET);
      const messages = useAgentChatStore.getState().messages;
      const assistant = messages.find((message) => message.role === 'assistant');
      expect(assistant?.thinkingSteps?.length).toBe(SSE_PROGRESS_MEASUREMENT_EVENT_COUNT);

      vi.unstubAllGlobals();
    });

    it('keeps stopStream callable during a long in-flight stream', async () => {
      let releaseStream: (() => void) | undefined;
      const hold = new Promise<void>((resolve) => {
        releaseStream = resolve;
      });

      const { agentApi } = await import('../../api/agent');
      vi.spyOn(agentApi, 'chatStream').mockResolvedValue(
        new Response(
          new ReadableStream({
            async start(controller) {
              controller.enqueue(
                encoder.encode(`data: ${JSON.stringify({ type: 'stage_start', stage: 'intel' })}\n`),
              );
              await hold;
              controller.enqueue(
                encoder.encode(`data: ${JSON.stringify({ type: 'done', success: true, content: 'done' })}\n`),
              );
              controller.close();
            },
          }),
          { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
        ),
      );
      vi.spyOn(agentApi, 'getChatSessions').mockResolvedValue([]);
      vi.spyOn(agentApi, 'getChatSessionMessages').mockResolvedValue({
        session_id: 'session-perf',
        messages: [],
        session_state: { selected_skill_ids: null },
        turn_identity_supported: true,
      });

      const streamPromise = useAgentChatStore.getState().startStream({
        message: 'stop responsiveness',
        session_id: 'session-perf',
      });

      await act(async () => {
        await Promise.resolve();
      });

      expect(useAgentChatStore.getState().loading).toBe(true);
      expect(useAgentChatStore.getState().abortController).not.toBeNull();

      act(() => {
        useAgentChatStore.getState().stopStream();
      });
      expect(useAgentChatStore.getState().progressSteps).toEqual([]);

      releaseStream?.();
      await act(async () => {
        await streamPromise;
      });
    });
  });
});
