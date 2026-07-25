const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

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

function writePack(root, { modelfileText = 'FROM ./weights.gguf\n', tamper = false } = {}) {
  fs.mkdirSync(root, { recursive: true });
  const files = {
    'weights.gguf': Buffer.from('GGUF-desktop-test'),
    Modelfile: Buffer.from(modelfileText),
    LICENSE: Buffer.from('Desktop test license\n'),
  };
  for (const [name, payload] of Object.entries(files)) {
    fs.writeFileSync(path.join(root, name), payload);
  }
  const manifest = {
    format_version: 1,
    model_id: 'stockpulse/desktop-test:q4',
    display_name: 'Desktop Test',
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

    assert.throws(
      () => parseModelPackModelfile(
        Buffer.from('FROM ./weights.gguf\nADAPTER ./outside.gguf\n'),
        'weights.gguf'
      ),
      (error) => error instanceof ModelPackError && error.code === 'unsafe_modelfile'
    );
  } finally {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
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

test('desktop import spawns trusted Ollama command with fixed argument positions', async () => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-model-pack-import-'));
  const source = path.join(tempRoot, 'source');
  writePack(source);
  const archive = archiveFromDirectory(source, path.join(tempRoot, 'test.modelpack'));
  const calls = [];
  const progress = [];
  const spawnImpl = (command, args, options) => {
    calls.push({ command, args: [...args], options });
    const child = new EventEmitter();
    child.kill = () => true;
    setImmediate(() => {
      child.emit('exit', 0, null);
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
