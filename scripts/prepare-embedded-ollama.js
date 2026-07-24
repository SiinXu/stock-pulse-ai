#!/usr/bin/env node

const crypto = require('node:crypto');
const fs = require('node:fs');
const https = require('node:https');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { pipeline } = require('node:stream/promises');

const REPOSITORY_ROOT = path.resolve(__dirname, '..');
const DESKTOP_ROOT = path.join(REPOSITORY_ROOT, 'apps', 'dsa-desktop');
const CONFIG_PATH = path.join(DESKTOP_ROOT, 'ollama-runtime.json');
const DEFAULT_OUTPUT_DIR = path.join(DESKTOP_ROOT, 'vendor', 'ollama');
const PREPARED_MANIFEST_FILE = 'runtime-manifest.json';
const DOWNLOAD_TIMEOUT_MS = 60_000;
const MAX_REDIRECTS = 5;

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

function openDownload(url, {
  httpsImpl = https,
  redirectCount = 0,
  timeoutMs = DOWNLOAD_TIMEOUT_MS,
} = {}) {
  return new Promise((resolve, reject) => {
    let parsedUrl;
    try {
      parsedUrl = new URL(url);
    } catch (error) {
      reject(error);
      return;
    }
    if (parsedUrl.protocol !== 'https:') {
      reject(new Error(`Refusing non-HTTPS embedded Ollama download: ${parsedUrl.protocol}`));
      return;
    }

    const request = httpsImpl.get(parsedUrl, {
      headers: {
        Accept: 'application/octet-stream',
        'User-Agent': 'StockPulse-Desktop-Build',
      },
    }, (response) => {
      const statusCode = response.statusCode || 0;
      if (statusCode >= 300 && statusCode < 400 && response.headers.location) {
        response.resume();
        if (redirectCount >= MAX_REDIRECTS) {
          reject(new Error('Too many redirects while downloading embedded Ollama.'));
          return;
        }
        const redirectUrl = new URL(response.headers.location, parsedUrl).toString();
        openDownload(redirectUrl, {
          httpsImpl,
          redirectCount: redirectCount + 1,
          timeoutMs,
        }).then(resolve, reject);
        return;
      }
      if (statusCode !== 200) {
        response.resume();
        reject(new Error(`Embedded Ollama download failed with HTTP ${statusCode}.`));
        return;
      }
      resolve(response);
    });
    request.setTimeout(timeoutMs, () => {
      request.destroy(new Error(`Embedded Ollama download timed out after ${timeoutMs}ms.`));
    });
    request.on('error', reject);
  });
}

async function downloadFile(url, destination, options = {}) {
  const response = await openDownload(url, options);
  await pipeline(response, fs.createWriteStream(destination, { flags: 'wx' }));
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
    await assertFileChecksum(overridePath, artifact.sha256);
    return overridePath;
  }

  fs.mkdirSync(cacheDir, { recursive: true });
  const archivePath = path.join(cacheDir, artifact.fileName);
  if (fs.existsSync(archivePath)) {
    await assertFileChecksum(archivePath, artifact.sha256);
    console.log(`Using verified embedded Ollama cache: ${archivePath}`);
    return archivePath;
  }

  const temporaryPath = `${archivePath}.part-${process.pid}`;
  console.log(`Downloading embedded Ollama from ${artifact.downloadUrl}`);
  for (let attempt = 1; attempt <= downloadAttempts; attempt += 1) {
    fs.rmSync(temporaryPath, { force: true });
    try {
      await downloadImpl(artifact.downloadUrl, temporaryPath);
      await assertFileChecksum(temporaryPath, artifact.sha256);
      fs.renameSync(temporaryPath, archivePath);
      return archivePath;
    } catch (error) {
      fs.rmSync(temporaryPath, { force: true });
      if (error && error.code === 'OLLAMA_CHECKSUM_MISMATCH') {
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

function buildPreparedManifest(config, artifact, platform, arch) {
  return {
    schemaVersion: 1,
    runtime: config.runtime,
    version: config.version,
    platform,
    architecture: arch,
    supportedArchitectures: artifact.architectures,
    binaryPath: artifact.binaryPath,
    requiredPaths: artifact.requiredPaths,
    archive: {
      fileName: artifact.fileName,
      sha256: artifact.sha256,
    },
  };
}

function preparedRuntimeIsCurrent(outputDir, expectedManifest, artifact, platform) {
  try {
    const manifestPath = path.join(outputDir, PREPARED_MANIFEST_FILE);
    const actualManifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
    if (JSON.stringify(actualManifest) !== JSON.stringify(expectedManifest)) {
      return false;
    }
    validatePreparedRuntime(outputDir, artifact, platform);
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
  const preparedManifest = buildPreparedManifest(config, artifact, platform, arch);
  const stagingDir = `${outputDir}.tmp-${process.pid}-${Date.now()}`;
  fs.rmSync(stagingDir, { recursive: true, force: true });
  fs.mkdirSync(stagingDir, { recursive: true });
  try {
    extractArchive({ archivePath, artifact, stagingDir, platform, spawnSyncImpl });
    validatePreparedRuntime(stagingDir, artifact, platform);
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
  PREPARED_MANIFEST_FILE,
  assertFileChecksum,
  buildPreparedManifest,
  calculateFileSha256,
  ensureVerifiedArchive,
  parseArguments,
  prepareEmbeddedOllama,
  preparedRuntimeIsCurrent,
  readRuntimeConfig,
  resolveContainedPath,
  selectArtifact,
  validatePreparedRuntime,
};
