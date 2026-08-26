// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Isolated AGENT_RED_TEAM_ENABLED settings-help catalog (Refs #1135).
 *
 * Keep this module off SettingsPage / settings-route / locale-* /
 * extra-locale-* families, and do not emit a new entry-map filename
 * (that inflates criticalPath). Do not import it from settingsTranslations
 * or core locale packs. Attach it to the existing CredentialInput chunk,
 * the same lazy boundary used by skill-retrieval help.
 */
import type { UiLanguage } from '../i18n/uiLanguages';
import type { SettingsHelpDefinition, SettingsHelpSourceMap } from './settingsHelpSourceTypes';

type AdditionalRedTeamLanguage = Exclude<UiLanguage, 'zh' | 'en'>;

export const RED_TEAM_HELP_KEY = 'settings.agent.AGENT_RED_TEAM_ENABLED';

// Keep these const names so TestSettingsFieldTitleContract can inventory
// the isolated title map without copying literals into SettingsPage cores.
const fieldTitleMapZh = {
  AGENT_RED_TEAM_ENABLED: '对抗性红队二审',
} as const;

const fieldTitleMapEn = {
  AGENT_RED_TEAM_ENABLED: 'Adversarial Red-Team Second Opinion',
} satisfies Record<keyof typeof fieldTitleMapZh, string>;

export const RED_TEAM_FIELD_TITLE_MAP_ZH = fieldTitleMapZh;
export const RED_TEAM_FIELD_TITLE_MAP_EN = fieldTitleMapEn;

export const RED_TEAM_FIELD_DESCRIPTION = {
  AGENT_RED_TEAM_ENABLED:
    '可选的 Decision 后对抗二审（默认关闭；仅 Native Multi 非 Chat 的 full/specialist，或显式请求覆盖）。不替换主决策对象。',
} as const;

const RED_TEAM_EXAMPLES = [
  'AGENT_RED_TEAM_ENABLED=false',
  'AGENT_RED_TEAM_ENABLED=true',
] as const;

const redTeamSettingsHelpEn: SettingsHelpDefinition = {
  title: fieldTitleMapEn.AGENT_RED_TEAM_ENABLED,
  summary: 'Run one tool-free post-Decision red-team review on Native Multi full/specialist analysis.',
  usage: 'Keep this off unless you want an independent challenge of weak evidence and overconfidence after the primary decision.',
  valueNotes: [
    'Default is off. Chat never runs this stage. quick and standard skip it unless an explicit request override is set.',
    'The stage cannot replace decision_type, confidence_level, or operation_advice. Existing data_limitations keep the 12 product slots first; overflow stays in the red-team section. Budget or provider failure fails soft.',
  ],
  impact: ['Adds at most one LLM turn after Decision and appends challenges to risks/gaps.'],
  notes: ['This is not Bull-Bear debate and not a Risk veto.'],
  examples: [...RED_TEAM_EXAMPLES],
};

const redTeamSettingsHelpZh: SettingsHelpDefinition = {
  title: fieldTitleMapZh.AGENT_RED_TEAM_ENABLED,
  summary: '在 Native Multi 的 full/specialist 分析中，于 Decision 之后执行一次无工具红队复核。',
  usage: '仅在需要独立挑战弱证据与过度自信时开启；默认关闭。',
  valueNotes: [
    '默认关闭。Chat 永不运行。quick / standard 除非显式请求覆盖，否则不运行。',
    '不会改写 decision_type、confidence_level 或 operation_advice。已有 data_limitations 优先占用 12 个产品槽位，溢出只留在红队章节。预算或供应商失败会 fail-soft。',
  ],
  impact: ['最多在 Decision 之后增加一次 LLM 调用，并把挑战追加到风险与证据缺口。'],
  notes: ['这不是多空辩论，也不是 Risk veto。'],
  examples: [...RED_TEAM_EXAMPLES],
};

// Single-quoted `'settings.agent.AGENT_RED_TEAM_ENABLED': {` so
// TestSettingsHelpContract can discover the registry help key.
export const RED_TEAM_SETTINGS_HELP_EN: SettingsHelpSourceMap = {
  'settings.agent.AGENT_RED_TEAM_ENABLED': {
    ...redTeamSettingsHelpEn,
  },
};

export const RED_TEAM_SETTINGS_HELP_ZH: SettingsHelpSourceMap = {
  'settings.agent.AGENT_RED_TEAM_ENABLED': {
    ...redTeamSettingsHelpZh,
  },
};

type ExtraRedTeamHelp = {
  title: string;
  summary: string;
  usage: string;
  valueNotes: readonly [string, string];
  impact: readonly [string];
  notes: readonly [string];
};

