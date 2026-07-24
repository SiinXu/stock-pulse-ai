#!/usr/bin/env node

const crypto = require('node:crypto');
const dns = require('node:dns');
const fs = require('node:fs');
const https = require('node:https');
const net = require('node:net');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { Transform } = require('node:stream');
const { pipeline } = require('node:stream/promises');

const REPOSITORY_ROOT = path.resolve(__dirname, '..');
const DESKTOP_ROOT = path.join(REPOSITORY_ROOT, 'apps', 'dsa-desktop');
const CONFIG_PATH = path.join(DESKTOP_ROOT, 'ollama-runtime.json');
const DEFAULT_OUTPUT_DIR = path.join(DESKTOP_ROOT, 'vendor', 'ollama');
const PREPARED_MANIFEST_FILE = 'runtime-manifest.json';
const DOWNLOAD_TIMEOUT_MS = 60_000;
const DOWNLOAD_TOTAL_TIMEOUT_MS = 30 * 60_000;
const MAX_REDIRECTS = 5;
const ALLOWED_DOWNLOAD_HOSTS = new Set([
  'github.com',
  'release-assets.githubusercontent.com',
]);

const BLOCKED_DOWNLOAD_ADDRESSES = new net.BlockList();
const GLOBAL_DOWNLOAD_IPV6_ADDRESSES = new net.BlockList();
GLOBAL_DOWNLOAD_IPV6_ADDRESSES.addSubnet('2000::', 3, 'ipv6');

// Mirror the IANA special-purpose registries and fail closed for IPv6 outside
// the currently allocated global-unicast space. Broad registry parents are
// intentional: the fixed GitHub release hosts do not depend on their narrow
// anycast exceptions, so a false denial is safer than admitting a special-use
// or newly reserved destination.
for (const [network, prefix] of [
  ['0.0.0.0', 8],
  ['10.0.0.0', 8],
  ['100.64.0.0', 10],
  ['127.0.0.0', 8],
  ['169.254.0.0', 16],
  ['172.16.0.0', 12],
  ['192.0.0.0', 24],
  ['192.0.2.0', 24],
  ['192.31.196.0', 24],
  ['192.52.193.0', 24],
  ['192.88.99.0', 24],
  ['192.168.0.0', 16],
  ['192.175.48.0', 24],
  ['198.18.0.0', 15],
  ['198.51.100.0', 24],
  ['203.0.113.0', 24],
  ['224.0.0.0', 4],
  ['240.0.0.0', 4],
]) {
  BLOCKED_DOWNLOAD_ADDRESSES.addSubnet(network, prefix, 'ipv4');
}
for (const [network, prefix] of [
  ['::', 128],
  ['::1', 128],
  ['64:ff9b::', 96],
  ['64:ff9b:1::', 48],
  ['100::', 64],
  ['100:0:0:1::', 64],
  ['2001::', 23],
  ['2001:db8::', 32],
  ['2002::', 16],
  ['2620:4f:8000::', 48],
  ['3fff::', 20],
  ['5f00::', 16],
  ['fc00::', 7],
  ['fec0::', 10],
  ['fe80::', 10],
  ['ff00::', 8],
]) {
  BLOCKED_DOWNLOAD_ADDRESSES.addSubnet(network, prefix, 'ipv6');
}

