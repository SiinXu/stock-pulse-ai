import type React from 'react';
import { useState, useEffect } from 'react';
import { motion } from "motion/react";
import { Loader2, TrendingUp } from "lucide-react";
import { Button, Input } from '../components/common';
import { UiLanguageToggle } from '../components/i18n/UiLanguageToggle';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { ParsedApiError } from '../api/error';
import { isParsedApiError, localizeParsedApiError } from '../api/error';
import { useAuth } from '../hooks';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { SettingsAlert } from '../components/settings';

const LoginPage: React.FC = () => {
  const { login, passwordSet, setupState } = useAuth();
  const { language, t } = useUiLanguage();
  const navigate = useNavigate();

  // Set page title
  useEffect(() => {
    document.title = t('login.pageTitle');
  }, [t]);
  const [searchParams] = useSearchParams();
  const rawRedirect = searchParams.get('redirect') ?? '';
  const redirect =
    rawRedirect.startsWith('/') && !rawRedirect.startsWith('//') ? rawRedirect : '/';

  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | ParsedApiError | null>(null);

  const isFirstTime = setupState === 'no_password' || !passwordSet;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (isFirstTime && password !== passwordConfirm) {
      setError(t('login.passwordMismatch'));
      return;
    }
    setIsSubmitting(true);
    try {
      const result = await login(password, isFirstTime ? passwordConfirm : undefined);
      if (result.success) {
        navigate(redirect, { replace: true });
      } else {
        setError(result.error ?? t('login.loginFailed'));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden bg-background px-4 py-12 font-sans selection:bg-[var(--login-accent-soft)]">
      <div className="absolute right-4 top-4 z-30">
        <UiLanguageToggle />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="relative z-10 w-full max-w-sm"
      >
        <div className="flex flex-col rounded-3xl border border-[var(--login-border-card)] bg-[var(--login-bg-card)] p-8 shadow-soft-card">
          <div className="flex flex-col items-center text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full border border-[var(--login-border-card)] bg-[var(--login-bg-main)]">
              <TrendingUp className="h-6 w-6 text-[var(--login-text-primary)]" aria-hidden="true" />
            </div>
            <h1 className="mt-4 text-lg font-semibold tracking-tight text-[var(--login-text-primary)]">
              StockPulse
            </h1>
            <h2 className="mt-5 text-2xl font-semibold tracking-tight text-[var(--login-text-primary)]">
              {isFirstTime ? t('login.setupTitle') : t('login.adminLogin')}
            </h2>
            <p className="mt-2 text-sm text-[var(--login-text-secondary)]">
              {isFirstTime ? t('login.setupDescription') : t('login.loginDescription')}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="mt-8 space-y-6">
            <div className="space-y-4">
              <Input
                id="password"
                type="password"
                appearance="login"
                allowTogglePassword
                iconType="password"
                label={isFirstTime ? t('login.adminPassword') : t('login.loginPassword')}
                placeholder={isFirstTime ? t('login.setupPasswordPlaceholder') : t('login.loginPasswordPlaceholder')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isSubmitting}
                autoFocus
                autoComplete={isFirstTime ? 'new-password' : 'current-password'}
              />

              {isFirstTime && (
                <Input
                  id="passwordConfirm"
                  type="password"
                  appearance="login"
                  allowTogglePassword
                  iconType="password"
                  label={t('login.confirmPassword')}
                  placeholder={t('login.confirmPasswordPlaceholder')}
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  disabled={isSubmitting}
                  autoComplete="new-password"
                />
              )}
            </div>

            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="overflow-hidden"
              >
                <SettingsAlert
                  title={isFirstTime ? t('login.setupFailed') : t('login.validationFailed')}
                  message={isParsedApiError(error) ? localizeParsedApiError(error, language).message : error}
                  variant="error"
                  className="!border-[var(--login-error-border)] !bg-[var(--login-error-bg)] !text-[var(--login-error-text)]"
                />
              </motion.div>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              className="h-12 w-full font-medium"
              disabled={isSubmitting}
            >
              <div className="flex items-center justify-center gap-2">
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>{isFirstTime ? t('login.setupSubmitting') : t('login.loginSubmitting')}</span>
                  </>
                ) : (
                  <span>{isFirstTime ? t('login.setupSubmit') : t('login.loginSubmit')}</span>
                )}
              </div>
            </Button>
          </form>

          <p className="mt-8 border-t border-[var(--login-border-card)] pt-5 text-center text-xs text-[var(--login-text-muted)]">
            {t('login.secureConnection')}
          </p>
        </div>
      </motion.div>
    </div>
  );
};

export default LoginPage;
