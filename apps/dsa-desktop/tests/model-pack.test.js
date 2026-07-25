const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Writable } = require('node:stream');
const test = require('node:test');
const yauzl = require('yauzl');

const {
  ModelPackError,
  MODEL_PACK_MAX_ENTRIES,
  importModelPack,
  inspectModelPack,
  parseModelPackManifest,
  parseModelPackModelfile,
  spawnOllamaCreate,
} = require('../model-pack.js');

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function writePack(
  root,
  {
    modelfileText = 'FROM ./weights.gguf\n',
    tamper = false,
    modelId = 'stockpulse/desktop-test:q4',
    displayName = 'Desktop Test',
    ggufPayload = Buffer.from('GGUF-desktop-test'),
  } = {}
) {
  fs.mkdirSync(root, { recursive: true });
  const files = {
    'weights.gguf': Buffer.from(ggufPayload),
    Modelfile: Buffer.from(modelfileText),
    LICENSE: Buffer.from('Desktop test license\n'),
  };
  for (const [name, payload] of Object.entries(files)) {
    fs.writeFileSync(path.join(root, name), payload);
  }
  const manifest = {
    format_version: 1,
    model_id: modelId,
    display_name: displayName,
    gguf_file: 'weights.gguf',
    modelfile: 'Modelfile',
    license: { id: 'LicenseRef-Test', file: 'LICENSE' },
    minimum_memory_gb: 8,
    files: [
      {
        path: 'weights.gguf',
        role: 'gguf',
        sha256: sha256(files['weights.gguf']),
        size_bytes: files['weights.gguf'].length,
      },
      {
        path: 'Modelfile',
        role: 'modelfile',
        sha256: sha256(files.Modelfile),
        size_bytes: files.Modelfile.length,
      },
      {
        path: 'LICENSE',
        role: 'license',
        sha256: sha256(files.LICENSE),
        size_bytes: files.LICENSE.length,
      },
    ],
  };
  fs.writeFileSync(path.join(root, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  if (tamper) {
    fs.writeFileSync(path.join(root, 'weights.gguf'), Buffer.from('GGUF-evilxxx-test'));
  }
  return { root, manifest };
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function storedZip(entries) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  for (const [name, rawPayload] of entries) {
    const filename = Buffer.from(name);
    const payload = Buffer.from(rawPayload);
    const checksum = crc32(payload);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(0, 8);
    local.writeUInt16LE(0, 10);
    local.writeUInt16LE(0, 12);
    local.writeUInt32LE(checksum, 14);
    local.writeUInt32LE(payload.length, 18);
    local.writeUInt32LE(payload.length, 22);
    local.writeUInt16LE(filename.length, 26);
    local.writeUInt16LE(0, 28);
    localParts.push(local, filename, payload);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(0x0314, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8);
    central.writeUInt16LE(0, 10);
    central.writeUInt16LE(0, 12);
    central.writeUInt16LE(0, 14);
    central.writeUInt32LE(checksum, 16);
    central.writeUInt32LE(payload.length, 20);
    central.writeUInt32LE(payload.length, 24);
    central.writeUInt16LE(filename.length, 28);
    central.writeUInt16LE(0, 30);
    central.writeUInt16LE(0, 32);
    central.writeUInt16LE(0, 34);
    central.writeUInt16LE(0, 36);
    central.writeUInt32LE((0o100644 << 16) >>> 0, 38);
    central.writeUInt32LE(offset, 42);
    centralParts.push(central, filename);
    offset += local.length + filename.length + payload.length;
  }
  const centralPayload = Buffer.concat(centralParts);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralPayload.length, 12);
  end.writeUInt32LE(offset, 16);
  end.writeUInt16LE(0, 20);
  return Buffer.concat([...localParts, centralPayload, end]);
}

function archiveFromDirectory(root, archivePath, extras = []) {
  const names = ['manifest.json', 'weights.gguf', 'Modelfile', 'LICENSE'];
  const entries = names.map((name) => [name, fs.readFileSync(path.join(root, name))]);
  fs.writeFileSync(archivePath, storedZip([...entries, ...extras]));
  return archivePath;
}

function enoughDisk() {
  return Number.MAX_SAFE_INTEGER;
}

test('manifest and Modelfile parsers enforce the shared data-only contract', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-parser-'));
  const { root } = writePack(tempRoot);
  try {
    const manifest = parseModelPackManifest(fs.readFileSync(path.join(root, 'manifest.json')));
    const modelfile = parseModelPackModelfile(
      fs.readFileSync(path.join(root, 'Modelfile')),
      manifest.ggufFile
    );
    assert.equal(manifest.modelId, 'stockpulse/desktop-test:q4');
    assert.equal(modelfile.fromFile, 'weights.gguf');
    const portable = parseModelPackModelfile(
      Buffer.from(
        'FROM ./weights.gguf\n' +
        'PARAMETER temperature 0.2\n' +
        'PARAMETER num_ctx 8192\n' +
        'PARAMETER use_mmap true\n' +
        'PARAMETER stop "END"\n' +
        'PARAMETER stop "DONE"\n' +
        'PARAMETER stop "\\n"\n' +
        'SYSTEM """Portable system text"""\n'
      ),
      'weights.gguf'
    );
    assert.deepEqual(portable.parameters, {
      temperature: 0.2,
      num_ctx: 8192,
      use_mmap: true,
      stop: ['END', 'DONE', '\\n'],
    });
    assert.equal(portable.system, 'Portable system text');
    assert.deepEqual(
      parseModelPackModelfile(
        Buffer.from('FROM ./weights.gguf\nPARAMETER stop "END"\n'),
        'weights.gguf'
      ).parameters,
      { stop: ['END'] }
    );
    assert.deepEqual(
      parseModelPackModelfile(
        Buffer.from('FROM ./weights.gguf\nPARAMETER temperature 0.10000000001\n'),
        'weights.gguf'
      ).parameters,
      { temperature: 0.1 }
    );

    assert.throws(
      () => parseModelPackModelfile(
        Buffer.from('FROM ./weights.gguf\nADAPTER ./outside.gguf\n'),
        'weights.gguf'
      ),
      (error) => error instanceof ModelPackError && error.code === 'unsafe_modelfile'
    );
    for (const ambiguous of [
      'SYSTEM "quoted system text"',
      'TEMPLATE `quoted template text`',
      'PARAMETER temperature 0.1\nPARAMETER temperature 0.2',
      'FROM\t./weights.gguf',
      'SYSTEM \uFEFF"quoted system text"',
      'SYSTEM safe\u2028ADAPTER ./outside.gguf',
      'PARAMETER temperature NaN',
      'PARAMETER temperature Infinity',
      'PARAMETER temperature 1e999',
      'PARAMETER temperature 1e39',
      'PARAMETER temperature 1e-999',
      'PARAMETER num_ctx 9007199254740992',
      'PARAMETER num_ctx 9007199254740992.0',
      'PARAMETER num_ctx 1.0',
      'PARAMETER num_ctx 1e20',
      'PARAMETER num_ctx 99999999999999999999999999999999999999999999999999',
      'PARAMETER future_option 1',
      'PARAMETER TEMPERATURE 0.1',
      'PARAMETER use_mmap 1',
      'PARAMETER stop true',
      'ſYSTEM portable text',
      'PARAMETER Key value',
      'SYSTEM a\u200Db',
      'PARAMETER stop "a\u200Bb"',
      'TEMPLATE \u00A0template text\u00A0',
      'PARAMETER stop "a\\"b"',
      'PARAMETER stop "unclosed',
      'PARAMETER stop unquoted',
      'PARAMETER stop null',
      'PARAMETER stop [1]',
      'PARAMETER stop {"value":1}',
    ]) {
      assert.throws(
        () => parseModelPackModelfile(
          Buffer.from(`FROM ./weights.gguf\n${ambiguous}\n`),
          'weights.gguf'
        ),
        (error) => (
          error instanceof ModelPackError
          && error.code === 'unsafe_modelfile'
          && /rebuild the pack/i.test(error.userMessage)
        )
      );
    }
    const portableLines = parseModelPackModelfile(
      Buffer.from(
        'FROM ./weights.gguf\r\n' +
        'PARAMETER temperature 0.2\r\n' +
        'SYSTEM portable text\r\n'
      ),
      'weights.gguf'
    );
    assert.equal(portableLines.fromFile, 'weights.gguf');
    assert.deepEqual(portableLines.parameters, { temperature: 0.2 });
    assert.equal(portableLines.system, 'portable text');
    const tripleBlocks = parseModelPackModelfile(
      Buffer.from(
        'FROM ./weights.gguf\r\n' +
        'SYSTEM """\r\nsystem text\r\n"""\r\n' +
        'TEMPLATE """\r\ntemplate text\r\n"""\r\n'
      ),
      'weights.gguf'
    );
    assert.equal(tripleBlocks.system, '\nsystem text\n');
    assert.equal(tripleBlocks.template, '\ntemplate text\n');
    assert.throws(
      () => parseModelPackModelfile(
        Buffer.from('\uFEFFFROM ./weights.gguf\n'),
        'weights.gguf'
      ),
      (error) => error instanceof ModelPackError
        && error.code === 'unsafe_modelfile'
        && /byte-order mark/.test(error.userMessage)
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('manifest uses ASCII model ids and Unicode scalar display lengths', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-unicode-'));
  const { manifest } = writePack(tempRoot);
  try {
    manifest.display_name = '😀'.repeat(160);
    const parsed = parseModelPackManifest(Buffer.from(JSON.stringify(manifest)));
    assert.equal([...parsed.displayName].length, 160);

    manifest.model_id = 'K:q4';
    assert.throws(
      () => parseModelPackManifest(Buffer.from(JSON.stringify(manifest))),
      (error) => error instanceof ModelPackError
        && error.code === 'invalid_manifest'
        && /model_id/.test(error.userMessage)
    );

    manifest.model_id = 'stockpulse/portable:q4';
    manifest.display_name = '😀'.repeat(161);
    assert.throws(
      () => parseModelPackManifest(Buffer.from(JSON.stringify(manifest))),
      (error) => error instanceof ModelPackError
        && error.code === 'invalid_manifest'
        && /160 characters/.test(error.userMessage)
    );

    manifest.display_name = '\uD800';
    assert.throws(
      () => parseModelPackManifest(Buffer.from(JSON.stringify(manifest))),
      (error) => error instanceof ModelPackError
        && error.code === 'invalid_manifest'
        && /invalid Unicode/.test(error.userMessage)
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('manifest preserves only pinned Ollama model identities with explicit tags', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-model-id-'));
  const { manifest } = writePack(tempRoot);
  try {
    for (const modelId of [
      'finance',
      'acme.finance/model:q4',
      `${'n'.repeat(81)}/model:q4`,
      `namespace/${'m'.repeat(81)}:q4`,
      `namespace/model:${'t'.repeat(81)}`,
    ]) {
      manifest.model_id = modelId;
      assert.throws(
        () => parseModelPackManifest(Buffer.from(JSON.stringify(manifest))),
        (error) => error instanceof ModelPackError
          && error.code === 'invalid_manifest'
          && /model_id/.test(error.userMessage)
      );
    }

    manifest.model_id = `${'n'.repeat(80)}/${'m'.repeat(80)}:${'t'.repeat(80)}`;
    const parsed = parseModelPackManifest(Buffer.from(JSON.stringify(manifest)));
    assert.equal(parsed.modelId, manifest.model_id);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('manifest normalizes semantic JSON integers across transports', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-integers-'));
  const { manifest } = writePack(tempRoot);
  try {
    manifest.format_version = 1.0;
    manifest.minimum_memory_gb = 8.0;
    manifest.files = manifest.files.map((entry) => ({
      ...entry,
      size_bytes: Number(`${entry.size_bytes}.0`),
    }));
    const parsed = parseModelPackManifest(Buffer.from(JSON.stringify(manifest)));
    assert.equal(parsed.formatVersion, 1);
    assert.equal(parsed.minimumMemoryGb, 8);
    assert.ok(parsed.files.every((entry) => Number.isSafeInteger(entry.sizeBytes)));
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('manifest maps deeply nested JSON to a stable validation error', () => {
  const depth = 1200;
  const payload = Buffer.from(
    '{"format_version":1,"model_id":"stockpulse/deep:q4","display_name":' +
    '['.repeat(depth) +
    '"deep"' +
    ']'.repeat(depth) +
    ',"gguf_file":"weights.gguf","modelfile":"Modelfile",' +
    '"license":{"id":"LicenseRef-Test","file":"LICENSE"},' +
    '"minimum_memory_gb":8,"files":[]}'
  );

  assert.throws(
    () => parseModelPackManifest(payload),
    (error) => error instanceof ModelPackError && error.code === 'invalid_manifest'
  );
});

test('manifest rejects declared payloads above the shared 64 GiB limit', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-limit-'));
  const { root } = writePack(tempRoot);
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf-8'));
    manifest.files[0].size_bytes = (64 * 1024 * 1024 * 1024) + 1;
    assert.throws(
      () => parseModelPackManifest(Buffer.from(JSON.stringify(manifest))),
      (error) => error instanceof ModelPackError && error.code === 'model_pack_too_large'
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('manifest reserves its own filename for metadata', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-reserved-'));
  const { manifest } = writePack(tempRoot);
  manifest.modelfile = 'Manifest.json';
  manifest.files[1].path = 'Manifest.json';
  try {
    assert.throws(
      () => parseModelPackManifest(Buffer.from(JSON.stringify(manifest))),
      (error) => error instanceof ModelPackError
        && error.code === 'invalid_manifest'
        && /reserved manifest\.json/i.test(error.userMessage)
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('manifest rejects cross-platform unsafe payload filenames', () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-filenames-'));
  const { manifest } = writePack(tempRoot);
  try {
    for (const unsafeFilename of ['CON', 'nul.txt', 'LICENSE.']) {
      manifest.license.file = unsafeFilename;
      manifest.files.find((entry) => entry.role === 'license').path = unsafeFilename;
      assert.throws(
        () => parseModelPackManifest(Buffer.from(JSON.stringify(manifest))),
        (error) => error instanceof ModelPackError
          && error.code === 'invalid_manifest'
          && /root-level safe filename/.test(error.userMessage)
      );
    }
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('directory rejects oversized Modelfile and license roles before disk admission', async () => {
  for (const [role, limit, code] of [
    ['modelfile', 1024 * 1024, 'unsafe_modelfile'],
    ['license', 2 * 1024 * 1024, 'invalid_license_file'],
  ]) {
    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), `stockpulse-model-pack-${role}-limit-`));
    const { root } = writePack(tempRoot);
    const manifestPath = path.join(root, 'manifest.json');
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
    manifest.files.find((entry) => entry.role === role).size_bytes = limit + 1;
    fs.writeFileSync(manifestPath, JSON.stringify(manifest));
    let diskChecks = 0;
    try {
      await assert.rejects(
        inspectModelPack(root, {
          diskFreeProvider: () => {
            diskChecks += 1;
            return enoughDisk();
          },
        }),
        (error) => error instanceof ModelPackError && error.code === code
      );
      assert.equal(diskChecks, 0);
    } finally {
      fs.rmSync(tempRoot, { recursive: true, force: true });
    }
  }
});

test('directory inspection rejects an unbounded extra file inventory', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-count-'));
  const { root } = writePack(tempRoot);
  try {
    for (let index = 0; index < MODEL_PACK_MAX_ENTRIES; index += 1) {
      fs.writeFileSync(path.join(root, `extra-${String(index).padStart(3, '0')}`), 'x');
    }
    await assert.rejects(
      inspectModelPack(root, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError && error.code === 'invalid_archive'
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('directory inspection counts empty directories toward the entry limit', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-dir-count-'));
  const { root } = writePack(tempRoot);
  try {
    for (let index = 0; index < MODEL_PACK_MAX_ENTRIES; index += 1) {
      fs.mkdirSync(path.join(root, `empty-${String(index).padStart(3, '0')}`));
    }
    await assert.rejects(
      inspectModelPack(root, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError
        && error.code === 'invalid_archive'
        && /too many entries/i.test(error.userMessage)
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('directory inspection rejects actual size before disk admission or snapshot copy', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-size-first-'));
  const { root } = writePack(tempRoot);
  fs.writeFileSync(path.join(root, 'weights.gguf'), Buffer.concat([
    Buffer.from('GGUF'),
    Buffer.alloc(4 * 1024 * 1024, 120),
  ]));
  let diskChecks = 0;
  try {
    await assert.rejects(
      inspectModelPack(root, {
        diskFreeProvider: () => {
          diskChecks += 1;
          return enoughDisk();
        },
      }),
      (error) => error instanceof ModelPackError && error.code === 'size_mismatch'
    );
    assert.equal(diskChecks, 0);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('directory inspection rejects growth between preflight and bounded copy', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-grow-copy-'));
  const { root } = writePack(tempRoot);
  const ggufPath = path.join(root, 'weights.gguf');
  try {
    await assert.rejects(
      inspectModelPack(root, {
        diskFreeProvider: () => {
          fs.appendFileSync(ggufPath, Buffer.alloc(4 * 1024 * 1024, 120));
          return enoughDisk();
        },
      }),
      (error) => (
        error instanceof ModelPackError
        && error.code === 'size_mismatch'
        && /Stop modifying/.test(error.userMessage)
      )
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('directory manifest growth is read with a hard byte bound', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-grow-manifest-'));
  const { root } = writePack(tempRoot);
  const manifestPath = path.join(root, 'manifest.json');
  const maxManifestBytes = 1024 * 1024;
  const originalOpen = fs.promises.open;
  let largestRead = 0;
  fs.promises.open = async (...args) => {
    const handle = await originalOpen(...args);
    if (args[0] !== manifestPath || args[1] !== 'r') {
      return handle;
    }
    const originalStat = handle.stat.bind(handle);
    const originalRead = handle.read.bind(handle);
    let grew = false;
    handle.stat = async (...statArgs) => {
      const result = await originalStat(...statArgs);
      if (!grew) {
        fs.appendFileSync(manifestPath, Buffer.alloc(maxManifestBytes + 1, 120));
        grew = true;
      }
      return result;
    };
    handle.read = async (buffer, offset, length, position) => {
      largestRead = Math.max(largestRead, length);
      assert.ok(length <= maxManifestBytes + 1);
      return originalRead(buffer, offset, length, position);
    };
    return handle;
  };
  try {
    await assert.rejects(
      inspectModelPack(root, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError && error.code === 'invalid_manifest'
    );
    assert.equal(largestRead, maxManifestBytes + 1);
  } finally {
    fs.promises.open = originalOpen;
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('directory inspection verifies hashes and reports unlisted files', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-dir-'));
  const { root } = writePack(tempRoot);
  fs.writeFileSync(path.join(root, 'notes.txt'), 'extra');
  fs.mkdirSync(path.join(root, 'extras'));
  fs.writeFileSync(path.join(root, 'extras', 'details.txt'), 'nested extra');
  try {
    const inspected = await inspectModelPack(root, { diskFreeProvider: enoughDisk });
    assert.equal(inspected.manifest.modelId, 'stockpulse/desktop-test:q4');
    assert.deepEqual(inspected.warnings, [
      'Unexpected file is not part of the manifest: extras/details.txt',
      'Unexpected file is not part of the manifest: notes.txt',
    ]);
    assert.notEqual(inspected.root, root);
    assert.equal(fs.readFileSync(inspected.ggufPath, 'utf-8'), 'GGUF-desktop-test');
    const snapshotRoot = inspected.root;
    fs.writeFileSync(path.join(root, 'weights.gguf'), 'GGUF-replaced-after-validation');
    fs.writeFileSync(path.join(root, 'Modelfile'), 'FROM /private/outside.gguf\n');
    assert.equal(fs.readFileSync(inspected.ggufPath, 'utf-8'), 'GGUF-desktop-test');
    assert.match(fs.readFileSync(inspected.modelfilePath, 'utf-8'), /^FROM \.\/weights\.gguf/);
    await inspected.cleanup();
    assert.equal(fs.existsSync(snapshotRoot), false);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test(
  'directory inspection rejects nested symbolic links',
  { skip: process.platform === 'win32' },
  async () => {
    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-link-'));
    const { root } = writePack(tempRoot);
    fs.mkdirSync(path.join(root, 'extras'));
    fs.symlinkSync(path.join(root, 'LICENSE'), path.join(root, 'extras', 'license-link'));
    try {
      await assert.rejects(
        inspectModelPack(root, { diskFreeProvider: enoughDisk }),
        (error) => error instanceof ModelPackError && error.code === 'unsafe_package_entry'
      );
    } finally {
      fs.rmSync(tempRoot, { recursive: true, force: true });
    }
  }
);

test('directory inspection rejects tampering and insufficient disk before create', async () => {
  const tamperedRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-tamper-'));
  const diskRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-disk-'));
  writePack(tamperedRoot, { tamper: true });
  writePack(diskRoot);
  try {
    await assert.rejects(
      inspectModelPack(tamperedRoot, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError && error.code === 'hash_mismatch'
    );
    await assert.rejects(
      inspectModelPack(diskRoot, { diskFreeProvider: () => 0 }),
      (error) => (
        error instanceof ModelPackError
        && error.code === 'insufficient_disk_space'
        && /Free at least/.test(error.userMessage)
      )
    );
  } finally {
    fs.rmSync(tamperedRoot, { recursive: true, force: true });
    fs.rmSync(diskRoot, { recursive: true, force: true });
  }
});

test('archive inspection extracts declared files only and removes temporary data', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-zip-'));
  const source = path.join(tempRoot, 'source');
  writePack(source);
  const archive = archiveFromDirectory(
    source,
    path.join(tempRoot, 'test.modelpack'),
    [['notes.txt', Buffer.from('extra')]]
  );
  try {
    const inspected = await inspectModelPack(archive, { diskFreeProvider: enoughDisk });
    const extractedRoot = inspected.root;
    assert.notEqual(extractedRoot, source);
    assert.equal(fs.existsSync(path.join(extractedRoot, 'notes.txt')), false);
    assert.deepEqual(inspected.warnings, [
      'Unexpected file is not part of the manifest: notes.txt',
    ]);
    await inspected.cleanup();
    assert.equal(fs.existsSync(extractedRoot), false);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('archive inspection keeps one private snapshot across inventory and extraction', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-zip-snapshot-'));
  const alphaRoot = path.join(tempRoot, 'alpha');
  const bravoRoot = path.join(tempRoot, 'bravo');
  writePack(alphaRoot, {
    modelId: 'stockpulse/alpha:q4',
    displayName: 'Alpha',
    ggufPayload: Buffer.from('GGUF-alpha-snapshot'),
  });
  writePack(bravoRoot, {
    modelId: 'stockpulse/bravo:q4',
    displayName: 'Bravo',
    ggufPayload: Buffer.from('GGUF-bravo-replacement'),
  });
  const selected = archiveFromDirectory(alphaRoot, path.join(tempRoot, 'selected.modelpack'));
  const replacement = archiveFromDirectory(
    bravoRoot,
    path.join(tempRoot, 'replacement.modelpack'),
    [['unsafe-extra.txt', Buffer.from('replacement-only')]]
  );
  let diskChecks = 0;
  try {
    const inspected = await inspectModelPack(selected, {
      diskFreeProvider: () => {
        diskChecks += 1;
        if (diskChecks === 2) {
          fs.renameSync(replacement, selected);
        }
        return enoughDisk();
      },
    });
    assert.equal(diskChecks, 2);
    assert.equal(inspected.manifest.modelId, 'stockpulse/alpha:q4');
    assert.equal(fs.readFileSync(inspected.ggufPath, 'utf-8'), 'GGUF-alpha-snapshot');
    assert.equal(fs.existsSync(path.join(inspected.root, 'unsafe-extra.txt')), false);
    const privateRoot = path.dirname(inspected.root);
    await inspected.cleanup();
    assert.equal(fs.existsSync(privateRoot), false);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('archive inspection rejects traversal entries without writing outside', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-traversal-'));
  const source = path.join(tempRoot, 'source');
  writePack(source);
  const archive = archiveFromDirectory(
    source,
    path.join(tempRoot, 'unsafe.modelpack'),
    [['../outside.txt', Buffer.from('escape')]]
  );
  try {
    await assert.rejects(
      inspectModelPack(archive, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError && error.code === 'unsafe_archive_entry'
    );
    assert.equal(fs.existsSync(path.join(tempRoot, 'outside.txt')), false);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('archive inspection rejects duplicate names before extraction', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-duplicate-'));
  const source = path.join(tempRoot, 'source');
  writePack(source);
  const archive = archiveFromDirectory(
    source,
    path.join(tempRoot, 'duplicate.modelpack'),
    [['LICENSE', Buffer.from('duplicate')]]
  );
  try {
    await assert.rejects(
      inspectModelPack(archive, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError && error.code === 'unsafe_archive_entry'
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('archive inspection rejects non-ASCII member identity before extraction', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-unicode-entry-'));
  const source = path.join(tempRoot, 'source');
  writePack(source);
  const archive = archiveFromDirectory(
    source,
    path.join(tempRoot, 'unicode-entry.modelpack'),
    [
      ['ſ.txt', Buffer.from('unicode')],
      ['s.txt', Buffer.from('ascii')],
    ]
  );
  try {
    await assert.rejects(
      inspectModelPack(archive, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError
        && error.code === 'unsafe_archive_entry'
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('archive inspection rejects Windows-reserved extra members', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-reserved-entry-'));
  const source = path.join(tempRoot, 'source');
  writePack(source);
  const archive = archiveFromDirectory(
    source,
    path.join(tempRoot, 'reserved-entry.modelpack'),
    [['CON.txt', Buffer.from('reserved')]]
  );
  try {
    await assert.rejects(
      inspectModelPack(archive, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError
        && error.code === 'unsafe_archive_entry'
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('desktop import spawns trusted Ollama command with fixed argument positions', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-import-'));
  const source = path.join(tempRoot, 'source');
  writePack(source, {
    modelfileText:
      'FROM ./weights.gguf\r\n' +
      'PARAMETER num_ctx 8192\r\n' +
      'PARAMETER use_mmap true\r\n' +
      'PARAMETER stop "END"\r\n' +
      'SYSTEM """\r\nsystem text\r\n"""\r\n' +
      'TEMPLATE template text\r\n',
  });
  const archive = archiveFromDirectory(source, path.join(tempRoot, 'test.modelpack'));
  const calls = [];
  const progress = [];
  const spawnImpl = (command, args, options) => {
    calls.push({
      command,
      args: [...args],
      options,
      canonicalModelfile: fs.readFileSync(args[3], 'utf8'),
    });
    const child = new EventEmitter();
    child.kill = () => true;
    setImmediate(() => {
      child.emit('exit', 0, null);
      child.emit('close', 0, null);
    });
    return child;
  };
  try {
    const result = await importModelPack(archive, {
      spawnImpl,
      runtimeCommand: '/trusted/embedded/ollama',
      diskFreeProvider: enoughDisk,
      onProgress: (percent, message) => progress.push([percent, message]),
    });

    assert.equal(result.modelId, 'stockpulse/desktop-test:q4');
    assert.equal(result.displayName, 'Desktop Test');
    assert.equal(calls[0].command, '/trusted/embedded/ollama');
    assert.deepEqual(calls[0].args.slice(0, 3), [
      'create',
      'stockpulse/desktop-test:q4',
      '-f',
    ]);
    assert.match(calls[0].args[3], /Modelfile$/);
    assert.equal(
      calls[0].canonicalModelfile,
      'FROM ./weights.gguf\n' +
      'PARAMETER num_ctx 8192\n' +
      'PARAMETER use_mmap true\n' +
      'PARAMETER stop "END"\n' +
      'TEMPLATE """template text"""\n' +
      'SYSTEM """\nsystem text\n"""\n'
    );
    assert.doesNotMatch(calls[0].canonicalModelfile, /LICENSE/u);
    assert.equal(calls[0].options.shell, false);
    assert.equal(calls[0].options.stdio, 'ignore');
    assert.deepEqual(progress, [
      [35, 'Model Pack verified'],
      [90, 'Model created in Ollama'],
    ]);
    assert.equal(fs.existsSync(calls[0].options.cwd), false);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('post-preflight staging ENOSPC stays actionable', async (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-enospc-'));
  writePack(tempRoot);
  const diskError = Object.assign(new Error('disk full'), { code: 'ENOSPC' });
  t.mock.method(fs.promises, 'writeFile', async () => {
    throw diskError;
  });

  try {
    await assert.rejects(
      inspectModelPack(tempRoot, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError
        && error.code === 'insufficient_disk_space'
        && /Free disk space/.test(error.userMessage)
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('archive output errors close extraction streams before typed cleanup', async (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-stream-'));
  const source = path.join(tempRoot, 'source');
  writePack(source);
  const archive = archiveFromDirectory(source, path.join(tempRoot, 'test.modelpack'));
  let outputClosed = false;

  class BrokenOutput extends Writable {
    _write(_chunk, _encoding, callback) {
      const error = Object.assign(new Error('injected output failure'), { code: 'EIO' });
      callback(error);
    }
  }

  t.mock.method(fs, 'createWriteStream', () => {
    const output = new BrokenOutput({ emitClose: true });
    output.once('close', () => {
      outputClosed = true;
    });
    return output;
  });

  try {
    await assert.rejects(
      inspectModelPack(archive, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError && error.code === 'invalid_archive'
    );
    assert.equal(outputClosed, true);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('archive ENOSPC closes extraction streams before actionable cleanup', async (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-zip-enospc-'));
  const source = path.join(tempRoot, 'source');
  writePack(source);
  const archive = archiveFromDirectory(source, path.join(tempRoot, 'test.modelpack'));
  const openedInputs = [];
  let outputClosed = false;
  const originalOpen = yauzl.open;

  t.mock.method(yauzl, 'open', (archivePath, options, callback) => {
    originalOpen(archivePath, options, (error, zipFile) => {
      if (zipFile) {
        const originalOpenReadStream = zipFile.openReadStream.bind(zipFile);
        zipFile.openReadStream = (entry, done) => {
          originalOpenReadStream(entry, (streamError, input) => {
            if (input) {
              openedInputs.push(input);
            }
            done(streamError, input);
          });
        };
      }
      callback(error, zipFile);
    });
  });

  class DiskFullOutput extends Writable {
    _write(_chunk, _encoding, callback) {
      callback(Object.assign(new Error('disk full'), { code: 'ENOSPC' }));
    }
  }

  t.mock.method(fs, 'createWriteStream', () => {
    const output = new DiskFullOutput({ emitClose: true });
    output.once('close', () => {
      outputClosed = true;
    });
    return output;
  });

  try {
    await assert.rejects(
      inspectModelPack(archive, { diskFreeProvider: enoughDisk }),
      (error) => error instanceof ModelPackError
        && error.code === 'insufficient_disk_space'
        && /Free disk space/.test(error.userMessage)
    );
    assert.equal(outputClosed, true);
    assert.ok(openedInputs.length > 0);
    assert.equal(openedInputs.every((input) => input.destroyed), true);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('validation failures never spawn Ollama', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-no-spawn-'));
  writePack(tempRoot, { tamper: true });
  const calls = [];
  try {
    await assert.rejects(
      importModelPack(tempRoot, {
        spawnImpl: () => calls.push('spawn'),
        diskFreeProvider: enoughDisk,
      }),
      (error) => error instanceof ModelPackError && error.code === 'hash_mismatch'
    );
    assert.deepEqual(calls, []);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('Ollama timeout waits for child close before staging cleanup', { timeout: 5000 }, async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-timeout-'));
  writePack(tempRoot);
  const child = new EventEmitter();
  let inspectedRoot = null;
  let killed = false;
  let resolveSpawned;
  let resolveKilled;
  const spawned = new Promise((resolve) => {
    resolveSpawned = resolve;
  });
  const killObserved = new Promise((resolve) => {
    resolveKilled = resolve;
  });
  child.kill = () => {
    killed = true;
    resolveKilled();
    return true;
  };

  try {
    const pending = importModelPack(tempRoot, {
      diskFreeProvider: enoughDisk,
      timeoutMs: 5,
      spawnImpl: (_command, _args, options) => {
        inspectedRoot = options.cwd;
        resolveSpawned();
        return child;
      },
    });
    const rejected = assert.rejects(
      pending,
      (error) => error instanceof ModelPackError && error.code === 'ollama_create_timeout'
    );
    await spawned;
    await killObserved;
    assert.equal(killed, true);
    assert.equal(fs.existsSync(inspectedRoot), true);
    child.emit('exit', null, 'SIGTERM');
    assert.equal(fs.existsSync(inspectedRoot), true);
    child.emit('close', null, 'SIGTERM');

    await rejected;
    assert.equal(fs.existsSync(inspectedRoot), false);
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
});

test('spawn failure returns actionable Ollama guidance without a raw process error', async () => {
  const inspected = {
    root: '/safe/pack',
    manifest: { modelId: 'stockpulse/desktop-test:q4' },
    modelfilePath: '/safe/pack/Modelfile',
  };
  await assert.rejects(
    spawnOllamaCreate(inspected, {
      spawnImpl: () => {
        throw new Error('ENOENT /private/bin');
      },
    }),
    (error) => (
      error instanceof ModelPackError
      && error.code === 'ollama_unavailable'
      && /Install or start Ollama/.test(error.userMessage)
      && !error.userMessage.includes('/private/bin')
    )
  );
});
