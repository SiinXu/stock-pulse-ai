'use strict';

const { spawn } = require('child_process');

const DESKTOP_CLI_INSTALL_GUIDE_URLS = Object.freeze({
  ollama: 'https://ollama.com/download',
  codex: 'https://github.com/openai/codex',
  claude: 'https://code.claude.com/docs/en/overview',
  opencode: 'https://opencode.ai/docs/cli',
});

const DESKTOP_CLI_INSTALL_GUIDE_HOSTS = Object.freeze(
  new Set(
    Object.values(DESKTOP_CLI_INSTALL_GUIDE_URLS).map((url) => new URL(url).hostname.toLowerCase())
  )
);

const GUIDANCE_COPY = Object.freeze({
  zh: Object.freeze({
    title: '本机 CLI 对桌面进程的可见性',
    intro: '状态来自桌面壳的有界 PATH 探测，不暴露原始 PATH 或可执行文件绝对路径。',
    statusAvailable: '可用',
    statusMissing: '缺失',
    statusUnknown: '未知',
    missingHint: '桌面进程看不到该命令。请在系统终端安装到登录 PATH（macOS 常见 Homebrew），然后重新检测或重启桌面端。',
    unknownHint: '探测超时、PATH 不可用或权限错误。不能据此断定已安装或未安装；请打开终端核对后再重试。',
    availableHint: '桌面进程可见该命令。',
    openTerminal: '打开系统终端',
    openInstallGuide: '打开安装说明',
    recheck: '重新检测',
    terminalOpened: '已尝试打开系统终端。',
    terminalUnsupported: '当前平台无法自动打开终端。请手动打开系统终端后重试。',
    guideOpened: '已在系统浏览器打开安装说明。',
    guideUnsupported: '该命令没有可打开的安装说明。',
    pathUnavailable: '当前进程 PATH 不可用；请从终端启动一次应用，或确认登录环境已配置 PATH。',
    deepLinkRejectedTitle: '不支持的桌面深链',
    deepLinkRejectedMessage:
      '该 stockpulse:// 链接未通过白名单校验，当前页面未改变。仅支持 stockpulse://app/<允许路径> 形式。',
  }),
  en: Object.freeze({
    title: 'CLI visibility for the Desktop process',
    intro: 'Statuses come from a bounded Desktop PATH probe. Raw PATH and absolute executable paths are never exposed.',
    statusAvailable: 'Available',
    statusMissing: 'Missing',
    statusUnknown: 'Unknown',
    missingHint:
      'The Desktop process cannot see this command. Install it on your login PATH (Homebrew is common on macOS), then recheck or restart Desktop.',
    unknownHint:
      'Probe timed out, PATH was unavailable, or a permission error occurred. Do not treat this as installed or missing; open a terminal, verify, then retry.',
    availableHint: 'The Desktop process can see this command.',
    openTerminal: 'Open system terminal',
    openInstallGuide: 'Open install guide',
    recheck: 'Recheck',
    terminalOpened: 'Tried to open the system terminal.',
    terminalUnsupported: 'This platform cannot open a terminal automatically. Open one manually and retry.',
    guideOpened: 'Opened the install guide in the system browser.',
    guideUnsupported: 'No install guide is available for that command.',
    pathUnavailable:
      'Process PATH is unavailable. Launch Desktop once from a terminal, or confirm login PATH is configured.',
    deepLinkRejectedTitle: 'Unsupported desktop deep link',
    deepLinkRejectedMessage:
      'That stockpulse:// link failed the allowlist check. The current page was not changed. Only stockpulse://app/<allowed-path> is supported.',
  }),
});

function normalizeGuidanceLocale(locale) {
  const raw = String(locale || '').trim().toLowerCase();
  if (raw.startsWith('zh')) {
    return 'zh';
  }
  return 'en';
}

function getGuidanceCopy(locale) {
  return GUIDANCE_COPY[normalizeGuidanceLocale(locale)] || GUIDANCE_COPY.en;
}

function sanitizeDiagnosticsForRenderer(diagnostics) {
  const pathInfo = diagnostics && diagnostics.path && typeof diagnostics.path === 'object'
    ? diagnostics.path
    : {};
  const cli = Array.isArray(diagnostics && diagnostics.cli)
    ? diagnostics.cli.map((entry) => ({
      name: String(entry && entry.name ? entry.name : '').trim(),
      status: entry && entry.status === 'available'
        ? 'available'
        : entry && entry.status === 'missing'
          ? 'missing'
          : 'unknown',
      reason: entry && typeof entry.reason === 'string' ? entry.reason : null,
    })).filter((entry) => entry.name)
    : [];

  return {
    schemaVersion: sanitizeNonNegativeInteger(diagnostics && diagnostics.schemaVersion, 2),
    generatedAt: typeof diagnostics?.generatedAt === 'string' ? diagnostics.generatedAt : null,
    platform: typeof diagnostics?.platform === 'string' ? diagnostics.platform : 'unknown',
    path: {
      effectiveEntryCount: sanitizeNonNegativeInteger(pathInfo.effectiveEntryCount, 0),
      limited: Boolean(pathInfo.limited),
      augmented: Boolean(pathInfo.augmented),
      policy: typeof pathInfo.policy === 'string' ? pathInfo.policy : 'unknown',
    },
    cli,
  };
}

