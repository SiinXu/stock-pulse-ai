import React from 'react';
import { FlaskConical } from 'lucide-react';
import { InlineAlert, Switch } from '../common';
import { cn } from '../../utils/cn';
import type { UiTextKey } from '../../i18n/uiText';
import {
  DEFAULT_WHAT_IF_MAX_TURNS,
  type WhatIfDimension,
  type WhatIfDirection,
  type WhatIfDraftState,
  isWhatIfLimitReached,
  parseMagnitude,
} from './whatIfScenario';

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

export interface WhatIfScenarioPanelProps {
  t: Translate;
  draft: WhatIfDraftState;
  onChange: (next: WhatIfDraftState) => void;
  disabled?: boolean;
}

const DIMENSION_OPTIONS: Array<{ value: WhatIfDimension; labelKey: UiTextKey }> = [
  { value: 'index_move', labelKey: 'chat.whatIf.dimension.index' },
  { value: 'fx_rate', labelKey: 'chat.whatIf.dimension.fx' },
  { value: 'interest_rate', labelKey: 'chat.whatIf.dimension.rate' },
  { value: 'earnings', labelKey: 'chat.whatIf.dimension.earnings' },
];

export function WhatIfScenarioPanel({ t, draft, onChange, disabled = false }: WhatIfScenarioPanelProps): React.ReactElement {
  const limitReached = isWhatIfLimitReached(draft);
  const magnitudeInvalid = draft.enabled && draft.dimension !== 'earnings' && parseMagnitude(draft.magnitude) === null;
  const setField = <K extends keyof WhatIfDraftState>(key: K, value: WhatIfDraftState[K]) => {
    onChange({ ...draft, [key]: value });
  };
  const onDimensionChange = (dimension: WhatIfDimension) => {
    if (dimension === 'earnings') {
      onChange({
        ...draft,
        dimension,
        direction: draft.direction === 'beat' || draft.direction === 'miss' || draft.direction === 'inline' ? draft.direction : 'miss',
      });
      return;
    }
    onChange({
      ...draft,
      dimension,
      direction: draft.direction === 'up' || draft.direction === 'down' ? draft.direction : 'down',
    });
  };
  return (
    <div className={cn('border-t border-subtle bg-card/70 px-4 py-3 md:px-6', draft.enabled && 'bg-warning/5')} data-testid="chat-what-if-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <FlaskConical className="h-4 w-4 shrink-0 text-warning" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">{t('chat.whatIf.title')}</p>
            <p className="text-xs text-secondary-text">{t('chat.whatIf.subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-secondary-text" data-testid="chat-what-if-turn-count">
            {t('chat.whatIf.turns', { used: draft.turnCount, max: DEFAULT_WHAT_IF_MAX_TURNS })}
          </span>
          <Switch
            checked={draft.enabled}
            onCheckedChange={(enabled) => setField('enabled', enabled)}
            disabled={disabled || limitReached}
            aria-label={t('chat.whatIf.toggle')}
            testId="chat-what-if-toggle"
          />
        </div>
      </div>
      {draft.enabled ? (
        <div className="mt-3 space-y-3" data-testid="chat-what-if-form">
          <InlineAlert variant="warning" size="compact" title={t('chat.whatIf.bannerTitle')} message={t('chat.whatIf.bannerMessage')} />
          {limitReached ? (
            <InlineAlert variant="danger" size="compact" title={t('chat.whatIf.limitTitle')} message={t('chat.whatIf.limitMessage', { max: DEFAULT_WHAT_IF_MAX_TURNS })} />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="flex min-w-0 flex-col gap-1 text-xs text-secondary-text">
                {t('chat.whatIf.dimensionLabel')}
                <select className="rounded-md border border-subtle bg-background px-2 py-1.5 text-sm text-foreground" value={draft.dimension} disabled={disabled} onChange={(e) => onDimensionChange(e.target.value as WhatIfDimension)} data-testid="chat-what-if-dimension">
                  {DIMENSION_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{t(option.labelKey)}</option>
                  ))}
                </select>
              </label>
              {draft.dimension === 'earnings' ? (
                <label className="flex min-w-0 flex-col gap-1 text-xs text-secondary-text">
                  {t('chat.whatIf.outcomeLabel')}
                  <select className="rounded-md border border-subtle bg-background px-2 py-1.5 text-sm text-foreground" value={draft.direction} disabled={disabled} onChange={(e) => setField('direction', e.target.value as WhatIfDirection)} data-testid="chat-what-if-earnings">
                    <option value="beat">{t('chat.whatIf.earnings.beat')}</option>
                    <option value="miss">{t('chat.whatIf.earnings.miss')}</option>
                    <option value="inline">{t('chat.whatIf.earnings.inline')}</option>
                  </select>
                </label>
              ) : (
                <>
                  <label className="flex min-w-0 flex-col gap-1 text-xs text-secondary-text">
                    {t('chat.whatIf.directionLabel')}
                    <select className="rounded-md border border-subtle bg-background px-2 py-1.5 text-sm text-foreground" value={draft.direction === 'up' || draft.direction === 'down' ? draft.direction : 'down'} disabled={disabled} onChange={(e) => setField('direction', e.target.value as WhatIfDirection)} data-testid="chat-what-if-direction">
                      <option value="up">{t('chat.whatIf.direction.up')}</option>
                      <option value="down">{t('chat.whatIf.direction.down')}</option>
                    </select>
                  </label>
                  <label className="flex min-w-0 flex-col gap-1 text-xs text-secondary-text">
                    {t(draft.dimension === 'interest_rate' ? 'chat.whatIf.magnitudeBpLabel' : 'chat.whatIf.magnitudePctLabel')}
                    <input type="number" min={0} step="any" className="rounded-md border border-subtle bg-background px-2 py-1.5 text-sm text-foreground" value={draft.magnitude} disabled={disabled} onChange={(e) => setField('magnitude', e.target.value)} data-testid="chat-what-if-magnitude" />
                  </label>
                </>
              )}
              {draft.dimension === 'fx_rate' ? (
                <label className="flex min-w-0 flex-col gap-1 text-xs text-secondary-text">
                  {t('chat.whatIf.fxPairLabel')}
                  <input type="text" className="rounded-md border border-subtle bg-background px-2 py-1.5 text-sm text-foreground" value={draft.currencyPair} disabled={disabled} onChange={(e) => setField('currencyPair', e.target.value)} data-testid="chat-what-if-fx-pair" />
                </label>
              ) : null}
            </div>
          )}
          {magnitudeInvalid ? <p className="text-xs text-danger" data-testid="chat-what-if-magnitude-error">{t('chat.whatIf.magnitudeInvalid')}</p> : null}
          <p className="text-xs text-secondary-text">{t('chat.whatIf.extraTurnHint')}</p>
        </div>
      ) : null}
    </div>
  );
}
