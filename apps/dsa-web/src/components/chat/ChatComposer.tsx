import React, { lazy, Suspense } from 'react';
import { ChevronDown, FlaskConical, Minimize2, RefreshCw, Send, SlidersHorizontal, Square } from 'lucide-react';
import type { SkillInfo } from '../../api/agent';
import type { ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  Button,
  Checkbox,
  IconButton,
  InlineAlert,
  Loading,
  Tooltip,
} from '../common';
import { cn } from '../../utils/cn';
import { getStrategyDisplay } from '../../utils/strategyDisplay';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';
import type { WhatIfDraftState } from './whatIfScenario';

const WhatIfScenarioPanel = lazy(() =>
  import('./WhatIfScenarioPanel').then((module) => ({ default: module.WhatIfScenarioPanel })),
);

type Translate = (key: UiTextKey, params?: Record<string, string | number>) => string;

export interface ChatComposerProps {
  language: UiLanguage;
  t: Translate;
  sessionError: ParsedApiError | null;
  sessionLoading: boolean;
  chatError: ParsedApiError | null;
  lastFailedRequest: unknown;
  onRetryLastStream: () => void;
  isFollowUpContextLoading: boolean;
  contextCompressionEnabled: boolean;
  contextCompressionLoaded: boolean;
  contextCompressionSaving: boolean;
  contextCompressionError: string | null;
  onContextCompressionChange: (enabled: boolean) => void;
  whatIfDraft: WhatIfDraftState;
  onWhatIfChange: (next: WhatIfDraftState) => void;
  skills: SkillInfo[];
  selectedSkillIds: string[];
  selectedSkillIdSet: Set<string>;
  skillLimitReached: boolean;
  selectedSkillSummary: string;
  mobileSkillPickerOpen: boolean;
  onMobileSkillPickerOpenChange: (open: boolean) => void;
  skillPickerRef: React.RefObject<HTMLDivElement | null>;
  showSkillDesc: string | null;
  onShowSkillDesc: (skillId: string | null) => void;
  onToggleSkill: (skillId: string) => void;
  onClearSkills: () => void;
  activeStockCode: string | null;
  stockInWatchlist: boolean;
  isWatchlistActioning: boolean;
  watchlistMessage: string | null;
  onToggleWatchlist: () => void;
  input: string;
  onInputChange: (value: string) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  loading: boolean;
  isSkillsLoading: boolean;
  onStop: () => void;
  onSend: () => void;
}

