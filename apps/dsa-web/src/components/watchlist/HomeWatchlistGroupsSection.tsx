// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import type React from 'react';
import { useMemo } from 'react';
import { Section } from '../common';
import { WatchlistGroupsPanel } from './WatchlistGroupsPanel';
import { useWatchlist } from '../../hooks/useWatchlist';
import { useWatchlistGroups } from '../../hooks/useWatchlistGroups';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

export const HomeWatchlistGroupsSection: React.FC = () => {
  const { t } = useUiLanguage();
  const watchlist = useWatchlist();
  const watchlistGroups = useWatchlistGroups();
  const watchlistRows = useMemo(
    () => watchlist.watchlistCodes.map((code) => ({ code, analyzedToday: false })),
    [watchlist.watchlistCodes],
  );

  return (
    <Section
      title={t('watchlist.groupsSectionTitle')}
      description={t('watchlist.groupsSectionDescription')}
    >
      <WatchlistGroupsPanel
        groups={watchlistGroups.groups}
        watchlistRows={watchlistRows}
        loading={watchlistGroups.isLoading || watchlist.isLoading}
        actioning={watchlistGroups.isActioning || watchlist.isActioning}
        errorMessage={watchlistGroups.errorMessage}
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
