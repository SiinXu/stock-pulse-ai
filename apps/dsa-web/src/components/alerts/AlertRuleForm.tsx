import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { portfolioApi } from '../../api/portfolio';
import type {
  AlertRuleCreateRequest,
  AlertRuleItem,
  AlertSeverity,
  AlertTargetScope,
  AlertType,
  MarketLightStatus,
  MarketRegion,
  PortfolioStopLossMode,
} from '../../types/alerts';
import type { PortfolioAccountItem } from '../../types/portfolio';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { formatUiText, type UiLanguage } from '../../i18n/uiText';
import {
  ALERT_CHANGE_DIRECTION_OPTIONS,
  ALERT_CROSS_DIRECTION_OPTIONS,
  ALERT_FORM_TEXT,
  ALERT_MARKET_LIGHT_STATUS_OPTIONS,
  ALERT_MARKET_REGION_OPTIONS,
  ALERT_MARKET_TYPE_OPTIONS,
  ALERT_PORTFOLIO_TYPE_OPTIONS,
  ALERT_PRICE_DIRECTION_OPTIONS,
  ALERT_SEVERITY_OPTIONS,
  ALERT_STOP_LOSS_MODE_OPTIONS,
  ALERT_SYMBOL_TYPE_OPTIONS,
  ALERT_TARGET_SCOPE_OPTIONS,
  ALERT_THRESHOLD_DIRECTION_OPTIONS,
} from '../../locales/alerts';
import { validateStockCode } from '../../utils/validation';
import { Button, Checkbox, Input, Select } from '../common';

const MAX_REQUESTED_DAYS = 365;

interface AlertRuleFormValues {
  name: string;
  targetScope: AlertTargetScope;
  target: string;
  portfolioTarget: string;
  marketRegion: MarketRegion;
  alertType: AlertType;
  severity: AlertSeverity;
  enabled: boolean;
  priceDirection: 'above' | 'below';
  changeDirection: 'up' | 'down';
  thresholdDirection: 'above' | 'below';
  crossDirection: 'bullish_cross' | 'bearish_cross';
  stopLossMode: PortfolioStopLossMode;
  price: string;
  changePct: string;
  multiplier: string;
  window: string;
  period: string;
  threshold: string;
  fastPeriod: string;
  slowPeriod: string;
  signalPeriod: string;
  kPeriod: string;
  dPeriod: string;
  marketLightStatuses: MarketLightStatus[];
  minDrop: string;
}

function numText(value: number | undefined | null, fallback = ''): string {
  return value === undefined || value === null ? fallback : String(value);
}

// Reverse the create payload back into editable form field state so the
// existing form can load an existing rule for editing.
function alertRuleToFormValues(rule: AlertRuleItem): AlertRuleFormValues {
  const params = rule.parameters ?? {};
  const scope = rule.targetScope as AlertTargetScope;
  const direction = params.direction;
  return {
    name: rule.name ?? '',
    targetScope: scope,
    target: scope === 'single_symbol' ? rule.target ?? '' : '',
    portfolioTarget: isPortfolioScope(scope) ? rule.target || 'all' : 'all',
    marketRegion: scope === 'market' ? ((rule.target as MarketRegion) || 'cn') : 'cn',
    alertType: rule.alertType as AlertType,
    severity: rule.severity as AlertSeverity,
    enabled: rule.enabled,
    priceDirection: direction === 'below' ? 'below' : 'above',
    changeDirection: direction === 'down' ? 'down' : 'up',
    thresholdDirection: direction === 'below' ? 'below' : 'above',
    crossDirection: direction === 'bearish_cross' ? 'bearish_cross' : 'bullish_cross',
    stopLossMode: (params.mode as PortfolioStopLossMode) ?? 'near',
    price: numText(params.price),
    changePct: numText(params.changePct),
    multiplier: numText(params.multiplier),
    window: numText(params.window, '20'),
    period: numText(params.period, '12'),
    threshold: numText(params.threshold),
    fastPeriod: numText(params.fastPeriod, '12'),
    slowPeriod: numText(params.slowPeriod, '26'),
    signalPeriod: numText(params.signalPeriod, '9'),
    kPeriod: numText(params.kPeriod, '3'),
    dPeriod: numText(params.dPeriod, '3'),
    marketLightStatuses: Array.isArray(params.statuses) && params.statuses.length > 0
      ? params.statuses
      : ['red', 'yellow'],
    minDrop: numText(params.minDrop, '10'),
  };
}