const EXTRA_RED_TEAM_HELP = {
  de: {
    title: 'Adversariale Red-Team-Zweitmeinung',
    summary: 'Führt nach Decision in Native-Multi-full/specialist-Analysen eine einmalige werkzeugfreie Red-Team-Prüfung aus.',
    usage: 'Nur aktivieren, wenn nach der Primärentscheidung schwache Evidenz und Überconfidence unabhängig angegriffen werden sollen.',
    valueNotes: [
      'Standardmäßig aus. Chat führt diese Stufe nie aus. quick und standard überspringen sie ohne explizite Anforderungsüberschreibung.',
      'Die Stufe darf decision_type, confidence_level oder operation_advice nicht ersetzen. Vorhandene data_limitations belegen zuerst die 12 Produktslots; Überlauf bleibt im Red-Team-Abschnitt. Budget- oder Anbieterfehler enden fail-soft.',
    ],
    impact: ['Fügt nach Decision höchstens einen LLM-Aufruf hinzu und hängt Herausforderungen an Risiken/Lücken an.'],
    notes: ['Das ist keine Bullen-Bären-Debatte und kein Risk-Veto.'],
  },
  es: {
    title: 'Segunda opinión adversarial red-team',
    summary: 'Ejecuta una revisión red-team sin herramientas después de Decision en análisis Native Multi full/specialist.',
    usage: 'Actívelo solo si quiere cuestionar de forma independiente evidencia débil y exceso de confianza tras la decisión primaria.',
    valueNotes: [
      'Desactivado por defecto. Chat nunca ejecuta esta etapa. quick y standard la omiten salvo una anulación explícita de la solicitud.',
      'La etapa no puede reemplazar decision_type, confidence_level ni operation_advice. Los data_limitations existentes ocupan primero los 12 huecos de producto; el excedente permanece en la sección red-team. Fallos de presupuesto o proveedor son fail-soft.',
    ],
    impact: ['Añade como máximo un turno LLM después de Decision y agrega desafíos a riesgos/huecos.'],
    notes: ['No es el debate alcista-bajista ni un veto de Risk.'],
  },
  fr: {
    title: 'Second avis adversarial red-team',
    summary: 'Exécute un examen red-team sans outil après Decision pour les analyses Native Multi full/specialist.',
    usage: 'Activez seulement si vous voulez attaquer indépendamment les preuves faibles et la surconfiance après la décision primaire.',
    valueNotes: [
      'Désactivé par défaut. Chat n’exécute jamais cette étape. quick et standard la sautent sauf surcharge explicite de requête.',
      'L’étape ne peut pas remplacer decision_type, confidence_level ou operation_advice. Les data_limitations existantes occupent d’abord les 12 emplacements produit ; le trop-plein reste dans la section red-team. Un échec de budget ou de fournisseur reste fail-soft.',
    ],
    impact: ['Ajoute au plus un tour LLM après Decision et ajoute les contestations aux risques/lacunes.'],
    notes: ['Ce n’est ni le débat haussier-baissier ni un veto Risk.'],
  },
  id: {
    title: 'Pendapat kedua red-team adversarial',
    summary: 'Menjalankan satu tinjauan red-team tanpa alat setelah Decision pada analisis Native Multi full/specialist.',
    usage: 'Aktifkan hanya jika Anda ingin menantang bukti lemah dan overconfidence secara independen setelah keputusan utama.',
    valueNotes: [
      'Default nonaktif. Chat tidak pernah menjalankan tahap ini. quick dan standard melewatinya kecuali ada override permintaan eksplisit.',
      'Tahap ini tidak boleh mengganti decision_type, confidence_level, atau operation_advice. data_limitations yang sudah ada mengisi 12 slot produk lebih dulu; kelebihan tetap di bagian red-team. Kegagalan anggaran atau penyedia bersifat fail-soft.',
    ],
    impact: ['Menambah paling banyak satu giliran LLM setelah Decision dan menambahkan tantangan ke risiko/celah.'],
    notes: ['Ini bukan debat Bull-Bear dan bukan veto Risk.'],
  },
  ja: {
    title: '敵対的レッドチーム再意見',
    summary: 'Native Multi の full/specialist 分析で、Decision 後にツールなしのレッドチーム再審査を 1 回実行します。',
    usage: '主決定の後で弱い証拠と過信を独立に攻撃したい場合のみ有効にしてください。',
    valueNotes: [
      '既定では無効です。Chat はこの段階を実行しません。quick と standard は明示的なリクエスト上書きがなければスキップします。',
      'decision_type、confidence_level、operation_advice は置き換えません。既存の data_limitations が先に 12 個の製品枠を占め、溢れた分はレッドチーム節に残ります。予算やプロバイダー失敗は fail-soft です。',
    ],
    impact: ['Decision の後に LLM 呼び出しを最大 1 回追加し、課題をリスク/ギャップに追記します。'],
    notes: ['強気・弱気討論でも Risk veto でもありません。'],
  },
  ko: {
    title: '적대적 레드팀 재의견',
    summary: 'Native Multi full/specialist 분석에서 Decision 이후 도구 없는 레드팀 재검토를 한 번 실행합니다.',
    usage: '주 결정 이후 약한 증거와 과신을 독립적으로 공격하려는 경우에만 켜세요.',
    valueNotes: [
      '기본값은 비활성입니다. Chat은 이 단계를 실행하지 않습니다. quick과 standard는 명시적 요청 재정의가 없으면 건너뜁니다.',
      'decision_type, confidence_level, operation_advice를 바꾸지 않습니다. 기존 data_limitations가 12개 제품 슬롯을 먼저 차지하고, 넘친 항목은 레드팀 섹션에만 남습니다. 예산 또는 공급자 실패는 fail-soft입니다.',
    ],
    impact: ['Decision 이후 LLM 호출을 최대 1회 추가하고 도전 항목을 위험/공백에 덧붙입니다.'],
    notes: ['강세-약세 토론도 아니고 Risk veto도 아닙니다.'],
  },
  ms: {
    title: 'Pendapat kedua red-team adversarial',
    summary: 'Menjalankan satu semakan red-team tanpa alat selepas Decision pada analisis Native Multi full/specialist.',
    usage: 'Dayakan hanya jika anda mahu mencabar bukti lemah dan keyakinan berlebihan secara bebas selepas keputusan utama.',
    valueNotes: [
      'Lalai dimatikan. Chat tidak pernah menjalankan peringkat ini. quick dan standard melaluinya kecuali override permintaan eksplisit.',
      'Peringkat ini tidak boleh menggantikan decision_type, confidence_level atau operation_advice. data_limitations sedia ada mengisi 12 slot produk dahulu; limpahan kekal dalam bahagian red-team. Kegagalan belanjawan atau penyedia adalah fail-soft.',
    ],
    impact: ['Menambah paling banyak satu pusingan LLM selepas Decision dan menambah cabaran ke risiko/jurang.'],
    notes: ['Ini bukan debat Bull-Bear dan bukan veto Risk.'],
  },
  "zh-TW": {
    title: '對抗性紅隊二審',
    summary: '在 Native Multi 的 full/specialist 分析中，於 Decision 之後執行一次無工具紅隊複核。',
    usage: '僅在需要獨立挑戰弱證據與過度自信時開啟；預設關閉。',
    valueNotes: [
      '預設關閉。Chat 永不執行。quick / standard 除非顯式請求覆蓋，否則不執行。',
      '不會改寫 decision_type、confidence_level 或 operation_advice。既有 data_limitations 優先占用 12 個產品槽位，溢出只留在紅隊章節。預算或供應商失敗會 fail-soft。',
    ],
    impact: ['最多在 Decision 之後增加一次 LLM 呼叫，並把挑戰追加到風險與證據缺口。'],
    notes: ['這不是多空辯論，也不是 Risk veto。'],
  },
} as const satisfies Record<AdditionalRedTeamLanguage, ExtraRedTeamHelp>;

