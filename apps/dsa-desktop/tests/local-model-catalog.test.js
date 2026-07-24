const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const {
  deriveDesktopLocalModelPresets,
  loadDesktopLocalModelPresets,
  resolveLocalModelCatalogPath,
} = require('../local-model-catalog');


test('desktop presets are derived from the repository catalog', () => {
  const catalogPath = resolveLocalModelCatalogPath();
  const presets = loadDesktopLocalModelPresets({ catalogPath });

  assert.equal(path.basename(catalogPath), 'local_model_catalog.json');
  assert.deepEqual(
    presets.map((preset) => preset.id),
    ['qwen3:4b', 'qwen3:8b', 'gemma4:12b', 'deepseek-r1:8b']
  );
  assert.deepEqual(
    presets.map((preset) => preset.approxSizeGb),
    [2.5, 5.2, 7.6, 5.2]
  );
  assert.equal(Object.isFrozen(presets), true);
  assert.equal(presets.every((preset) => Object.isFrozen(preset)), true);
});

test('desktop projection rejects duplicate pull tags', () => {
  const catalog = JSON.parse(fs.readFileSync(resolveLocalModelCatalogPath(), 'utf8'));
  const duplicate = structuredClone(catalog.models[0]);
  duplicate.id = 'duplicate';
  catalog.models.push(duplicate);

  assert.throws(
    () => deriveDesktopLocalModelPresets(catalog),
    /Invalid desktop local model preset/
  );
});

test('desktop projection rejects a guided-only pull recommendation', () => {
  const catalog = JSON.parse(fs.readFileSync(resolveLocalModelCatalogPath(), 'utf8'));
  catalog.models[0].license.redistribution = 'guided_only';

  assert.throws(
    () => deriveDesktopLocalModelPresets(catalog),
    /Invalid desktop local model preset/
  );
});
