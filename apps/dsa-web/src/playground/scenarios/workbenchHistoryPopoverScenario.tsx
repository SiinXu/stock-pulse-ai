import { useState } from 'react';
import { WorkbenchHistoryPopover } from '../../components/history/WorkbenchHistoryPopover';
import { fixtureHistoryItems } from '../fixtures';
import { usePlaygroundScenario } from '../scenarioContext';

export default function WorkbenchHistoryPopoverStory() {
  const { scenario } = usePlaygroundScenario();
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const items = scenario === 'empty' ? [] : fixtureHistoryItems;
  const toggle = (id: number) => setSelectedIds((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  return (
    <WorkbenchHistoryPopover
      items={items}
      isLoading={scenario === 'loading'}
      isLoadingMore={false}
      hasMore={false}
      selectedId={items[0]?.id}
      selectedIds={selectedIds}
      isDeleting={false}
      onItemClick={() => undefined}
      onLoadMore={() => undefined}
      onToggleItemSelection={toggle}
      onToggleSelectAll={() => setSelectedIds(new Set(items.map((item) => item.id)))}
      onDeleteSelected={() => setSelectedIds(new Set())}
    />
  );
}
