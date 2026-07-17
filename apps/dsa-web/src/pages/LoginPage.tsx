import type React from 'react';
import { useState, useEffect } from 'react';
import { motion, useMotionValue, useTransform, useSpring } from "motion/react";
import { Lock, Loader2, Cpu, TrendingUp, Network, ShieldCheck } from "lucide-react";
import { Button, Input, ParticleBackground } from '../components/common';
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

  // 3D Tilt effect values
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  // Smooth out the mouse movement
  const smoothX = useSpring(mouseX, { damping: 30, stiffness: 200 });
  const smoothY = useSpring(mouseY, { damping: 30, stiffness: 200 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const x = e.clientX / window.innerWidth - 0.5;
      const y = e.clientY / window.innerHeight - 0.5;
      mouseX.set(x);
      mouseY.set(y);
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [mouseX, mouseY]);

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
    <div className="relative flex min-h-dvh flex-col justify-center overflow-hidden bg-[var(--login-bg-main)] py-12 font-sans selection:bg-[var(--login-accent-soft)] sm:px-6 lg:px-8 [perspective:1500px]">
      {/* Dynamic Background */}
      <ParticleBackground />

      <div className="absolute right-4 top-4 z-30">
        <UiLanguageToggle />
      </div>

      {/* Cyber Grid */}
      <div className="absolute inset-0 z-0 bg-[linear-gradient(to_right,var(--login-grid-line)_1px,transparent_1px),linear-gradient(to_bottom,var(--login-grid-line)_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:var(--login-grid-mask)]" />

      <div className="sm:mx-auto sm:w-full sm:max-w-md relative z-10">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="flex flex-col items-center justify-center mb-10 relative"
        >
          {/* Immersive Full-Height Background Logo */}
          <motion.div
            style={{
              x: useTransform(smoothX, [-0.5, 0.5], [-8, 8]),
              y: useTransform(smoothY, [-0.5, 0.5], [-8, 8]),
              rotate: useTransform(smoothX, [-0.5, 0.5], [-0.5, 0.5]),
            }}
            className="pointer-events-none absolute -top-[20vh] -z-10 opacity-80"
          >
            <div className="relative flex h-[120vh] w-[120vh] items-center justify-center rounded-full border border-[var(--login-accent-soft)] bg-gradient-to-br from-[var(--login-accent-soft)] to-[hsl(var(--foreground)/0.1)] blur-sm">
              <Cpu className="h-[70vh] w-[70vh] text-[hsl(var(--foreground)/0.22)] brightness-50" />
              <TrendingUp className="absolute h-[25vh] w-[25vh] translate-x-[15vh] translate-y-[15vh] text-[hsl(var(--primary)/0.3)] brightness-50" />
            </div>
          </motion.div>

          <div className="mt-8 flex flex-col items-center">
            <h2 className="text-4xl font-extrabold tracking-tighter text-[var(--login-text-primary)] sm:text-6xl">
              <span className="bg-gradient-to-r from-[var(--login-brand-start)] to-[var(--login-brand-end)] bg-clip-text text-transparent">StockPulse</span>
            </h2>
            <h3 className="mt-1 text-xl font-bold uppercase tracking-[0.5em] text-[var(--login-text-muted)]">
              {t('login.brandTagline')}
            </h3>
          </div>

          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            className="mt-6 flex items-center gap-2 rounded-full border border-[var(--login-accent-border)] bg-[var(--login-accent-soft)] px-3 py-1 text-xs font-medium text-[var(--login-accent-text)] backdrop-blur-sm"
          >
            <Network className="h-3 w-3" />
            <span>{t('login.systemBadge')}</span>
          </motion.div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="relative group z-20 pointer-events-auto"
        >
          <div className="pointer-events-auto relative flex flex-col overflow-hidden rounded-3xl border border-[var(--login-border-card)] bg-[var(--login-bg-card)] p-8 shadow-soft-card">
            <div className="mb-8">
              <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-[var(--login-text-primary)]">
                {isFirstTime ? (
                  <>
                    <ShieldCheck className="h-6 w-6 text-emerald-400" />
                    <span>{t('login.setupTitle')}</span>
                  </>
                ) : (
                  <>
                    <Lock className="h-5 w-5 text-[var(--login-accent-text)]" />
                    <span>{t('login.adminLogin')}</span>
                  </>
                )}
              </h1>
              <p className="mt-2 text-sm text-[var(--login-text-secondary)]">
                {isFirstTime
                  ? t('login.setupDescription')
                  : t('login.loginDescription')}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
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
          </div>
        </motion.div>

        {/* Footer info */}
        <motion.p 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6 }}
          className="mt-8 text-center font-mono text-xs uppercase tracking-wider text-[var(--login-text-muted)]"
        >
          {t('login.secureConnection')}
        </motion.p>
      </div>

    </div>
  );
};

export default LoginPage;
