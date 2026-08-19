// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useContext, useRef, useState } from 'react';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { ToastContext } from '../common/toastContext';
import type { WatchlistGroup, WatchlistGroupRestoreSnapshot } from '../../types/watchlist';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

export interface WatchlistGroupDeleteFlowProps {
  group: WatchlistGroup;
  groups: WatchlistGroup[];
  actioning?: boolean;
  onDeleteGroup: (groupId: string) => Promise<boolean> | boolean;
  onRestoreGroup?: (snapshot: WatchlistGroupRestoreSnapshot) => Promise<boolean> | boolean;
  onClose: () => void;
  onAnnounce: (message: string) => void;
  groupName: (group: WatchlistGroup) => string;
}

function exclusiveMemberCodes(group: WatchlistGroup, groups: WatchlistGroup[]): string[] {
  return group.members
    .filter((member) => groups.every((candidate) => (
      candidate.id === group.id
      || candidate.members.every((other) => other.stockCode !== member.stockCode)
    )))
    .map((member) => member.stockCode);
}

const WatchlistGroupDeleteFlow: React.FC<WatchlistGroupDeleteFlowProps> = ({
  group,
  groups,
  actioning = false,
  onDeleteGroup,
  onRestoreGroup,
  onClose,
  onAnnounce,
  groupName,
}) => {
  const { t } = useUiLanguage();
  const toast = useContext(ToastContext);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const restoreInFlightRef = useRef(false);
  const displayName = groupName(group);

  const handleUndoDelete = async (snapshot: WatchlistGroupRestoreSnapshot) => {
    if (!onRestoreGroup || restoreInFlightRef.current || actioning) return;
    restoreInFlightRef.current = true;
    try {
      const succeeded = await onRestoreGroup(snapshot);
      if (succeeded) {
        onAnnounce(t('watchlist.groupRestored', { name: displayName }));
        return;
      }
      toast?.showToast({
        title: t('watchlist.groupRestoreFailed'),
        tone: 'danger',
        durationMs: 6000,
      });
    } finally {
      restoreInFlightRef.current = false;
    }
  };

  const handleConfirmDelete = async () => {
    if (group.isDefault || actioning || isConfirmingDelete) return;
    const snapshot: WatchlistGroupRestoreSnapshot = {
      groupId: group.id,
      name: group.name,
      memberCodes: group.members.map((member) => member.stockCode),
      exclusiveMemberCodes: exclusiveMemberCodes(group, groups),
      orderedGroupIds: groups.map((item) => item.id),
    };
    setIsConfirmingDelete(true);
    try {
      const succeeded = await onDeleteGroup(group.id);
      if (!succeeded) return;
      onClose();
      onAnnounce(t('watchlist.groupDeletedMessage', { name: displayName }));
      if (!onRestoreGroup || !toast) return;
      toast.showToast({
        title: t('watchlist.groupDeletedTitle'),
        message: t('watchlist.groupDeletedMessage', { name: displayName }),
        tone: 'success',
        durationMs: 8000,
        action: {
          label: t('watchlist.undoDelete'),
          onClick: () => {
            void handleUndoDelete(snapshot);
          },
        },
      });
    } finally {
      setIsConfirmingDelete(false);
    }
  };

  return (
    <ConfirmDialog
      isOpen
      title={t('watchlist.deleteGroupTitle')}
      message={t('watchlist.deleteGroupConfirm', {
        name: displayName,
        count: exclusiveMemberCodes(group, groups).length,
      })}
      confirmText={t('common.delete')}
      cancelText={t('common.cancel')}
      isDanger
      confirmDisabled={actioning || isConfirmingDelete}
      cancelDisabled={isConfirmingDelete}
      onConfirm={() => { void handleConfirmDelete(); }}
      onCancel={() => {
        if (!isConfirmingDelete) onClose();
      }}
    />
  );
};

export default WatchlistGroupDeleteFlow;