function fromExtra(fields: ExtraRedTeamHelp): SettingsHelpDefinition {
  return {
    title: fields.title,
    summary: fields.summary,
    usage: fields.usage,
    valueNotes: [...fields.valueNotes],
    impact: [...fields.impact],
    notes: [...fields.notes],
    examples: [...RED_TEAM_EXAMPLES],
  };
}

export function isRedTeamHelpKey(helpKey: string): boolean {
  return helpKey === RED_TEAM_HELP_KEY || helpKey === 'AGENT_RED_TEAM_ENABLED';
}

export function getRedTeamSettingsHelp(language: UiLanguage): SettingsHelpDefinition {
  if (language === 'zh') {
    return redTeamSettingsHelpZh;
  }
  if (language === 'en') {
    return redTeamSettingsHelpEn;
  }
  return fromExtra(EXTRA_RED_TEAM_HELP[language]);
}

export function getRedTeamFieldTitle(language: UiLanguage): string {
  return getRedTeamSettingsHelp(language).title ?? RED_TEAM_FIELD_TITLE_MAP_EN.AGENT_RED_TEAM_ENABLED;
}

export function getRedTeamFieldDescription(): string {
  return RED_TEAM_FIELD_DESCRIPTION.AGENT_RED_TEAM_ENABLED;
}
