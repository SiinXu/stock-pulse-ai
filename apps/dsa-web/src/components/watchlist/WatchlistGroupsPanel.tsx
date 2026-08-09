// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, FolderPlus, GripVertical, MoreHorizontal, Trash2 } from 'lucide-react';
import { IconButton, Input, InlineAlert } from '../common';
import type { HomeWatchlistRow, WatchlistGroup } from '../../types/watchlist';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { truncateStockName } from '../../utils/stockName';

export interface WatchlistGroupsPanelProps {
  groups: WatchlistGroup[];
  watchlistRows: HomeWatchlistRow[];
  loading?: boolean;
  actioning?: boolean;
  errorMessage?: string | null;
  onCreateGroup: (name: string) => Promise<void> | void;
  onDeleteGroup: (groupId: string) => Promise<void> | void;
  onReorderGroups: (orderedIds: string[]) => Promise<void> | void;
  onReorderMembers: (groupId: string, orderedCodes: string[]) => Promise<void> | void;
  onMoveMember: (params: {
    stockCode: string;
    sourceGroupId: string;
    targetGroupId: string;
    targetIndex?: number;
  }) => Promise<void> | void;
  onRemoveFromWatchlist: (code: string) => Promise<boolean | void>;
}

type DragPayload =
  | { kind: 'group'; groupId: string }
  | { kind: 'member'; groupId: string; stockCode: string };

function parseDragPayload(raw: string): DragPayload | null {
  try {
    const parsed = JSON.parse(raw) as DragPayload;
    if (parsed?.kind === 'group' && parsed.groupId) return parsed;
    if (parsed?.kind === 'member' && parsed.groupId && parsed.stockCode) return parsed;
  } catch {
    // Invalid cross-page drag payloads are ignored.
  }
  return null;
}

