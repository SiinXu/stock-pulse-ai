// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button, InlineAlert, Section, Select } from '../common';
import { WatchlistGroupsPanel } from './WatchlistGroupsPanel';
import { useWatchlist } from '../../hooks/useWatchlist';
import { useWatchlistGroups } from '../../hooks/useWatchlistGroups';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { useWatchlistScores } from '../../hooks/useWatchlistScores';
import type { WatchlistScoreSortMode } from '../../types/watchlistScore';
import { orderWatchlistByScore } from '../../utils/watchlistScoreOrder';

export interface HomeWatchlistGroupsSectionProps {
  /** Changes when Home observes a new analysis or runs its page-level refresh. */
  scoreRefreshKey?: string | number;
}

export const HomeWatchlistGroupsSection: React.FC<HomeWatchlistGroupsSectionProps> = ({
  scoreRefreshKey = '',
}) => {
  const { t } = useUiLanguage();
  const watchlist = useWatchlist();
  const watchlistGroups = useWatchlistGroups();
  const [scoreSort, setScoreSort] = useState<WatchlistScoreSortMode>('manual');
  const [scoreRefreshGeneration, setScoreRefreshGeneration] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const watchlistRows = useMemo(
    () => watchlist.watchlistCodes.map((code) => ({ code, analyzedToday: false })),
    [watchlist.watchlistCodes],
  );
  const scoreState = useWatchlistScores(
    watchlist.watchlistCodes,
    `${String(scoreRefreshKey)}\n${watchlistGroups.revision ?? 'unresolved'}\n${scoreRefreshGeneration}`,
  );
  const effectiveScoreSort = scoreState.status === 'ready' ? scoreSort : 'manual';
  const displayedGroups = useMemo(() => watchlistGroups.groups.map((group) => ({
    ...group,
    members: orderWatchlistByScore(
      group.members,
      scoreState.itemsByCode,
      effectiveScoreSort,
    ),
  })), [effectiveScoreSort, scoreState.itemsByCode, watchlistGroups.groups]);

  const handleRefresh = async () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      await Promise.all([
        watchlist.refresh(),
        watchlistGroups.refresh(),
      ]);
      setScoreRefreshGeneration((generation) => generation + 1);
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <Section
      title={t('watchlist.groupsSectionTitle')}
      description={t('watchlist.groupsSectionDescription')}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          value={effectiveScoreSort}
          onChange={(value) => setScoreSort(value as WatchlistScoreSortMode)}
          options={[
            { value: 'manual', label: t('watchlistScore.sortManual') },
            { value: 'score_desc', label: t('watchlistScore.sortScoreDesc') },
            { value: 'score_asc', label: t('watchlistScore.sortScoreAsc') },
          ]}
          ariaLabel={t('watchlistScore.sortManual')}
          className="min-w-44"
          size="default"
          disabled={scoreState.status !== 'ready'}
        />
        <Button
          type="button"
          size="default"
          variant="secondary"
          isLoading={isRefreshing}
          disabled={isRefreshing || watchlist.isActioning || watchlistGroups.isActioning}
          onClick={() => void handleRefresh()}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {t('watchlist.refresh')}
        </Button>
      </div>
      {scoreState.status === 'error' ? (
        <InlineAlert
          className="mb-3"
          variant="danger"
          size="compact"
          title={t('common.failure')}
          message={t('watchlistScore.loadFailed')}
        />
      ) : null}
      <WatchlistGroupsPanel
        groups={displayedGroups}
        watchlistRows={watchlistRows}
        loading={watchlistGroups.isLoading || watchlist.isLoading}
        actioning={watchlistGroups.isActioning || watchlist.isActioning}
        errorMessage={watchlistGroups.errorMessage}
        scoreStatus={scoreState.status}
        scoreItemsByCode={scoreState.itemsByCode}
        memberReorderingDisabled={effectiveScoreSort !== 'manual'}
        onCreateGroup={watchlistGroups.createGroup}
        onDeleteGroup={watchlistGroups.deleteGroup}
        onReorderGroups={watchlistGroups.reorderGroups}
        onReorderMembers={watchlistGroups.reorderMembers}
        onMoveMember={watchlistGroups.moveMember}
        onRemoveFromWatchlist={async (code) => {
          const ok = await watchlist.removeFromWatchlist(code);
          if (ok) await watchlistGroups.refresh();
          return ok;
        }}
      />
    </Section>
  );
};

export default HomeWatchlistGroupsSection;