interface AlertRuleFormProps {
  onSubmit: (payload: AlertRuleCreateRequest) => Promise<boolean | void> | boolean | void;
  isSubmitting?: boolean;
  mode?: 'create' | 'edit';
  initialRule?: AlertRuleItem;
}

function isPortfolioScope(scope: AlertTargetScope): boolean {
  return scope === 'portfolio_holdings' || scope === 'portfolio_account';
}

function defaultAlertTypeForScope(scope: AlertTargetScope): AlertType {
  if (scope === 'market') return 'market_light_status';
  return scope === 'portfolio_account' ? 'portfolio_stop_loss' : 'price_cross';
}

function optionsForScope(scope: AlertTargetScope, language: UiLanguage) {
  if (scope === 'market') return ALERT_MARKET_TYPE_OPTIONS[language];
  return scope === 'portfolio_account' ? ALERT_PORTFOLIO_TYPE_OPTIONS[language] : ALERT_SYMBOL_TYPE_OPTIONS[language];
}

export const AlertRuleForm: React.FC<AlertRuleFormProps> = ({
  onSubmit,
  isSubmitting = false,
  mode = 'create',
  initialRule,
}) => {
  const { language } = useUiLanguage();
  const text = ALERT_FORM_TEXT[language];
  const seed = useMemo(() => (initialRule ? alertRuleToFormValues(initialRule) : null), [initialRule]);
  const [name, setName] = useState(seed?.name ?? '');
  const [targetScope, setTargetScope] = useState<AlertTargetScope>(seed?.targetScope ?? 'single_symbol');
  const [target, setTarget] = useState(seed?.target ?? '');
  const [portfolioTarget, setPortfolioTarget] = useState(seed?.portfolioTarget ?? 'all');
  const [marketRegion, setMarketRegion] = useState<MarketRegion>(seed?.marketRegion ?? 'cn');
  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [accountsError, setAccountsError] = useState<string | null>(null);
  const [alertType, setAlertType] = useState<AlertType>(seed?.alertType ?? 'price_cross');
  const [severity, setSeverity] = useState<AlertSeverity>(seed?.severity ?? 'warning');
  const [enabled, setEnabled] = useState(seed?.enabled ?? true);
  const [priceDirection, setPriceDirection] = useState<'above' | 'below'>(seed?.priceDirection ?? 'above');
  const [changeDirection, setChangeDirection] = useState<'up' | 'down'>(seed?.changeDirection ?? 'up');
  const [thresholdDirection, setThresholdDirection] = useState<'above' | 'below'>(seed?.thresholdDirection ?? 'above');
  const [crossDirection, setCrossDirection] = useState<'bullish_cross' | 'bearish_cross'>(seed?.crossDirection ?? 'bullish_cross');
  const [stopLossMode, setStopLossMode] = useState<PortfolioStopLossMode>(seed?.stopLossMode ?? 'near');
  const [price, setPrice] = useState(seed?.price ?? '');
  const [changePct, setChangePct] = useState(seed?.changePct ?? '');
  const [multiplier, setMultiplier] = useState(seed?.multiplier ?? '');
  const [window, setWindow] = useState(seed?.window ?? '20');
  const [period, setPeriod] = useState(seed?.period ?? '12');
  const [threshold, setThreshold] = useState(seed?.threshold ?? '');
  const [fastPeriod, setFastPeriod] = useState(seed?.fastPeriod ?? '12');
  const [slowPeriod, setSlowPeriod] = useState(seed?.slowPeriod ?? '26');
  const [signalPeriod, setSignalPeriod] = useState(seed?.signalPeriod ?? '9');
  const [kPeriod, setKPeriod] = useState(seed?.kPeriod ?? '3');
  const [dPeriod, setDPeriod] = useState(seed?.dPeriod ?? '3');
  const [marketLightStatuses, setMarketLightStatuses] = useState<MarketLightStatus[]>(seed?.marketLightStatuses ?? ['red', 'yellow']);
  const [minDrop, setMinDrop] = useState(seed?.minDrop ?? '10');
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!isPortfolioScope(targetScope)) return undefined;
    let cancelled = false;
    void portfolioApi.getAccounts(false)
      .then((response) => {
        if (cancelled) return;
        setAccounts(response.accounts ?? []);
        setAccountsError(null);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setAccounts([]);
        setAccountsError(error instanceof Error ? error.message : text.accountLoadFailed);
      });
    return () => {
      cancelled = true;
    };
  }, [targetScope, text.accountLoadFailed]);

  const alertTypeOptions = useMemo(() => optionsForScope(targetScope, language), [language, targetScope]);
  const portfolioTargetOptions = useMemo(() => [
    { value: 'all', label: text.allAccounts },
    ...accounts.map((account) => ({
      value: String(account.id),
      label: `${account.name} #${account.id}`,
    })),
  ], [accounts, text.allAccounts]);

  const resetParameters = (nextType: AlertType) => {
    if (nextType === 'price_cross') {
      setPriceDirection('above');
      setPrice('');
    } else if (nextType === 'price_change_percent') {
      setChangeDirection('up');
      setChangePct('');
    } else if (nextType === 'volume_spike') {
      setMultiplier('');
    } else if (nextType === 'ma_price_cross') {
      setThresholdDirection('above');
      setWindow('20');
    } else if (nextType === 'rsi_threshold') {
      setThresholdDirection('above');
      setPeriod('12');
      setThreshold('');
    } else if (nextType === 'macd_cross') {
      setCrossDirection('bullish_cross');
      setFastPeriod('12');
      setSlowPeriod('26');
      setSignalPeriod('9');
    } else if (nextType === 'kdj_cross') {
      setCrossDirection('bullish_cross');
      setPeriod('9');
      setKPeriod('3');
      setDPeriod('3');
    } else if (nextType === 'cci_threshold') {
      setThresholdDirection('above');
      setPeriod('14');
      setThreshold('');
    } else if (nextType === 'portfolio_stop_loss') {
      setStopLossMode('near');
    } else if (nextType === 'market_light_status') {
      setMarketLightStatuses(['red', 'yellow']);
    } else if (nextType === 'market_light_score_drop') {
      setMinDrop('10');
    }
  };

  const toggleMarketLightStatus = (status: MarketLightStatus) => {
    setMarketLightStatuses((current) => (
      current.includes(status)
        ? current.filter((item) => item !== status)
        : [...current, status]
    ));
  };

  const setValidationError = (fieldId: string, message: string) => {
    setFormError(message);
    setFieldErrors({ [fieldId]: message });
    globalThis.setTimeout(() => document.getElementById(fieldId)?.focus(), 0);
  };

  const parsePositiveNumber = (value: string, label: string, fieldId: string): number | null => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setValidationError(fieldId, formatUiText(text.positiveNumber, { label }));
      return null;
    }
    return parsed;
  };

  const parseIntegerInRange = (value: string, label: string, fieldId: string, min = 2, max = 250): number | null => {
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < min || parsed > max) {
      setValidationError(fieldId, formatUiText(text.integerRange, { label, min, max }));
      return null;
    }
    return parsed;
  };

  const parseFiniteNumber = (value: string, label: string, fieldId: string): number | null => {
    if (value.trim() === '') {
      setValidationError(fieldId, formatUiText(text.required, { label }));
      return null;
    }
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      setValidationError(fieldId, formatUiText(text.finiteNumber, { label }));
      return null;
    }
    return parsed;
  };

  const parseRsiThreshold = (value: string): number | null => {
    const parsed = parseFiniteNumber(value, text.rsiThreshold, 'alert-rsi-threshold');
    if (parsed == null) return null;
    if (parsed < 0 || parsed > 100) {
      setValidationError('alert-rsi-threshold', text.rsiRange);
      return null;
    }
    return parsed;
  };

  const ensureRequiredBarsWithinLimit = (label: string, requiredBars: number, fieldId: string): boolean => {
    if (requiredBars > MAX_REQUESTED_DAYS) {
      setValidationError(fieldId, formatUiText(text.requiredBarsLimit, { label, requiredBars, max: MAX_REQUESTED_DAYS }));
      return false;
    }
    return true;
  };

  const buildParameters = (): AlertRuleCreateRequest['parameters'] | null => {
    if (alertType === 'price_cross') {
      const parsedPrice = parsePositiveNumber(price, text.priceThreshold, 'alert-price');
      if (parsedPrice == null) return null;
      return { direction: priceDirection, price: parsedPrice };
    }
    if (alertType === 'price_change_percent') {
      const parsedChangePct = parsePositiveNumber(changePct, text.changePctThreshold, 'alert-change-pct');
      if (parsedChangePct == null) return null;
      return { direction: changeDirection, changePct: parsedChangePct };
    }
    if (alertType === 'volume_spike') {
      const parsedMultiplier = parsePositiveNumber(multiplier, text.volumeMultiplier, 'alert-volume-multiplier');
      if (parsedMultiplier == null) return null;
      return { multiplier: parsedMultiplier };
    }
    if (alertType === 'ma_price_cross') {
      const parsedWindow = parseIntegerInRange(window, text.maWindow, 'alert-ma-window');
      if (parsedWindow == null) return null;
      return { direction: thresholdDirection, window: parsedWindow };
    }
    if (alertType === 'rsi_threshold') {
      const parsedPeriod = parseIntegerInRange(period, text.rsiPeriod, 'alert-rsi-period');
      const parsedThreshold = parseRsiThreshold(threshold);
      if (parsedPeriod == null || parsedThreshold == null) return null;
      return { direction: thresholdDirection, period: parsedPeriod, threshold: parsedThreshold };
    }
    if (alertType === 'macd_cross') {
      const parsedFast = parseIntegerInRange(fastPeriod, text.fastPeriod, 'alert-fast-period');
      const parsedSlow = parseIntegerInRange(slowPeriod, text.slowPeriod, 'alert-slow-period');
      const parsedSignal = parseIntegerInRange(signalPeriod, text.signalPeriod, 'alert-signal-period');
      if (parsedFast == null || parsedSlow == null || parsedSignal == null) return null;
      if (parsedFast >= parsedSlow) {
        setValidationError('alert-fast-period', text.fastLessThanSlow);
        return null;
      }
      if (!ensureRequiredBarsWithinLimit('MACD', parsedSlow + parsedSignal + 1, 'alert-slow-period')) return null;
      return {
        direction: crossDirection,
        fastPeriod: parsedFast,
        slowPeriod: parsedSlow,
        signalPeriod: parsedSignal,
      };
    }
    if (alertType === 'kdj_cross') {
      const parsedPeriod = parseIntegerInRange(period, text.kdjPeriod, 'alert-kdj-period');
      const parsedK = parseIntegerInRange(kPeriod, text.kPeriod, 'alert-k-period');
      const parsedD = parseIntegerInRange(dPeriod, text.dPeriod, 'alert-d-period');
      if (parsedPeriod == null || parsedK == null || parsedD == null) return null;
      if (!ensureRequiredBarsWithinLimit('KDJ', parsedPeriod + parsedK + parsedD + 1, 'alert-kdj-period')) return null;
      return { direction: crossDirection, period: parsedPeriod, kPeriod: parsedK, dPeriod: parsedD };
    }
    if (alertType === 'cci_threshold') {
      const parsedPeriod = parseIntegerInRange(period, text.cciPeriod, 'alert-cci-period');
      const parsedThreshold = parseFiniteNumber(threshold, text.cciThreshold, 'alert-cci-threshold');
      if (parsedPeriod == null || parsedThreshold == null) return null;
      return { direction: thresholdDirection, period: parsedPeriod, threshold: parsedThreshold };
    }
    if (alertType === 'portfolio_stop_loss') {
      return { mode: stopLossMode };
    }
    if (alertType === 'market_light_status') {
      if (marketLightStatuses.length === 0) {
        setFormError(text.noMarketStatus);
        return null;
      }
      return { statuses: marketLightStatuses };
    }
    if (alertType === 'market_light_score_drop') {
      const parsedMinDrop = parsePositiveNumber(minDrop, text.scoreDropThreshold, 'alert-score-drop');
      if (parsedMinDrop == null) return null;
      return { minDrop: parsedMinDrop };
    }
    return {};
  };

  const handleScopeChange = (value: string) => {
    const nextScope = value as AlertTargetScope;
    const nextType = defaultAlertTypeForScope(nextScope);
    setTargetScope(nextScope);
    setAlertType(nextType);
    setPortfolioTarget('all');
    setMarketRegion('cn');
    resetParameters(nextType);
    setFormError(null);
    setFieldErrors({});
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFieldErrors({});
    let resolvedTarget = target.trim();
    if (targetScope === 'single_symbol') {
      const targetValidation = validateStockCode(target);
      if (!targetValidation.valid) {
        setValidationError(
          'alert-target-code',
          language === 'zh' ? (targetValidation.message ?? text.invalidStockCode) : text.invalidStockCode,
        );
        return;
      }
      resolvedTarget = targetValidation.normalized;
    } else if (targetScope === 'watchlist') {
      resolvedTarget = 'default';
    } else if (targetScope === 'market') {
      resolvedTarget = marketRegion;
    } else {
      resolvedTarget = portfolioTarget;
    }

    const parameters = buildParameters();
    if (parameters == null) return;

    setFormError(null);
    const submitted = await onSubmit({
      name: name.trim() || undefined,
      targetScope,
      target: resolvedTarget,
      alertType,
      parameters,
      severity,
      enabled,
    });
    if (submitted === false) return;
    // In edit mode the parent closes the modal on success; keep the values so
    // a re-open (or a failed follow-up) does not lose the edited rule.
    if (mode === 'edit') return;
    setName('');
    setTarget('');
    setPortfolioTarget('all');
    setMarketRegion('cn');
    setPrice('');
    setChangePct('');
    setMultiplier('');
    setWindow('20');
    setPeriod('12');
    setThreshold('');
    setFastPeriod('12');
    setSlowPeriod('26');
    setSignalPeriod('9');
    setKPeriod('3');
    setDPeriod('3');
    setMarketLightStatuses(['red', 'yellow']);
    setMinDrop('10');
    resetParameters(alertType);
    setEnabled(true);
  };

  const renderTargetControl = () => {
    if (targetScope === 'single_symbol') {
      return (
        <Input
          id="alert-target-code"
          label={text.targetCode}
          value={target}
          onChange={(event) => setTarget(event.target.value)}
          placeholder="600519 / AAPL / hk00700"
          error={fieldErrors['alert-target-code']}
          disabled={isSubmitting}
        />
      );
    }
    if (targetScope === 'watchlist') {
      return (
        <Input
          label={text.target}
          value="default"
          onChange={() => undefined}
          disabled
        />
      );
    }
    if (targetScope === 'market') {
      return (
        <Select
          label={text.marketRegion}
          value={marketRegion}
          options={ALERT_MARKET_REGION_OPTIONS[language]}
          disabled={isSubmitting}
          onChange={(value) => setMarketRegion(value as MarketRegion)}
        />
      );
    }
    return (
      <div className="space-y-2">
        <Select
          label={text.account}
          value={portfolioTarget}
          options={portfolioTargetOptions}
          disabled={isSubmitting}
          onChange={setPortfolioTarget}
        />
        {accountsError ? <p role="alert" className="text-xs text-warning">{accountsError}</p> : null}
      </div>
    );
  };

  return (
    <form className="space-y-4" noValidate onSubmit={(event) => void handleSubmit(event)}>
        <div className="grid gap-4 md:grid-cols-2">
          <Input
            label={text.ruleName}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={text.ruleNamePlaceholder}
            disabled={isSubmitting}
          />
          <Select
            label={text.targetScope}
            value={targetScope}
            options={ALERT_TARGET_SCOPE_OPTIONS[language]}
            disabled={isSubmitting}
            onChange={handleScopeChange}
          />
          {renderTargetControl()}
          <Select
            label={text.ruleType}
            value={alertType}
            options={alertTypeOptions}
            disabled={isSubmitting}
            onChange={(value) => {
              const nextType = value as AlertType;
              setAlertType(nextType);
              resetParameters(nextType);
            }}
          />
          <Select
            label={text.severity}
            value={severity}
            options={ALERT_SEVERITY_OPTIONS[language]}
            disabled={isSubmitting}
            onChange={(value) => setSeverity(value as AlertSeverity)}
          />
        </div>

        {alertType === 'price_cross' ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Select
              label={text.direction}
              value={priceDirection}
              options={ALERT_PRICE_DIRECTION_OPTIONS[language]}
              disabled={isSubmitting}
              onChange={(value) => setPriceDirection(value as 'above' | 'below')}
            />
            <Input
              id="alert-price"
              label={text.priceThreshold}
              type="number"
              min="0"
              step="0.0001"
              value={price}
              error={fieldErrors['alert-price']}
              onChange={(event) => setPrice(event.target.value)}
              disabled={isSubmitting}
            />
          </div>
        ) : null}

        {alertType === 'price_change_percent' ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Select
              label={text.direction}
              value={changeDirection}
              options={ALERT_CHANGE_DIRECTION_OPTIONS[language]}
              disabled={isSubmitting}
              onChange={(value) => setChangeDirection(value as 'up' | 'down')}
            />
            <Input
              id="alert-change-pct"
              label={text.changePctThreshold}
              type="number"
              min="0"
              step="0.01"
              value={changePct}
              error={fieldErrors['alert-change-pct']}
              onChange={(event) => setChangePct(event.target.value)}
              disabled={isSubmitting}
            />
          </div>
        ) : null}

        {alertType === 'volume_spike' ? (
          <Input
            id="alert-volume-multiplier"
            label={text.volumeMultiplier}
            type="number"
            min="0"
            step="0.01"
            value={multiplier}
            error={fieldErrors['alert-volume-multiplier']}
            onChange={(event) => setMultiplier(event.target.value)}
            disabled={isSubmitting}
          />
        ) : null}

        {alertType === 'ma_price_cross' ? (
          <div className="grid gap-4 md:grid-cols-2">
            <Select
              label={text.maDirection}
              value={thresholdDirection}
              options={ALERT_THRESHOLD_DIRECTION_OPTIONS[language]}
              disabled={isSubmitting}
              onChange={(value) => setThresholdDirection(value as 'above' | 'below')}
            />
            <Input
              id="alert-ma-window"
              label={text.maWindow}
              type="number"
              min="2"
              max="250"
              step="1"
              value={window}
              error={fieldErrors['alert-ma-window']}
              onChange={(event) => setWindow(event.target.value)}
              disabled={isSubmitting}
            />
          </div>
        ) : null}

        {alertType === 'rsi_threshold' ? (
          <div className="grid gap-4 md:grid-cols-3">
            <Select
              label={text.thresholdDirection}
              value={thresholdDirection}
              options={ALERT_THRESHOLD_DIRECTION_OPTIONS[language]}
              disabled={isSubmitting}
              onChange={(value) => setThresholdDirection(value as 'above' | 'below')}
            />
            <Input
              id="alert-rsi-period"
              label={text.rsiPeriod}
              type="number"
              min="2"
              max="250"
              step="1"
              value={period}
              error={fieldErrors['alert-rsi-period']}
              onChange={(event) => setPeriod(event.target.value)}
              disabled={isSubmitting}
            />
            <Input
              id="alert-rsi-threshold"
              label={text.rsiThreshold}
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={threshold}
              error={fieldErrors['alert-rsi-threshold']}
              onChange={(event) => setThreshold(event.target.value)}
              disabled={isSubmitting}
            />
          </div>
        ) : null}

        {alertType === 'macd_cross' ? (
          <div className="grid gap-4 md:grid-cols-4">
            <Select
              label={text.crossDirection}
              value={crossDirection}
              options={ALERT_CROSS_DIRECTION_OPTIONS[language]}
              disabled={isSubmitting}
              onChange={(value) => setCrossDirection(value as 'bullish_cross' | 'bearish_cross')}
            />
            <Input
              id="alert-fast-period"
              label={text.fastPeriod}
              type="number"
              min="2"
              max="250"
              step="1"
              value={fastPeriod}
              error={fieldErrors['alert-fast-period']}
              onChange={(event) => setFastPeriod(event.target.value)}
              disabled={isSubmitting}
            />
            <Input
              id="alert-slow-period"
              label={text.slowPeriod}
              type="number"
              min="2"
              max="250"
              step="1"
              value={slowPeriod}
              error={fieldErrors['alert-slow-period']}
              onChange={(event) => setSlowPeriod(event.target.value)}
              disabled={isSubmitting}
            />
            <Input
              id="alert-signal-period"
              label={text.signalPeriod}
              type="number"
              min="2"
              max="250"
              step="1"
              value={signalPeriod}
              error={fieldErrors['alert-signal-period']}
              onChange={(event) => setSignalPeriod(event.target.value)}
              disabled={isSubmitting}
            />
          </div>
        ) : null}

        {alertType === 'kdj_cross' ? (
          <div className="grid gap-4 md:grid-cols-4">
            <Select
              label={text.crossDirection}
              value={crossDirection}
              options={ALERT_CROSS_DIRECTION_OPTIONS[language]}
              disabled={isSubmitting}
              onChange={(value) => setCrossDirection(value as 'bullish_cross' | 'bearish_cross')}
            />
            <Input
              id="alert-kdj-period"
              label={text.kdjPeriod}
              type="number"
              min="2"
              max="250"
              step="1"
              value={period}
              error={fieldErrors['alert-kdj-period']}
              onChange={(event) => setPeriod(event.target.value)}
              disabled={isSubmitting}
            />
            <Input
              id="alert-k-period"
              label={text.kPeriod}
              type="number"
              min="2"
              max="250"
              step="1"
              value={kPeriod}
              error={fieldErrors['alert-k-period']}
              onChange={(event) => setKPeriod(event.target.value)}
              disabled={isSubmitting}
            />
            <Input
              id="alert-d-period"
              label={text.dPeriod}
              type="number"
              min="2"
              max="250"
              step="1"
              value={dPeriod}
              error={fieldErrors['alert-d-period']}
              onChange={(event) => setDPeriod(event.target.value)}
              disabled={isSubmitting}
            />
          </div>
        ) : null}

        {alertType === 'cci_threshold' ? (
          <div className="grid gap-4 md:grid-cols-3">
            <Select
              label={text.thresholdDirection}
              value={thresholdDirection}
              options={ALERT_THRESHOLD_DIRECTION_OPTIONS[language]}
              disabled={isSubmitting}
              onChange={(value) => setThresholdDirection(value as 'above' | 'below')}
            />
            <Input
              id="alert-cci-period"
              label={text.cciPeriod}
              type="number"
              min="2"
              max="250"
              step="1"
              value={period}
              error={fieldErrors['alert-cci-period']}
              onChange={(event) => setPeriod(event.target.value)}
              disabled={isSubmitting}
            />
            <Input
              id="alert-cci-threshold"
              label={text.cciThreshold}
              type="number"
              step="0.01"
              value={threshold}
              error={fieldErrors['alert-cci-threshold']}
              onChange={(event) => setThreshold(event.target.value)}
              disabled={isSubmitting}
            />
          </div>
        ) : null}

        {alertType === 'portfolio_stop_loss' ? (
          <Select
            label={text.stopLossMode}
            value={stopLossMode}
            options={ALERT_STOP_LOSS_MODE_OPTIONS[language]}
            disabled={isSubmitting}
            onChange={(value) => setStopLossMode(value as PortfolioStopLossMode)}
          />
        ) : null}

        {alertType === 'market_light_status' ? (
          <div className="space-y-2">
            <div className="text-sm font-medium text-foreground">{text.triggerStatus}</div>
            <div className="grid gap-3 sm:grid-cols-2">
              {ALERT_MARKET_LIGHT_STATUS_OPTIONS[language].map((option) => (
                <Checkbox
                  key={option.value}
                  label={option.label}
                  checked={marketLightStatuses.includes(option.value)}
                  disabled={isSubmitting}
                  onChange={() => toggleMarketLightStatus(option.value)}
                />
              ))}
            </div>
          </div>
        ) : null}

        {alertType === 'market_light_score_drop' ? (
          <Input
            id="alert-score-drop"
            label={text.scoreDropThreshold}
            type="number"
            min="0"
            max="100"
            step="1"
            value={minDrop}
            error={fieldErrors['alert-score-drop']}
            onChange={(event) => setMinDrop(event.target.value)}
            disabled={isSubmitting}
          />
        ) : null}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Checkbox
            label={text.enableAfterCreate}
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            disabled={isSubmitting}
          />
          <Button variant="primary" type="submit" isLoading={isSubmitting} loadingText={mode === 'edit' ? text.updating : text.creating}>
            {mode === 'edit' ? text.update : text.create}
          </Button>
        </div>
        {formError ? (
          <p role={Object.keys(fieldErrors).length === 0 ? 'alert' : undefined} className="text-sm text-danger">
            {formError}
          </p>
        ) : null}
    </form>
  );
};
