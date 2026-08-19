/**
 * Runtime performance contract measurements for Issue #883.
 * Full declared input sizes — do not shrink item/field/event counts to pass.
 * When DSA_RUNTIME_PERF_REPORT is set, measured values are written for the soft gate.
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';
import { createRef, memo, useCallback, useState } from 'react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { HistoryList } from '../../components/history/HistoryList';
import { SettingsField } from '../../components/settings/SettingsField';
import { areSettingsFieldPropsEqual } from '../../components/settings/settingsFieldMemo';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import type { HistoryItem } from '../../types/analysis';
import type { SystemConfigFieldSchema, SystemConfigItem } from '../../types/systemConfig';
import { useAgentChatStore, type Message, type ProgressStep } from '../../stores/agentChatStore';
import { DataTable, type DataTableColumn } from '../../components/common/DataTable';
import { ChatMessageList, type ChatMessageListProps } from '../../components/chat/ChatMessageList';
import DecisionSignalFeedListSection from '../../components/decision-signals/DecisionSignalFeedListSection';
import {
  DEFAULT_LIST_FILTERS,
  mergeWatchlistSignalResponses,
  PAGE_SIZE,
} from '../../components/decision-signals/decisionSignalsPageModel';
import type { DecisionSignalItem } from '../../types/decisionSignals';
import type { AlphaSiftCandidate } from '../../api/alphasift';
import { SCREENING_TEXT } from '../../locales/screening';
import { ScreeningResultsSection } from '../../components/screening/ScreeningResultsSection';
import { HomeDashboardLayout } from '../../components/dashboard/HomeDashboardLayout';
import { resetDashboardLayoutStoreForTests } from '../../stores/dashboardLayoutStore';
import { DASHBOARD_WIDGET_IDS } from '../../types/dashboardLayout';
import { UI_TEXT, type UiTextKey } from '../../i18n/uiText';
import { flushRuntimePerfReport, recordRuntimePerf } from '../runtimePerfReport';
import {
  CHAT_MARKDOWN_MEASUREMENT_BUBBLE_COUNT,
  CHAT_MARKDOWN_REMOUNT_BUDGET,
  DATATABLE_MAX_MOUNTED_ROWS_BUDGET,
  DATATABLE_MEASUREMENT_ITEM_COUNT,
  HISTORY_LIST_MAX_MOUNTED_ROWS_BUDGET,
  HISTORY_LIST_MEASUREMENT_ITEM_COUNT,
  HISTORY_LIST_MEASUREMENT_VIEWPORT_PX,
  HOME_WIDGET_SLOT_BUDGET,
  SCREENING_RESULTS_MAX_MOUNTED_ROWS_BUDGET,
  SCREENING_RESULTS_MEASUREMENT_ITEM_COUNT,
  SETTINGS_FIELD_MEASUREMENT_COUNT,
  SETTINGS_FIELD_SIBLING_RERENDER_BUDGET,
  SIGNALS_LIST_MEASUREMENT_ITEM_COUNT,
  SIGNALS_LIST_PAGE_SIZE,
  SSE_PROGRESS_COMMIT_BUDGET,
  SSE_PROGRESS_MEASUREMENT_EVENT_COUNT,
} from '../runtimeBudgets';

function record(id: string, value: number, unit: string) {
  recordRuntimePerf(id, value, unit);
}

afterEach(() => {
  flushRuntimePerfReport();
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
  describe('data-table-virtualization', () => {
    it(`mounts at most ${DATATABLE_MAX_MOUNTED_ROWS_BUDGET} DataTable rows for ${DATATABLE_MEASUREMENT_ITEM_COUNT} items`, () => {
      type MeasureRow = { id: number; symbol: string };
      const rows: MeasureRow[] = Array.from(
        { length: DATATABLE_MEASUREMENT_ITEM_COUNT },
        (_, index) => ({ id: index + 1, symbol: `SYM${index + 1}` }),
      );
      const columns: DataTableColumn<MeasureRow>[] = [
        { id: 'symbol', header: 'Symbol', cell: (row) => row.symbol },
      ];
      render(
        <DataTable
          caption="Measurement table"
          scrollAreaLabel="Measurement table"
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.id}
          getRowTestId={(row) => `measure-row-${row.id}`}
          emptyState={{ title: 'Empty' }}
        />,
      );

      const region = screen.getByRole('region', { name: 'Measurement table' });
      expect(region).toHaveAttribute('data-data-table-virtualized', 'true');
      expect(region).toHaveAttribute('data-total-count', String(DATATABLE_MEASUREMENT_ITEM_COUNT));

      const mounted = document.querySelectorAll('[data-testid^="measure-row-"]').length;
      record('data-table-virtualization', mounted, 'rows');
      expect(mounted).toBeGreaterThan(0);
      expect(mounted).toBeLessThan(DATATABLE_MEASUREMENT_ITEM_COUNT);
      expect(mounted).toBeLessThanOrEqual(DATATABLE_MAX_MOUNTED_ROWS_BUDGET);
    });
  });

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
      const bodyRenderSpies = Object.fromEntries(
        fieldKeys.map((key) => [key, vi.fn<() => void>()]),
      ) as Record<string, Mock<() => void>>;

      // Count renders of a memo boundary that uses the same equality as SettingsField.
      // React.Profiler is not used: it can fire when the Profiler host re-renders even
      // if the memoized child bails out.
      type CountedProps = {
        item: SystemConfigItem;
        value: string;
        onChange: (key: string, value: string) => void;
      };
      const CountedSettingsField = memo(function CountedSettingsField(props: CountedProps) {
        bodyRenderSpies[props.item.key]();
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
        expect(bodyRenderSpies[key]).toHaveBeenCalledTimes(1);
      }
      const baseline = Object.fromEntries(
        fieldKeys.map((key) => [key, bodyRenderSpies[key].mock.calls.length]),
      );

      fireEvent.click(screen.getByRole('button', { name: 'edit-field-0' }));

      expect(screen.getByRole('textbox', { name: 'Field 0' })).toHaveValue('edited-0');
      expect(screen.getByRole('textbox', { name: 'Field 1' })).toHaveValue('value-1');
      expect(
        screen.getByRole('textbox', { name: `Field ${SETTINGS_FIELD_MEASUREMENT_COUNT - 1}` }),
      ).toHaveValue(`value-${SETTINGS_FIELD_MEASUREMENT_COUNT - 1}`);

      const siblingRerenders = fieldKeys
        .filter((key) => key !== 'FIELD_0')
        .reduce((sum, key) => sum + (bodyRenderSpies[key].mock.calls.length - baseline[key]), 0);
      const editedRerenders = bodyRenderSpies.FIELD_0.mock.calls.length - baseline.FIELD_0;

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

function buildSignal(index: number): DecisionSignalItem {
  return {
    id: index + 1,
    stockCode: `${600000 + (index % 900)}`,
    stockName: `Signal ${index + 1}`,
    market: 'cn',
    sourceType: 'analysis',
    triggerSource: 'web',
    action: 'hold',
    planQuality: 'complete',
    status: 'active',
    createdAt: `2026-03-${String((index % 28) + 1).padStart(2, '0')}T08:00:00Z`,
    presentation: {
      action: 'hold',
      label: 'Hold',
      timestamp: `2026-03-${String((index % 28) + 1).padStart(2, '0')}T08:00:00Z`,
    },
  };
}

function buildScreeningCandidate(index: number): AlphaSiftCandidate {
  return {
    rank: index + 1,
    code: `${600000 + (index % 900)}`,
    name: `Candidate ${index + 1}`,
    industry: 'Demo',
    price: 10 + (index % 20),
    changePct: 0.5,
    score: 70,
    reason: 'Deterministic screening fixture.',
    raw: {},
  };
}

const chatTranslate = (key: UiTextKey, params: Record<string, string | number> = {}) => {
  let value = UI_TEXT.en[key];
  Object.entries(params).forEach(([name, replacement]) => {
    value = value.replace(`{${name}}`, String(replacement));
  });
  return value;
};

describe('signals-list-pagination', () => {
  it(`mounts at most ${SIGNALS_LIST_PAGE_SIZE} cards from ${SIGNALS_LIST_MEASUREMENT_ITEM_COUNT} signals`, () => {
    expect(PAGE_SIZE).toBe(SIGNALS_LIST_PAGE_SIZE);
    const universe = Array.from(
      { length: SIGNALS_LIST_MEASUREMENT_ITEM_COUNT },
      (_, index) => buildSignal(index),
    );
    const page = mergeWatchlistSignalResponses(
      [{ stockCode: 'ALL', response: { items: universe, total: universe.length, page: 1, pageSize: PAGE_SIZE } }],
      1,
    );
    expect(page.items.length).toBe(SIGNALS_LIST_PAGE_SIZE);
    expect(page.items.length).toBeLessThan(SIGNALS_LIST_MEASUREMENT_ITEM_COUNT);

    const { container } = render(
      <UiLanguageProvider initialLanguage="en">
        <DecisionSignalFeedListSection
          filters={DEFAULT_LIST_FILTERS}
          onFiltersChange={vi.fn()}
          onApplyFilters={vi.fn()}
          advancedFilterCount={0}
          appliedSourceReportId={undefined}
          signalScopeLabel="All"
          loading={false}
          error={null}
          onRetry={vi.fn()}
          total={page.total}
          items={page.items}
          selectedId={null}
          onSelect={vi.fn()}
          page={1}
          onPageChange={vi.fn()}
          reassessPanel={null}
          onCreateFirstRule={vi.fn()}
        />
      </UiLanguageProvider>,
    );

    const mounted = container.querySelectorAll('article').length;
    record('signals-list-pagination', mounted, 'cards');
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThanOrEqual(SIGNALS_LIST_PAGE_SIZE);
    expect(SIGNALS_LIST_MEASUREMENT_ITEM_COUNT).toBeGreaterThanOrEqual(150);
  });
});

describe('screening-results-mounted-rows', () => {
  it(`records mounted rows for ${SCREENING_RESULTS_MEASUREMENT_ITEM_COUNT} candidates`, { timeout: 30_000 }, () => {
    const candidates = Array.from(
      { length: SCREENING_RESULTS_MEASUREMENT_ITEM_COUNT },
      (_, index) => buildScreeningCandidate(index),
    );
    const { container } = render(
      <ScreeningResultsSection
        text={SCREENING_TEXT.en}
        language="en"
        candidates={candidates}
        expandedCode={null}
        llmDegraded={false}
        onExpandedCodeChange={() => undefined}
      />,
    );

    const table = container.querySelector('table');
    const bodyRows = table?.tBodies[0]?.querySelectorAll('tr').length ?? 0;
    record('screening-results-mounted-rows', bodyRows, 'rows');
    expect(bodyRows).toBeGreaterThan(0);
    expect(candidates.length).toBe(SCREENING_RESULTS_MEASUREMENT_ITEM_COUNT);
    expect(SCREENING_RESULTS_MEASUREMENT_ITEM_COUNT).toBeGreaterThanOrEqual(150);
    expect(SCREENING_RESULTS_MAX_MOUNTED_ROWS_BUDGET).toBe(40);
  });
});

describe('chat-markdown-isolation', () => {
  it(`keeps ${CHAT_MARKDOWN_MEASUREMENT_BUBBLE_COUNT} prior bubbles mounted across progress updates`, () => {
    const messages: Message[] = Array.from(
      { length: CHAT_MARKDOWN_MEASUREMENT_BUBBLE_COUNT },
      (_, index) => ({
        id: `assistant-${index + 1}`,
        role: index % 2 === 0 ? 'assistant' as const : 'user' as const,
        content: index % 2 === 0 ? `Completed markdown ${index + 1}.` : `User ${index + 1}`,
      }),
    );
    const listProps: ChatMessageListProps = {
      language: 'en',
      t: chatTranslate,
      text: { copied: 'Copied', copy: 'Copy' },
      messages,
      loading: true,
      progressSteps: [{ type: 'thinking', message: 'Planning' }],
      agentUnavailable: false,
      quickQuestions: [],
      onQuickQuestion: vi.fn(),
      quickQuestionsDisabled: false,
      expandedThinking: new Set(),
      onToggleThinking: vi.fn(),
      copiedMessages: new Set(),
      onCopyMessage: vi.fn(),
      onDownloadMessage: vi.fn(),
      messagesViewportRef: createRef<HTMLDivElement>(),
      messagesEndRef: createRef<HTMLDivElement>(),
      onScroll: vi.fn(),
    };

    const { container, rerender } = render(
      <UiLanguageProvider initialLanguage="en">
        <ChatMessageList {...listProps} />
      </UiLanguageProvider>,
    );
    const before = [...container.querySelectorAll('[data-chat-message-id]')];
    expect(before).toHaveLength(CHAT_MARKDOWN_MEASUREMENT_BUBBLE_COUNT);

    const nextProgress: ProgressStep[] = [
      { type: 'thinking', message: 'Planning' },
      { type: 'tool_start', tool: 'search', display_name: 'Search' },
    ];
    rerender(
      <UiLanguageProvider initialLanguage="en">
        <ChatMessageList {...listProps} progressSteps={nextProgress} />
      </UiLanguageProvider>,
    );
    const after = [...container.querySelectorAll('[data-chat-message-id]')];
    const remounts = after.reduce((count, node, index) => (
      node === before[index] ? count : count + 1
    ), 0);
    record('chat-markdown-isolation', remounts, 'remounts');
    expect(after).toHaveLength(CHAT_MARKDOWN_MEASUREMENT_BUBBLE_COUNT);
    expect(remounts).toBeLessThanOrEqual(CHAT_MARKDOWN_REMOUNT_BUDGET);
    expect(screen.getByTestId('chat-live-progress')).toBeInTheDocument();
  });
});

describe('home-widget-slots', () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetDashboardLayoutStoreForTests();
  });

  it(`keeps ${HOME_WIDGET_SLOT_BUDGET} independent Home widget slots`, () => {
    render(
      <MemoryRouter>
        <UiLanguageProvider initialLanguage="en">
          <HomeDashboardLayout
            widgets={{
              watchlist: <div>Watchlist body</div>,
              portfolio_health: <div>Health body</div>,
              alerts: <div>Alerts body</div>,
              recent_reports: <div>Reports body</div>,
            }}
          />
        </UiLanguageProvider>
      </MemoryRouter>,
    );

    const slots = document.querySelectorAll('[data-testid^="home-dashboard-widget-"]').length;
    record('home-widget-slots', slots, 'slots');
    expect(DASHBOARD_WIDGET_IDS).toHaveLength(HOME_WIDGET_SLOT_BUDGET);
    expect(slots).toBeGreaterThanOrEqual(HOME_WIDGET_SLOT_BUDGET);
  });
});

