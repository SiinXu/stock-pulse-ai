import type { Message } from '../../stores/agentChatStore';
import type { ChatFollowUpContext } from '../../utils/chatFollowUp';
import { extractStockCodesFromMessage } from '../../utils/chatStockCode';
import { normalizeStockCode } from '../../utils/stockCode';

const STRONG_COMPARE_STOCK_MESSAGE_RE = /比较|对比|\bvs\b|和[^，。,.!?！？]{0,40}比/i;
const WEAK_COMPARE_STOCK_MESSAGE_RE = /差异(?!化)|区别|不同|相比|对照|比一比/;
const CHOICE_COMPARE_STOCK_MESSAGE_RE = /哪个|哪只|哪一个|谁更|更值得|更适合|怎么选|选哪|二选一/;
const LINKED_COMPARE_STOCK_MESSAGE_RE = /(?:和|与|跟|同)[^，。,.!?！？]{0,40}(?:差异(?!化)|区别|不同|相比|对照|比一比)/;
const SWITCH_STOCK_MESSAGE_RE = /换成|改看|分析|看看|研究|诊断/;

export type ActiveStockContext = Pick<ChatFollowUpContext, 'stock_code' | 'stock_name'>;
export type ActiveStockResolution = {
  context: ActiveStockContext;
  useForCurrentSend: boolean;
};

export const isCompareStockMessage = (
  message: string,
  stockCodes: string[],
  currentStockCode?: string | null,
): boolean => {
  if (STRONG_COMPARE_STOCK_MESSAGE_RE.test(message)) {
    return true;
  }
  const current = currentStockCode ? normalizeStockCode(currentStockCode) : null;
  const newStockCodes = current
    ? stockCodes.filter((code) => code !== current)
    : stockCodes;
  if (newStockCodes.length >= 2) {
    return true;
  }
  if (CHOICE_COMPARE_STOCK_MESSAGE_RE.test(message) && stockCodes.length >= 2) {
    return true;
  }
  if (!WEAK_COMPARE_STOCK_MESSAGE_RE.test(message)) {
    return false;
  }
  if (stockCodes.length >= 2) {
    return true;
  }
  if (!currentStockCode) {
    return false;
  }
  const hasNewStock = stockCodes.some((code) => code !== current);
  return hasNewStock && LINKED_COMPARE_STOCK_MESSAGE_RE.test(message);
};

export const resolveActiveStockContextFromMessage = (
  message: string,
  currentContext: ActiveStockContext | null,
): ActiveStockResolution | null => {
  const stockCodes = extractStockCodesFromMessage(message);
  const stockCode = stockCodes[0] ?? null;
  if (!stockCode) {
    return null;
  }

  const isCompare = isCompareStockMessage(message, stockCodes, currentContext?.stock_code);
  const isSwitch = SWITCH_STOCK_MESSAGE_RE.test(message);
  const currentStockCode = currentContext?.stock_code
    ? normalizeStockCode(currentContext.stock_code)
    : null;
  const newStockCodes = currentStockCode
    ? stockCodes.filter((code) => code !== currentStockCode)
    : stockCodes;
  // Explicit switches can mention the old stock; use the single new code when present.
  const targetStockCode = isSwitch && newStockCodes.length === 1
    ? newStockCodes[0]
    : stockCode;
  const isDifferentStock = currentStockCode !== targetStockCode;

  // Compare messages and implicit follow-ups must not rewrite the active stock context.
  if (isCompare || (currentContext && !isSwitch)) {
    return null;
  }

  return {
    context: {
      stock_code: targetStockCode,
      stock_name: currentContext && !isDifferentStock
        ? currentContext.stock_name
        : null,
    },
    // Only explicit switches should affect the context sent with the current request.
    useForCurrentSend: isSwitch && isDifferentStock,
  };
};

export const restoreActiveStockContextFromMessages = (
  messages: Message[],
): ActiveStockContext | null => {
  let restoredContext: ActiveStockContext | null = null;
  for (const message of messages) {
    if (message.role !== 'user') {
      continue;
    }
    const resolution = resolveActiveStockContextFromMessage(message.content, restoredContext);
    if (resolution) {
      restoredContext = resolution.context;
    }
  }
  return restoredContext;
};