function readRuntimeConfig(configPath = CONFIG_PATH) {
  const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
  if (config.schemaVersion !== 1 || config.runtime !== 'ollama') {
    throw new Error(`Unsupported embedded Ollama manifest: ${configPath}`);
  }
  if (!/^v\d+\.\d+\.\d+$/.test(String(config.version || ''))) {
    throw new Error('Embedded Ollama version must be an exact release tag.');
  }
  const expectedReleaseUrl = `https://github.com/ollama/ollama/releases/download/${config.version}`;
  if (config.releaseBaseUrl !== expectedReleaseUrl
    || config.checksumSourceUrl !== `${expectedReleaseUrl}/sha256sum.txt`) {
    throw new Error('Embedded Ollama URLs must match the official pinned release.');
  }
  const goModules = config.goRuntime && config.goRuntime.modules;
  if (!config.goRuntime
    || !/^go\d+\.\d+\.\d+$/.test(String(config.goRuntime.version || ''))
    || !Array.isArray(goModules)
    || goModules.length === 0) {
    throw new Error('Embedded Ollama Go runtime inventory is invalid.');
  }
  const moduleKeys = goModules.map((entry) => {
    if (!entry
      || !/^[A-Za-z0-9._~+/-]+$/.test(String(entry.path || ''))
      || !/^v[^\s]+$/.test(String(entry.version || ''))) {
      throw new Error('Embedded Ollama Go module inventory contains an invalid entry.');
    }
    return `${entry.path}@${entry.version}`;
  });
  if (new Set(moduleKeys).size !== moduleKeys.length
    || JSON.stringify(moduleKeys) !== JSON.stringify([...moduleKeys].sort())) {
    throw new Error('Embedded Ollama Go module inventory must be unique and sorted.');
  }
  return config;
}

function selectArtifact(config, platform, arch) {
  const key = platform === 'darwin' ? 'darwin' : `${platform}-${arch}`;
  const artifact = config.artifacts && config.artifacts[key];
  if (!artifact || !Array.isArray(artifact.architectures) || !artifact.architectures.includes(arch)) {
    throw new Error(`Embedded Ollama is not configured for ${platform}/${arch}.`);
  }
  if (!/^[a-f0-9]{64}$/.test(String(artifact.sha256 || ''))) {
    throw new Error(`Embedded Ollama checksum is invalid for ${platform}/${arch}.`);
  }
  if (!Number.isSafeInteger(artifact.sizeBytes) || artifact.sizeBytes <= 0) {
    throw new Error(`Embedded Ollama byte size is invalid for ${platform}/${arch}.`);
  }
  if (!['tgz', 'zip'].includes(artifact.archiveType)) {
    throw new Error(`Unsupported embedded Ollama archive type: ${artifact.archiveType}`);
  }
  if (!/^[A-Za-z0-9._-]+$/.test(String(artifact.fileName || ''))
    || !Array.isArray(artifact.requiredPaths)
    || artifact.requiredPaths.length === 0
    || typeof artifact.binaryPath !== 'string') {
    throw new Error(`Embedded Ollama artifact paths are invalid for ${platform}/${arch}.`);
  }
  return {
    ...artifact,
    downloadUrl: `${config.releaseBaseUrl}/${artifact.fileName}`,
  };
}

function calculateFileSha256(filePath, fsImpl = fs) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256');
    const input = fsImpl.createReadStream(filePath);
    input.on('data', (chunk) => hash.update(chunk));
    input.on('error', reject);
    input.on('end', () => resolve(hash.digest('hex')));
  });
}

async function assertFileChecksum(filePath, expectedSha256, fsImpl = fs) {
  const actualSha256 = await calculateFileSha256(filePath, fsImpl);
  if (actualSha256 !== expectedSha256) {
    const error = new Error(
      `Embedded Ollama checksum mismatch for ${path.basename(filePath)}: `
      + `expected ${expectedSha256}, received ${actualSha256}`
    );
    error.code = 'OLLAMA_CHECKSUM_MISMATCH';
    throw error;
  }
  return actualSha256;
}

function assertFileSize(filePath, expectedBytes, fsImpl = fs) {
  const actualBytes = fsImpl.statSync(filePath).size;
  if (actualBytes !== expectedBytes) {
    const error = new Error(
      `Embedded Ollama byte-size mismatch for ${path.basename(filePath)}: `
      + `expected ${expectedBytes}, received ${actualBytes}`
    );
    error.code = 'OLLAMA_SIZE_MISMATCH';
    throw error;
  }
  return actualBytes;
}

function normalizeRuntimeRelativePath(relativePath) {
  return relativePath.split(path.sep).join('/');
}

