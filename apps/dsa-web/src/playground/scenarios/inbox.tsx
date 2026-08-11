// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { NotificationInboxList } from '../../components/notification-center';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { NOTIFICATION_CENTER_TEXT } from '../../locales/notificationCenter';
import { usePlaygroundScenario } from '../scenarioContext';

const NotificationInboxListStory = () => {
  const { language } = useUiLanguage();
  const { scenario } = usePlaygroundScenario();
  const text = NOTIFICATION_CENTER_TEXT[language];

  return (
    <NotificationInboxList
      items={scenario === 'empty' ? [] : [{
        id: 'v1:analysis_complete:42:1786320000000000',
        kind: 'analysis_complete',
        titleKey: 'analysisCompleteTitle',
        titleParams: { label: 'AAPL' },
        summary: 'Hold · Stable outlook',
        severity: 'info',
        createdAt: '2026-08-10T00:00:00Z',
        isRead: false,
        href: '/research/analysis?segment=history&recordId=42',
        sourceId: '42',
      }]}
      emptyTitle={text.emptyTitle}
      emptyDescription={text.emptyDescription}
      onMarkRead={() => undefined}
    />
  );
};

export default NotificationInboxListStory;
