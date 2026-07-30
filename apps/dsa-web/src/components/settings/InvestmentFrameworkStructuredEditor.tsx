// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
import { useRef, useState } from 'react';
import type React from 'react';
import { ArrowDown, ArrowUp, Copy, Plus, Trash2 } from 'lucide-react';
import type {
  InvestmentFrameworkContent,
  InvestmentFrameworkDecisionBranch,
  InvestmentFrameworkDecisionNode,
  InvestmentFrameworkEvaluationDimension,
} from '../../types/investmentFramework';
import type { UiTextKey } from '../../i18n/uiText';
import { Button, ConfirmDialog } from '../common';
import LineListTextarea from './LineListTextarea';
import { SettingsAlert } from './SettingsAlert';
import {
  canCommitInvestmentFrameworkNodeRename,
  INVESTMENT_FRAMEWORK_LIMITS,
  nextFrameworkNodeId,
  nodeDeleteBlockers,
  normalizeInvestmentFrameworkNodeId,
  type InvestmentFrameworkValidationIssue,
} from './investmentFrameworkEditorModel';

type InvestmentFrameworkStructuredEditorProps = {
  content: InvestmentFrameworkContent;
  issues: InvestmentFrameworkValidationIssue[];
  disabled?: boolean;
  onChange: (content: InvestmentFrameworkContent) => void;
  formatIssue: (issue: InvestmentFrameworkValidationIssue) => string;
  t: (key: UiTextKey, params?: Record<string, string | number>) => string;
};

type NodeRenameSession = {
  nodeIndex: number;
  originalNodeId: string;
  rootReferencesNode: boolean;
  branchReferences: Array<{ nodeIndex: number; branchIndex: number }>;
};

const fieldClass =
  'w-full rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] px-3 py-2 text-sm text-foreground outline-none transition-[border-color,background-color] focus:border-[var(--settings-border-strong)]';

function moveItem<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length) return items;
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

const InvestmentFrameworkStructuredEditor: React.FC<
  InvestmentFrameworkStructuredEditorProps
