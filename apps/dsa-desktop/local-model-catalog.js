const fs = require('fs');
const path = require('path');

const OLLAMA_TAG_PATTERN =
  /^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)?(?::[a-z0-9]+(?:[._-][a-z0-9]+)*)?$/i;

function resolveLocalModelCatalogPath({
  baseDir = __dirname,
  resourcesPath = process.resourcesPath,
  existsSync = fs.existsSync,
} = {}) {
  const sourcePath = path.resolve(baseDir, '..', '..', 'src', 'llm', 'local_model_catalog.json');
  if (existsSync(sourcePath)) {
    return sourcePath;
  }

  if (typeof resourcesPath === 'string' && resourcesPath.trim()) {
    const packagedPath = path.join(resourcesPath, 'local-model-catalog.json');
    if (existsSync(packagedPath)) {
      return packagedPath;
    }
  }

  throw new Error('Local model catalog is missing from both source and packaged resources');
}

function deriveDesktopLocalModelPresets(catalog) {
  if (!catalog || catalog.schema_version !== 1 || !Array.isArray(catalog.models)) {
    throw new Error('Local model catalog has an unsupported schema');
  }

  const seen = new Set();
  const presets = [];
  for (const model of catalog.models) {
    if (!model?.desktop?.recommended) {
      continue;
    }

    const tag = model?.install?.ollama_tag;
    if (
      model.section !== 'general' ||
      model?.license?.redistribution !== 'allowed_with_notice' ||
      model?.install?.method !== 'ollama_pull' ||
      model?.install?.status !== 'available' ||
      typeof tag !== 'string' ||
      !OLLAMA_TAG_PATTERN.test(tag) ||
      seen.has(tag)
    ) {
      throw new Error(`Invalid desktop local model preset: ${String(model?.id || tag || 'unknown')}`);
    }
    if (
      typeof model?.display_name?.en !== 'string' ||
      !Number.isInteger(model?.q4?.size_bytes) ||
      model.q4.size_bytes <= 0 ||
      !Number.isInteger(model.recommended_ram_gb) ||
      model.recommended_ram_gb <= 0 ||
      typeof model?.desktop?.guidance_en !== 'string'
    ) {
      throw new Error(`Incomplete desktop local model preset: ${model.id}`);
    }

    seen.add(tag);
    presets.push(
      Object.freeze({
        id: tag,
        label: model.display_name.en,
        approxSizeGb: Math.round((model.q4.size_bytes / 1_000_000_000) * 10) / 10,
        minRamGb: model.recommended_ram_gb,
        guidance: model.desktop.guidance_en,
      })
    );
  }

  if (presets.length === 0) {
    throw new Error('Local model catalog does not declare any desktop presets');
  }
  return Object.freeze(presets);
}

function loadDesktopLocalModelPresets(options = {}) {
  const catalogPath = options.catalogPath || resolveLocalModelCatalogPath(options);
  let catalog;
  try {
    catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
  } catch (error) {
    throw new Error(`Failed to read local model catalog at ${catalogPath}: ${error.message}`);
  }
  return deriveDesktopLocalModelPresets(catalog);
}

module.exports = {
  OLLAMA_TAG_PATTERN,
  deriveDesktopLocalModelPresets,
  loadDesktopLocalModelPresets,
  resolveLocalModelCatalogPath,
};
