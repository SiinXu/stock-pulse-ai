import { useMemo, useState } from 'react';
import {
  DEFAULT_WHAT_IF_DRAFT,
  DEFAULT_WHAT_IF_MAX_TURNS,
  HYPOTHETICAL_ASSUMPTION_MARKER,
  buildWhatIfAssumption,
  countWhatIfTurnsInMessages,
  isWhatIfLimitReached,
  mergeWhatIfIntoContext,
  type WhatIfDraftState,
} from './whatIfScenario';

export type ChatWhatIfSendPlan =
  | {
      ok: true;
      message: string;
      context: Record<string, unknown> | undefined;
    }
  | {
      ok: false;
      errorKey: 'chat.whatIf.limitMessage' | 'chat.whatIf.magnitudeInvalid';
      errorParams?: Record<string, string | number>;
    };

export function useChatWhatIf(messages: Array<{ role: string; content: string }>) {
  const [draftBase, setDraftBase] = useState<Omit<WhatIfDraftState, 'turnCount'>>({
    enabled: DEFAULT_WHAT_IF_DRAFT.enabled,
    dimension: DEFAULT_WHAT_IF_DRAFT.dimension,
    direction: DEFAULT_WHAT_IF_DRAFT.direction,
    magnitude: DEFAULT_WHAT_IF_DRAFT.magnitude,
    currencyPair: DEFAULT_WHAT_IF_DRAFT.currencyPair,
  });

  const turnCount = useMemo(
    () => countWhatIfTurnsInMessages(messages),
    [messages],
  );

  const whatIfDraft: WhatIfDraftState = useMemo(
    () => ({ ...draftBase, turnCount }),
    [draftBase, turnCount],
  );

  const setWhatIfDraft = (
    next: WhatIfDraftState | ((prev: WhatIfDraftState) => WhatIfDraftState),
  ) => {
    setDraftBase((prevBase) => {
      const prev: WhatIfDraftState = { ...prevBase, turnCount };
      const resolved = typeof next === 'function' ? next(prev) : next;
      const { turnCount: _ignored, ...rest } = resolved;
      return rest;
    });
  };

  const planWhatIfSend = (
    msgText: string,
    baseContext: Record<string, unknown> | null | undefined,
  ): ChatWhatIfSendPlan => {
    if (!whatIfDraft.enabled) {
      return {
        ok: true,
        message: msgText,
        context: baseContext ?? undefined,
      };
    }
    if (isWhatIfLimitReached(whatIfDraft)) {
      return {
        ok: false,
        errorKey: 'chat.whatIf.limitMessage',
        errorParams: { max: DEFAULT_WHAT_IF_MAX_TURNS },
      };
    }
    if (!buildWhatIfAssumption(whatIfDraft)) {
      return {
        ok: false,
        errorKey: 'chat.whatIf.magnitudeInvalid',
      };
    }
    return {
      ok: true,
      message: `${HYPOTHETICAL_ASSUMPTION_MARKER}\n${msgText}`,
      context: mergeWhatIfIntoContext(baseContext, whatIfDraft),
    };
  };

  return {
    whatIfDraft,
    setWhatIfDraft,
    planWhatIfSend,
  };
}
