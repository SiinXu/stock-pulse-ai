// Copyright (c) 2026 SiinXu / StockPulse contributors
// SPDX-License-Identifier: AGPL-3.0-only
/**
 * Isolated AGENT_SKILL_RETRIEVAL_K settings-help catalog (Refs #1123).
 *
 * Keep this module off SettingsPage / settings-route / locale-* /
 * extra-locale-* families, and do not emit a new entry-map filename
 * (that inflates criticalPath). Do not import it from settingsTranslations
 * or core locale packs.
 */
import type { UiLanguage } from '../i18n/uiLanguages';
import type { SettingsHelpDefinition, SettingsHelpSourceMap } from './settingsHelpSourceTypes';

type AdditionalSkillRetrievalLanguage = Exclude<UiLanguage, 'zh' | 'en'>;

export const SKILL_RETRIEVAL_HELP_KEY = 'settings.agent.AGENT_SKILL_RETRIEVAL_K';

// Keep these const names so TestSettingsFieldTitleContract can inventory
// the isolated title map without copying literals into SettingsPage cores.
const fieldTitleMapZh = {
  AGENT_SKILL_RETRIEVAL_K: '技能检索 Top-K',
} as const;

const fieldTitleMapEn = {
  AGENT_SKILL_RETRIEVAL_K: 'Skill Retrieval Top-K',
} satisfies Record<keyof typeof fieldTitleMapZh, string>;

export const SKILL_RETRIEVAL_FIELD_TITLE_MAP_ZH = fieldTitleMapZh;
export const SKILL_RETRIEVAL_FIELD_TITLE_MAP_EN = fieldTitleMapEn;

export const SKILL_RETRIEVAL_FIELD_DESCRIPTION = {
  AGENT_SKILL_RETRIEVAL_K:
    '自动 SkillRouter 按目录描述检索的数量。0 关闭并保持当前路由。正整数硬顶 8；空匹配回退默认路由集，不会启用 AGENT_SKILLS=all。当次请求指定技能、工厂/配置显式 AGENT_SKILLS（具体列表或 all）以及 AGENT_SKILL_ROUTING=manual 仍优先。',
} as const;

const SKILL_RETRIEVAL_EXAMPLES = [
  'AGENT_SKILL_RETRIEVAL_K=0',
  'AGENT_SKILL_RETRIEVAL_K=2',
] as const;

const skillRetrievalSettingsHelpEn: SettingsHelpDefinition = {
  title: fieldTitleMapEn.AGENT_SKILL_RETRIEVAL_K,
  summary: 'How many catalog skills automatic SkillRouter may retrieve by description. 0 keeps the current router.',
  usage: "Leave at 0 to disable retrieval and keep today's regime or default SkillRouter. A positive integer (hard cap 8) ranks catalog descriptions, display names, and aliases on the implicit automatic path only.",
  valueNotes: [
    '0 is default-off. Values above 8 clamp to 8. Empty catalog, empty query, or all-zero match falls back to the default router set, never AGENT_SKILLS=all.',
  ],
  impact: ['Affects which skills automatic Agent analysis loads when AGENT_SKILL_RETRIEVAL_K is greater than 0.'],
  notes: [
    'Per-run requested skills, factory or config explicit AGENT_SKILLS (specific or all), and AGENT_SKILL_ROUTING=manual still win.',
    'This does not rank tools and does not write episode retrieval logs.',
  ],
  examples: [...SKILL_RETRIEVAL_EXAMPLES],
};

const skillRetrievalSettingsHelpZh: SettingsHelpDefinition = {
  title: fieldTitleMapZh.AGENT_SKILL_RETRIEVAL_K,
  summary: '自动 SkillRouter 按目录描述检索时最多选取的技能数量。0 保持当前路由。',
  usage: '保持为 0 可关闭检索，并沿用今日的市场状态或默认 SkillRouter。正整数（硬顶 8）仅在隐式自动路径上按目录描述、显示名和别名排序。',
  valueNotes: [
    '0 为默认关闭。大于 8 的值会钳到 8。空目录、空查询或全零匹配会回退到默认路由集，绝不会启用 AGENT_SKILLS=all。',
  ],
  impact: ['当 AGENT_SKILL_RETRIEVAL_K 大于 0 时，影响自动 Agent 分析加载哪些技能。'],
  notes: [
    '当次请求指定的技能、工厂或配置显式 AGENT_SKILLS（具体列表或 all）以及 AGENT_SKILL_ROUTING=manual 仍然优先。',
    '这不会对工具排序，也不会写入 episode 检索日志。',
  ],
  examples: [...SKILL_RETRIEVAL_EXAMPLES],
};

