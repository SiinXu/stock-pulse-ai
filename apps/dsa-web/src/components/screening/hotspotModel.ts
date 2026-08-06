import type React from 'react';
import {
  Activity,
  Building2,
  Droplet,
  Factory,
  Gem,
  Landmark,
  Pickaxe,
  Plane,
  Shield,
  Stethoscope,
  Trees,
  Utensils,
  Wrench,
} from 'lucide-react';
import type { AlphaSiftHotspot, AlphaSiftHotspotDetail, AlphaSiftHotspotsResponse } from '../../api/alphasift';
import { formatUiText, type UiLanguage } from '../../i18n/uiText';
import { formatUiDateTime, getUiListSeparator } from '../../utils/uiLocale';
import { formatNumber } from './screeningCandidateModel';
import { summarizeAlphaSiftDiagnostic } from './screeningMessages';
import type { ScreeningText } from './screeningText';

export const ALPHASIFT_HOTSPOT_NO_CACHE_HINT = 'No cached AlphaSift hotspot snapshot. Click refresh to fetch live hotspots.';
export const ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE = 'eastmoney_hotspot_unavailable';

export const formatHotspotEmptyMessage = (result: AlphaSiftHotspotsResponse, text: ScreeningText) => {
  const message = String(result.message || '').trim();
  const sourceErrors = result.sourceErrors || [];
  if (message && sourceErrors.includes(ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE)) {
    return message;
  }
  if (message === ALPHASIFT_HOTSPOT_NO_CACHE_HINT) {
    return text.noCachedHotspots;
  }
  const sourceError = sourceErrors[0];
  if (sourceError) {
    return formatUiText(text.hotspotUnavailableDetail, { detail: summarizeAlphaSiftDiagnostic(sourceError, text) });
  }
  return text.hotspotUnavailable;
};

export const getRouteTimeLabel = (item: AlphaSiftHotspotDetail['route'][number], language: UiLanguage, text: ScreeningText) => {
  const rawTime = item.publishedAt || item.date || item.time || '';
  if (!rawTime) {
    return item.source || text.pendingConfirmation;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(rawTime)) {
    return rawTime;
  }
  const parsed = new Date(rawTime);
  if (!Number.isNaN(parsed.getTime())) {
    return formatUiDateTime(parsed, language, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }
  return rawTime;
};

export const getHotspotRouteItems = (detail: AlphaSiftHotspotDetail) => {
  const route = detail.route || [];
  if (route.length > 0) {
    return route;
  }
  return detail.timeline || [];
};

export const formatHotspotMetric = (value: unknown, text: ScreeningText, digits = 1) => {
  const formatted = formatNumber(value, digits);
  return formatted === '-' ? text.observing : formatted;
};

export const getHotspotLeadersText = (item: AlphaSiftHotspot, language: UiLanguage, text: ScreeningText) => {
  const leaders = (item.leaders || []).map((value) => String(value).trim()).filter(Boolean);
  if (leaders.length > 0) {
    return leaders.slice(0, 2).join(getUiListSeparator(language));
  }
  return text.observing;
};

export const getHotspotSampleText = (item: AlphaSiftHotspot, text: ScreeningText) => {
  if (item.sampleStockCount == null || Number.isNaN(Number(item.sampleStockCount))) {
    return text.activeStocksObserving;
  }
  return formatUiText(text.stockCoverage, { count: item.sampleStockCount });
};

export const formatStockChangeText = (value: unknown, text: ScreeningText) => {
  const formatted = formatNumber(value);
  return formatted === '-' ? text.quotePending : `${formatted}%`;
};

export const formatHotspotUpdatedAt = (value: string | null, language: UiLanguage, text: ScreeningText) => {
  if (!value) {
    return text.refreshPending;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return formatUiDateTime(parsed, language, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
};

export const getHotspotStrength = (item: AlphaSiftHotspot, index: number, text: ScreeningText) => {
  const heat = Number(item.heatScore ?? 0);
  const changePct = Number(item.changePct ?? 0);
  if (index === 0 || heat >= 90 || changePct >= 8) {
    return { label: text.strengthLeading, className: 'bg-red-500/10 text-red-500' };
  }
  if (heat >= 80 || changePct >= 5) {
    return { label: text.strengthStrong, className: 'bg-blue-500/10 text-blue-500' };
  }
  return { label: text.strengthFirm, className: 'bg-primary/10 text-primary' };
};

const HOTSPOT_ICON_RULES: Array<{
  pattern: RegExp;
  icon: React.ComponentType<{ className?: string }>;
  className: string;
}> = [
  { pattern: /金|银|铜|铝|铅|锌|钼|钴|镍|贵金属|矿|有色/, icon: Pickaxe, className: 'bg-orange-500/10 text-orange-500' },
  { pattern: /黄金|珠宝/, icon: Gem, className: 'bg-amber-500/10 text-amber-500' },
  { pattern: /油|气|能源|煤/, icon: Droplet, className: 'bg-yellow-700/10 text-yellow-700' },
  { pattern: /金融|券商|银行|保险|资本/, icon: Landmark, className: 'bg-orange-500/10 text-orange-500' },
  { pattern: /航空|机场|航天|运输/, icon: Plane, className: 'bg-blue-500/10 text-blue-500' },
  { pattern: /林业|农业|种植/, icon: Trees, className: 'bg-emerald-500/10 text-emerald-500' },
  { pattern: /医疗|诊断|卫生|医药/, icon: Stethoscope, className: 'bg-teal-500/10 text-teal-500' },
  { pattern: /食品|餐饮|酒/, icon: Utensils, className: 'bg-violet-500/10 text-violet-500' },
  { pattern: /工业|制造|修理|机械|设备/, icon: Wrench, className: 'bg-blue-500/10 text-blue-500' },
  { pattern: /租赁|地产|建筑/, icon: Building2, className: 'bg-emerald-500/10 text-emerald-500' },
  { pattern: /电|芯片|算力|AI|机器人/, icon: Factory, className: 'bg-indigo-500/10 text-indigo-500' },
  { pattern: /保险|安全/, icon: Shield, className: 'bg-blue-500/10 text-blue-500' },
];

export const getHotspotIcon = (topic: string) => {
  const match = HOTSPOT_ICON_RULES.find((rule) => rule.pattern.test(topic));
  return match || { icon: Activity, className: 'bg-primary/10 text-primary' };
};
