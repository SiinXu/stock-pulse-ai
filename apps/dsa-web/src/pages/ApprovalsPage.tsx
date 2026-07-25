import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Clock3, RefreshCw, ShieldAlert, XCircle } from 'lucide-react';
import { approvalsApi } from '../api/approvals';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  ApiErrorAlert,
  Badge,
  Button,
  Checkbox,
  EmptyState,
  Input,
  InlineAlert,
  PageHeader,
  Section,
  StatePanel,
  Switch,
  WorkspacePage,
} from '../components/common';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { APPROVALS_TEXT } from '../locales/approvals';
import type {
  ApprovalDecision,
  ApprovalProposal,
  ApprovalRiskSource,
  ApprovalRule,
  ApprovalStatus,
} from '../types/approvals';

const RULE_MIN_SECONDS = 30;
const RULE_MAX_SECONDS = 3600;

function statusVariant(status: ApprovalStatus) {
  if (status === 'approved') return 'success' as const;
  if (status === 'pending') return 'warning' as const;
  if (status === 'rejected' || status === 'expired') return 'danger' as const;
  return 'history' as const;
}

const ApprovalsPage: React.FC = () => {
  const { language } = useUiLanguage();
  const text = APPROVALS_TEXT[language];
  const [rule, setRule] = useState<ApprovalRule | null>(null);
  const [proposals, setProposals] = useState<ApprovalProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [riskSources, setRiskSources] = useState<ApprovalRiskSource[]>(['risk_veto', 'risk_downgrade']);
  const [expiry, setExpiry] = useState(300);
  const [savingRule, setSavingRule] = useState(false);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const mountedRef = useRef(true);

  const applyRule = useCallback((next: ApprovalRule) => {
    setRule(next);
    setEnabled(next.enabled);
    setRiskSources(next.riskSources);
    setExpiry(next.expiresInSeconds);
  }, []);

  const load = useCallback(async (background = false) => {
    if (background) setRefreshing(true);
    else setLoading(true);
    try {
      const [nextRule, page] = await Promise.all([
        approvalsApi.getRule(),
        approvalsApi.list({ page: 1, pageSize: 50 }),
      ]);
      if (!mountedRef.current) return;
      applyRule(nextRule);
      setProposals(page.items);
      setError(null);
    } catch (cause) {
      if (mountedRef.current) setError(getParsedApiError(cause, language));
    } finally {
      if (mountedRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [applyRule, language]);

  const pollProposals = useCallback(async () => {
    setRefreshing(true);
    try {
      const page = await approvalsApi.list({ page: 1, pageSize: 50 });
      if (!mountedRef.current) return;
      setProposals(page.items);
    } catch (cause) {
      if (mountedRef.current) setError(getParsedApiError(cause, language));
    } finally {
      if (mountedRef.current) setRefreshing(false);
    }
  }, [language]);

  useEffect(() => {
    document.title = text.documentTitle;
  }, [text.documentTitle]);

  useEffect(() => {
    mountedRef.current = true;
    void load();
    const refreshTimer = window.setInterval(() => void pollProposals(), 5_000);
    const countdownTimer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      mountedRef.current = false;
      window.clearInterval(refreshTimer);
      window.clearInterval(countdownTimer);
    };
  }, [load, pollProposals]);

  const pending = useMemo(
    () => proposals.filter((proposal) => proposal.status === 'pending'),
    [proposals],
  );
  const terminal = useMemo(
    () => proposals.filter((proposal) => proposal.status !== 'pending'),
    [proposals],
  );

  const toggleRiskSource = (source: ApprovalRiskSource, checked: boolean) => {
    setRiskSources((current) => (
      checked
        ? [...new Set([...current, source])]
        : current.filter((item) => item !== source)
    ));
  };

  const saveRule = async () => {
    if (!rule || riskSources.length === 0) return;
    setSavingRule(true);
    setNotice(null);
    try {
      const next = await approvalsApi.updateRule({
        enabled,
        riskSources,
        expiresInSeconds: expiry,
        expectedVersion: rule.version,
      });
      applyRule(next);
      setError(null);
      setNotice(text.ruleSaved);
    } catch (cause) {
      const parsed = getParsedApiError(cause, language);
      if (parsed.status === 409) {
        await load(true);
        setNotice(text.conflictRefresh);
      } else {
        setError(parsed);
      }
    } finally {
      setSavingRule(false);
    }
  };

  const decide = async (proposal: ApprovalProposal, decision: ApprovalDecision) => {
    if (decidingId) return;
    setDecidingId(proposal.id);
    setNotice(null);
    try {
      const updated = await approvalsApi.decide(proposal.id, decision, proposal.version);
      setProposals((current) => current.map((item) => (
        item.id === updated.id ? updated : item
      )));
      setError(null);
    } catch (cause) {
      const parsed = getParsedApiError(cause, language);
      if (parsed.status === 409) {
        await pollProposals();
        setNotice(text.conflictRefresh);
      } else {
        setError(parsed);
      }
    } finally {
      setDecidingId(null);
    }
  };

  const statusLabel = (status: ApprovalStatus) => ({
    pending: text.statusPending,
    approved: text.statusApproved,
    rejected: text.statusRejected,
    expired: text.statusExpired,
    cancelled: text.statusCancelled,
  })[status];

  const renderProposal = (proposal: ApprovalProposal) => {
    const seconds = Math.max(0, Math.ceil((new Date(proposal.expiresAt).getTime() - now) / 1000));
    const pendingActive = proposal.status === 'pending' && seconds > 0;
    const timingLabel = proposal.status === 'pending'
      ? (pendingActive ? text.expiresIn.replace('{seconds}', String(seconds)) : text.expired)
      : (proposal.status === 'expired' ? text.expired : statusLabel(proposal.status));
    return (
      <article
        key={proposal.id}
        className="rounded-xl border border-border bg-surface-2/60 p-4"
        data-testid={`approval-${proposal.id}`}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={statusVariant(proposal.status)}>
                {statusLabel(proposal.status)}
              </Badge>
              <span className="font-mono text-xs text-secondary-text">
                {proposal.context.stockCode || '—'}
              </span>
            </div>
            <p className="mt-3 text-sm text-foreground">{proposal.context.riskSummary}</p>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-secondary-text">
            <Clock3 className="h-4 w-4" aria-hidden="true" />
            {timingLabel}
          </div>
        </div>
        <dl className="mt-4 grid gap-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-secondary-text">{text.originalSignal}</dt>
            <dd className="mt-1 text-sm font-semibold text-foreground">{proposal.context.originalSignal}</dd>
          </div>
          <div>
            <dt className="text-xs text-secondary-text">{text.conservativeSignal}</dt>
            <dd className="mt-1 text-sm font-semibold text-foreground">{proposal.context.conservativeSignal}</dd>
          </div>
          <div>
            <dt className="text-xs text-secondary-text">{text.riskSummary}</dt>
            <dd className="mt-1 text-sm text-foreground">{proposal.context.riskSource}</dd>
          </div>
        </dl>
        {proposal.status === 'pending' ? (
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="primary"
              size="comfortable"
              isLoading={decidingId === proposal.id}
              loadingText={text.processing}
              disabled={!pendingActive || decidingId !== null}
              onClick={() => void decide(proposal, 'approved')}
            >
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              {text.approve}
            </Button>
            <Button
              variant="danger-subtle"
              size="comfortable"
              disabled={!pendingActive || decidingId !== null}
              onClick={() => void decide(proposal, 'rejected')}
            >
              <XCircle className="h-4 w-4" aria-hidden="true" />
              {text.reject}
            </Button>
          </div>
        ) : (
          <p className="mt-4 text-xs text-secondary-text">
            {proposal.consumedAt ? text.consumed : text.notConsumed}
          </p>
        )}
      </article>
    );
  };

  return (
    <WorkspacePage data-testid="approvals-page" contentClassName="space-y-6">
      <PageHeader
        eyebrow={text.eyebrow}
        title={text.title}
        description={text.description}
        actions={(
          <Button
            variant="outline"
            size="comfortable"
            isLoading={refreshing}
            onClick={() => void load(true)}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            {text.refresh}
          </Button>
        )}
      />

      {error ? (
        <ApiErrorAlert
          error={error}
          actionLabel={text.recover}
          onAction={() => void load()}
          onDismiss={() => setError(null)}
        />
      ) : null}
      {notice ? <InlineAlert variant="info" title={text.title} message={notice} /> : null}

      <Section
        title={text.ruleTitle}
        description={text.ruleDescription}
        level="canvas"
        padding="md"
        actions={<ShieldAlert className="h-5 w-5 text-warning" aria-hidden="true" />}
      >
        {loading || !rule ? (
          <StatePanel state="loading" title={text.refresh} size="compact" />
        ) : (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
            <div className="space-y-4">
              <label className="flex min-h-11 items-center justify-between gap-4 rounded-lg border border-border px-3">
                <span className="text-sm font-medium text-foreground">{text.enabled}</span>
                <Switch
                  checked={enabled}
                  onCheckedChange={setEnabled}
                  aria-label={text.enabled}
                  testId="approval-rule-enabled"
                />
              </label>
              <fieldset>
                <legend className="mb-2 text-sm font-medium text-foreground">{text.riskSources}</legend>
                <div className="flex flex-wrap gap-4">
                  <Checkbox
                    label={text.riskVeto}
                    checked={riskSources.includes('risk_veto')}
                    onChange={(event) => toggleRiskSource('risk_veto', event.currentTarget.checked)}
                  />
                  <Checkbox
                    label={text.riskDowngrade}
                    checked={riskSources.includes('risk_downgrade')}
                    onChange={(event) => toggleRiskSource('risk_downgrade', event.currentTarget.checked)}
                  />
                </div>
              </fieldset>
            </div>
            <div className="space-y-3">
              <Input
                type="number"
                min={RULE_MIN_SECONDS}
                max={RULE_MAX_SECONDS}
                label={text.expiry}
                hint={text.expiryHint}
                value={expiry}
                onChange={(event) => setExpiry(Number(event.currentTarget.value))}
              />
              <div className="grid">
                <Button
                  variant="primary"
                  size="comfortable"
                  isLoading={savingRule}
                  loadingText={text.saving}
                  disabled={
                    riskSources.length === 0
                    || !Number.isInteger(expiry)
                    || expiry < RULE_MIN_SECONDS
                    || expiry > RULE_MAX_SECONDS
                  }
                  onClick={() => void saveRule()}
                >
                  {text.saveRule}
                </Button>
              </div>
            </div>
          </div>
        )}
      </Section>

      <Section title={text.pendingTitle} level="canvas" padding="md">
        {loading ? (
          <StatePanel state="loading" title={text.refresh} size="compact" />
        ) : pending.length === 0 ? (
          <EmptyState compact title={text.emptyPending} />
        ) : (
          <div className="space-y-3">{pending.map(renderProposal)}</div>
        )}
      </Section>

      <Section title={text.historyTitle} level="canvas" padding="md">
        {terminal.length === 0 ? (
          <EmptyState compact title={text.emptyHistory} />
        ) : (
          <div className="space-y-3">{terminal.map(renderProposal)}</div>
        )}
      </Section>
    </WorkspacePage>
  );
};

export default ApprovalsPage;
