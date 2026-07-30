// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it } from 'vitest';
import type { InvestmentFrameworkContent } from '../../../types/investmentFramework';
import {
  INVESTMENT_FRAMEWORK_CASEFOLD_UNICODE_VERSION,
  INVESTMENT_FRAMEWORK_LIMITS,
  casefoldInvestmentFrameworkDimensionName,
  nextFrameworkNodeId,
  nodeDeleteBlockers,
  validationIssuesFromFrameworkApiDetails,
  validateInvestmentFrameworkContent,
} from '../investmentFrameworkEditorModel';

function validContent(): InvestmentFrameworkContent {
  return {
    schemaVersion: 'investment-framework-content-v1',
    title: 'Quality framework',
    rootNodeId: 'root',
    decisionTree: [
      {
        nodeId: 'root',
        question: 'Is quality high?',
        branches: [
          { condition: 'Yes', targetNodeId: 'valuation', outcome: null },
          { condition: 'No', targetNodeId: null, outcome: 'Reject' },
        ],
      },
      {
        nodeId: 'valuation',
        question: 'Is valuation acceptable?',
        branches: [
          { condition: 'Yes', targetNodeId: null, outcome: 'Consider' },
          { condition: 'No', targetNodeId: null, outcome: 'Watch' },
        ],
      },
    ],
    evaluationDimensions: [
      { name: 'Moat', weight: 50, criteria: ['Pricing power'] },
      { name: 'Balance sheet', weight: 50, criteria: ['Net cash'] },
    ],
    riskRules: [],
    trackingCriteria: [],
    freeFormRules: null,
  };
}

