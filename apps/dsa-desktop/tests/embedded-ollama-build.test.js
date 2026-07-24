const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');
const test = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { PassThrough, Readable } = require('node:stream');

const prepareScript = require('../../../scripts/prepare-embedded-ollama');

function createTemporaryDirectory(t, prefix) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

function createHttpsFixture(responses) {
  const calls = [];
  return {
    calls,
    get(url, options, callback) {
      calls.push({ url: url.toString(), options });
      const request = new EventEmitter();
      request.setTimeout = () => request;
      request.destroy = (error = new Error('request destroyed')) => {
        setImmediate(() => request.emit('error', error));
      };
      const responseSpec = responses.shift();
      if (responseSpec !== 'never') {
        setImmediate(() => {
          const response = responseSpec.stream || Readable.from(responseSpec.chunks || []);
          response.statusCode = responseSpec.statusCode;
          response.headers = responseSpec.headers || {};
          callback(response);
        });
      }
      return request;
    },
  };
}

test('embedded Ollama manifest pins official artifacts for every desktop target', () => {
  const config = prepareScript.readRuntimeConfig();
  const darwinArm64 = prepareScript.selectArtifact(config, 'darwin', 'arm64');
  const darwinX64 = prepareScript.selectArtifact(config, 'darwin', 'x64');
  const windowsX64 = prepareScript.selectArtifact(config, 'win32', 'x64');

  assert.equal(config.version, 'v0.32.3');
  assert.equal(config.goRuntime.version, 'go1.26.0');
  assert.equal(config.goRuntime.modules.length, 70);
  assert.equal(darwinArm64.fileName, 'ollama-darwin.tgz');
  assert.equal(darwinArm64.sizeBytes, 145790989);
  assert.equal(darwinArm64.sha256, darwinX64.sha256);
  assert.equal(windowsX64.fileName, 'ollama-windows-amd64.zip');
  assert.equal(windowsX64.sizeBytes, 1457806156);
  for (const artifact of [darwinArm64, darwinX64, windowsX64]) {
    assert.match(artifact.downloadUrl, /^https:\/\/github\.com\/ollama\/ollama\/releases\/download\/v0\.32\.3\//);
    assert.match(artifact.sha256, /^[a-f0-9]{64}$/);
  }
  assert.throws(
    () => prepareScript.selectArtifact(config, 'win32', 'arm64'),
    /not configured/
  );
});

test('third-party notices cover native and linked Go components in both Ollama archives', () => {
  const repositoryRoot = path.resolve(__dirname, '..', '..', '..');
  const notices = fs.readFileSync(path.join(repositoryRoot, 'THIRD_PARTY_NOTICES'), 'utf-8');
  for (const component of [
    'Ollama',
    'llama.cpp and ggml',
    'MLX, including JACCL',
    'pocketfft',
    'Metal-cpp 26',
    'LLVM runtime libraries',
    'mingw-w64 runtime',
    'NVIDIA CUDA Runtime and cuBLAS',
    'Microsoft Visual C++ runtime libraries',
  ]) {
    assert.ok(notices.includes(component), `missing notice for ${component}`);
  }
  assert.match(notices, /Apache License\s+Version 2\.0, January 2004/);
  assert.match(notices, /LLVM Exceptions to the Apache 2\.0 License/);
  assert.match(notices, /Copyright 2009 The Go Authors/);
  assert.match(notices, /Apache Arrow\s+Copyright 2016-2019 The Apache Software Foundation/);
  for (const module of prepareScript.readRuntimeConfig().goRuntime.modules) {
    assert.ok(
      notices.includes(`${module.path} ${module.version}`),
      `missing linked Go module notice for ${module.path}@${module.version}`
    );
  }
});

test('embedded Ollama downloads reject unapproved destinations and private DNS results', async () => {
  for (const url of [
    'http://github.com/ollama/ollama/releases/download/v0.32.3/runtime.tgz',
    'https://example.com/runtime.tgz',
    'https://user:password@github.com/runtime.tgz',
    'https://github.com:444/runtime.tgz',
  ]) {
    assert.throws(() => prepareScript.validateDownloadUrl(url), /Refusing embedded Ollama/);
  }

  for (const address of [
    '0.0.0.0',
    '10.0.0.1',
    '100.64.0.1',
    '127.0.0.1',
    '169.254.169.254',
    '172.16.0.1',
    '192.0.0.8',
    '192.0.2.1',
    '192.31.196.1',
    '192.52.193.1',
    '192.88.99.2',
    '192.168.0.1',
    '192.175.48.1',
    '198.18.0.1',
    '198.51.100.1',
    '203.0.113.1',
    '224.0.0.1',
    '240.0.0.1',
    '255.255.255.255',
    '::',
    '::1',
    '::ffff:127.0.0.1',
    '::ffff:8.8.8.8',
    '64:ff9b::7f00:1',
    '64:ff9b:1::1',
    '100::1',
    '100:0:0:1::1',
    '2001::1',
    '2001:2::1',
    '2001:10::1',
    '2001:db8::1',
    '2002:7f00:1::',
    '2620:4f:8000::1',
    '3fff::1',
    '5f00::1',
    'fc00::1',
    'fec0::1',
    'fe80::1',
    'ff00::1',
    '4000::1',
    '2001:4860:4860::8888%lo0',
    'not-an-ip',
    null,
    undefined,
  ]) {
    assert.equal(
      prepareScript.isPublicDownloadAddress(address),
      false,
      `expected a non-public address: ${address}`
    );
  }
  for (const address of [
    '8.8.8.8',
    '140.82.112.4',
    '2001:4860:4860::8888',
    '2606:4700:4700::1111',
  ]) {
    assert.equal(
      prepareScript.isPublicDownloadAddress(address),
      true,
      `expected a public address: ${address}`
    );
  }

  const privateLookup = prepareScript.createPublicLookup((_hostname, options, callback) => {
    assert.equal(options.all, true);
    callback(null, [{ address: '127.0.0.1', family: 4 }]);
  });
  await assert.rejects(
    new Promise((resolve, reject) => {
      privateLookup('github.com', {}, (error, address) => error ? reject(error) : resolve(address));
    }),
    /exclusively to public addresses/
  );

  const mixedLookup = prepareScript.createPublicLookup((_hostname, _options, callback) => {
    callback(null, [
      { address: '140.82.112.4', family: 4 },
      { address: '2001:2::1', family: 6 },
    ]);
  });
  await assert.rejects(
    new Promise((resolve, reject) => {
      mixedLookup('github.com', { all: true }, (error, addresses) => (
        error ? reject(error) : resolve(addresses)
      ));
    }),
    /exclusively to public addresses/
  );

  const publicLookup = prepareScript.createPublicLookup((_hostname, _options, callback) => {
    callback(null, [{ address: '140.82.112.4', family: 4 }]);
  });
  assert.equal(
    await new Promise((resolve, reject) => {
      publicLookup('github.com', {}, (error, address) => error ? reject(error) : resolve(address));
    }),
    '140.82.112.4'
  );
  assert.deepEqual(
    await new Promise((resolve, reject) => {
      publicLookup('github.com', { all: true }, (error, addresses) => (
        error ? reject(error) : resolve(addresses)
      ));
    }),
    [{ address: '140.82.112.4', family: 4 }]
  );
});

test('embedded Ollama redirects remain on approved release hosts', async () => {
  const httpsImpl = createHttpsFixture([{
    statusCode: 302,
    headers: { location: 'https://example.com/untrusted-runtime.tgz' },
  }]);

  await assert.rejects(
    prepareScript.openDownload(
      'https://github.com/ollama/ollama/releases/download/v0.32.3/runtime.tgz',
      { httpsImpl }
    ),
    /Refusing embedded Ollama download destination/
  );
  assert.equal(httpsImpl.calls.length, 1);
});

test('embedded Ollama downloads enforce exact streaming byte bounds', async (t) => {
  const tmpDir = createTemporaryDirectory(t, 'dsa-ollama-download-bounds-');
  const destination = path.join(tmpDir, 'runtime.tgz');
  const declaredOversized = createHttpsFixture([{
    statusCode: 200,
    headers: { 'content-length': '6' },
    chunks: [Buffer.from('abcdef')],
  }]);

  await assert.rejects(
    prepareScript.downloadFile(
      'https://github.com/ollama/ollama/releases/download/v0.32.3/runtime.tgz',
      destination,
      { expectedBytes: 5, maxBytes: 5, httpsImpl: declaredOversized }
    ),
    /response-size mismatch/
  );
  assert.equal(fs.existsSync(destination), false);

  const oversized = createHttpsFixture([{
    statusCode: 200,
    chunks: [Buffer.from('abcdef')],
  }]);

  await assert.rejects(
    prepareScript.downloadFile(
      'https://github.com/ollama/ollama/releases/download/v0.32.3/runtime.tgz',
      destination,
      { expectedBytes: 5, maxBytes: 5, httpsImpl: oversized }
    ),
    /response-size mismatch/
  );

  fs.rmSync(destination, { force: true });
  const exact = createHttpsFixture([{
    statusCode: 200,
    headers: { 'content-length': '5' },
    chunks: [Buffer.from('abc'), Buffer.from('de')],
  }]);
  await prepareScript.downloadFile(
    'https://github.com/ollama/ollama/releases/download/v0.32.3/runtime.tgz',
    destination,
    { expectedBytes: 5, maxBytes: 5, httpsImpl: exact }
  );
  assert.equal(fs.readFileSync(destination, 'utf-8'), 'abcde');
});

test('embedded Ollama downloads enforce a wall-clock deadline before response headers', async (t) => {
  const tmpDir = createTemporaryDirectory(t, 'dsa-ollama-download-deadline-');
  const httpsImpl = createHttpsFixture(['never']);

  await assert.rejects(
    prepareScript.downloadFile(
      'https://github.com/ollama/ollama/releases/download/v0.32.3/runtime.tgz',
      path.join(tmpDir, 'runtime.tgz'),
      { expectedBytes: 5, maxBytes: 5, totalTimeoutMs: 10, httpsImpl }
    ),
    /exceeded its total time limit/
  );
});

test('embedded Ollama downloads enforce a wall-clock deadline on a trickled response body', async (t) => {
  const tmpDir = createTemporaryDirectory(t, 'dsa-ollama-download-trickle-');
  const stream = new PassThrough();
  stream.write('a');
  const httpsImpl = createHttpsFixture([{
    statusCode: 200,
    stream,
  }]);

  await assert.rejects(
    prepareScript.downloadFile(
      'https://github.com/ollama/ollama/releases/download/v0.32.3/runtime.tgz',
      path.join(tmpDir, 'runtime.tgz'),
      { expectedBytes: 5, maxBytes: 5, totalTimeoutMs: 10, httpsImpl }
    ),
    /exceeded its total time limit/
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

test('a corrupt cached Ollama archive fails its pinned size before any replacement download', async (t) => {
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
    /byte-size mismatch/
  );
  assert.equal(downloadCalled, false);
});

test('a downloaded checksum mismatch fails without retrying the payload', async (t) => {
  const tmpDir = createTemporaryDirectory(t, 'dsa-ollama-download-sha-');
  let attempts = 0;
  const artifact = {
    fileName: 'runtime.tgz',
    downloadUrl: 'https://example.invalid/runtime.tgz',
    sizeBytes: Buffer.byteLength('unexpected payload'),
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
    goRuntime: {
      version: 'go1.2.3',
      modules: [{ path: 'example.com/runtime', version: 'v1.0.0' }],
    },
    artifacts: {
      darwin: {
        architectures: ['arm64', 'x64'],
        fileName: 'fixture.tgz',
        archiveType: 'tgz',
        sizeBytes: archiveContent.length,
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
      for (const fileName of ['ollama', 'llama-server', 'libllama-server-impl.dylib']) {
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
  assert.equal(result.manifest.schemaVersion, 2);
  assert.deepEqual(Object.keys(result.manifest.fileSha256).sort(), [
    'libllama-server-impl.dylib',
    'llama-server',
    'ollama',
  ]);
  assert.equal(
    await prepareScript.preparedRuntimeIsCurrent(
      outputDir,
      result.manifest,
      prepareScript.selectArtifact(prepareScript.readRuntimeConfig(configPath), 'darwin', 'arm64'),
      'darwin'
    ),
    true
  );

  fs.writeFileSync(path.join(outputDir, 'libllama-server-impl.dylib'), 'corrupt library bytes');
  assert.equal(
    await prepareScript.preparedRuntimeIsCurrent(
      outputDir,
      result.manifest,
      prepareScript.selectArtifact(prepareScript.readRuntimeConfig(configPath), 'darwin', 'arm64'),
      'darwin'
    ),
    false
  );
  await assert.rejects(
    prepareScript.verifyPreparedOllama({
      platform: 'darwin',
      arch: 'arm64',
      configPath,
      outputDir,
    }),
    /checksum mismatch/
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