// Single-quoted `'settings.agent.AGENT_SKILL_RETRIEVAL_K': {` so
// TestSettingsHelpContract can discover the registry help key.
export const SKILL_RETRIEVAL_SETTINGS_HELP_EN: SettingsHelpSourceMap = {
  'settings.agent.AGENT_SKILL_RETRIEVAL_K': {
    ...skillRetrievalSettingsHelpEn,
  },
};

export const SKILL_RETRIEVAL_SETTINGS_HELP_ZH: SettingsHelpSourceMap = {
  'settings.agent.AGENT_SKILL_RETRIEVAL_K': {
    ...skillRetrievalSettingsHelpZh,
  },
};

type ExtraSkillRetrievalHelp = {
  title: string;
  summary: string;
  usage: string;
  valueNotes: readonly [string];
  impact: readonly [string];
  notes: readonly [string, string];
};

const EXTRA_SKILL_RETRIEVAL_HELP = {
  "de": {
    title: 'Skill-Abruf Top-K',
    summary: 'Wie viele Katalog-Skills der automatische SkillRouter anhand der Beschreibung abrufen darf. 0 behält den aktuellen Router.',
    usage: 'Belassen Sie 0, um den Abruf zu deaktivieren und den heutigen Regime- oder Standard-SkillRouter beizubehalten. Eine positive Ganzzahl (Hartgrenze 8) ordnet Katalogbeschreibungen, Anzeigenamen und Aliase nur auf dem impliziten automatischen Pfad.',
    valueNotes: [
      '0 ist standardmäßig aus. Werte über 8 werden auf 8 begrenzt. Ein leerer Katalog, eine leere Abfrage oder eine All-Null-Übereinstimmung fällt auf die Standard-Router-Menge zurück, niemals AGENT_SKILLS=all.',
    ],
    impact: ['Beeinflusst, welche Skills die automatische Agent-Analyse lädt, wenn AGENT_SKILL_RETRIEVAL_K größer als 0 ist.'],
    notes: [
      'Pro Lauf angeforderte Skills, fabrik- oder konfigurationsseitig explizite AGENT_SKILLS (spezifisch oder all) und AGENT_SKILL_ROUTING=manual haben Vorrang.',
      'Dies bewertet keine Tools und schreibt keine Episode-Abrufprotokolle.',
    ],
  },
  "es": {
    title: 'Recuperación de skills Top-K',
    summary: 'Cuántas skills del catálogo puede recuperar el SkillRouter automático por descripción. 0 mantiene el enrutador actual.',
    usage: 'Deje 0 para desactivar la recuperación y conservar el SkillRouter de régimen o predeterminado de hoy. Un entero positivo (tope 8) ordena descripciones, nombres visibles y alias del catálogo solo en la ruta automática implícita.',
    valueNotes: [
      '0 está desactivado por defecto. Los valores mayores que 8 se limitan a 8. Un catálogo vacío, una consulta vacía o una coincidencia todo-cero vuelve al conjunto de enrutador predeterminado, nunca AGENT_SKILLS=all.',
    ],
    impact: ['Afecta qué skills carga el análisis automático del Agent cuando AGENT_SKILL_RETRIEVAL_K es mayor que 0.'],
    notes: [
      'Las skills solicitadas por ejecución, AGENT_SKILLS explícitas de fábrica o configuración (específicas o all) y AGENT_SKILL_ROUTING=manual siguen ganando.',
      'Esto no ordena herramientas ni escribe registros de recuperación de episode.',
    ],
  },
  "fr": {
    title: 'Récupération de skills Top-K',
    summary: 'Nombre de skills du catalogue que le SkillRouter automatique peut récupérer d’après la description. 0 conserve le routeur actuel.',
    usage: 'Laissez 0 pour désactiver la récupération et conserver le SkillRouter de régime ou par défaut d’aujourd’hui. Un entier positif (plafond 8) classe les descriptions, noms d’affichage et alias du catalogue uniquement sur le chemin automatique implicite.',
    valueNotes: [
      '0 est désactivé par défaut. Les valeurs supérieures à 8 sont limitées à 8. Un catalogue vide, une requête vide ou une correspondance tout-zéro revient à l’ensemble de routeur par défaut, jamais AGENT_SKILLS=all.',
    ],
    impact: ['Influence les skills chargés par l’analyse Agent automatique lorsque AGENT_SKILL_RETRIEVAL_K est supérieur à 0.'],
    notes: [
      'Les skills demandées par exécution, les AGENT_SKILLS explicites d’usine ou de configuration (spécifiques ou all) et AGENT_SKILL_ROUTING=manual restent prioritaires.',
      'Cela ne classe pas les outils et n’écrit pas de journaux de récupération d’episode.',
    ],
  },
  "id": {
    title: 'Pengambilan Skill Top-K',
    summary: 'Berapa banyak skill katalog yang boleh diambil SkillRouter otomatis berdasarkan deskripsi. 0 mempertahankan router saat ini.',
    usage: 'Biarkan 0 untuk menonaktifkan pengambilan dan mempertahankan SkillRouter rezim atau default hari ini. Bilangan bulat positif (batas keras 8) merangking deskripsi, nama tampilan, dan alias katalog hanya pada jalur otomatis implisit.',
    valueNotes: [
      '0 nonaktif secara default. Nilai di atas 8 dipotong menjadi 8. Katalog kosong, kueri kosong, atau kecocokan semua-nol kembali ke set router default, bukan AGENT_SKILLS=all.',
    ],
    impact: ['Memengaruhi skill yang dimuat analisis Agent otomatis ketika AGENT_SKILL_RETRIEVAL_K lebih besar dari 0.'],
    notes: [
      'Skill yang diminta per jalankan, AGENT_SKILLS eksplisit pabrik atau konfigurasi (spesifik atau all), dan AGENT_SKILL_ROUTING=manual tetap diutamakan.',
      'Ini tidak merangking alat dan tidak menulis log pengambilan episode.',
    ],
  },
  "ja": {
    title: 'スキル検索 Top-K',
    summary: '自動 SkillRouter がカタログ説明から取得できるスキル数。0 は現行ルーターを維持します。',
    usage: '0 のままにすると検索を無効にし、今日のレジームまたは既定の SkillRouter を維持します。正の整数（上限 8）は暗黙の自動パスでのみカタログの説明・表示名・別名で順位付けします。',
    valueNotes: [
      '0 はデフォルトオフです。8 を超える値は 8 に制限されます。空のカタログ、空のクエリ、または全ゼロ一致は既定ルーター集合にフォールバックし、AGENT_SKILLS=all にはなりません。',
    ],
    impact: ['AGENT_SKILL_RETRIEVAL_K が 0 より大きいとき、自動 Agent 分析が読み込むスキルに影響します。'],
    notes: [
      '実行ごとの要求スキル、ファクトリまたは設定の明示的な AGENT_SKILLS（具体リストまたは all）、および AGENT_SKILL_ROUTING=manual が優先されます。',
      'ツールの順位付けは行わず、episode 検索ログも書き込みません。',
    ],
  },
  "ko": {
    title: '스킬 검색 Top-K',
    summary: '자동 SkillRouter가 카탈로그 설명으로 가져올 수 있는 스킬 수입니다. 0은 현재 라우터를 유지합니다.',
    usage: '0으로 두면 검색이 꺼지고 오늘의 레짐 또는 기본 SkillRouter가 유지됩니다. 양의 정수(상한 8)는 암시적 자동 경로에서만 카탈로그 설명, 표시 이름, 별칭으로 순위를 매깁니다.',
    valueNotes: [
      '0은 기본 해제입니다. 8을 넘는 값은 8로 제한됩니다. 빈 카탈로그, 빈 쿼리 또는 전무(0) 일치는 기본 라우터 집합으로 돌아가며 AGENT_SKILLS=all 이 되지 않습니다.',
    ],
    impact: ['AGENT_SKILL_RETRIEVAL_K 가 0보다 클 때 자동 Agent 분석이 로드하는 스킬에 영향을 줍니다.'],
    notes: [
      '실행마다 요청한 스킬, 팩토리 또는 설정의 명시적 AGENT_SKILLS(구체 목록 또는 all), 그리고 AGENT_SKILL_ROUTING=manual 이 우선합니다.',
      '도구 순위를 매기지 않으며 episode 검색 로그도 쓰지 않습니다.',
    ],
  },
  "ms": {
    title: 'Carian Skill Top-K',
    summary: 'Bilangan skill katalog yang boleh diambil SkillRouter automatik mengikut perihalan. 0 mengekalkan penghala semasa.',
    usage: 'Biarkan 0 untuk mematikan carian dan mengekalkan SkillRouter rejim atau lalai hari ini. Integer positif (had keras 8) menyusun perihalan, nama paparan dan alias katalog hanya pada laluan automatik tersirat.',
    valueNotes: [
      '0 dimatikan secara lalai. Nilai di atas 8 dikepit kepada 8. Katalog kosong, pertanyaan kosong atau padanan semua-sifar jatuh kembali ke set penghala lalai, bukan AGENT_SKILLS=all.',
    ],
    impact: ['Mempengaruhi skill yang dimuatkan analisis Agent automatik apabila AGENT_SKILL_RETRIEVAL_K lebih besar daripada 0.'],
    notes: [
      'Skill yang diminta setiap larian, AGENT_SKILLS eksplisit kilang atau konfigurasi (khusus atau all), dan AGENT_SKILL_ROUTING=manual masih diutamakan.',
      'Ini tidak menyusun alat dan tidak menulis log carian episode.',
    ],
  },
  "zh-TW": {
    title: '技能檢索 Top-K',
    summary: '自動 SkillRouter 依目錄描述檢索時最多選取的技能數量。0 保持目前路由。',
    usage: '保持為 0 可關閉檢索，並沿用今日的市場狀態或預設 SkillRouter。正整數（硬頂 8）僅在隱式自動路徑上依目錄描述、顯示名稱和別名排序。',
    valueNotes: [
      '0 為預設關閉。大於 8 的值會鉗到 8。空目錄、空查詢或全零匹配會回退到預設路由集，絕不會啟用 AGENT_SKILLS=all。',
    ],
    impact: ['當 AGENT_SKILL_RETRIEVAL_K 大於 0 時，影響自動 Agent 分析載入哪些技能。'],
    notes: [
      '當次請求指定的技能、工廠或設定顯式 AGENT_SKILLS（具體清單或 all）以及 AGENT_SKILL_ROUTING=manual 仍然優先。',
      '這不會對工具排序，也不會寫入 episode 檢索日誌。',
    ],
  },
} as const satisfies Record<AdditionalSkillRetrievalLanguage, ExtraSkillRetrievalHelp>;