function collectRuntimeFilePaths(rootDir, fsImpl = fs) {
  const root = path.resolve(rootDir);
  const realRoot = fsImpl.realpathSync(root);
  const files = [];
  const walk = (directory, relativeDirectory = '') => {
    const entries = fsImpl.readdirSync(directory, { withFileTypes: true })
      .sort((left, right) => left.name.localeCompare(right.name, 'en'));
    for (const entry of entries) {
      const relativePath = relativeDirectory
        ? path.join(relativeDirectory, entry.name)
        : entry.name;
      if (normalizeRuntimeRelativePath(relativePath) === PREPARED_MANIFEST_FILE) {
        continue;
      }
      const resourcePath = resolveContainedPath(root, relativePath);
      const linkStats = fsImpl.lstatSync(resourcePath);
      if (linkStats.isDirectory()) {
        walk(resourcePath, relativePath);
        continue;
      }
      const stats = fsImpl.statSync(resourcePath);
      const realResourcePath = fsImpl.realpathSync(resourcePath);
      if ((realResourcePath !== realRoot && !realResourcePath.startsWith(`${realRoot}${path.sep}`))
        || !stats.isFile()) {
        throw new Error(`Unsupported embedded Ollama archive entry: ${relativePath}`);
      }
      files.push(normalizeRuntimeRelativePath(relativePath));
    }
  };
  walk(root);
  return files.sort();
}

async function calculateRuntimeFileSha256(rootDir, runtimeFilePaths, fsImpl = fs) {
  const hashes = {};
  for (const relativePath of runtimeFilePaths) {
    const resourcePath = resolveContainedPath(rootDir, relativePath);
    hashes[relativePath] = await calculateFileSha256(resourcePath, fsImpl);
  }
  return hashes;
}

function createDownloadPolicyError(message) {
  const error = new Error(message);
  error.code = 'OLLAMA_DOWNLOAD_POLICY';
  return error;
}

function validateDownloadUrl(url) {
  let parsedUrl;
  try {
    parsedUrl = url instanceof URL ? url : new URL(url);
  } catch (_error) {
    throw createDownloadPolicyError('Embedded Ollama download URL is invalid.');
  }
  const hostname = parsedUrl.hostname.toLowerCase();
  if (parsedUrl.protocol !== 'https:'
    || parsedUrl.username
    || parsedUrl.password
    || (parsedUrl.port && parsedUrl.port !== '443')
    || !ALLOWED_DOWNLOAD_HOSTS.has(hostname)) {
    throw createDownloadPolicyError(
      `Refusing embedded Ollama download destination: ${parsedUrl.origin}`
    );
  }
  return parsedUrl;
}

function isPublicDownloadAddress(address) {
  if (typeof address !== 'string'
    || address.includes('%')
    || address.toLowerCase().startsWith('::ffff:')) {
    return false;
  }
  const family = net.isIP(address);
  if (!family) {
    return false;
  }
  const addressType = family === 4 ? 'ipv4' : 'ipv6';
  if (family === 6 && !GLOBAL_DOWNLOAD_IPV6_ADDRESSES.check(address, addressType)) {
    return false;
  }
  return !BLOCKED_DOWNLOAD_ADDRESSES.check(address, addressType);
}

function createPublicLookup(lookupImpl = dns.lookup) {
  return (hostname, options, callback) => {
    lookupImpl(hostname, { all: true, verbatim: true }, (error, records) => {
      if (error) {
        callback(error);
        return;
      }
      const addresses = Array.isArray(records) ? records : [];
      if (addresses.length === 0
        || addresses.some((record) => !record || !isPublicDownloadAddress(record.address))) {
        callback(createDownloadPolicyError(
          `Embedded Ollama download host did not resolve exclusively to public addresses: ${hostname}`
        ));
        return;
      }
      if (options && options.all) {
        callback(null, addresses);
        return;
      }
      callback(null, addresses[0].address, addresses[0].family);
    });
  };
}

