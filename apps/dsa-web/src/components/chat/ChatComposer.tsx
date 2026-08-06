import React from 'react';
import { ChevronDown, RefreshCw, SlidersHorizontal } from 'lucide-react';
import type { SkillInfo } from '../../api/agent';
import type { ParsedApiError } from '../../api/error';
import {
  ApiErrorAlert,
  Button,
  Checkbox,
  IconButton,
  InlineAlert,
  Switch,
  Tooltip,
} from '../common';
import { cn } from '../../utils/cn';
import { getStrategyDisplay } from '../../utils/strategyDisplay';
import type { UiLanguage, UiTextKey } from '../../i18n/uiText';

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
  skills,
  selectedSkillIds,
  selectedSkillIdSet,
  skillLimitReached,
  selectedSkillSummary,
  mobileSkillPickerOpen,
  onMobileSkillPickerOpenChange,
  skillPickerRef,
  showSkillDesc,
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
  return (
    <div className="relative z-20 border-t border-subtle bg-card/88 p-4 md:p-6">
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
                lastFailedRequest && 'pr-12',
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
        <div
          data-testid="context-compression-settings"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-subtle bg-subtle-soft px-3 py-1"
        >
          <div className="min-w-0">
            <span className="text-sm font-medium text-foreground">
              {t('chat.contextCompression')}
            </span>
            <span className="ml-2 text-xs text-muted-text">
              {t('chat.contextCompressionDescription')}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {contextCompressionSaving ? (
              <span className="text-xs text-muted-text">{t('chat.saving')}</span>
            ) : null}
            <Switch
              checked={contextCompressionEnabled}
              onCheckedChange={onContextCompressionChange}
              aria-label={t('chat.contextCompression')}
              disabled={!contextCompressionLoaded || contextCompressionSaving}
              visualTestId="context-compression-switch-visual"
            />
          </div>
        </div>
        {contextCompressionError ? (
          <InlineAlert
            variant="danger"
            size="compact"
            title={t('chat.contextCompressionUnsaved')}
            message={contextCompressionError}
          />
        ) : null}
        {skills.length > 0 && (
          <div className="relative space-y-2" ref={skillPickerRef}>
            <button
              type="button"
              className="home-surface-button flex h-9 w-full items-center justify-between gap-2 rounded-lg px-2 text-left text-xs text-foreground !shadow-none"
              aria-label={
                mobileSkillPickerOpen ? t('chat.collapseStrategies') : t('chat.expandStrategies')
              }
              aria-expanded={mobileSkillPickerOpen}
              aria-controls="chat-skill-picker-panel"
              onClick={() => onMobileSkillPickerOpenChange(!mobileSkillPickerOpen)}
            >
              <span className="flex min-w-0 items-center gap-2">
                <SlidersHorizontal className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                <span className="flex-shrink-0 font-medium">{t('chat.strategy')}</span>
                <span className="truncate text-xs text-muted-text">{selectedSkillSummary}</span>
              </span>
              <ChevronDown
                className={cn(
                  'h-4 w-4 flex-shrink-0 text-muted-text transition-transform',
                  mobileSkillPickerOpen ? 'rotate-180' : '',
                )}
                aria-hidden="true"
              />
            </button>
            <div
              id="chat-skill-picker-panel"
              data-testid="chat-skill-picker-panel"
              className={cn(
                mobileSkillPickerOpen ? 'flex' : 'hidden',
                'absolute bottom-full left-0 right-0 z-20 mb-2 max-h-60 flex-col gap-y-2 overflow-y-auto rounded-xl border border-border bg-card px-3 py-2.5 shadow-soft-card',
              )}
            >
              <Checkbox
                name="general-analysis"
                value=""
                checked={selectedSkillIds.length === 0}
                onChange={onClearSkills}
                containerClassName="group min-h-8 gap-1.5 text-sm"
                label={(
                  <span
                    className={`text-sm transition-colors ${
                      selectedSkillIds.length === 0
                        ? 'font-medium text-foreground'
                        : 'font-normal text-secondary-text group-hover:text-foreground'
                    }`}
                  >
                    {t('chat.generalAnalysis')}
                  </span>
                )}
              />
              {skills.map((s) => {
                const checked = selectedSkillIdSet.has(s.id);
                const disabled = !checked && skillLimitReached;
                const display = getStrategyDisplay(s, language);
                return (
                  <div
                    key={s.id}
                    className={`flex min-h-8 items-center gap-1.5 cursor-pointer group relative ${
                      disabled ? 'opacity-60 cursor-not-allowed' : ''
                    }`}
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
                      label={(
                        <span
                          className={`text-sm transition-colors ${
                            checked
                              ? 'font-medium text-foreground'
                              : 'font-normal text-secondary-text group-hover:text-foreground'
                          }`}
                        >
                          {display.name}
                        </span>
                      )}
                    />
                    {showSkillDesc === s.id && s.description && (
                      <div className="skill-desc-tooltip">
                        <p className="skill-title">{display.name}</p>
                        <p>{display.description}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

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

        <div className="flex items-end gap-3">
          <textarea
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={onKeyDown}
            aria-label={t('chat.messageInput')}
            placeholder={t('chat.inputPlaceholder')}
            disabled={loading || sessionLoading}
            rows={1}
            className="flex-1 min-h-11 max-h-50 rounded-sm border border-border bg-transparent px-3 py-2 text-base placeholder:text-muted-text transition-colors duration-200 focus:outline-none focus:border-muted-text resize-none disabled:cursor-not-allowed disabled:opacity-60 sm:text-sm"
            style={{ height: 'auto' }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = 'auto';
              target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
            }}
          />
          {loading ? (
            <Button
              variant="secondary"
              onClick={onStop}
              aria-label={t('chat.stop')}
              className="flex-shrink-0"
            >
              {t('chat.stop')}
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={onSend}
              disabled={
                !input.trim() || isFollowUpContextLoading || isSkillsLoading || sessionLoading
              }
              className="btn-primary flex-shrink-0"
            >
              {t('chat.send')}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
