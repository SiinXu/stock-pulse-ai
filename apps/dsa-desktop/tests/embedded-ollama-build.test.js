const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const test = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const prepareScript = require('../../../scripts/prepare-embedded-ollama');

function createTemporaryDirectory(t, prefix) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

test('embedded Ollama manifest pins official artifacts for every desktop target', () => {
  const config = prepareScript.readRuntimeConfig();
  const darwinArm64 = prepareScript.selectArtifact(config, 'darwin', 'arm64');
  const darwinX64 = prepareScript.selectArtifact(config, 'darwin', 'x64');
  const windowsX64 = prepareScript.selectArtifact(config, 'win32', 'x64');

  assert.equal(config.version, 'v0.32.3');
  assert.equal(darwinArm64.fileName, 'ollama-darwin.tgz');
  assert.equal(darwinArm64.sha256, darwinX64.sha256);
  assert.equal(windowsX64.fileName, 'ollama-windows-amd64.zip');
  for (const artifact of [darwinArm64, darwinX64, windowsX64]) {
    assert.match(artifact.downloadUrl, /^https:\/\/github\.com\/ollama\/ollama\/releases\/download\/v0\.32\.3\//);
    assert.match(artifact.sha256, /^[a-f0-9]{64}$/);
  }
  assert.throws(
    () => prepareScript.selectArtifact(config, 'win32', 'arm64'),
    /not configured/
  );
});

test('embedded Ollama checksum verification reads the real artifact path', async (t) => {
  const tmpDir = createTemporaryDirectory(t, 'dsa-ollama-sha-');
  const archivePath = path.join(tmpDir, 'runtime.tgz');
  const content = Buffer.from('deterministic embedded Ollama fixture');
  fs.writeFileSync(archivePath, content);
  const expected = crypto.createHash('sha256').update(content).digest('hex');

  assert.equal(await prepareScript.assertFileChecksum(archivePath, expected), expected);
  await assert.rejects(
    prepareScript.assertFileChecksum(archivePath, '0'.repeat(64)),
    /checksum mismatch/
  );
});

test('a corrupt cached Ollama archive fails before any replacement download', async (t) => {
  const tmpDir = createTemporaryDirectory(t, 'dsa-ollama-cache-');
  const config = prepareScript.readRuntimeConfig();
  const artifact = prepareScript.selectArtifact(config, 'darwin', 'arm64');
  fs.writeFileSync(path.join(tmpDir, artifact.fileName), 'corrupt');
  let downloadCalled = false;

  await assert.rejects(
    prepareScript.ensureVerifiedArchive({
      artifact,
      cacheDir: tmpDir,
      downloadImpl: async () => {
        downloadCalled = true;
      },
    }),
    /checksum mismatch/
  );
  assert.equal(downloadCalled, false);
});

test('a downloaded checksum mismatch fails without retrying the payload', async (t) => {
  const tmpDir = createTemporaryDirectory(t, 'dsa-ollama-download-sha-');
  let attempts = 0;
  const artifact = {
    fileName: 'runtime.tgz',
    downloadUrl: 'https://example.invalid/runtime.tgz',
    sha256: '0'.repeat(64),
  };

  await assert.rejects(
    prepareScript.ensureVerifiedArchive({
      artifact,
      cacheDir: tmpDir,
      retryDelayMs: 0,
      downloadImpl: async (_url, destination) => {
        attempts += 1;
        fs.writeFileSync(destination, 'unexpected payload');
      },
    }),
    /checksum mismatch/
  );
  assert.equal(attempts, 1);
});

test('preparation verifies an archive before atomically publishing its runtime', async (t) => {
  const tmpDir = createTemporaryDirectory(t, 'dsa-ollama-prepare-');
  const archivePath = path.join(tmpDir, 'fixture.tgz');
  const archiveContent = Buffer.from('verified archive bytes');
  fs.writeFileSync(archivePath, archiveContent);
  const sha256 = crypto.createHash('sha256').update(archiveContent).digest('hex');
  const configPath = path.join(tmpDir, 'ollama-runtime.json');
  fs.writeFileSync(configPath, JSON.stringify({
    schemaVersion: 1,
    runtime: 'ollama',
    version: 'v1.2.3',
    releaseBaseUrl: 'https://github.com/ollama/ollama/releases/download/v1.2.3',
    checksumSourceUrl: 'https://github.com/ollama/ollama/releases/download/v1.2.3/sha256sum.txt',
    artifacts: {
      darwin: {
        architectures: ['arm64', 'x64'],
        fileName: 'fixture.tgz',
        archiveType: 'tgz',
        sha256,
        binaryPath: 'ollama',
        requiredPaths: ['ollama', 'llama-server'],
      },
    },
  }));
  const outputDir = path.join(tmpDir, 'prepared', 'ollama');
  const spawnRecords = [];

  const result = await prepareScript.prepareEmbeddedOllama({
    platform: 'darwin',
    arch: 'arm64',
    configPath,
    outputDir,
    archiveOverride: archivePath,
    spawnSyncImpl: (command, args) => {
      spawnRecords.push({ command, args: [...args] });
      const stagingDir = args[args.indexOf('-C') + 1];
      for (const fileName of ['ollama', 'llama-server']) {
        const filePath = path.join(stagingDir, fileName);
        fs.writeFileSync(filePath, fileName);
        fs.chmodSync(filePath, 0o755);
      }
      return { status: 0, stdout: '', stderr: '' };
    },
  });

  assert.equal(spawnRecords.length, 1);
  assert.equal(spawnRecords[0].command, 'tar');
  assert.equal(result.outputDir, outputDir);
  assert.equal(fs.statSync(path.join(outputDir, 'ollama')).isFile(), true);
  assert.deepEqual(
    JSON.parse(fs.readFileSync(path.join(outputDir, 'runtime-manifest.json'), 'utf-8')),
    result.manifest
  );
  assert.equal(
    prepareScript.preparedRuntimeIsCurrent(
      outputDir,
      result.manifest,
      prepareScript.selectArtifact(prepareScript.readRuntimeConfig(configPath), 'darwin', 'arm64'),
      'darwin'
    ),
    true
  );
});

test('embedded runtime paths cannot escape the prepared resource root', () => {
  assert.throws(
    () => prepareScript.resolveContainedPath('/tmp/runtime', '../outside'),
    /escapes its root/
  );
  assert.throws(
    () => prepareScript.resolveContainedPath('/tmp/runtime', '/absolute'),
    /Invalid embedded Ollama resource path/
  );
});
