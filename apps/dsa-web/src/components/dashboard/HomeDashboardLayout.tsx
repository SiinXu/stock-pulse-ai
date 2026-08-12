// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Eye,
  GripVertical,
  RotateCcw,
  SlidersHorizontal,
} from 'lucide-react';
import { Button, EmptyState, IconButton } from '../common';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { useDashboardLayoutStore } from '../../stores/dashboardLayoutStore';
import {
  type DashboardWidgetId,
  movedIds,
  visibleDashboardWidgets,
} from '../../types/dashboardLayout';

export type HomeDashboardLayoutProps = {
  widgets: Partial<Record<DashboardWidgetId, React.ReactNode>>;
  widgetTitles?: Partial<Record<DashboardWidgetId, string>>;
};

type DragPayload = { kind: 'dashboard_widget'; widgetId: DashboardWidgetId };

function parseDragPayload(raw: string): DragPayload | null {
  try {
    const parsed = JSON.parse(raw) as DragPayload;
    if (parsed?.kind === 'dashboard_widget' && parsed.widgetId) return parsed;
  } catch {
    // Cross-page or malformed drag payloads are ignored.
  }
  return null;
}

/**
 * Independent Home container for show/hide/reorder of key dashboard widgets.
 * Reuses the watchlist-groups interaction contract: desktop HTML5 drag from a
 * dedicated handle, keyboard Arrow Up/Down on that handle, mobile non-drag
 * chevrons, and revision-based store commits.
 */