function openDownload(url, {
  httpsImpl = https,
  lookupImpl = dns.lookup,
  redirectCount = 0,
  timeoutMs = DOWNLOAD_TIMEOUT_MS,
  deadlineAt = Date.now() + DOWNLOAD_TOTAL_TIMEOUT_MS,
} = {}) {
  return new Promise((resolve, reject) => {
    let parsedUrl;
    try {
      parsedUrl = validateDownloadUrl(url);
    } catch (error) {
      reject(error);
      return;
    }
    const remainingMs = deadlineAt - Date.now();
    if (remainingMs <= 0) {
      reject(new Error('Embedded Ollama download exceeded its total time limit.'));
      return;
    }

    let settled = false;
    let deadlineTimer;
    const finish = (fn, value) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(deadlineTimer);
      fn(value);
    };
    const request = httpsImpl.get(parsedUrl, {
      headers: {
        Accept: 'application/octet-stream',
        'User-Agent': 'StockPulse-Desktop-Build',
      },
      lookup: createPublicLookup(lookupImpl),
    }, (response) => {
      const statusCode = response.statusCode || 0;
      if (statusCode >= 300 && statusCode < 400 && response.headers.location) {
        response.destroy();
        if (redirectCount >= MAX_REDIRECTS) {
          finish(reject, createDownloadPolicyError(
            'Too many redirects while downloading embedded Ollama.'
          ));
          return;
        }
        let redirectUrl;
        try {
          redirectUrl = validateDownloadUrl(new URL(response.headers.location, parsedUrl));
        } catch (error) {
          finish(reject, error);
          return;
        }
        clearTimeout(deadlineTimer);
        settled = true;
        openDownload(redirectUrl, {
          httpsImpl,
          lookupImpl,
          redirectCount: redirectCount + 1,
          timeoutMs,
          deadlineAt,
        }).then(resolve, reject);
        return;
      }
      if (statusCode !== 200) {
        response.destroy();
        finish(reject, new Error(`Embedded Ollama download failed with HTTP ${statusCode}.`));
        return;
      }
      finish(resolve, response);
    });
    request.setTimeout(timeoutMs, () => {
      request.destroy(new Error(
        `Embedded Ollama download was inactive for more than ${timeoutMs}ms.`
      ));
    });
    deadlineTimer = setTimeout(() => {
      request.destroy(new Error('Embedded Ollama download exceeded its total time limit.'));
    }, remainingMs);
    request.on('error', (error) => finish(reject, error));
  });
}

function createDownloadSizeError(expectedBytes, actualBytes) {
  const error = new Error(
    `Embedded Ollama response-size mismatch: expected ${expectedBytes}, received ${actualBytes}`
  );
  error.code = 'OLLAMA_SIZE_MISMATCH';
  return error;
}

async function downloadFile(url, destination, {
  expectedBytes,
  maxBytes = expectedBytes,
  totalTimeoutMs = DOWNLOAD_TOTAL_TIMEOUT_MS,
  ...openOptions
} = {}) {
  if (!Number.isSafeInteger(expectedBytes) || expectedBytes <= 0
    || !Number.isSafeInteger(maxBytes) || maxBytes < expectedBytes
    || !Number.isSafeInteger(totalTimeoutMs) || totalTimeoutMs <= 0) {
    throw new Error('Embedded Ollama download bounds are invalid.');
  }
  const deadlineAt = Date.now() + totalTimeoutMs;
  let response;
  let receivedBytes = 0;
  const totalTimer = setTimeout(() => {
    if (response) {
      response.destroy(new Error('Embedded Ollama download exceeded its total time limit.'));
    }
  }, totalTimeoutMs);
  try {
    response = await openDownload(url, { ...openOptions, deadlineAt });
    const contentLengthHeader = response.headers['content-length'];
    if (contentLengthHeader !== undefined) {
      const contentLength = Number(contentLengthHeader);
      if (!Number.isSafeInteger(contentLength)
        || contentLength !== expectedBytes
        || contentLength > maxBytes) {
        response.destroy();
        throw createDownloadSizeError(expectedBytes, contentLengthHeader);
      }
    }
    const limiter = new Transform({
      transform(chunk, encoding, callback) {
        receivedBytes += Buffer.isBuffer(chunk) ? chunk.length : Buffer.byteLength(chunk, encoding);
        if (receivedBytes > maxBytes) {
          callback(createDownloadSizeError(expectedBytes, receivedBytes));
          return;
        }
        callback(null, chunk);
      },
      flush(callback) {
        if (receivedBytes !== expectedBytes) {
          callback(createDownloadSizeError(expectedBytes, receivedBytes));
          return;
        }
        callback();
      },
    });
    await pipeline(response, limiter, fs.createWriteStream(destination, { flags: 'wx' }));
  } finally {
    clearTimeout(totalTimer);
  }
}

