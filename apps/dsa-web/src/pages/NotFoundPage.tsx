import type React from 'react';
import { useEffect } from 'react';
import { Home } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';

const NotFoundPage: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useUiLanguage();

  // Set page title
  useEffect(() => {
    document.title = t('notFound.pageTitle');
  }, [t]);

  return (
    <div className="flex min-h-full flex-col items-center justify-center px-4 text-center">
      {/* 404 */}
      <div className="relative mb-8">
        <span
          className="text-8xl font-bold text-transparent bg-clip-text"
          style={{
            backgroundImage: 'linear-gradient(135deg, hsl(var(--foreground)) 0%, hsl(var(--primary)) 100%)',
          }}
        >
          404
        </span>
      </div>

      <h1 className="text-2xl font-bold text-foreground mb-2">{t('notFound.title')}</h1>
      <p className="text-muted-text mb-8">{t('notFound.description')}</p>

      <Button
        type="button"
        variant="primary"
        size="primary"
        onClick={() => navigate('/')}
      >
        <Home className="h-4 w-4" />
        {t('notFound.backHome')}
      </Button>
    </div>
  );
};

export default NotFoundPage;