function sanitizeNonNegativeInteger(value, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return fallback;
  }
  return Math.floor(parsed);
}

function assertRendererSafePayload(payload) {
  const serialized = JSON.stringify(payload);
  const forbidden = [
    '/opt/homebrew',
    '/usr/local/bin',
    '/Users/',
    'C:\\\\',
    'C:/',
    'Application Support',
    'effectiveEntries',
    'appDir',
    'envFile',
    'PATHEXT',
  ];
  for (const token of forbidden) {
    if (serialized.includes(token)) {
      throw new Error(`Renderer diagnostics payload leaked sensitive token: ${token}`);
    }
  }
  return payload;
}

function buildCliOperatorGuidance(diagnostics, { locale = 'en' } = {}) {
  const copy = getGuidanceCopy(locale);
  const safe = sanitizeDiagnosticsForRenderer(diagnostics);
  const pathUnavailable = safe.cli.some((entry) => entry.reason === 'path_unavailable')
    || (safe.path.effectiveEntryCount === 0 && safe.path.policy !== 'macos-gui-homebrew-extend');

  const commands = safe.cli.map((entry) => {
    let hint = copy.availableHint;
    if (entry.status === 'missing') {
      hint = copy.missingHint;
    } else if (entry.status === 'unknown') {
      hint = entry.reason === 'path_unavailable' ? copy.pathUnavailable : copy.unknownHint;
    }
    return {
      name: entry.name,
      status: entry.status,
      reason: entry.reason,
      statusLabel: entry.status === 'available'
        ? copy.statusAvailable
        : entry.status === 'missing'
          ? copy.statusMissing
          : copy.statusUnknown,
      hint,
      installGuideAvailable: Object.prototype.hasOwnProperty.call(
        DESKTOP_CLI_INSTALL_GUIDE_URLS,
        entry.name
      ),
    };
  });

  const needsAction = commands.some(
    (entry) => entry.status === 'missing' || entry.status === 'unknown'
  );

  const payload = {
    ...safe,
    copy: {
      title: copy.title,
      intro: copy.intro,
      openTerminal: copy.openTerminal,
      openInstallGuide: copy.openInstallGuide,
      recheck: copy.recheck,
      pathUnavailable: pathUnavailable ? copy.pathUnavailable : null,
    },
    needsAction,
    actions: {
      openTerminalSupported: true,
      installGuideSupported: true,
    },
    commands,
  };
  return assertRendererSafePayload(payload);
}

function resolveCliInstallGuideUrl(commandName) {
  const name = String(commandName || '').trim();
  if (!Object.prototype.hasOwnProperty.call(DESKTOP_CLI_INSTALL_GUIDE_URLS, name)) {
    return null;
  }
  const url = DESKTOP_CLI_INSTALL_GUIDE_URLS[name];
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:') {
      return null;
    }
    if (!DESKTOP_CLI_INSTALL_GUIDE_HOSTS.has(parsed.hostname.toLowerCase())) {
      return null;
    }
    return parsed.toString();
  } catch (_error) {
    return null;
  }
}

async function openOperatorTerminal({
  platform = process.platform,
  spawnImpl = spawn,
} = {}) {
  try {
    let child;
    if (platform === 'darwin') {
      child = spawnImpl('open', ['-a', 'Terminal'], {
        detached: true,
        stdio: 'ignore',
      });
    } else if (platform === 'win32') {
      child = spawnImpl('cmd.exe', ['/c', 'start', '', 'cmd.exe'], {
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      });
    } else {
      child = spawnImpl('x-terminal-emulator', [], {
        detached: true,
        stdio: 'ignore',
      });
    }
    if (!child || typeof child.once !== 'function') {
      return { ok: false, error: 'terminal_launch_failed' };
    }
    const launched = await new Promise((resolve) => {
      child.once('spawn', () => resolve(true));
      child.once('error', () => resolve(false));
    });
    if (!launched) {
      return { ok: false, error: 'terminal_launch_failed' };
    }
    if (typeof child.unref === 'function') {
      child.unref();
    }
    return { ok: true };
  } catch (_error) {
    return { ok: false, error: 'terminal_launch_failed' };
  }
}

async function openCliInstallGuide(commandName, {
  openExternal,
} = {}) {
  if (typeof openExternal !== 'function') {
    return { ok: false, error: 'open_external_unavailable' };
  }
  const url = resolveCliInstallGuideUrl(commandName);
  if (!url) {
    return { ok: false, error: 'guide_unsupported' };
  }
  try {
    await openExternal(url);
  } catch (_error) {
    return { ok: false, error: 'guide_open_failed' };
  }
  return { ok: true, urlHost: new URL(url).hostname };
}

function getDeepLinkRejectionCopy(locale) {
  const copy = getGuidanceCopy(locale);
  return {
    title: copy.deepLinkRejectedTitle,
    message: copy.deepLinkRejectedMessage,
  };
}

module.exports = {
  DESKTOP_CLI_INSTALL_GUIDE_URLS,
  GUIDANCE_COPY,
  assertRendererSafePayload,
  buildCliOperatorGuidance,
  getDeepLinkRejectionCopy,
  getGuidanceCopy,
  normalizeGuidanceLocale,
  openCliInstallGuide,
  openOperatorTerminal,
  resolveCliInstallGuideUrl,
  sanitizeDiagnosticsForRenderer,
};
