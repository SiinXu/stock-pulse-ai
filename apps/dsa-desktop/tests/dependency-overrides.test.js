const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { tar: createBuilderTar } = require('app-builder-lib/out/targets/archive');
const { TmpDir } = require('temp-file');
const tar = require('tar');

const desktopPackage = require('../package.json');
const tarPackage = require('tar/package.json');

test('tar override remains compatible with the app-builder-lib archive path', async () => {
  assert.equal(
    desktopPackage.overrides['app-builder-lib'].tar,
    tarPackage.version
  );

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-builder-tar-'));
  const source = path.join(root, 'source');
  const output = path.join(root, 'probe.tar.gz');
  const tempDirManager = new TmpDir('desktop-tar-override-test');

  try {
    fs.mkdirSync(source);
    fs.writeFileSync(path.join(source, 'probe.txt'), 'ok\n');

    await createBuilderTar(
      'normal',
      'tar.gz',
      output,
      source,
      false,
      tempDirManager
    );

    const entries = [];
    await tar.list({
      file: output,
      onentry: (entry) => entries.push(entry.path),
    });

    assert.ok(fs.statSync(output).size > 0);
    assert.deepEqual(entries, ['probe/', 'probe/probe.txt']);
  } finally {
    await tempDirManager.cleanup();
    fs.rmSync(root, { recursive: true, force: true });
  }
});