function fromExtra(fields: ExtraSkillRetrievalHelp): SettingsHelpDefinition {
  return {
    title: fields.title,
    summary: fields.summary,
    usage: fields.usage,
    valueNotes: [...fields.valueNotes],
    impact: [...fields.impact],
    notes: [...fields.notes],
    examples: [...SKILL_RETRIEVAL_EXAMPLES],
  };
}

export function isSkillRetrievalHelpKey(helpKey: string): boolean {
  return helpKey === SKILL_RETRIEVAL_HELP_KEY || helpKey === 'AGENT_SKILL_RETRIEVAL_K';
}

export function getSkillRetrievalSettingsHelp(language: UiLanguage): SettingsHelpDefinition {
  if (language === 'zh') {
    return skillRetrievalSettingsHelpZh;
  }
  if (language === 'en') {
    return skillRetrievalSettingsHelpEn;
  }
  return fromExtra(EXTRA_SKILL_RETRIEVAL_HELP[language]);
}

export function getSkillRetrievalFieldTitle(language: UiLanguage): string {
  return getSkillRetrievalSettingsHelp(language).title ?? SKILL_RETRIEVAL_FIELD_TITLE_MAP_EN.AGENT_SKILL_RETRIEVAL_K;
}

export function getSkillRetrievalFieldDescription(): string {
  return SKILL_RETRIEVAL_FIELD_DESCRIPTION.AGENT_SKILL_RETRIEVAL_K;
}