async function ensureVerifiedArchive({
  artifact,
  cacheDir,
  archiveOverride = '',
  downloadImpl = downloadFile,
  downloadAttempts = 3,
  retryDelayMs = 1000,
}) {
  if (archiveOverride) {
    const overridePath = path.resolve(archiveOverride);
    assertFileSize(overridePath, artifact.sizeBytes);
    await assertFileChecksum(overridePath, artifact.sha256);
    return overridePath;
  }

  fs.mkdirSync(cacheDir, { recursive: true });
  const archivePath = path.join(cacheDir, artifact.fileName);
  if (fs.existsSync(archivePath)) {
    assertFileSize(archivePath, artifact.sizeBytes);
    await assertFileChecksum(archivePath, artifact.sha256);
    console.log(`Using verified embedded Ollama cache: ${archivePath}`);
    return archivePath;
  }

  const temporaryPath = `${archivePath}.part-${process.pid}`;
  console.log(`Downloading embedded Ollama from ${artifact.downloadUrl}`);
  for (let attempt = 1; attempt <= downloadAttempts; attempt += 1) {
    fs.rmSync(temporaryPath, { force: true });
    try {
      await downloadImpl(artifact.downloadUrl, temporaryPath, {
        expectedBytes: artifact.sizeBytes,
        maxBytes: artifact.sizeBytes,
        totalTimeoutMs: DOWNLOAD_TOTAL_TIMEOUT_MS,
      });
      assertFileSize(temporaryPath, artifact.sizeBytes);
      await assertFileChecksum(temporaryPath, artifact.sha256);
      fs.renameSync(temporaryPath, archivePath);
      return archivePath;
    } catch (error) {
      fs.rmSync(temporaryPath, { force: true });
      if (error && [
        'OLLAMA_CHECKSUM_MISMATCH',
        'OLLAMA_DOWNLOAD_POLICY',
        'OLLAMA_SIZE_MISMATCH',
      ].includes(error.code)) {
        throw error;
      }
      if (attempt === downloadAttempts) {
        throw error;
      }
      console.warn(`Embedded Ollama download attempt ${attempt} failed; retrying.`);
      await new Promise((resolve) => setTimeout(resolve, retryDelayMs * attempt));
    }
  }
  throw new Error('Embedded Ollama download did not complete.');
}

function resolveContainedPath(rootDir, relativePath) {
  if (!relativePath || path.isAbsolute(relativePath)) {
    throw new Error(`Invalid embedded Ollama resource path: ${relativePath}`);
  }
  const root = path.resolve(rootDir);
  const candidate = path.resolve(root, relativePath);
  if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) {
    throw new Error(`Embedded Ollama resource escapes its root: ${relativePath}`);
  }
  return candidate;
}

function validatePreparedRuntime(rootDir, artifact, platform, fsImpl = fs) {
  for (const relativePath of artifact.requiredPaths) {
    const resourcePath = resolveContainedPath(rootDir, relativePath);
    const stats = fsImpl.statSync(resourcePath);
    if (!stats.isFile()) {
      throw new Error(`Embedded Ollama resource is not a file: ${relativePath}`);
    }
  }
  const binaryPath = resolveContainedPath(rootDir, artifact.binaryPath);
  if (platform === 'darwin') {
    fsImpl.accessSync(binaryPath, fs.constants.X_OK);
  }
  return binaryPath;
}