describe('investmentFrameworkEditorModel', () => {
  it('accepts a valid decision tree and evaluation dimensions', () => {
    expect(validateInvestmentFrameworkContent(validContent())).toEqual([]);
  });

  it.each([
    ['duplicate IDs', (content: InvestmentFrameworkContent) => {
      content.decisionTree![1].nodeId = 'root';
    }, 'duplicate_node_id'],
    ['unknown target', (content: InvestmentFrameworkContent) => {
      content.decisionTree![0].branches[0].targetNodeId = 'missing';
    }, 'target_unknown'],
    ['cycle', (content: InvestmentFrameworkContent) => {
      content.decisionTree![1].branches[0] = {
        condition: 'Loop',
        targetNodeId: 'root',
        outcome: null,
      };
    }, 'cycle'],
    ['unreachable node', (content: InvestmentFrameworkContent) => {
      content.decisionTree!.push({
        nodeId: 'orphan',
        question: 'Orphan?',
        branches: [{ condition: 'Done', targetNodeId: null, outcome: 'Done' }],
      });
    }, 'unreachable'],
    ['invalid weight', (content: InvestmentFrameworkContent) => {
      content.evaluationDimensions![0].weight = 101;
    }, 'invalid_weight'],
    ['duplicate dimension names', (content: InvestmentFrameworkContent) => {
      content.evaluationDimensions![1].name = 'moat';
    }, 'duplicate_dimension_name'],
  ])('rejects %s', (_label, mutate, expectedCode) => {
    const content = validContent();
    mutate(content);

    expect(validateInvestmentFrameworkContent(content)).toEqual(
      expect.arrayContaining([expect.objectContaining({ code: expectedCode })]),
    );
  });

  it('locates a normalized duplicate node ID at every related node', () => {
    const content = validContent();
    content.decisionTree![1].nodeId = ' root ';

    expect(validateInvestmentFrameworkContent(content).filter(
      (issue) => issue.code === 'duplicate_node_id',
    )).toEqual([
      {
        code: 'duplicate_node_id',
        path: 'decisionTree.0.nodeId',
        value: 'root',
      },
      {
        code: 'duplicate_node_id',
        path: 'decisionTree.1.nodeId',
        value: 'root',
      },
    ]);
  });

  it('matches backend whitespace normalization throughout graph validation', () => {
    const content = validContent();
    content.rootNodeId = 'root';
    content.decisionTree = [
      {
        nodeId: ' root ',
        question: 'Start?',
        branches: [{ condition: 'Continue', targetNodeId: ' child ', outcome: null }],
      },
      {
        nodeId: ' child ',
        question: 'Finish?',
        branches: [{ condition: 'Done', targetNodeId: null, outcome: 'Accept' }],
      },
    ];

    expect(validateInvestmentFrameworkContent(content)).toEqual([]);
    expect(nodeDeleteBlockers(content, 'child')).toContain('root');
  });

  it('detects cycles after applying backend whitespace normalization', () => {
    const content = validContent();
    content.rootNodeId = ' A ';
    content.decisionTree = [
      {
        nodeId: ' A ',
        question: 'A?',
        branches: [{ condition: 'To B', targetNodeId: ' B ', outcome: null }],
      },
      {
        nodeId: ' B ',
        question: 'B?',
        branches: [{ condition: 'To A', targetNodeId: ' A ', outcome: null }],
      },
    ];

    expect(validateInvestmentFrameworkContent(content)).toEqual(
      expect.arrayContaining([expect.objectContaining({ code: 'cycle' })]),
    );
  });

  it('does not generate a node ID that collides after backend whitespace normalization', () => {
    const content = validContent();
    content.decisionTree = [
      ...content.decisionTree!,
      {
        nodeId: ' node-3 ',
        question: 'Third?',
        branches: [{ condition: 'Done', targetNodeId: null, outcome: 'Done' }],
      },
    ];

    expect(nextFrameworkNodeId(content.decisionTree)).toBe('node-4');
  });

  it('matches backend Unicode casefold semantics for duplicate dimension names', () => {
    const content = validContent();
    content.evaluationDimensions![0].name = 'Straße';
    content.evaluationDimensions![1].name = 'STRASSE';

    expect(validateInvestmentFrameworkContent(content).filter(
      (issue) => issue.code === 'duplicate_dimension_name',
    )).toEqual([
      {
        code: 'duplicate_dimension_name',
        path: 'evaluationDimensions.0.name',
        value: 'strasse',
      },
      {
        code: 'duplicate_dimension_name',
        path: 'evaluationDimensions.1.name',
        value: 'strasse',
      },
    ]);
  });

  it('uses the pinned Unicode 15.0 full casefold independently of the host runtime', () => {
    expect(INVESTMENT_FRAMEWORK_CASEFOLD_UNICODE_VERSION).toBe('15.0.0');
    expect(casefoldInvestmentFrameworkDimensionName('Straße')).toBe('strasse');
    expect(casefoldInvestmentFrameworkDimensionName('STRASSE')).toBe('strasse');
    expect(casefoldInvestmentFrameworkDimensionName('Σςσ')).toBe('σσσ');
    expect(casefoldInvestmentFrameworkDimensionName('ﬃ')).toBe('ffi');
    expect(casefoldInvestmentFrameworkDimensionName('\uAB70')).toBe('\u13A0');
    expect(casefoldInvestmentFrameworkDimensionName('\u{10400}')).toBe('\u{10428}');
    expect(casefoldInvestmentFrameworkDimensionName('\u2C2F')).toBe('\u2C5F');
  });

  it('rejects every field in a duplicate introduced after Unicode 13', () => {
    const content = validContent();
    content.evaluationDimensions![0].name = '\u2C2F';
    content.evaluationDimensions![1].name = '\u2C5F';

    expect(validateInvestmentFrameworkContent(content).filter(
      (issue) => issue.code === 'duplicate_dimension_name',
    )).toEqual([
      {
        code: 'duplicate_dimension_name',
        path: 'evaluationDimensions.0.name',
        value: '\u2C5F',
      },
      {
        code: 'duplicate_dimension_name',
        path: 'evaluationDimensions.1.name',
        value: '\u2C5F',
      },
    ]);
  });

  it.each([
    ['U+1C89/U+1C8A', 0x1c89, 0x1c8a],
    ['U+A7CB/U+0264', 0xa7cb, 0x0264],
    ['U+A7CC/U+A7CD', 0xa7cc, 0xa7cd],
    ['U+A7DA/U+A7DB', 0xa7da, 0xa7db],
    ['U+A7DC/U+019B', 0xa7dc, 0x019b],
    ['U+10D50/U+10D70', 0x10d50, 0x10d70],
  ])(
    'does not falsely reject the backend-allowed Unicode 16 addition %s',
    (_label, sourceCodePoint, targetCodePoint) => {
      const source = String.fromCodePoint(sourceCodePoint);
      const target = String.fromCodePoint(targetCodePoint);
      const content = validContent();
      content.evaluationDimensions![0].name = source;
      content.evaluationDimensions![1].name = target;

      expect(casefoldInvestmentFrameworkDimensionName(source)).toBe(source);
      expect(casefoldInvestmentFrameworkDimensionName(target)).toBe(target);
      expect(validateInvestmentFrameworkContent(content).filter(
        (issue) => issue.code === 'duplicate_dimension_name',
      )).toEqual([]);
    },
  );

  it('blocks deletion of the root and nodes with inbound references', () => {
    const content = validContent();

    expect(nodeDeleteBlockers(content, 'root')).toContain('root');
    expect(nodeDeleteBlockers(content, 'valuation')).toContain('root');
  });

  it('accepts every backend collection limit at its exact boundary', () => {
    const content = validContent();
    content.decisionTree = Array.from(
      { length: INVESTMENT_FRAMEWORK_LIMITS.nodes },
      (_value, index) => ({
        nodeId: `node-${index}`,
        question: `Question ${index}`,
        branches: index + 1 < INVESTMENT_FRAMEWORK_LIMITS.nodes
          ? [{ condition: 'Continue', targetNodeId: `node-${index + 1}`, outcome: null }]
          : [{ condition: 'Finish', targetNodeId: null, outcome: 'Done' }],
      }),
    );
    content.rootNodeId = 'node-0';
    content.decisionTree[0].branches = Array.from(
      { length: INVESTMENT_FRAMEWORK_LIMITS.branchesPerNode },
      () => ({ condition: 'Continue', targetNodeId: 'node-1', outcome: null }),
    );
    content.evaluationDimensions = Array.from(
      { length: INVESTMENT_FRAMEWORK_LIMITS.dimensions },
      (_value, index) => ({
        name: `Dimension ${index}`,
        weight: 50,
        criteria: Array.from(
          { length: INVESTMENT_FRAMEWORK_LIMITS.criteriaPerDimension },
          (_criterion, criterionIndex) => `Criterion ${criterionIndex}`,
        ),
      }),
    );
    content.riskRules = Array.from(
      { length: INVESTMENT_FRAMEWORK_LIMITS.riskRules },
      (_value, index) => `Risk ${index}`,
    );
    content.trackingCriteria = Array.from(
      { length: INVESTMENT_FRAMEWORK_LIMITS.trackingCriteria },
      (_value, index) => `Tracking ${index}`,
    );

    const codes = validateInvestmentFrameworkContent(content).map((issue) => issue.code);
    expect(codes).not.toEqual(expect.arrayContaining([
      'too_many_nodes',
      'too_many_branches',
      'too_many_dimensions',
      'too_many_dimension_criteria',
      'too_many_risk_rules',
      'too_many_tracking_criteria',
    ]));
  });

  it.each([
    ['nodes', (content: InvestmentFrameworkContent) => {
      content.decisionTree = Array.from(
        { length: INVESTMENT_FRAMEWORK_LIMITS.nodes + 1 },
        (_value, index) => ({
          nodeId: `node-${index}`,
          question: 'Question',
          branches: [{ condition: 'Finish', targetNodeId: null, outcome: 'Done' }],
        }),
      );
      content.rootNodeId = 'node-0';
    }, 'too_many_nodes', 'decisionTree'],
    ['branches', (content: InvestmentFrameworkContent) => {
      content.decisionTree![0].branches = Array.from(
        { length: INVESTMENT_FRAMEWORK_LIMITS.branchesPerNode + 1 },
        () => ({ condition: 'Finish', targetNodeId: null, outcome: 'Done' }),
      );
    }, 'too_many_branches', 'decisionTree.0.branches'],
    ['dimensions', (content: InvestmentFrameworkContent) => {
      content.evaluationDimensions = Array.from(
        { length: INVESTMENT_FRAMEWORK_LIMITS.dimensions + 1 },
        (_value, index) => ({ name: `Dimension ${index}`, weight: 50, criteria: [] }),
      );
    }, 'too_many_dimensions', 'evaluationDimensions'],
    ['dimension criteria', (content: InvestmentFrameworkContent) => {
      content.evaluationDimensions![0].criteria = Array.from(
        { length: INVESTMENT_FRAMEWORK_LIMITS.criteriaPerDimension + 1 },
        (_value, index) => `Criterion ${index}`,
      );
    }, 'too_many_dimension_criteria', 'evaluationDimensions.0.criteria'],
    ['risk rules', (content: InvestmentFrameworkContent) => {
      content.riskRules = Array.from(
        { length: INVESTMENT_FRAMEWORK_LIMITS.riskRules + 1 },
        (_value, index) => `Risk ${index}`,
      );
    }, 'too_many_risk_rules', 'riskRules'],
    ['tracking criteria', (content: InvestmentFrameworkContent) => {
      content.trackingCriteria = Array.from(
        { length: INVESTMENT_FRAMEWORK_LIMITS.trackingCriteria + 1 },
        (_value, index) => `Tracking ${index}`,
      );
    }, 'too_many_tracking_criteria', 'trackingCriteria'],
  ])('rejects a %s collection above the backend boundary', (
    _label,
    mutate,
    expectedCode,
    expectedPath,
  ) => {
    const content = validContent();
    mutate(content);

    expect(validateInvestmentFrameworkContent(content)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: expectedCode, path: expectedPath }),
      ]),
    );
  });

  it('accepts backend string lengths at their exact boundaries', () => {
    const content = validContent();
    content.title = 't'.repeat(INVESTMENT_FRAMEWORK_LIMITS.titleLength);
    content.description = 'd'.repeat(INVESTMENT_FRAMEWORK_LIMITS.descriptionLength);
    content.freeFormRules = 'f'.repeat(INVESTMENT_FRAMEWORK_LIMITS.freeFormRulesLength);
    content.decisionTree![0].question = 'q'.repeat(INVESTMENT_FRAMEWORK_LIMITS.ruleLength);
    content.decisionTree![0].branches[0].condition = 'c'.repeat(
      INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
    );
    content.decisionTree![0].branches[1].outcome = 'o'.repeat(
      INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
    );
    content.evaluationDimensions![0].name = 'n'.repeat(
      INVESTMENT_FRAMEWORK_LIMITS.dimensionNameLength,
    );
    content.evaluationDimensions![0].description = 'd'.repeat(
      INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
    );
    content.evaluationDimensions![0].criteria = [
      'c'.repeat(INVESTMENT_FRAMEWORK_LIMITS.ruleLength),
    ];
    content.riskRules = ['r'.repeat(INVESTMENT_FRAMEWORK_LIMITS.ruleLength)];
    content.trackingCriteria = ['t'.repeat(INVESTMENT_FRAMEWORK_LIMITS.ruleLength)];

    expect(validateInvestmentFrameworkContent(content)).toEqual([]);
  });

  it('counts astral Unicode characters with the backend code-point semantics', () => {
    const content = validContent();
    content.title = '😀'.repeat(INVESTMENT_FRAMEWORK_LIMITS.titleLength);
    content.decisionTree![0].question = '😀'.repeat(
      INVESTMENT_FRAMEWORK_LIMITS.ruleLength,
    );

    expect(validateInvestmentFrameworkContent(content)).toEqual([]);

    content.title += '😀';
    content.decisionTree![0].question += '😀';
    expect(validateInvestmentFrameworkContent(content)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: 'title_too_long', path: 'title' }),
        expect.objectContaining({ code: 'rule_length', path: 'decisionTree.0.question' }),
      ]),
    );
  });

  it.each([
    ['title', (content: InvestmentFrameworkContent) => {
      content.title = 't'.repeat(INVESTMENT_FRAMEWORK_LIMITS.titleLength + 1);
    }, 'title_too_long', 'title'],
    ['description', (content: InvestmentFrameworkContent) => {
      content.description = 'd'.repeat(INVESTMENT_FRAMEWORK_LIMITS.descriptionLength + 1);
    }, 'description_length', 'description'],
    ['node ID', (content: InvestmentFrameworkContent) => {
      content.decisionTree![0].nodeId = 'n'.repeat(
        INVESTMENT_FRAMEWORK_LIMITS.nodeIdLength + 1,
      );
    }, 'invalid_node_id', 'decisionTree.0.nodeId'],
    ['node question', (content: InvestmentFrameworkContent) => {
      content.decisionTree![0].question = 'q'.repeat(
        INVESTMENT_FRAMEWORK_LIMITS.ruleLength + 1,
      );
    }, 'rule_length', 'decisionTree.0.question'],
    ['branch condition', (content: InvestmentFrameworkContent) => {
      content.decisionTree![0].branches[0].condition = 'c'.repeat(
        INVESTMENT_FRAMEWORK_LIMITS.ruleLength + 1,
      );
    }, 'rule_length', 'decisionTree.0.branches.0.condition'],
    ['branch outcome', (content: InvestmentFrameworkContent) => {
      content.decisionTree![0].branches[1].outcome = 'o'.repeat(
        INVESTMENT_FRAMEWORK_LIMITS.ruleLength + 1,
      );
    }, 'rule_length', 'decisionTree.0.branches.1.outcome'],
    ['dimension name', (content: InvestmentFrameworkContent) => {
      content.evaluationDimensions![0].name = 'n'.repeat(
        INVESTMENT_FRAMEWORK_LIMITS.dimensionNameLength + 1,
      );
    }, 'dimension_name_too_long', 'evaluationDimensions.0.name'],
    ['dimension description', (content: InvestmentFrameworkContent) => {
      content.evaluationDimensions![0].description = 'd'.repeat(
        INVESTMENT_FRAMEWORK_LIMITS.ruleLength + 1,
      );
    }, 'dimension_description_length', 'evaluationDimensions.0.description'],
    ['dimension criterion', (content: InvestmentFrameworkContent) => {
      content.evaluationDimensions![0].criteria = [
        'c'.repeat(INVESTMENT_FRAMEWORK_LIMITS.ruleLength + 1),
      ];
    }, 'rule_length', 'evaluationDimensions.0.criteria.0'],
    ['risk rule', (content: InvestmentFrameworkContent) => {
      content.riskRules = ['r'.repeat(INVESTMENT_FRAMEWORK_LIMITS.ruleLength + 1)];
    }, 'rule_length', 'riskRules.0'],
    ['tracking criterion', (content: InvestmentFrameworkContent) => {
      content.trackingCriteria = ['t'.repeat(INVESTMENT_FRAMEWORK_LIMITS.ruleLength + 1)];
    }, 'rule_length', 'trackingCriteria.0'],
    ['free-form rules', (content: InvestmentFrameworkContent) => {
      content.freeFormRules = 'f'.repeat(
        INVESTMENT_FRAMEWORK_LIMITS.freeFormRulesLength + 1,
      );
    }, 'free_form_rules_length', 'freeFormRules'],
  ])('rejects %s above the backend string boundary', (
    _label,
    mutate,
    expectedCode,
    expectedPath,
  ) => {
    const content = validContent();
    mutate(content);

    expect(validateInvestmentFrameworkContent(content)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ code: expectedCode, path: expectedPath }),
      ]),
    );
  });

  it('maps sanitized 422 locations to the related node, dimension, and line rule', () => {
    const content = validContent();

    expect(validationIssuesFromFrameworkApiDetails({
      issues: [
        {
          type: 'string_too_long',
          loc: ['body', 'content', 'decision_tree', 1, 'question'],
          msg: 'String should have at most 1000 characters',
        },
        {
          type: 'too_long',
          loc: ['body', 'content', 'evaluation_dimensions', 0, 'criteria'],
          msg: 'List should have at most 30 items',
        },
        {
          type: 'string_too_long',
          loc: ['body', 'content', 'risk_rules', 2],
          msg: 'String should have at most 1000 characters',
        },
      ],
    }, content)).toEqual([
      {
        code: 'rule_length',
        path: 'decisionTree.1.question',
        value: undefined,
      },
      {
        code: 'too_many_dimension_criteria',
        path: 'evaluationDimensions.0.criteria',
        value: undefined,
      },
      {
        code: 'rule_length',
        path: 'riskRules.2',
        value: undefined,
      },
    ]);
  });
});
