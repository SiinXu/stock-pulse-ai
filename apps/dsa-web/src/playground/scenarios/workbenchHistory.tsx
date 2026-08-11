// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useState } from 'react';
import { WorkbenchHistoryPopover } from '../../components/history/WorkbenchHistoryPopover';
import { fixtureHistoryItems } from '../fixtures';

const WorkbenchHistoryPopoverStory = () => {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const toggle = (id: number) => setSelectedIds((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  return (
    <WorkbenchHistoryPopover
      items={fixtureHistoryItems}
      isLoading={false}
      isLoadingMore={false}
      hasMore={false}
      selectedId={fixtureHistoryItems[0]?.id}
      selectedIds={selectedIds}
      isDeleting={false}
      onItemClick={() => undefined}
      onLoadMore={() => undefined}
      onToggleItemSelection={toggle}
      onToggleSelectAll={() => setSelectedIds(new Set(fixtureHistoryItems.map((item) => item.id)))}
      onDeleteSelected={() => undefined}
    />
  );
};

export default WorkbenchHistoryPopoverStory;