function extractArchive({ archivePath, artifact, stagingDir, platform, spawnSyncImpl = spawnSync }) {
  const command = platform === 'win32' ? 'tar.exe' : 'tar';
  const args = artifact.archiveType === 'tgz'
    ? ['-xzf', archivePath, '-C', stagingDir]
    : ['-xf', archivePath, '-C', stagingDir];
  const result = spawnSyncImpl(command, args, {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(
      `Failed to extract embedded Ollama with ${command}: `
      + String(result.stderr || result.stdout || `exit ${result.status}`).trim()
    );
  }
}

function buildPreparedManifest(config, artifact, platform, arch, fileSha256) {
  return {
    schemaVersion: 2,
    runtime: config.runtime,
    version: config.version,
    platform,
    architecture: arch,
    supportedArchitectures: artifact.architectures,
    binaryPath: artifact.binaryPath,
    requiredPaths: artifact.requiredPaths,
    fileSha256,
    archive: {
      fileName: artifact.fileName,
      sizeBytes: artifact.sizeBytes,
      sha256: artifact.sha256,
    },
  };
}

async function assertPreparedRuntimeMatchesManifest(
  rootDir,
  manifest,
  artifact,
  platform,
  arch,
  fsImpl = fs
) {
  const runtimeFilePaths = collectRuntimeFilePaths(rootDir, fsImpl);
  if (manifest.schemaVersion !== 2
    || manifest.runtime !== 'ollama'
    || manifest.platform !== platform
    || manifest.architecture !== arch
    || manifest.binaryPath !== artifact.binaryPath
    || JSON.stringify(manifest.supportedArchitectures) !== JSON.stringify(artifact.architectures)
    || JSON.stringify(manifest.requiredPaths) !== JSON.stringify(artifact.requiredPaths)
    || !manifest.archive
    || manifest.archive.fileName !== artifact.fileName
    || manifest.archive.sizeBytes !== artifact.sizeBytes
    || manifest.archive.sha256 !== artifact.sha256
    || !manifest.fileSha256
    || typeof manifest.fileSha256 !== 'object'
    || Array.isArray(manifest.fileSha256)
    || JSON.stringify(Object.keys(manifest.fileSha256).sort())
      !== JSON.stringify(runtimeFilePaths)
    || artifact.requiredPaths.some((relativePath) => !runtimeFilePaths.includes(relativePath))) {
    throw new Error(`Embedded Ollama prepared manifest is invalid for ${platform}/${arch}.`);
  }

  validatePreparedRuntime(rootDir, artifact, platform, fsImpl);
  for (const relativePath of runtimeFilePaths) {
    const expectedSha256 = manifest.fileSha256[relativePath];
    if (!/^[a-f0-9]{64}$/.test(String(expectedSha256 || ''))) {
      throw new Error(`Embedded Ollama runtime-file checksum is invalid: ${relativePath}`);
    }
    await assertFileChecksum(resolveContainedPath(rootDir, relativePath), expectedSha256, fsImpl);
  }
  return true;
}

async function verifyPreparedOllama({
  platform = process.platform,
  arch = process.arch,
  configPath = CONFIG_PATH,
  outputDir = DEFAULT_OUTPUT_DIR,
  fsImpl = fs,
} = {}) {
  const config = readRuntimeConfig(configPath);
  const artifact = selectArtifact(config, platform, arch);
  const manifestPath = path.join(outputDir, PREPARED_MANIFEST_FILE);
  const manifest = JSON.parse(fsImpl.readFileSync(manifestPath, 'utf-8'));
  if (manifest.version !== config.version) {
    throw new Error(`Embedded Ollama prepared version does not match ${config.version}.`);
  }
  await assertPreparedRuntimeMatchesManifest(
    outputDir,
    manifest,
    artifact,
    platform,
    arch,
    fsImpl
  );
  return manifest;
}

async function preparedRuntimeIsCurrent(outputDir, expectedManifest, artifact, platform, fsImpl = fs) {
  try {
    const manifestPath = path.join(outputDir, PREPARED_MANIFEST_FILE);
    const actualManifest = JSON.parse(fsImpl.readFileSync(manifestPath, 'utf-8'));
    if (JSON.stringify(actualManifest) !== JSON.stringify(expectedManifest)) {
      return false;
    }
    await assertPreparedRuntimeMatchesManifest(
      outputDir,
      actualManifest,
      artifact,
      platform,
      actualManifest.architecture,
      fsImpl
    );
    return true;
  } catch (_error) {
    return false;
  }
}

async function prepareEmbeddedOllama({
  platform = process.platform,
  arch = process.arch,
  configPath = CONFIG_PATH,
  outputDir = DEFAULT_OUTPUT_DIR,
  cacheDir = '',
  archiveOverride = '',
  downloadImpl = downloadFile,
  spawnSyncImpl = spawnSync,
} = {}) {
  const config = readRuntimeConfig(configPath);
  const artifact = selectArtifact(config, platform, arch);
  const resolvedCacheDir = cacheDir || path.join(DESKTOP_ROOT, '.ollama-cache', config.version);
  const archivePath = await ensureVerifiedArchive({
    artifact,
    cacheDir: resolvedCacheDir,
    archiveOverride,
    downloadImpl,
  });
  let preparedManifest;
  const stagingDir = `${outputDir}.tmp-${process.pid}-${Date.now()}`;
  fs.rmSync(stagingDir, { recursive: true, force: true });
  fs.mkdirSync(stagingDir, { recursive: true });
  try {
    extractArchive({ archivePath, artifact, stagingDir, platform, spawnSyncImpl });
    validatePreparedRuntime(stagingDir, artifact, platform);
    const runtimeFilePaths = collectRuntimeFilePaths(stagingDir);
    const fileSha256 = await calculateRuntimeFileSha256(stagingDir, runtimeFilePaths);
    preparedManifest = buildPreparedManifest(
      config,
      artifact,
      platform,
      arch,
      fileSha256
    );
    fs.writeFileSync(
      path.join(stagingDir, PREPARED_MANIFEST_FILE),
      `${JSON.stringify(preparedManifest, null, 2)}\n`,
      'utf-8'
    );
    fs.rmSync(outputDir, { recursive: true, force: true });
    fs.mkdirSync(path.dirname(outputDir), { recursive: true });
    fs.renameSync(stagingDir, outputDir);
  } catch (error) {
    fs.rmSync(stagingDir, { recursive: true, force: true });
    throw error;
  }
  console.log(`Prepared embedded Ollama ${config.version} for ${platform}/${arch}.`);
  return { archivePath, outputDir, manifest: preparedManifest };
}

function parseArguments(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (!['--platform', '--arch', '--cache-dir', '--output-dir', '--archive'].includes(argument)) {
      throw new Error(`Unknown argument: ${argument}`);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith('--')) {
      throw new Error(`Missing value for ${argument}`);
    }
    index += 1;
    const key = {
      '--platform': 'platform',
      '--arch': 'arch',
      '--cache-dir': 'cacheDir',
      '--output-dir': 'outputDir',
      '--archive': 'archiveOverride',
    }[argument];
    options[key] = value;
  }
  return options;
}

if (require.main === module) {
  prepareEmbeddedOllama(parseArguments(process.argv.slice(2))).catch((error) => {
    console.error(`Failed to prepare embedded Ollama: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  });
}

module.exports = {
  ALLOWED_DOWNLOAD_HOSTS,
  DOWNLOAD_TOTAL_TIMEOUT_MS,
  PREPARED_MANIFEST_FILE,
  assertFileChecksum,
  assertFileSize,
  assertPreparedRuntimeMatchesManifest,
  buildPreparedManifest,
  calculateFileSha256,
  calculateRuntimeFileSha256,
  collectRuntimeFilePaths,
  createPublicLookup,
  downloadFile,
  ensureVerifiedArchive,
  isPublicDownloadAddress,
  openDownload,
  parseArguments,
  prepareEmbeddedOllama,
  preparedRuntimeIsCurrent,
  readRuntimeConfig,
  resolveContainedPath,
  selectArtifact,
  validatePreparedRuntime,
  validateDownloadUrl,
  verifyPreparedOllama,
};
