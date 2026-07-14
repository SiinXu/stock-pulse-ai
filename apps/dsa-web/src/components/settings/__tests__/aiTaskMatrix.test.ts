import { describe, expect, it } from 'vitest';
import { resolveAiTaskMatrix } from '../aiTaskMatrix';

function accessor(values: Record<string, string>) {
  return (key: string) => values[key] ?? '';
}

describe('resolveAiTaskMatrix', () => {
  it('resolves the four task rows in order', () => {
    const rows = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'openai/gpt-4o-mini' }));
    expect(rows.map((row) => row.id)).toEqual(['report', 'market_review', 'agent', 'vision']);
  });

  it('market review inherits the report model', () => {
    const rows = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'openai/gpt-4o' }));
    const market = rows.find((row) => row.id === 'market_review')!;
    expect(market.primaryModel).toBe('openai/gpt-4o');
    expect(market.primaryInherited).toBe(true);
  });

  it('agent uses its dedicated model when set, otherwise inherits', () => {
    const withAgent = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'openai/gpt-4o', AGENT_LITELLM_MODEL: 'openai/o3' }));
    const agentRow = withAgent.find((row) => row.id === 'agent')!;
    expect(agentRow.primaryModel).toBe('openai/o3');
    expect(agentRow.primaryInherited).toBe(false);

    const withoutAgent = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'openai/gpt-4o' }));
    const inherited = withoutAgent.find((row) => row.id === 'agent')!;
    expect(inherited.primaryModel).toBe('openai/gpt-4o');
    expect(inherited.primaryInherited).toBe(true);
  });

  it('vision falls back to the report model and carries no fallback list', () => {
    const rows = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'openai/gpt-4o', LITELLM_FALLBACK_MODELS: 'a,b' }));
    const vision = rows.find((row) => row.id === 'vision')!;
    expect(vision.primaryModel).toBe('openai/gpt-4o');
    expect(vision.fallbackModels).toEqual([]);
  });

  it('parses fallback models and applies them to model tasks', () => {
    const rows = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'm', LITELLM_FALLBACK_MODELS: ' a , b ,, c ' }));
    const report = rows.find((row) => row.id === 'report')!;
    expect(report.fallbackModels).toEqual(['a', 'b', 'c']);
  });

  it('defaults the execution backend to litellm and surfaces the failover backend', () => {
    const rows = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'm', GENERATION_FALLBACK_BACKEND: 'codex_cli' }));
    expect(rows[0].backendId).toBe('litellm');
    expect(rows[0].fallbackBackendId).toBe('codex_cli');
  });

  it('marks a task without a resolvable model as inactive', () => {
    const rows = resolveAiTaskMatrix(accessor({}));
    expect(rows.every((row) => row.active === false)).toBe(true);
    const withModel = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'm' }));
    expect(withModel.find((row) => row.id === 'report')!.active).toBe(true);
  });

  describe('authoritative status', () => {
    it('marks an empty model as unconfigured', () => {
      const rows = resolveAiTaskMatrix(accessor({}), { availableRoutes: new Set(['openai/gpt-4o']) });
      const report = rows.find((row) => row.id === 'report')!;
      expect(report.status).toBe('unconfigured');
      expect(report.active).toBe(false);
    });

    it('marks a model declared by an enabled connection as active', () => {
      const rows = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'openai/gpt-4o' }), {
        availableRoutes: new Set(['openai/gpt-4o']),
      });
      const report = rows.find((row) => row.id === 'report')!;
      expect(report.status).toBe('active');
      expect(report.active).toBe(true);
    });

    it('marks a set model not declared by any connection as unavailable', () => {
      const rows = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'openai/gpt-4o' }), {
        availableRoutes: new Set(['anthropic/claude-3-5-sonnet']),
      });
      const report = rows.find((row) => row.id === 'report')!;
      expect(report.status).toBe('unavailable');
      expect(report.active).toBe(false);
    });

    it('treats a selected local CLI backend as active without a route set', () => {
      const rows = resolveAiTaskMatrix(accessor({ GENERATION_BACKEND: 'codex_cli' }), {
        availableRoutes: new Set<string>(),
      });
      expect(rows.every((row) => row.status === 'active')).toBe(true);
    });

    it('falls back to non-empty status when no route set is provided', () => {
      const rows = resolveAiTaskMatrix(accessor({ LITELLM_MODEL: 'openai/gpt-4o' }));
      const report = rows.find((row) => row.id === 'report')!;
      expect(report.status).toBe('active');
    });
  });
});