> = ({
  content,
  issues,
  disabled = false,
  onChange,
  formatIssue,
  t,
}) => {
  const [pendingDeleteNode, setPendingDeleteNode] = useState<number | null>(null);
  const [dependencyWarning, setDependencyWarning] = useState('');
  const renameSession = useRef<NodeRenameSession | null>(null);
  const nodes = content.decisionTree ?? [];
  const dimensions = content.evaluationDimensions ?? [];

  const setNodes = (decisionTree: InvestmentFrameworkDecisionNode[], rootNodeId = content.rootNodeId) => {
    onChange({ ...content, decisionTree, rootNodeId: rootNodeId ?? null });
  };

  const updateNode = (index: number, update: Partial<InvestmentFrameworkDecisionNode>) => {
    const next = nodes.map((node, nodeIndex) => (
      nodeIndex === index ? { ...node, ...update } : node
    ));
    setNodes(next);
  };

  const beginNodeRename = (nodeIndex: number) => {
    if (renameSession.current?.nodeIndex === nodeIndex) return;
    const originalNodeId = nodes[nodeIndex]?.nodeId;
    if (originalNodeId === undefined) return;
    const normalizedNodeId = normalizeInvestmentFrameworkNodeId(originalNodeId);
    const branchReferences: NodeRenameSession['branchReferences'] = [];
    nodes.forEach((node, currentNodeIndex) => {
      node.branches.forEach((branch, branchIndex) => {
        if (
          normalizedNodeId
          && normalizeInvestmentFrameworkNodeId(branch.targetNodeId) === normalizedNodeId
        ) {
          branchReferences.push({ nodeIndex: currentNodeIndex, branchIndex });
        }
      });
    });
    renameSession.current = {
      nodeIndex,
      originalNodeId,
      rootReferencesNode: Boolean(
        normalizedNodeId
        && normalizeInvestmentFrameworkNodeId(content.rootNodeId) === normalizedNodeId
      ),
      branchReferences,
    };
  };

  const updateNodeIdDraft = (nodeIndex: number, nextNodeId: string) => {
    beginNodeRename(nodeIndex);
    updateNode(nodeIndex, { nodeId: nextNodeId });
  };

  const finishNodeRename = (nodeIndex: number) => {
    const session = renameSession.current;
    if (!session || session.nodeIndex !== nodeIndex) return;
    renameSession.current = null;
    const nextNodeId = nodes[nodeIndex]?.nodeId;
    if (
      nextNodeId === undefined
      || !canCommitInvestmentFrameworkNodeRename(nodes, nodeIndex, nextNodeId)
    ) {
      updateNode(nodeIndex, { nodeId: session.originalNodeId });
      return;
    }
    const referencedBranches = new Set(
      session.branchReferences.map(
        (reference) => `${reference.nodeIndex}:${reference.branchIndex}`,
      ),
    );
    const next = nodes.map((node, currentNodeIndex) => ({
      ...node,
      branches: node.branches.map((branch, branchIndex) => (
        referencedBranches.has(`${currentNodeIndex}:${branchIndex}`)
          ? { ...branch, targetNodeId: nextNodeId }
          : branch
      )),
    }));
    setNodes(
      next,
      session.rootReferencesNode ? nextNodeId : content.rootNodeId,
    );
  };

  const updateBranch = (
    nodeIndex: number,
    branchIndex: number,
    update: Partial<InvestmentFrameworkDecisionBranch>,
  ) => {
    const branches = nodes[nodeIndex].branches.map((branch, currentIndex) => (
      currentIndex === branchIndex ? { ...branch, ...update } : branch
    ));
    updateNode(nodeIndex, { branches });
  };

  const addNode = () => {
    const nodeId = nextFrameworkNodeId(nodes);
    const nextNode: InvestmentFrameworkDecisionNode = {
      nodeId,
      question: '',
      branches: [{ condition: '', targetNodeId: null, outcome: '' }],
    };
    setNodes([...nodes, nextNode], content.rootNodeId || nodeId);
  };

  const duplicateNode = (index: number) => {
    const source = nodes[index];
    const nodeId = nextFrameworkNodeId(
      nodes,
      `${normalizeInvestmentFrameworkNodeId(source.nodeId)}-copy`,
    );
    setNodes([
      ...nodes.slice(0, index + 1),
      {
        ...source,
        nodeId,
        branches: source.branches.map((branch) => ({ ...branch })),
      },
      ...nodes.slice(index + 1),
    ]);
  };

  const requestDeleteNode = (index: number) => {
    const node = nodes[index];
    const blockers = nodeDeleteBlockers(content, node.nodeId);
    if (blockers.length) {
      setDependencyWarning(t('settings.frameworkNodeDeleteBlocked', {
        node: node.nodeId,
        dependencies: blockers.join(', '),
      }));
      return;
    }
    setDependencyWarning('');
    setPendingDeleteNode(index);
  };

  const deleteNode = () => {
    if (pendingDeleteNode === null) return;
    setNodes(nodes.filter((_node, index) => index !== pendingDeleteNode));
    setPendingDeleteNode(null);
  };

  const setDimensions = (evaluationDimensions: InvestmentFrameworkEvaluationDimension[]) => {
    onChange({ ...content, evaluationDimensions });
  };

  const updateDimension = (
    index: number,
    update: Partial<InvestmentFrameworkEvaluationDimension>,
  ) => {
    setDimensions(dimensions.map((dimension, currentIndex) => (
      currentIndex === index ? { ...dimension, ...update } : dimension
    )));
  };

  const addDimension = () => {
    setDimensions([
      ...dimensions,
      { name: '', weight: 0, criteria: [], description: null },
    ]);
  };

  const duplicateDimension = (index: number) => {
    const source = dimensions[index];
    setDimensions([
      ...dimensions.slice(0, index + 1),
      {
        ...source,
        name: `${source.name} ${t('common.copy')}`.trim(),
        criteria: [...(source.criteria ?? [])],
      },
      ...dimensions.slice(index + 1),
    ]);
  };

  const treeIssues = issues.filter((issue) => (
    issue.path.startsWith('decisionTree') || issue.path === 'rootNodeId'
  ));
  const dimensionIssues = issues.filter((issue) => issue.path.startsWith('evaluationDimensions'));

  return (
    <div className="space-y-6">
      <section className="space-y-3" aria-labelledby="framework-decision-tree-heading">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 id="framework-decision-tree-heading" className="text-base font-semibold text-foreground">
              {t('settings.frameworkDecisionTree')}
            </h3>
            <p className="mt-1 text-xs leading-5 text-secondary-text">
              {t('settings.frameworkDecisionTreeDescription')}
            </p>
            <p className="mt-1 text-xs text-muted-text">
              {t('settings.frameworkLimitUsage', {
                current: nodes.length,
                limit: INVESTMENT_FRAMEWORK_LIMITS.nodes,
              })}
            </p>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="compact"
            disabled={disabled || nodes.length >= INVESTMENT_FRAMEWORK_LIMITS.nodes}
            onClick={addNode}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('settings.frameworkAddNode')}
          </Button>
        </div>

        {dependencyWarning ? (
          <SettingsAlert
            title={t('settings.frameworkDependencyWarning')}
            message={dependencyWarning}
            variant="error"
          />
        ) : null}
        {treeIssues.length ? (
          <SettingsAlert
            title={t('settings.frameworkTreeValidation')}
            message={treeIssues.map(formatIssue).join(' · ')}
            variant="error"
          />
        ) : null}

        {nodes.length ? (
          <label className="block space-y-1" htmlFor="investment-framework-root">
            <span className="text-sm font-medium text-foreground">
              {t('settings.frameworkRootNode')}
            </span>
            <select
              id="investment-framework-root"
              className={fieldClass}
              value={content.rootNodeId ?? ''}
              disabled={disabled}
              onChange={(event) => onChange({ ...content, rootNodeId: event.target.value || null })}
            >
              <option value="">{t('settings.frameworkSelectRoot')}</option>
              {nodes.map((node, index) => (
                <option key={`${node.nodeId}-${index}`} value={node.nodeId}>
                  {node.nodeId || t('settings.frameworkUnnamedNode', { number: index + 1 })}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="rounded-lg border border-dashed settings-border px-3 py-4 text-xs text-muted-text">
            {t('settings.frameworkDecisionTreeEmpty')}
          </p>
        )}

        <div className="space-y-4">
          {nodes.map((node, nodeIndex) => {
            const nodeIssues = issues.filter((issue) => issue.path.startsWith(`decisionTree.${nodeIndex}`));
            return (
              <article
                key={nodeIndex}
                className="rounded-xl border settings-border bg-background/35 p-4"
                data-testid={`framework-node-${nodeIndex}`}
                data-validation-error={nodeIssues.length ? 'true' : undefined}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold text-foreground">
                    {t('settings.frameworkNode', { number: nodeIndex + 1 })}
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="compact"
                      disabled={disabled || nodeIndex === 0}
                      aria-label={t('settings.frameworkMoveNodeUp', { number: nodeIndex + 1 })}
                      onClick={() => setNodes(moveItem(nodes, nodeIndex, nodeIndex - 1))}
                    >
                      <ArrowUp className="h-4 w-4" aria-hidden="true" />
                      <span>{t('settings.frameworkMoveNodeUp', { number: nodeIndex + 1 })}</span>
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="compact"
                      disabled={disabled || nodeIndex === nodes.length - 1}
                      aria-label={t('settings.frameworkMoveNodeDown', { number: nodeIndex + 1 })}
                      onClick={() => setNodes(moveItem(nodes, nodeIndex, nodeIndex + 1))}
                    >
                      <ArrowDown className="h-4 w-4" aria-hidden="true" />
                      <span>{t('settings.frameworkMoveNodeDown', { number: nodeIndex + 1 })}</span>
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="compact"
                      disabled={disabled || nodes.length >= INVESTMENT_FRAMEWORK_LIMITS.nodes}
                      aria-label={t('settings.frameworkDuplicateNode', { number: nodeIndex + 1 })}
                      onClick={() => duplicateNode(nodeIndex)}
                    >
                      <Copy className="h-4 w-4" aria-hidden="true" />
                      <span>{t('settings.frameworkDuplicateNode', { number: nodeIndex + 1 })}</span>
                    </Button>
                    <Button
                      type="button"
                      variant="danger-subtle"
                      size="compact"
                      disabled={disabled}
                      aria-label={t('settings.frameworkDeleteNode', { number: nodeIndex + 1 })}
                      onClick={() => requestDeleteNode(nodeIndex)}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                      <span>{t('settings.frameworkDeleteNode', { number: nodeIndex + 1 })}</span>
                    </Button>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                  <label className="block space-y-1">
                    <span className="text-xs font-medium text-secondary-text">
                      {t('settings.frameworkNodeId')}
                    </span>
                    <input
                      className={fieldClass}
                      aria-label={t('settings.frameworkNodeIdAria', { number: nodeIndex + 1 })}
                      value={node.nodeId}
                      disabled={disabled}
                      onFocus={() => beginNodeRename(nodeIndex)}
                      onBlur={() => finishNodeRename(nodeIndex)}
                      onChange={(event) => updateNodeIdDraft(nodeIndex, event.target.value)}
                    />
                  </label>
                  <label className="block space-y-1">
                    <span className="text-xs font-medium text-secondary-text">
                      {t('settings.frameworkNodeQuestion')}
                    </span>
                    <input
                      className={fieldClass}
                      aria-label={t('settings.frameworkNodeQuestionAria', { number: nodeIndex + 1 })}
                      value={node.question}
                      disabled={disabled}
                      onChange={(event) => updateNode(nodeIndex, { question: event.target.value })}
                    />
                  </label>
                </div>

                {nodeIssues.length ? (
                  <p className="mt-2 text-xs text-danger" role="alert">
                    {nodeIssues.map(formatIssue).join(' · ')}
                  </p>
                ) : null}

                <div className="mt-4 space-y-3">
                  {node.branches.map((branch, branchIndex) => {
                    const usesTarget = branch.targetNodeId != null;
                    return (
                      <div
                        key={branchIndex}
                        className="grid grid-cols-1 gap-2 rounded-lg border border-border/60 p-3 lg:grid-cols-[1fr_10rem_1fr_auto]"
                      >
                        <label className="block space-y-1">
                          <span className="text-xs text-muted-text">
                            {t('settings.frameworkBranchCondition', { number: branchIndex + 1 })}
                          </span>
                          <input
                            className={fieldClass}
                            value={branch.condition}
                            disabled={disabled}
                            onChange={(event) => updateBranch(nodeIndex, branchIndex, {
                              condition: event.target.value,
                            })}
                          />
                        </label>
                        <label className="block space-y-1">
                          <span className="text-xs text-muted-text">
                            {t('settings.frameworkBranchDestination')}
                          </span>
                          <select
                            className={fieldClass}
                            value={usesTarget ? 'target' : 'outcome'}
                            disabled={disabled}
                            onChange={(event) => updateBranch(
                              nodeIndex,
                              branchIndex,
                              event.target.value === 'target'
                                ? { targetNodeId: '', outcome: null }
                                : { targetNodeId: null, outcome: '' },
                            )}
                          >
                            <option value="outcome">{t('settings.frameworkBranchOutcome')}</option>
                            <option value="target">{t('settings.frameworkBranchTarget')}</option>
                          </select>
                        </label>
                        <label className="block space-y-1">
                          <span className="text-xs text-muted-text">
                            {usesTarget
                              ? t('settings.frameworkBranchTarget')
                              : t('settings.frameworkBranchOutcome')}
                          </span>
                          {usesTarget ? (
                            <select
                              className={fieldClass}
                              value={branch.targetNodeId ?? ''}
                              disabled={disabled}
                              onChange={(event) => updateBranch(nodeIndex, branchIndex, {
                                targetNodeId: event.target.value,
                                outcome: null,
                              })}
                            >
                              <option value="">{t('settings.frameworkSelectTarget')}</option>
                              {nodes.map((targetNode, targetIndex) => (
                                <option key={`${targetNode.nodeId}-${targetIndex}`} value={targetNode.nodeId}>
                                  {targetNode.nodeId}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <input
                              className={fieldClass}
                              value={branch.outcome ?? ''}
                              disabled={disabled}
                              onChange={(event) => updateBranch(nodeIndex, branchIndex, {
                                targetNodeId: null,
                                outcome: event.target.value,
                              })}
                            />
                          )}
                        </label>
                        <Button
                          type="button"
                          variant="danger-subtle"
                          size="compact"
                          className="self-end"
                          disabled={disabled || node.branches.length <= 1}
                          aria-label={t('settings.frameworkDeleteBranch', { number: branchIndex + 1 })}
                          onClick={() => updateNode(nodeIndex, {
                            branches: node.branches.filter((_item, index) => index !== branchIndex),
                          })}
                        >
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                          <span>{t('settings.frameworkDeleteBranch', { number: branchIndex + 1 })}</span>
                        </Button>
                      </div>
                    );
                  })}
                  <Button
                    type="button"
                    variant="ghost"
                    size="compact"
                    disabled={
                      disabled
                      || node.branches.length >= INVESTMENT_FRAMEWORK_LIMITS.branchesPerNode
                    }
                    onClick={() => updateNode(nodeIndex, {
                      branches: [
                        ...node.branches,
                        { condition: '', targetNodeId: null, outcome: '' },
                      ],
                    })}
                  >
                    <Plus className="h-4 w-4" aria-hidden="true" />
                    {t('settings.frameworkAddBranch')}
                  </Button>
                  <span className="text-xs text-muted-text">
                    {t('settings.frameworkLimitUsage', {
                      current: node.branches.length,
                      limit: INVESTMENT_FRAMEWORK_LIMITS.branchesPerNode,
                    })}
                  </span>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="space-y-3" aria-labelledby="framework-dimensions-heading">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 id="framework-dimensions-heading" className="text-base font-semibold text-foreground">
              {t('settings.frameworkDimensions')}
            </h3>
            <p className="mt-1 text-xs leading-5 text-secondary-text">
              {t('settings.frameworkDimensionsDescription')}
            </p>
            <p className="mt-1 text-xs text-muted-text">
              {t('settings.frameworkLimitUsage', {
                current: dimensions.length,
                limit: INVESTMENT_FRAMEWORK_LIMITS.dimensions,
              })}
            </p>
          </div>
          <Button
            type="button"
            variant="secondary"
            size="compact"
            disabled={disabled || dimensions.length >= INVESTMENT_FRAMEWORK_LIMITS.dimensions}
            onClick={addDimension}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('settings.frameworkAddDimension')}
          </Button>
        </div>
        {dimensionIssues.length ? (
          <SettingsAlert
            title={t('settings.frameworkDimensionValidation')}
            message={dimensionIssues.map(formatIssue).join(' · ')}
            variant="error"
          />
        ) : null}
        {dimensions.length === 0 ? (
          <p className="rounded-lg border border-dashed settings-border px-3 py-4 text-xs text-muted-text">
            {t('settings.frameworkDimensionsEmpty')}
          </p>
        ) : null}
        <div className="space-y-3">
          {dimensions.map((dimension, index) => {
            const currentDimensionIssues = issues.filter((issue) => (
              issue.path.startsWith(`evaluationDimensions.${index}`)
            ));
            return (
              <article
                key={index}
                className="rounded-xl border settings-border bg-background/35 p-4"
                data-testid={`framework-dimension-${index}`}
                data-validation-error={currentDimensionIssues.length ? 'true' : undefined}
              >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-sm font-semibold text-foreground">
                  {t('settings.frameworkDimension', { number: index + 1 })}
                </h4>
                <div className="flex gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="compact"
                    disabled={disabled || index === 0}
                    aria-label={t('settings.frameworkMoveDimensionUp', { number: index + 1 })}
                    onClick={() => setDimensions(moveItem(dimensions, index, index - 1))}
                  >
                    <ArrowUp className="h-4 w-4" aria-hidden="true" />
                    <span>{t('settings.frameworkMoveDimensionUp', { number: index + 1 })}</span>
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="compact"
                    disabled={disabled || index === dimensions.length - 1}
                    aria-label={t('settings.frameworkMoveDimensionDown', { number: index + 1 })}
                    onClick={() => setDimensions(moveItem(dimensions, index, index + 1))}
                  >
                    <ArrowDown className="h-4 w-4" aria-hidden="true" />
                    <span>{t('settings.frameworkMoveDimensionDown', { number: index + 1 })}</span>
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="compact"
                    disabled={
                      disabled
                      || dimensions.length >= INVESTMENT_FRAMEWORK_LIMITS.dimensions
                    }
                    aria-label={t('settings.frameworkDuplicateDimension', { number: index + 1 })}
                    onClick={() => duplicateDimension(index)}
                  >
                    <Copy className="h-4 w-4" aria-hidden="true" />
                    <span>{t('settings.frameworkDuplicateDimension', { number: index + 1 })}</span>
                  </Button>
                  <Button
                    type="button"
                    variant="danger-subtle"
                    size="compact"
                    disabled={disabled}
                    aria-label={t('settings.frameworkDeleteDimension', { number: index + 1 })}
                    onClick={() => setDimensions(dimensions.filter((_item, itemIndex) => itemIndex !== index))}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                    <span>{t('settings.frameworkDeleteDimension', { number: index + 1 })}</span>
                  </Button>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-[1fr_8rem]">
                <label className="block space-y-1">
                  <span className="text-xs font-medium text-secondary-text">
                    {t('settings.frameworkDimensionName')}
                  </span>
                  <input
                    className={fieldClass}
                    aria-label={t('settings.frameworkDimensionNameAria', { number: index + 1 })}
                    value={dimension.name}
                    disabled={disabled}
                    onChange={(event) => updateDimension(index, { name: event.target.value })}
                  />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs font-medium text-secondary-text">
                    {t('settings.frameworkDimensionWeight')}
                  </span>
                  <input
                    className={fieldClass}
                    aria-label={t('settings.frameworkDimensionWeightAria', { number: index + 1 })}
                    type="number"
                    min={0}
                    max={100}
                    step="any"
                    value={Number.isFinite(dimension.weight) ? dimension.weight : ''}
                    disabled={disabled}
                    onChange={(event) => updateDimension(index, {
                      weight: event.target.value === '' ? Number.NaN : Number(event.target.value),
                    })}
                  />
                </label>
              </div>
              <label className="mt-3 block space-y-1">
                <span className="text-xs font-medium text-secondary-text">
                  {t('settings.frameworkDimensionDescription')}
                </span>
                <textarea
                  className={`${fieldClass} min-h-16`}
                  value={dimension.description ?? ''}
                  disabled={disabled}
                  onChange={(event) => updateDimension(index, {
                    description: event.target.value || null,
                  })}
                />
              </label>
              <label className="mt-3 block space-y-1">
                <span className="text-xs font-medium text-secondary-text">
                  {t('settings.frameworkDimensionCriteria')}
                </span>
                <span className="block text-xs text-muted-text">
                  {t('settings.frameworkLimitUsage', {
                    current: dimension.criteria?.length ?? 0,
                    limit: INVESTMENT_FRAMEWORK_LIMITS.criteriaPerDimension,
                  })}
                  {' · '}
                  {t('settings.frameworkRuleLengthHint', {
                    limit: INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
                  })}
                </span>
                <LineListTextarea
                  className={`${fieldClass} min-h-20`}
                  aria-label={t('settings.frameworkDimensionCriteria')}
                  values={dimension.criteria}
                  disabled={disabled}
                  placeholder={t('settings.frameworkListPlaceholder')}
                  onValuesChange={(criteria) => updateDimension(index, { criteria })}
                />
              </label>
              {currentDimensionIssues.length ? (
                <p
                  className="mt-2 text-xs text-danger"
                  role="alert"
                  data-testid={`framework-dimension-errors-${index}`}
                >
                  {currentDimensionIssues.map(formatIssue).join(' · ')}
                </p>
              ) : null}
            </article>
            );
          })}
        </div>
      </section>

      <ConfirmDialog
        isOpen={pendingDeleteNode !== null}
        title={t('settings.frameworkDeleteNodeConfirmTitle')}
        message={t('settings.frameworkDeleteNodeConfirmMessage', {
          node: pendingDeleteNode === null ? '' : nodes[pendingDeleteNode]?.nodeId ?? '',
        })}
        confirmText={t('settings.frameworkDeleteNodeConfirmAction')}
        isDanger
        onConfirm={deleteNode}
        onCancel={() => setPendingDeleteNode(null)}
      />
    </div>
  );
};

export default InvestmentFrameworkStructuredEditor;