function moved<T>(items: T[], from: number, to: number): T[] {
  if (from < 0 || to < 0 || from === to) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export const WatchlistGroupsPanel: React.FC<WatchlistGroupsPanelProps> = ({
  groups,
  watchlistRows,
  loading = false,
  actioning = false,
  errorMessage = null,
  onCreateGroup,
  onDeleteGroup,
  onReorderGroups,
  onReorderMembers,
  onMoveMember,
  onRemoveFromWatchlist,
}) => {
  const { t } = useUiLanguage();
  const [draftName, setDraftName] = useState('');
  const [menuKey, setMenuKey] = useState<string | null>(null);
  const [draggingOver, setDraggingOver] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const menuRef = useRef<HTMLDivElement | null>(null);
  const triggerRefs = useRef(new Map<string, HTMLButtonElement>());

  const rowByCode = useMemo(() => {
    const map = new Map<string, HomeWatchlistRow>();
    for (const row of watchlistRows) map.set(row.code, row);
    return map;
  }, [watchlistRows]);

  const groupName = (group: WatchlistGroup) => (
    group.isDefault && group.nameKey ? t('watchlist.defaultGroupName') : group.name
  );

  const closeMenu = useCallback((returnFocus: boolean) => {
    const closingKey = menuKey;
    setMenuKey(null);
    if (returnFocus && closingKey) triggerRefs.current.get(closingKey)?.focus();
  }, [menuKey]);

  useEffect(() => {
    if (!menuKey) return undefined;
    menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeMenu(true);
      }
    };
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !triggerRefs.current.get(menuKey)?.contains(target)) {
        closeMenu(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('pointerdown', handlePointerDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [closeMenu, menuKey]);

  const reorderGroupBy = async (groupId: string, delta: number) => {
    const ids = groups.map((group) => group.id);
    const from = ids.indexOf(groupId);
    const to = Math.max(0, Math.min(from + delta, ids.length - 1));
    if (from === to || actioning) return;
    await onReorderGroups(moved(ids, from, to));
    setAnnouncement(t('watchlist.reorderAnnouncement', { item: groupName(groups[from]) }));
  };

  const reorderMemberBy = async (group: WatchlistGroup, stockCode: string, delta: number) => {
    const codes = group.members.map((member) => member.stockCode);
    const from = codes.indexOf(stockCode);
    const to = Math.max(0, Math.min(from + delta, codes.length - 1));
    if (from === to || actioning) return;
    await onReorderMembers(group.id, moved(codes, from, to));
    setAnnouncement(t('watchlist.reorderAnnouncement', { item: stockCode }));
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = draftName.trim();
    if (!name || actioning) return;
    await onCreateGroup(name);
    setDraftName('');
  };

  const handleGroupDrop = async (targetGroupId: string, event: React.DragEvent) => {
    event.preventDefault();
    setDraggingOver(null);
    const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
    if (!payload || actioning) return;
    if (payload.kind === 'group') {
      const ids = groups.map((group) => group.id);
      const from = ids.indexOf(payload.groupId);
      const to = ids.indexOf(targetGroupId);
      if (from >= 0 && to >= 0 && from !== to) await onReorderGroups(moved(ids, from, to));
      return;
    }
    if (payload.groupId !== targetGroupId) {
      await onMoveMember({
        stockCode: payload.stockCode,
        sourceGroupId: payload.groupId,
        targetGroupId,
      });
    }
  };

  const handleMemberDrop = async (
    targetGroup: WatchlistGroup,
    targetCode: string,
    event: React.DragEvent,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
    if (!payload || payload.kind !== 'member' || actioning) return;
    const codes = targetGroup.members.map((member) => member.stockCode);
    const targetIndex = codes.indexOf(targetCode);
    if (payload.groupId === targetGroup.id) {
      const from = codes.indexOf(payload.stockCode);
      if (from >= 0 && targetIndex >= 0 && from !== targetIndex) {
        await onReorderMembers(targetGroup.id, moved(codes, from, targetIndex));
      }
      return;
    }
    await onMoveMember({
      stockCode: payload.stockCode,
      sourceGroupId: payload.groupId,
      targetGroupId: targetGroup.id,
      targetIndex: Math.max(targetIndex, 0),
    });
  };

  if (loading) return <p className="text-xs text-muted-text">{t('watchlist.groupsLoading')}</p>;

  return (
    <div className="space-y-3" data-testid="watchlist-groups-panel">
      <p className="sr-only" aria-live="polite">{announcement}</p>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-secondary-text">{t('watchlist.groupsTitle')}</p>
        <span className="text-xs text-muted-text">{t('watchlist.groupsHint')}</span>
      </div>

      <form className="grid grid-cols-[minmax(0,1fr)_auto] gap-2" onSubmit={(event) => void handleCreate(event)}>
        <Input
          value={draftName}
          onChange={(event) => setDraftName(event.target.value)}
          placeholder={t('watchlist.groupNamePlaceholder')}
          aria-label={t('watchlist.groupNamePlaceholder')}
          disabled={actioning}
          className="text-xs"
        />
        <IconButton type="submit" size="comfortable" variant="outline" disabled={!draftName.trim() || actioning} aria-label={t('watchlist.createGroup')}>
          <FolderPlus className="h-4 w-4" aria-hidden="true" />
        </IconButton>
      </form>

      {errorMessage ? <InlineAlert variant="danger" size="compact" message={errorMessage} /> : null}

      {groups.length === 0 ? (
        <p className="text-xs text-muted-text">{t('watchlist.groupsEmpty')}</p>
      ) : (
        <div className="space-y-3">
          {groups.map((group, groupIndex) => {
            const displayName = groupName(group);
            return (
              <section
                key={group.id}
                className={`rounded-xl border border-subtle bg-base/30 p-2 ${draggingOver === group.id ? 'ring-1 ring-primary/40' : ''}`}
                onDragOver={(event) => { event.preventDefault(); setDraggingOver(group.id); }}
                onDragLeave={() => setDraggingOver((current) => (current === group.id ? null : current))}
                onDrop={(event) => void handleGroupDrop(group.id, event)}
                data-testid={`watchlist-group-${group.id}`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <button
                    type="button"
                    className="hidden cursor-grab text-muted-text sm:inline-flex"
                    draggable={!actioning}
                    onDragStart={(event) => {
                      event.dataTransfer.setData('application/json', JSON.stringify({ kind: 'group', groupId: group.id }));
                      event.dataTransfer.effectAllowed = 'move';
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                        event.preventDefault();
                        void reorderGroupBy(group.id, event.key === 'ArrowUp' ? -1 : 1);
                      }
                    }}
                    aria-label={t('watchlist.reorderGroupAria', { name: displayName })}
                  >
                    <GripVertical className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
                    {displayName}
                    {group.isDefault ? <span className="ml-2 text-xs font-normal text-muted-text">{t('watchlist.defaultGroupBadge')}</span> : null}
                  </h3>
                  <span className="text-xs text-muted-text">{t('common.itemsCount', { count: group.members.length })}</span>
                  <div className="flex sm:hidden">
                    <IconButton type="button" size="default" variant="ghost" disabled={actioning || groupIndex === 0} aria-label={t('watchlist.moveGroupUpAria', { name: displayName })} onClick={() => void reorderGroupBy(group.id, -1)}>
                      <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                    </IconButton>
                    <IconButton type="button" size="default" variant="ghost" disabled={actioning || groupIndex === groups.length - 1} aria-label={t('watchlist.moveGroupDownAria', { name: displayName })} onClick={() => void reorderGroupBy(group.id, 1)}>
                      <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                    </IconButton>
                  </div>
                  {!group.isDefault ? (
                    <IconButton type="button" size="default" variant="danger" disabled={actioning} aria-label={t('watchlist.deleteGroupAria', { name: displayName })} onClick={() => void onDeleteGroup(group.id)}>
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </IconButton>
                  ) : null}
                </div>

                {group.members.length === 0 ? (
                  <p className="px-1 py-2 text-xs text-muted-text">{t('watchlist.groupEmpty')}</p>
                ) : (
                  <ul className="space-y-1.5">
                    {group.members.map((member, memberIndex) => {
                      const row = rowByCode.get(member.stockCode);
                      const label = row?.latestItem?.stockName ? truncateStockName(row.latestItem.stockName) : member.stockCode;
                      const menuId = `${group.id}:${member.stockCode}`;
                      return (
                        <li
                          key={menuId}
                          className="flex items-center gap-2 rounded-lg border border-subtle/80 bg-background/40 px-2 py-1.5"
                          onDragOver={(event) => event.preventDefault()}
                          onDrop={(event) => void handleMemberDrop(group, member.stockCode, event)}
                          data-testid={`watchlist-member-${group.id}-${member.stockCode}`}
                        >
                          <button
                            type="button"
                            className="hidden cursor-grab text-muted-text sm:inline-flex"
                            draggable={!actioning}
                            onDragStart={(event) => {
                              event.dataTransfer.setData('application/json', JSON.stringify({ kind: 'member', groupId: group.id, stockCode: member.stockCode }));
                              event.dataTransfer.effectAllowed = 'move';
                            }}
                            onKeyDown={(event) => {
                              if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                                event.preventDefault();
                                void reorderMemberBy(group, member.stockCode, event.key === 'ArrowUp' ? -1 : 1);
                              }
                            }}
                            aria-label={t('watchlist.reorderMemberAria', { code: member.stockCode })}
                          >
                            <GripVertical className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-foreground">{label}</p>
                            <p className="truncate font-mono text-xs text-secondary-text">{member.stockCode}</p>
                          </div>
                          <div className="flex sm:hidden">
                            <IconButton type="button" size="default" variant="ghost" disabled={actioning || memberIndex === 0} aria-label={t('watchlist.moveMemberUpAria', { code: member.stockCode })} onClick={() => void reorderMemberBy(group, member.stockCode, -1)}>
                              <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
                            </IconButton>
                            <IconButton type="button" size="default" variant="ghost" disabled={actioning || memberIndex === group.members.length - 1} aria-label={t('watchlist.moveMemberDownAria', { code: member.stockCode })} onClick={() => void reorderMemberBy(group, member.stockCode, 1)}>
                              <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                            </IconButton>
                          </div>
                          <div className="relative">
                            <IconButton
                              ref={(node) => { if (node) triggerRefs.current.set(menuId, node); else triggerRefs.current.delete(menuId); }}
                              type="button"
                              size="default"
                              variant="ghost"
                              disabled={actioning}
                              aria-label={t('watchlist.memberActionsAria', { code: member.stockCode })}
                              aria-expanded={menuKey === menuId}
                              aria-haspopup="menu"
                              onClick={() => setMenuKey((current) => (current === menuId ? null : menuId))}
                            >
                              <MoreHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
                            </IconButton>
                            {menuKey === menuId ? (
                              <div ref={menuRef} className="absolute right-0 z-20 mt-1 min-w-40 rounded-lg border border-subtle bg-background p-1 shadow-lg" role="menu">
                                <p className="px-2 py-1 text-xs uppercase tracking-wide text-muted-text">{t('watchlist.moveToGroup')}</p>
                                {groups.filter((candidate) => candidate.id !== group.id).map((candidate) => (
                                  <button
                                    key={candidate.id}
                                    type="button"
                                    role="menuitem"
                                    className="block w-full rounded-md px-2 py-1.5 text-left text-xs text-foreground hover:bg-subtle-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                                    onClick={async () => {
                                      closeMenu(false);
                                      await onMoveMember({ stockCode: member.stockCode, sourceGroupId: group.id, targetGroupId: candidate.id });
                                      setAnnouncement(t('watchlist.moveAnnouncement', { code: member.stockCode, group: groupName(candidate) }));
                                    }}
                                  >
                                    {groupName(candidate)}
                                  </button>
                                ))}
                                <button
                                  type="button"
                                  role="menuitem"
                                  className="mt-1 block w-full rounded-md px-2 py-1.5 text-left text-xs text-danger hover:bg-subtle-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                                  onClick={() => { closeMenu(false); void onRemoveFromWatchlist(member.stockCode); }}
                                >
                                  {t('watchlist.removeAria', { code: member.stockCode })}
                                </button>
                              </div>
                            ) : null}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      )}

      <p className="text-xs text-muted-text sm:hidden">{t('watchlist.mobileMoveHint')}</p>
    </div>
  );
};

export default WatchlistGroupsPanel;
