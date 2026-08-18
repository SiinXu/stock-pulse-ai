import { describe, expect, it } from 'vitest';
import { UI_TEXT, type UiTextKey } from '../../../i18n/uiText';
import type { ProgressStep } from '../../../stores/agentChatStore';
import {
  advanceTraceRowModels,
  createTraceRowCache,
  getStepText,
  getStageDetail,
  getToolDetail,
  getTracePresentation,
  getTraceRowKeys,
  resetChatThinkingTraceStats,
  snapshotChatThinkingTraceStats,
} from '../chatThinkingTrace';

const t = (key: UiTextKey) => UI_TEXT.en[key];
const STREAM_N = 200;

function naiveRenderWork(steps: ProgressStep[]): void {
  getTraceRowKeys(steps);
  for (const step of steps) {
    getTracePresentation(step, false);
    getStepText(step, t);
    getToolDetail(step);
    getStageDetail(step);
  }
}

function makeStep(index: number): ProgressStep {
  return {
    type: 'thinking',
    step: index + 1,
    message: `Planning ${index + 1}`,
  };
}

describe('chatThinkingTrace incremental cache', () => {
  it('keeps per-append derivation work constant at N=200 while naive rebuild grows with N', () => {
    const steps: ProgressStep[] = [];
    const naiveIdentity: number[] = [];
    const incrementalIdentity: number[] = [];
    const incrementalDerive: number[] = [];
    const cache = createTraceRowCache();

    for (let index = 0; index < STREAM_N; index += 1) {
      steps.push(makeStep(index));

      resetChatThinkingTraceStats();
      naiveRenderWork(steps);
      naiveIdentity.push(snapshotChatThinkingTraceStats().identity);

      resetChatThinkingTraceStats();
      advanceTraceRowModels(cache, [...steps], t);
      const after = snapshotChatThinkingTraceStats();
      incrementalIdentity.push(after.identity);
      incrementalDerive.push(after.derive);
    }

    const naiveTotal = naiveIdentity.reduce((sum, value) => sum + value, 0);
    const incrementalTotal = incrementalIdentity.reduce((sum, value) => sum + value, 0);

    expect(naiveIdentity[0]).toBe(1);
    expect(naiveIdentity[STREAM_N - 1]).toBe(STREAM_N);
    expect(naiveTotal).toBe((STREAM_N * (STREAM_N + 1)) / 2);

    expect(incrementalIdentity[0]).toBe(1);
    expect(new Set(incrementalIdentity.slice(1))).toEqual(new Set([1]));
    expect(new Set(incrementalDerive)).toEqual(new Set([1]));
    expect(incrementalTotal).toBe(STREAM_N);
    expect(incrementalTotal).toBeLessThan(naiveTotal);
  });

  it('matches full-rebuild row keys when appending, prepending, and repeating identities', () => {
    const cache = createTraceRowCache();
    const failed: ProgressStep = {
      type: 'tool_done',
      tool: 'search',
      display_name: 'Search',
      success: false,
      duration: 0.4,
    };
    const success: ProgressStep = {
      type: 'tool_done',
      tool: 'lookup',
      display_name: 'Lookup',
      success: true,
      duration: 0.2,
    };
    const duplicate: ProgressStep = {
      type: 'thinking',
      step: 1,
      message: 'Planning',
    };
    const duplicateAgain: ProgressStep = {
      type: 'thinking',
      step: 1,
      message: 'Planning',
    };

    const first = [failed];
    expect(advanceTraceRowModels(cache, first, t).map((row) => row.rowKey)).toEqual(
      getTraceRowKeys(first),
    );

    const prepended = [success, failed];
    expect(advanceTraceRowModels(cache, prepended, t).map((row) => row.rowKey)).toEqual(
      getTraceRowKeys(prepended),
    );

    const withDuplicates = [success, failed, duplicate, duplicateAgain];
    expect(advanceTraceRowModels(cache, withDuplicates, t).map((row) => row.rowKey)).toEqual(
      getTraceRowKeys(withDuplicates),
    );
  });
});
