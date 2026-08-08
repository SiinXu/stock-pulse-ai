// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo, useState } from 'react';
import { FolderPlus, GripVertical, MoreHorizontal, Trash2 } from 'lucide-react';
import { IconButton, Input, InlineAlert } from '../common';
import type { HomeWatchlistRow } from '../../types/watchlist';
import type { WatchlistGroup } from '../../types/watchlist';
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
    return null;
  } catch {
    return null;
  }
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

  const rowByCode = useMemo(() => {
    const map = new Map<string, HomeWatchlistRow>();
    for (const row of watchlistRows) map.set(row.code, row);
    return map;
  }, [watchlistRows]);

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
      const ordered = groups.map((group) => group.id);
      const from = ordered.indexOf(payload.groupId);
      const to = ordered.indexOf(targetGroupId);
      if (from < 0 || to < 0 || from === to) return;
      ordered.splice(from, 1);
      ordered.splice(to, 0, payload.groupId);
      await onReorderGroups(ordered);
      return;
    }
    if (payload.kind === 'member') {
      if (payload.groupId === targetGroupId) return;
      await onMoveMember({
        stockCode: payload.stockCode,
        sourceGroupId: payload.groupId,
        targetGroupId,
      });
    }
  };

  const handleMemberDrop = async (
    targetGroupId: string,
    targetCode: string,
    event: React.DragEvent,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    setDraggingOver(null);
    const payload = parseDragPayload(event.dataTransfer.getData('application/json'));
    if (!payload || payload.kind !== 'member' || actioning) return;
    const targetGroup = groups.find((group) => group.id === targetGroupId);
    if (!targetGroup) return;
    const ordered = targetGroup.members.map((member) => member.stockCode);
    const targetIndex = ordered.indexOf(targetCode);

    if (payload.groupId === targetGroupId) {
      const from = ordered.indexOf(payload.stockCode);
      if (from < 0 || targetIndex < 0 || from === targetIndex) return;
      ordered.splice(from, 1);
      ordered.splice(targetIndex, 0, payload.stockCode);
      await onReorderMembers(targetGroupId, ordered);
      return;
    }
    await onMoveMember({
      stockCode: payload.stockCode,
      sourceGroupId: payload.groupId,
      targetGroupId,
      targetIndex: Math.max(targetIndex, 0),
    });
  };

  if (loading) {
    return <p className="text-xs text-muted-text">{t('watchlist.groupsLoading')}</p>;
  }

  return (
    <div className="space-y-3" data-testid="watchlist-groups-panel">
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
        <IconButton
          type="submit"
          size="comfortable"
          variant="outline"
          disabled={!draftName.trim() || actioning}
          aria-label={t('watchlist.createGroup')}
        >
          <FolderPlus className="h-4 w-4" aria-hidden="true" />
        </IconButton>
      </form>

      {errorMessage ? <InlineAlert variant="danger" size="compact" message={errorMessage} /> : null}

      {groups.length === 0 ? (
        <p className="text-xs text-muted-text">{t('watchlist.groupsEmpty')}</p>
      ) : (
        <div className="space-y-3">
          {groups.map((group) => (
            <section
              key={group.id}
              className={`rounded-xl border border-subtle bg-base/30 p-2 ${draggingOver === group.id ? 'ring-1 ring-primary/40' : ''}`}
              onDragOver={(event) => {
                event.preventDefault();
                setDraggingOver(group.id);
              }}
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
                    event.dataTransfer.setData(
                      'application/json',
                      JSON.stringify({ kind: 'group', groupId: group.id }),
                    );
                    event.dataTransfer.effectAllowed = 'move';
                  }}
                  aria-label={t('watchlist.dragGroupAria', { name: group.name })}
                >
                  <GripVertical className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
                <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
                  {group.name}
                  {group.isDefault ? (
                    <span className="ml-2 text-xs font-normal text-muted-text">
                      {t('watchlist.defaultGroupBadge')}
                    </span>
                  ) : null}
                </h3>
                <span className="text-xs text-muted-text">
                  {t('common.itemsCount', { count: group.members.length })}
                </span>
                {!group.isDefault ? (
                  <IconButton
                    type="button"
                    size="default"
                    variant="danger"
                    disabled={actioning}
                    aria-label={t('watchlist.deleteGroupAria', { name: group.name })}
                    onClick={() => void onDeleteGroup(group.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  </IconButton>
                ) : null}
              </div>

              {group.members.length === 0 ? (
                <p className="px-1 py-2 text-xs text-muted-text">{t('watchlist.groupEmpty')}</p>
              ) : (
                <ul className="space-y-1.5">
                  {group.members.map((member) => {
                    const row = rowByCode.get(member.stockCode);
                    const label = row?.latestItem?.stockName
                      ? truncateStockName(row.latestItem.stockName)
                      : member.stockCode;
                    const menuId = `${group.id}:${member.stockCode}`;
                    return (
                      <li
                        key={menuId}
                        className="flex items-center gap-2 rounded-lg border border-subtle/80 bg-background/40 px-2 py-1.5"
                        draggable={!actioning}
                        onDragStart={(event) => {
                          event.dataTransfer.setData(
                            'application/json',
                            JSON.stringify({
                              kind: 'member',
                              groupId: group.id,
                              stockCode: member.stockCode,
                            }),
                          );
                          event.dataTransfer.effectAllowed = 'move';
                        }}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={(event) => void handleMemberDrop(group.id, member.stockCode, event)}
                        data-testid={`watchlist-member-${group.id}-${member.stockCode}`}
                      >
                        <GripVertical className="hidden h-3.5 w-3.5 shrink-0 text-muted-text sm:block" aria-hidden="true" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground">{label}</p>
                          <p className="truncate font-mono text-xs text-secondary-text">{member.stockCode}</p>
                        </div>
                        <div className="relative">
                          <IconButton
                            type="button"
                            size="default"
                            variant="ghost"
                            disabled={actioning}
                            aria-label={t('watchlist.memberActionsAria', { code: member.stockCode })}
                            aria-expanded={menuKey === menuId}
                            onClick={() => setMenuKey((current) => (current === menuId ? null : menuId))}
                          >
                            <MoreHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
                          </IconButton>
                          {menuKey === menuId ? (
                            <div
                              className="absolute right-0 z-20 mt-1 min-w-40 rounded-lg border border-subtle bg-background p-1 shadow-lg"
                              role="menu"
                            >
                              <p className="px-2 py-1 text-[11px] uppercase tracking-wide text-muted-text">
                                {t('watchlist.moveToGroup')}
                              </p>
                              {groups
                                .filter((candidate) => candidate.id !== group.id)
                                .map((candidate) => (
                                  <button
                                    key={candidate.id}
                                    type="button"
                                    role="menuitem"
                                    className="block w-full rounded-md px-2 py-1.5 text-left text-xs text-foreground hover:bg-subtle-hover"
                                    onClick={() => {
                                      setMenuKey(null);
                                      void onMoveMember({
                                        stockCode: member.stockCode,
                                        sourceGroupId: group.id,
                                        targetGroupId: candidate.id,
                                      });
                                    }}
                                  >
                                    {candidate.name}
                                  </button>
                                ))}
                              <button
                                type="button"
                                role="menuitem"
                                className="mt-1 block w-full rounded-md px-2 py-1.5 text-left text-xs text-danger hover:bg-subtle-hover"
                                onClick={() => {
                                  setMenuKey(null);
                                  void onRemoveFromWatchlist(member.stockCode);
                                }}
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
          ))}
        </div>
      )}

      <p className="text-[11px] text-muted-text sm:hidden">{t('watchlist.mobileMoveHint')}</p>
    </div>
  );
};

export default WatchlistGroupsPanel;
