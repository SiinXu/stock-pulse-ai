import type React from 'react';
import { useEffect } from 'react';
import { Home } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { AppPage, Button, StatePanel } from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';

const NotFoundPage: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useUiLanguage();

  // Set page title
  useEffect(() => {
    document.title = t('notFound.pageTitle');
  }, [t]);

  return (
    <AppPage className="flex min-h-full items-center justify-center">
      <StatePanel
        status="empty"
        titleAs="h1"
        title={t('notFound.title')}
        description={t('notFound.description')}
        icon={<Home className="h-5 w-5" aria-hidden="true" />}
        action={(
          <Button
            type="button"
            variant="primary"
            size="md"
            onClick={() => navigate('/')}
          >
            <Home className="h-4 w-4" aria-hidden="true" />
            {t('notFound.backHome')}
          </Button>
        )}
      />
    </AppPage>
  );
};

export default NotFoundPage;
