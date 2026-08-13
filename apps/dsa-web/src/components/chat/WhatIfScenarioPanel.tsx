import React from 'react';
import { Link } from 'react-router-dom';
import { FlaskConical } from 'lucide-react';
import { Button, InlineAlert, Input, Select, Switch } from '../common';
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
  /** Analysis workbench launch href for the active stock; null when no stock context. */
  promoteHref?: string | null;
}

const DIMENSION_OPTIONS: Array<{ value: WhatIfDimension; labelKey: UiTextKey }> = [
  { value: 'index_move', labelKey: 'chat.whatIf.dimension.index' },
  { value: 'fx_rate', labelKey: 'chat.whatIf.dimension.fx' },
  { value: 'interest_rate', labelKey: 'chat.whatIf.dimension.rate' },
  { value: 'earnings', labelKey: 'chat.whatIf.dimension.earnings' },
];

export function WhatIfScenarioPanel({
  t,
  draft,
  onChange,
  disabled = false,
  promoteHref = null,
}: WhatIfScenarioPanelProps): React.ReactElement {
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
    <div className={cn('space-y-3', draft.enabled && '[&_[data-testid=chat-what-if-trigger]]:text-warning')} data-testid="chat-what-if-panel">
      <div
        className="flex h-9 min-w-0 items-center gap-2 rounded-lg px-2 text-xs text-foreground"
        data-testid="chat-what-if-trigger"
      >
        <div className="flex min-w-0 items-center gap-2">
          <FlaskConical className="h-4 w-4 shrink-0 text-warning" aria-hidden />
          <span className="truncate font-medium">{t('chat.whatIf.title')}</span>
        </div>
        <span className="ml-auto whitespace-nowrap text-muted-text" data-testid="chat-what-if-turn-count">
          {draft.turnCount}/{DEFAULT_WHAT_IF_MAX_TURNS}
        </span>
        <Switch
          checked={draft.enabled}
          onCheckedChange={(enabled) => setField('enabled', enabled)}
          disabled={disabled || limitReached}
          aria-label={t('chat.whatIf.toggle')}
          testId="chat-what-if-toggle"
        />
      </div>
      {draft.enabled ? (
        <div className="space-y-3 border-t border-subtle pt-3" data-testid="chat-what-if-form">
          <InlineAlert variant="warning" size="compact" title={t('chat.whatIf.bannerTitle')} message={t('chat.whatIf.bannerMessage')} />
          {limitReached ? (
            <InlineAlert variant="danger" size="compact" title={t('chat.whatIf.limitTitle')} message={t('chat.whatIf.limitMessage', { max: DEFAULT_WHAT_IF_MAX_TURNS })} />
          ) : (
            <div className="grid grid-cols-2 gap-3" data-testid="chat-what-if-fields">
              <div className="min-w-0" data-testid="chat-what-if-dimension">
                <Select
                  label={t('chat.whatIf.dimensionLabel')}
                  value={draft.dimension}
                  disabled={disabled}
                  onChange={(value) => onDimensionChange(value as WhatIfDimension)}
                  options={DIMENSION_OPTIONS.map((option) => ({ value: option.value, label: t(option.labelKey) }))}
                  className="w-full"
                />
              </div>
              {draft.dimension === 'earnings' ? (
                <div className="min-w-0" data-testid="chat-what-if-earnings">
                  <Select
                    label={t('chat.whatIf.outcomeLabel')}
                    value={draft.direction}
                    disabled={disabled}
                    onChange={(value) => setField('direction', value as WhatIfDirection)}
                    options={[
                      { value: 'beat', label: t('chat.whatIf.earnings.beat') },
                      { value: 'miss', label: t('chat.whatIf.earnings.miss') },
                      { value: 'inline', label: t('chat.whatIf.earnings.inline') },
                    ]}
                    className="w-full"
                  />
                </div>
              ) : (
                <>
                  <div className="min-w-0" data-testid="chat-what-if-direction">
                    <Select
                      label={t('chat.whatIf.directionLabel')}
                      value={draft.direction === 'up' || draft.direction === 'down' ? draft.direction : 'down'}
                      disabled={disabled}
                      onChange={(value) => setField('direction', value as WhatIfDirection)}
                      options={[
                        { value: 'up', label: t('chat.whatIf.direction.up') },
                        { value: 'down', label: t('chat.whatIf.direction.down') },
                      ]}
                      className="w-full"
                    />
                  </div>
                  <Input
                    label={t(draft.dimension === 'interest_rate' ? 'chat.whatIf.magnitudeBpLabel' : 'chat.whatIf.magnitudePctLabel')}
                    type="number"
                    min={0}
                    step="any"
                    value={draft.magnitude}
                    disabled={disabled}
                    onChange={(event) => setField('magnitude', event.target.value)}
                    fieldClassName="min-w-0"
                    data-testid="chat-what-if-magnitude"
                  />
                </>
              )}
              {draft.dimension === 'fx_rate' ? (
                <Input
                  label={t('chat.whatIf.fxPairLabel')}
                  type="text"
                  value={draft.currencyPair}
                  disabled={disabled}
                  onChange={(event) => setField('currencyPair', event.target.value)}
                  fieldClassName="min-w-0"
                  data-testid="chat-what-if-fx-pair"
                />
              ) : null}
            </div>
          )}
          {magnitudeInvalid ? <p className="text-xs text-danger" data-testid="chat-what-if-magnitude-error">{t('chat.whatIf.magnitudeInvalid')}</p> : null}
          <p className="text-xs text-secondary-text">{t('chat.whatIf.extraTurnHint')}</p>
          <div className="space-y-1.5 border-t border-subtle pt-3" data-testid="chat-what-if-promote">
            <p className="text-xs text-secondary-text">{t('chat.whatIf.promoteHint')}</p>
            {promoteHref ? (
              disabled ? (
                <Button
                  variant="secondary"
                  size="compact"
                  disabled
                >
                  {t('chat.whatIf.promote')}
                </Button>
              ) : (
                <Link
                  to={promoteHref}
                  className={cn(
                    'control-hit-target inline-flex h-5 min-w-5 items-center justify-center gap-1.5 rounded-md',
                    'border border-border bg-hover px-2 text-xs font-medium text-foreground shadow-soft-card',
                    'transition-colors hover:bg-subtle-hover dark:bg-border dark:hover:bg-subtle-active',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25',
                  )}
                >
                  {t('chat.whatIf.promote')}
                </Link>
              )
            ) : (
              <p className="text-xs text-muted-text">
                {t('chat.whatIf.promoteNeedStock')}
              </p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