export const HomeDashboardLayout: React.FC<HomeDashboardLayoutProps> = ({
  widgets,
  widgetTitles,
}) => {
  const { t } = useUiLanguage();
  const layout = useDashboardLayoutStore((state) => state.layout);
  const isActioning = useDashboardLayoutStore((state) => state.isActioning);
  const lastError = useDashboardLayoutStore((state) => state.lastError);
  const hydrate = useDashboardLayoutStore((state) => state.hydrate);
  const reorder = useDashboardLayoutStore((state) => state.reorder);
  const setVisible = useDashboardLayoutStore((state) => state.setVisible);
  const reset = useDashboardLayoutStore((state) => state.reset);

  const [customizing, setCustomizing] = useState(false);
  const [draggingOver, setDraggingOver] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const titleFor = useCallback((id: DashboardWidgetId) => {
    if (widgetTitles?.[id]) return widgetTitles[id]!;
    switch (id) {
      case 'watchlist':
        return t('watchlist.title');
      case 'portfolio_health':
        return t('home.dashboardLayout.widget.portfolioHealth');
      case 'alerts':
        return t('home.triggeredAlerts');
      case 'recent_reports':
        return t('home.recentAnalyses');
      default:
        return id;
    }
  }, [t, widgetTitles]);

  const orderedIds = useMemo(
    () => layout.widgets.map((widget) => widget.id),
    [layout.widgets],
  );
  const visible = useMemo(() => visibleDashboardWidgets(layout), [layout]);

  const commitReorder = useCallback((nextIds: DashboardWidgetId[]) => {
    const result = reorder(nextIds, layout.revision);
    if (result.ok) {
      setAnnouncement(t('home.dashboardLayout.reorderAnnouncement'));
    }
    return result.ok;
  }, [layout.revision, reorder, t]);

  const reorderBy = useCallback((widgetId: DashboardWidgetId, delta: number) => {
    if (isActioning) return;
    const from = orderedIds.indexOf(widgetId);
    if (from < 0) return;
    const to = Math.max(0, Math.min(from + delta, orderedIds.length - 1));
    if (from === to) return;
    commitReorder(movedIds(orderedIds, from, to));
  }, [commitReorder, isActioning, orderedIds]);

  const handleDropOn = useCallback((targetId: DashboardWidgetId, event: React.DragEvent) => {
    event.preventDefault();
    setDraggingOver(null);
    if (isActioning) return;
    const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
    if (!payload) return;
    const from = orderedIds.indexOf(payload.widgetId);
    const to = orderedIds.indexOf(targetId);
    if (from < 0 || to < 0 || from === to) return;
    commitReorder(movedIds(orderedIds, from, to));
  }, [commitReorder, isActioning, orderedIds]);

  const handleToggleVisible = useCallback((widgetId: DashboardWidgetId, nextVisible: boolean) => {
    if (isActioning) return;
    const result = setVisible(widgetId, nextVisible, layout.revision);
    if (result.ok) {
      setAnnouncement(
        nextVisible
          ? t('home.dashboardLayout.showAnnouncement', { item: titleFor(widgetId) })
          : t('home.dashboardLayout.hideAnnouncement', { item: titleFor(widgetId) }),
      );
    }
  }, [isActioning, layout.revision, setVisible, t, titleFor]);

  const handleReset = useCallback(() => {
    if (isActioning) return;
    const result = reset(layout.revision);
    if (result.ok) {
      setAnnouncement(t('home.dashboardLayout.resetAnnouncement'));
    }
  }, [isActioning, layout.revision, reset, t]);

  const conflictMessage = lastError === 'revision_conflict'
    ? t('home.dashboardLayout.conflict')
    : lastError === 'invalid'
      ? t('home.dashboardLayout.invalid')
      : null;

  const boardItems = customizing ? layout.widgets : visible;

  return (
    <section
      className="space-y-3"
      data-testid="home-dashboard-layout"
      aria-labelledby="home-dashboard-layout-heading"
    >
      <p
        className="sr-only"
        aria-live="polite"
        role="status"
        data-testid="home-dashboard-layout-announcement"
      >
        {announcement}
      </p>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2
            id="home-dashboard-layout-heading"
            className="text-base font-semibold text-foreground"
          >
            {t('home.dashboardLayout.title')}
          </h2>
          <p className="mt-1 text-sm text-secondary-text">
            {t('home.dashboardLayout.description')}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {customizing ? (
            <Button
              type="button"
              variant="secondary"
              size="default"
              disabled={isActioning}
              onClick={handleReset}
              data-testid="home-dashboard-layout-reset"
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              {t('home.dashboardLayout.reset')}
            </Button>
          ) : null}
          <Button
            type="button"
            variant="outline"
            size="default"
            aria-pressed={customizing}
            onClick={() => setCustomizing((value) => !value)}
            data-testid="home-dashboard-layout-customize"
          >
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
            {customizing
              ? t('home.dashboardLayout.doneCustomize')
              : t('home.dashboardLayout.customize')}
          </Button>
        </div>
      </div>

      {conflictMessage ? (
        <p className="text-xs text-warning" data-testid="home-dashboard-layout-error" role="status">
          {conflictMessage}
        </p>
      ) : null}

      {boardItems.length === 0 ? (
        <EmptyState
          compact
          title={t('home.dashboardLayout.emptyTitle')}
          description={t('home.dashboardLayout.emptyDescription')}
          action={(
            <Button
              type="button"
              variant="secondary"
              size="default"
              onClick={handleReset}
            >
              {t('home.dashboardLayout.reset')}
            </Button>
          )}
        />
      ) : (
        <div className="space-y-4" data-testid="home-dashboard-layout-board" role="list">
          {boardItems.map((widget, index) => {
            const content = widgets[widget.id];
            const title = titleFor(widget.id);
            const isHiddenInCustomize = customizing && !widget.visible;
            return (
              <div
                key={widget.id}
                className={`rounded-xl border border-border bg-base/20 ${
                  draggingOver === widget.id ? 'ring-1 ring-primary/40' : ''
                } ${isHiddenInCustomize ? 'opacity-60' : ''}`}
                onDragOver={(event) => {
                  if (!customizing) return;
                  event.preventDefault();
                  setDraggingOver(widget.id);
                }}
                onDragLeave={() => setDraggingOver((current) => (
                  current === widget.id ? null : current
                ))}
                onDrop={(event) => {
                  if (!customizing) return;
                  handleDropOn(widget.id, event);
                }}
                data-testid={`home-dashboard-widget-${widget.id}`}
                data-visible={widget.visible ? 'true' : 'false'}
                role="listitem"
              >
                {customizing ? (
                  <div className="flex items-center gap-2 border-b border-border/70 px-3 py-2">
                    <button
                      type="button"
                      className="hidden cursor-grab text-muted-text sm:inline-flex"
                      draggable={!isActioning}
                      onDragStart={(event) => {
                        event.dataTransfer.setData(
                          'application/json',
                          JSON.stringify({
                            kind: 'dashboard_widget',
                            widgetId: widget.id,
                          } satisfies DragPayload),
                        );
                        event.dataTransfer.effectAllowed = 'move';
                      }}
                      onKeyDown={(event) => {
                        if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                          event.preventDefault();
                          reorderBy(widget.id, event.key === 'ArrowUp' ? -1 : 1);
                        }
                      }}
                      aria-label={t('home.dashboardLayout.reorderAria', { name: title })}
                      data-testid={`home-dashboard-drag-${widget.id}`}
                    >
                      <GripVertical className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">
                      {title}
                    </span>
                    <div className="flex sm:hidden">
                      <IconButton
                        type="button"
                        size="default"
                        variant="ghost"
                        disabled={isActioning || index === 0}
                        aria-label={t('home.dashboardLayout.moveUpAria', { name: title })}
                        onClick={() => reorderBy(widget.id, -1)}
                        data-testid={`home-dashboard-move-up-${widget.id}`}
                      >
                        <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                      </IconButton>
                      <IconButton
                        type="button"
                        size="default"
                        variant="ghost"
                        disabled={isActioning || index === boardItems.length - 1}
                        aria-label={t('home.dashboardLayout.moveDownAria', { name: title })}
                        onClick={() => reorderBy(widget.id, 1)}
                        data-testid={`home-dashboard-move-down-${widget.id}`}
                      >
                        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                      </IconButton>
                    </div>
                    <IconButton
                      type="button"
                      size="default"
                      variant="ghost"
                      disabled={isActioning || (widget.visible && visible.length <= 1)}
                      aria-label={
                        widget.visible
                          ? t('home.dashboardLayout.hideAria', { name: title })
                          : t('home.dashboardLayout.showAria', { name: title })
                      }
                      onClick={() => handleToggleVisible(widget.id, !widget.visible)}
                      data-testid={`home-dashboard-toggle-${widget.id}`}
                    >
                      <Eye
                        className={`h-3.5 w-3.5 ${widget.visible ? '' : 'opacity-50'}`}
                        aria-hidden="true"
                      />
                    </IconButton>
                  </div>
                ) : null}
                {widget.visible && content != null ? (
                  <div className={customizing ? 'p-3' : undefined}>
                    {content}
                  </div>
                ) : customizing && !widget.visible ? (
                  <p className="px-3 py-4 text-xs text-muted-text">
                    {t('home.dashboardLayout.hiddenPlaceholder')}
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      {customizing ? (
        <p
          className="text-xs text-muted-text sm:hidden"
          data-testid="home-dashboard-layout-mobile-hint"
        >
          {t('home.dashboardLayout.mobileMoveHint')}
        </p>
      ) : null}
    </section>
  );
};

export default HomeDashboardLayout;