export function ChatComposer({
  language,
  t,
  sessionError,
  sessionLoading,
  chatError,
  lastFailedRequest,
  onRetryLastStream,
  isFollowUpContextLoading,
  contextCompressionEnabled,
  contextCompressionLoaded,
  contextCompressionSaving,
  contextCompressionError,
  onContextCompressionChange,
  whatIfDraft,
  onWhatIfChange,
  skills,
  selectedSkillIds,
  selectedSkillIdSet,
  skillLimitReached,
  selectedSkillSummary,
  mobileSkillPickerOpen,
  onMobileSkillPickerOpenChange,
  skillPickerRef,
  onShowSkillDesc,
  onToggleSkill,
  onClearSkills,
  activeStockCode,
  stockInWatchlist,
  isWatchlistActioning,
  watchlistMessage,
  onToggleWatchlist,
  input,
  onInputChange,
  onKeyDown,
  loading,
  isSkillsLoading,
  onStop,
  onSend,
}: ChatComposerProps): React.ReactElement {
  const [configurationOpen, setConfigurationOpen] = React.useState(false);

  return (
    <div className="relative z-20 bg-card/88 p-4 md:p-6">
      <div className="space-y-3">
        {sessionError ? <ApiErrorAlert error={sessionError} /> : null}
        {sessionLoading ? (
          <InlineAlert
            variant="info"
            size="compact"
            title={t('chat.loadingSessions')}
            message={t('common.loading')}
          />
        ) : null}
        {chatError ? (
          <div className="relative">
            <ApiErrorAlert
              error={chatError}
              className={cn(
                '[&>div>div]:w-full [&_details]:w-full',
                Boolean(lastFailedRequest) && 'pr-12',
              )}
            />
            {lastFailedRequest ? (
              <Tooltip content={t('common.retry')} className="absolute right-2 top-2 z-10">
                <IconButton
                  variant="danger"
                  size="compact"
                  tooltip={false}
                  aria-label={t('common.retry')}
                  onClick={onRetryLastStream}
                >
                  <RefreshCw aria-hidden="true" />
                </IconButton>
              </Tooltip>
            ) : null}
          </div>
        ) : null}
        {isFollowUpContextLoading ? (
          <InlineAlert
            variant="info"
            size="compact"
            title={t('chat.followUpLoadingTitle')}
            message={t('chat.followUpLoadingMessage')}
          />
        ) : null}
        {contextCompressionError ? (
          <InlineAlert
            variant="danger"
            size="compact"
            title={t('chat.contextCompressionUnsaved')}
            message={contextCompressionError}
          />
        ) : null}
        {activeStockCode && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-text font-mono">{activeStockCode}</span>
            <Button
              variant="secondary"
              size="compact"
              isLoading={isWatchlistActioning}
              onClick={onToggleWatchlist}
              className="text-xs"
            >
              {stockInWatchlist ? t('chat.removeWatchlist') : t('chat.addWatchlist')}
            </Button>
            {watchlistMessage && (
              <span className="text-xs text-secondary-text animate-in fade-in">
                {watchlistMessage}
              </span>
            )}
          </div>
        )}

        {configurationOpen ? (
          <div
            id="chat-what-if-configuration"
            role="region"
            aria-label={t('chat.whatIf.title')}
            className="rounded-xl border border-border bg-card p-4"
            data-testid="chat-what-if-configuration"
          >
            <div className="[&_[role=switch]]:h-9 [&_[role=switch]]:w-9 [&_[role=switch]>span]:scale-75">
              <Suspense fallback={<Loading label={t('common.loading')} />}>
                <WhatIfScenarioPanel
                  t={t}
                  draft={whatIfDraft}
                  onChange={onWhatIfChange}
                  disabled={loading || sessionLoading || isSkillsLoading}
                />
              </Suspense>
            </div>
          </div>
        ) : null}

        <div
          className="rounded-xl border border-border bg-transparent transition-colors focus-within:border-muted-text"
          data-testid="chat-composer-input"
        >
          <textarea
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={onKeyDown}
            aria-label={t('chat.messageInput')}
            placeholder={t('chat.inputPlaceholder')}
            disabled={loading || sessionLoading}
            rows={1}
            className="block min-h-11 max-h-50 w-full resize-none border-0 bg-transparent px-3 pt-3 text-base text-foreground placeholder:text-muted-text focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm"
            style={{ height: 'auto' }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = 'auto';
              target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
            }}
          />
          <div className="flex min-h-10 items-center gap-1 px-2 pb-2">
            {skills.length > 0 ? (
              <div className="relative min-w-0" ref={skillPickerRef}>
                <button
                  type="button"
                  className="flex h-8 max-w-56 items-center gap-1.5 rounded-lg px-2 text-left text-xs text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
                  aria-label={mobileSkillPickerOpen ? t('chat.collapseStrategies') : t('chat.expandStrategies')}
                  aria-expanded={mobileSkillPickerOpen}
                  aria-controls="chat-skill-picker-panel"
                  onClick={() => onMobileSkillPickerOpenChange(!mobileSkillPickerOpen)}
                >
                  <SlidersHorizontal className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="truncate">{selectedSkillSummary}</span>
                  <ChevronDown
                    className={cn('h-3.5 w-3.5 shrink-0 transition-transform', mobileSkillPickerOpen && 'rotate-180')}
                    aria-hidden="true"
                  />
                </button>
                <div
                  id="chat-skill-picker-panel"
                  data-testid="chat-skill-picker-panel"
                  className={cn(
                    mobileSkillPickerOpen ? 'flex' : 'hidden',
                    'absolute bottom-full left-0 z-20 mb-2 max-h-60 w-72 flex-col gap-y-2 overflow-y-auto rounded-xl border border-border bg-card px-3 py-2.5 shadow-soft-card',
                  )}
                >
                  <Checkbox
                    name="general-analysis"
                    value=""
                    checked={selectedSkillIds.length === 0}
                    onChange={onClearSkills}
                    containerClassName="group min-h-8 gap-1.5 text-sm"
                    label={(
                      <span className={selectedSkillIds.length === 0 ? 'text-sm font-medium text-foreground' : 'text-sm text-secondary-text group-hover:text-foreground'}>
                        {t('chat.generalAnalysis')}
                      </span>
                    )}
                  />
                  {skills.map((s) => {
                    const checked = selectedSkillIdSet.has(s.id);
                    const disabled = !checked && skillLimitReached;
                    const display = getStrategyDisplay(s, language);
                    return (
                      <Tooltip
                        key={s.id}
                        content={s.description ? (
                          <span className="block max-w-64">
                            <span className="block font-medium text-foreground">{display.name}</span>
                            <span className="mt-0.5 block text-secondary-text">{display.description}</span>
                          </span>
                        ) : null}
                        className="w-full"
                      >
                        <div
                          className={cn('group flex min-h-8 cursor-pointer items-center gap-1.5', disabled && 'cursor-not-allowed opacity-60')}
                          onMouseEnter={() => onShowSkillDesc(s.id)}
                          onMouseLeave={() => onShowSkillDesc(null)}
                        >
                          <Checkbox
                            name="skills"
                            value={s.id}
                            checked={checked}
                            disabled={disabled}
                            onChange={() => onToggleSkill(s.id)}
                            containerClassName="min-h-8 gap-1.5"
                            label={<span className={checked ? 'text-sm font-medium text-foreground' : 'text-sm text-secondary-text group-hover:text-foreground'}>{display.name}</span>}
                          />
                        </div>
                      </Tooltip>
                    );
                  })}
                </div>
              </div>
            ) : null}
            <IconButton
              size="default"
              variant="bare"
              onClick={() => onContextCompressionChange(!contextCompressionEnabled)}
              aria-label={t('chat.contextCompression')}
              aria-pressed={contextCompressionEnabled}
              disabled={!contextCompressionLoaded || contextCompressionSaving}
              className={contextCompressionEnabled ? 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary' : ''}
            >
              <Minimize2 aria-hidden="true" />
            </IconButton>
            <IconButton
              size="default"
              variant="bare"
              onClick={() => {
                if (!whatIfDraft.enabled) onWhatIfChange({ ...whatIfDraft, enabled: true });
                setConfigurationOpen((open) => !open);
              }}
              aria-label={t('chat.whatIf.title')}
              aria-pressed={whatIfDraft.enabled}
              aria-expanded={configurationOpen}
              aria-controls={configurationOpen ? 'chat-what-if-configuration' : undefined}
              disabled={loading || sessionLoading || isSkillsLoading}
              className={whatIfDraft.enabled ? 'bg-warning/10 text-warning hover:bg-warning/15 hover:text-warning' : ''}
            >
              <FlaskConical aria-hidden="true" />
            </IconButton>
            {loading ? (
              <IconButton
                variant="outline"
                size="default"
                onClick={onStop}
                aria-label={t('chat.stop')}
                className="ml-auto"
              >
                <Square aria-hidden="true" />
              </IconButton>
            ) : (
              <IconButton
                variant="bare"
                size="default"
                onClick={onSend}
                disabled={!input.trim() || isFollowUpContextLoading || isSkillsLoading || sessionLoading}
                aria-label={t('chat.send')}
                className="ml-auto bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground"
              >
                <Send aria-hidden="true" />
              </IconButton>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
