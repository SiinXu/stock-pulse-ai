const assert = require('node:assert/strict');
const test = require('node:test');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const DESKTOP_ROOT = path.resolve(__dirname, '..');
const REPOSITORY_ROOT = path.resolve(DESKTOP_ROOT, '..', '..');
const AUDIT_SCRIPT = path.join(DESKTOP_ROOT, 'scripts', 'macos-signature-audit.sh');

function readText(filePath) {
  return fs.readFileSync(filePath, 'utf-8');
}

function writeExecutable(filePath, contents) {
  fs.writeFileSync(filePath, contents, 'utf-8');
  fs.chmodSync(filePath, 0o755);
}

function createFakeSignatureTools(tempRoot) {
  const fakeBin = path.join(tempRoot, 'bin');
  fs.mkdirSync(fakeBin);
  writeExecutable(path.join(fakeBin, 'file'), `#!/usr/bin/env bash
candidate="${'${@: -1}'}"
if [[ "${'${candidate}'}" == *.bin ]]; then
  printf 'Mach-O 64-bit executable\\n'
else
  printf 'data\\n'
fi
`);
  writeExecutable(path.join(fakeBin, 'codesign'), `#!/usr/bin/env bash
candidate="${'${@: -1}'}"
marker="${'${candidate}'}.removed"
case "$1" in
  -d)
    if [[ -f "${'${marker}'}" ]] || [[ "${'${candidate}'}" == */unsigned.bin ]]; then
      printf 'code object is not signed at all\\n' >&2
      exit 1
    fi
    printf 'Authority=adhoc\\n' >&2
    ;;
  --verify)
    if [[ "${'${candidate}'}" == */broken.bin ]] && [[ ! -f "${'${marker}'}" ]]; then
      printf 'broken signature\\n' >&2
      exit 1
    fi
    ;;
  --remove-signature)
    : > "${'${marker}'}"
    ;;
esac
`);
  return fakeBin;
}

function runAudit(fakeBin, mode, artifact) {
  return spawnSync('bash', [AUDIT_SCRIPT, mode, artifact], {
    cwd: REPOSITORY_ROOT,
    env: {
      ...process.env,
      PATH: `${fakeBin}${path.delimiter}${process.env.PATH || ''}`,
    },
    encoding: 'utf-8',
  });
}

test('macOS unsigned packaging normalizes and audits signatures at every boundary', () => {
  const packageMetadata = JSON.parse(readText(path.join(DESKTOP_ROOT, 'package.json')));
  const afterPackHook = readText(path.join(DESKTOP_ROOT, 'scripts', 'afterPackMacos.js'));
  const backendScript = readText(path.join(REPOSITORY_ROOT, 'scripts', 'build-backend-macos.sh'));
  const desktopScript = readText(path.join(REPOSITORY_ROOT, 'scripts', 'build-desktop-macos.sh'));

  assert.equal(packageMetadata.build.mac.identity, null);
  assert.equal(packageMetadata.build.mac.hardenedRuntime, false);
  assert.equal(packageMetadata.build.afterPack, 'scripts/afterPackMacos.js');
  assert.match(afterPackHook, /context\.electronPlatformName !== 'darwin'/);
  assert.match(afterPackHook, /macos-signature-audit\.sh/);
  assert.match(afterPackHook, /execFileSync\('bash', \[auditScript, 'normalize', appPath\]/);

  const normalizeBackend = 'macos-signature-audit.sh" normalize "${packaged_root}"';
  assert.ok(backendScript.includes(normalizeBackend));
  assert.ok(backendScript.indexOf(normalizeBackend) < backendScript.indexOf('"${packaged_entry}" --help'));
  assert.match(desktopScript, /macos-signature-audit\.sh" check "\$\{app_path\}"/);
  assert.match(desktopScript, /verify_unsigned_dmg/);
  assert.match(desktopScript, /code has no resources but signature indicates they must be present/);
});

test('macOS signature normalization removes an invalid signature', {
  skip: process.platform === 'win32',
}, (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-signature-normalize-'));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));
  const fakeBin = createFakeSignatureTools(tempRoot);
  const artifact = path.join(tempRoot, 'artifact');
  fs.mkdirSync(artifact);
  fs.writeFileSync(path.join(artifact, 'broken.bin'), 'broken');
  fs.writeFileSync(path.join(artifact, 'unsigned.bin'), 'unsigned');

  const result = runAudit(fakeBin, 'normalize', artifact);

  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.existsSync(path.join(artifact, 'broken.bin.removed')), true);
  assert.match(result.stdout, /removed=1/);
});

test('macOS signature audit rejects an invalid signature without mutating it', {
  skip: process.platform === 'win32',
}, (t) => {
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'stockpulse-signature-check-'));
  t.after(() => fs.rmSync(tempRoot, { recursive: true, force: true }));
  const fakeBin = createFakeSignatureTools(tempRoot);
  const artifact = path.join(tempRoot, 'artifact');
  fs.mkdirSync(artifact);
  fs.writeFileSync(path.join(artifact, 'broken.bin'), 'broken');

  const result = runAudit(fakeBin, 'check', artifact);

  assert.notEqual(result.status, 0);
  assert.equal(fs.existsSync(path.join(artifact, 'broken.bin.removed')), false);
  assert.match(result.stderr, /invalid signature/);
});
