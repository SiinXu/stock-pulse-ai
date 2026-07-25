'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const yauzl = require('yauzl');

const MODEL_PACK_FORMAT_VERSION = 1;
const MODEL_PACK_MANIFEST_FILENAME = 'manifest.json';
const MODEL_PACK_MAX_MANIFEST_BYTES = 1024 * 1024;
const MODEL_PACK_MAX_MODELFILE_BYTES = 1024 * 1024;
const MODEL_PACK_MAX_LICENSE_BYTES = 2 * 1024 * 1024;
const MODEL_PACK_MAX_BYTES = 64 * 1024 * 1024 * 1024;
const MODEL_PACK_MAX_ENTRIES = 256;
const MODEL_PACK_HASH_CHUNK_SIZE = 1024 * 1024;
const MODEL_PACK_DISK_RESERVE_MIN_BYTES = 64 * 1024 * 1024;
const MODEL_PACK_DISK_RESERVE_MAX_BYTES = 512 * 1024 * 1024;
const MODEL_PACK_CREATE_TIMEOUT_MS = 30 * 60 * 1000;
const MODEL_PACK_OLLAMA_BINARY = 'ollama';
const MODEL_PACK_MODEL_ID_PATTERN =
  /^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)?(?::[a-z0-9]+(?:[._-][a-z0-9]+)*)?$/i;
const MODEL_PACK_SAFE_FILENAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const MODEL_PACK_SHA256_PATTERN = /^[0-9a-f]{64}$/;
const MODEL_PACK_LICENSE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9.+-]{0,127}$/;
const MODEL_PACK_PARAMETER_NAME_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;
const MODEL_PACK_REQUIRED_ROLES = Object.freeze(['gguf', 'modelfile', 'license']);
const MODEL_PACK_ALLOWED_INSTRUCTIONS = new Set(['FROM', 'PARAMETER', 'TEMPLATE', 'SYSTEM']);

class ModelPackError extends Error {
  constructor(code, userMessage, details = {}) {
    super(userMessage);
    this.name = 'ModelPackError';
    this.code = code;
    this.userMessage = userMessage;
    this.details = { ...details };
  }
}

function invalidManifest(message) {
  return new ModelPackError(
    'invalid_manifest',
    `manifest.json is invalid: ${message}. Build the pack again with the current tool.`
  );
}

function assertExactKeys(value, expected, location) {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  const missing = wanted.filter((key) => !Object.hasOwn(value, key));
  const extra = actual.filter((key) => !expected.includes(key));
  if (missing.length) {
    throw invalidManifest(`${location} is missing ${missing.join(', ')}`);
  }
  if (extra.length) {
    throw invalidManifest(`${location} has unsupported fields ${extra.join(', ')}`);
  }
}

function requireText(value, fieldName, maxLength = 160) {
  if (typeof value !== 'string') {
    throw invalidManifest(`${fieldName} must be text`);
  }
  const normalized = value.trim();
  if (!normalized || normalized.length > maxLength) {
    throw invalidManifest(`${fieldName} must contain between 1 and ${maxLength} characters`);
  }
  if ([...normalized].some((character) => character.charCodeAt(0) < 32)) {
    throw invalidManifest(`${fieldName} contains control characters`);
  }
  return normalized;
}

function requireFilename(value, fieldName) {
  const filename = requireText(value, fieldName, 128);
  if (!MODEL_PACK_SAFE_FILENAME_PATTERN.test(filename) || filename === '.' || filename === '..') {
    throw invalidManifest(`${fieldName} must be a root-level safe filename`);
  }
  return filename;
}

function parseModelPackManifest(payload) {
  if (!Buffer.isBuffer(payload) || payload.length < 1 || payload.length > MODEL_PACK_MAX_MANIFEST_BYTES) {
    throw invalidManifest(
      `manifest.json must contain between 1 and ${MODEL_PACK_MAX_MANIFEST_BYTES} bytes`
    );
  }
  let raw;
  try {
    raw = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(payload));
  } catch (_error) {
    throw invalidManifest('manifest.json must contain valid UTF-8 JSON');
  }
  if (!raw || Array.isArray(raw) || typeof raw !== 'object') {
    throw invalidManifest('the root value must be an object');
  }
  const manifestKeys = [
    'format_version',
    'model_id',
    'display_name',
    'gguf_file',
    'modelfile',
    'license',
    'minimum_memory_gb',
    'files',
  ];
  assertExactKeys(raw, manifestKeys, 'the manifest');
  if (!Number.isInteger(raw.format_version)) {
    throw invalidManifest('format_version must be an integer');
  }
  if (raw.format_version !== MODEL_PACK_FORMAT_VERSION) {
    throw new ModelPackError(
      'unsupported_format_version',
      `This Model Pack uses format version ${raw.format_version}. ` +
        `Update StockPulse or use a version ${MODEL_PACK_FORMAT_VERSION} pack.`
    );
  }
  const modelId = requireText(raw.model_id, 'model_id', 96);
  if (!MODEL_PACK_MODEL_ID_PATTERN.test(modelId)) {
    throw invalidManifest('model_id is not a valid Ollama model name');
  }
  const displayName = requireText(raw.display_name, 'display_name');
  const ggufFile = requireFilename(raw.gguf_file, 'gguf_file');
  if (!ggufFile.toLowerCase().endsWith('.gguf')) {
    throw invalidManifest('gguf_file must end in .gguf');
  }
  const modelfile = requireFilename(raw.modelfile, 'modelfile');
  if (!raw.license || Array.isArray(raw.license) || typeof raw.license !== 'object') {
    throw invalidManifest('license must be an object');
  }
  assertExactKeys(raw.license, ['id', 'file'], 'license');
  const licenseId = requireText(raw.license.id, 'license.id', 128);
  if (!MODEL_PACK_LICENSE_ID_PATTERN.test(licenseId)) {
    throw invalidManifest('license.id must be an SPDX id or LicenseRef identifier');
  }
  const licenseFile = requireFilename(raw.license.file, 'license.file');
  if (
    !Number.isInteger(raw.minimum_memory_gb)
    || raw.minimum_memory_gb < 1
    || raw.minimum_memory_gb > 2048
  ) {
    throw invalidManifest('minimum_memory_gb must be an integer from 1 to 2048');
  }
  if (!Array.isArray(raw.files) || raw.files.length !== MODEL_PACK_REQUIRED_ROLES.length) {
    throw invalidManifest('files must list exactly one gguf, modelfile, and license');
  }
  const seenPaths = new Set();
  const seenRoles = new Set();
  const files = raw.files.map((entry, index) => {
    if (!entry || Array.isArray(entry) || typeof entry !== 'object') {
      throw invalidManifest(`files[${index}] must be an object`);
    }
    assertExactKeys(entry, ['path', 'role', 'sha256', 'size_bytes'], `files[${index}]`);
    const entryPath = requireFilename(entry.path, `files[${index}].path`);
    if (entryPath.toLowerCase() === MODEL_PACK_MANIFEST_FILENAME) {
      throw invalidManifest(`files[${index}].path cannot use the reserved manifest.json name`);
    }
    const role = requireText(entry.role, `files[${index}].role`, 16);
    const digest = requireText(entry.sha256, `files[${index}].sha256`, 64).toLowerCase();
    if (!MODEL_PACK_REQUIRED_ROLES.includes(role)) {
      throw invalidManifest(`files[${index}].role is unsupported`);
    }
    if (!MODEL_PACK_SHA256_PATTERN.test(digest)) {
      throw invalidManifest(`files[${index}].sha256 must be 64 lowercase hex characters`);
    }
    if (!Number.isSafeInteger(entry.size_bytes) || entry.size_bytes < 1) {
      throw invalidManifest(`files[${index}].size_bytes must be a positive safe integer`);
    }
    if (seenPaths.has(entryPath.toLowerCase())) {
      throw invalidManifest('files contains duplicate paths');
    }
    if (seenRoles.has(role)) {
      throw invalidManifest(`files contains more than one ${role} entry`);
    }
    seenPaths.add(entryPath.toLowerCase());
    seenRoles.add(role);
    return Object.freeze({
      path: entryPath,
      role,
      sha256: digest,
      sizeBytes: entry.size_bytes,
    });
  });
  if (MODEL_PACK_REQUIRED_ROLES.some((role) => !seenRoles.has(role))) {
    throw invalidManifest('files must include gguf, modelfile, and license roles');
  }
  if (files.reduce((total, entry) => total + entry.sizeBytes, 0) > MODEL_PACK_MAX_BYTES) {
    throw new ModelPackError(
      'model_pack_too_large',
      'This Model Pack exceeds the 64 GiB limit. Build or select a smaller pack.'
    );
  }
  const rolePaths = Object.fromEntries(files.map((entry) => [entry.role, entry.path]));
  if (rolePaths.gguf !== ggufFile) {
    throw invalidManifest('gguf_file must match the file with role gguf');
  }
  if (rolePaths.modelfile !== modelfile) {
    throw invalidManifest('modelfile must match the file with role modelfile');
  }
  if (rolePaths.license !== licenseFile) {
    throw invalidManifest('license.file must match the file with role license');
  }
  return Object.freeze({
    formatVersion: raw.format_version,
    modelId,
    displayName,
    ggufFile,
    modelfile,
    license: Object.freeze({ id: licenseId, file: licenseFile }),
    minimumMemoryGb: raw.minimum_memory_gb,
    files: Object.freeze(files),
  });
}

function parseParameterValue(rawValue) {
  const value = rawValue.trim();
  if (!value) {
    throw new ModelPackError(
      'unsafe_modelfile',
      'PARAMETER requires a name and value. Fix the Modelfile and rebuild the pack.'
    );
  }
  try {
    const parsed = JSON.parse(value);
    if (parsed === null || Array.isArray(parsed) || typeof parsed === 'object') {
      return value;
    }
    return parsed;
  } catch (_error) {
    return value;
  }
}

function parseMultilineValue(lines, index, initial, instruction) {
  const value = initial.trim();
  if (!value) {
    throw new ModelPackError(
      'unsafe_modelfile',
      `${instruction} requires text. Fix the Modelfile and rebuild the pack.`
    );
  }
  if (!value.startsWith('"""')) {
    return { value, nextIndex: index };
  }
  const initialRemainder = value.slice(3);
  const sameLineEnd = initialRemainder.indexOf('"""');
  if (sameLineEnd >= 0) {
    if (initialRemainder.slice(sameLineEnd + 3).trim()) {
      throw new ModelPackError(
        'unsafe_modelfile',
        `${instruction} has content after its closing delimiter. Rebuild the pack.`
      );
    }
    return { value: initialRemainder.slice(0, sameLineEnd), nextIndex: index };
  }
  const block = initialRemainder ? [initialRemainder] : [];
  for (let cursor = index + 1; cursor < lines.length; cursor += 1) {
    const end = lines[cursor].indexOf('"""');
    if (end >= 0) {
      block.push(lines[cursor].slice(0, end));
      if (lines[cursor].slice(end + 3).trim()) {
        throw new ModelPackError(
          'unsafe_modelfile',
          `${instruction} has content after its closing delimiter. Rebuild the pack.`
        );
      }
      return { value: block.join('\n'), nextIndex: cursor };
    }
    block.push(lines[cursor]);
  }
  throw new ModelPackError(
    'unsafe_modelfile',
    `${instruction} has an unterminated triple-quoted block. Rebuild the pack.`
  );
}

function parseModelPackModelfile(payload, expectedGgufFile) {
  if (
    !Buffer.isBuffer(payload)
    || payload.length < 1
    || payload.length > MODEL_PACK_MAX_MODELFILE_BYTES
  ) {
    throw new ModelPackError(
      'unsafe_modelfile',
      `Modelfile must contain between 1 and ${MODEL_PACK_MAX_MODELFILE_BYTES} bytes.`
    );
  }
  let text;
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(payload);
  } catch (_error) {
    throw new ModelPackError('unsafe_modelfile', 'Modelfile must use UTF-8. Rebuild the pack.');
  }
  if (text.includes('\0')) {
    throw new ModelPackError('unsafe_modelfile', 'Modelfile contains a null byte. Rebuild the pack.');
  }
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/);
  let fromFile = null;
  const parameters = {};
  let template = null;
  let system = null;
  for (let index = 0; index < lines.length; index += 1) {
    const stripped = lines[index].trim();
    if (!stripped || stripped.startsWith('#')) {
      continue;
    }
    const separator = stripped.search(/\s/);
    const instruction = (separator < 0 ? stripped : stripped.slice(0, separator)).toUpperCase();
    const rawValue = separator < 0 ? '' : stripped.slice(separator).trim();
    if (!MODEL_PACK_ALLOWED_INSTRUCTIONS.has(instruction)) {
      throw new ModelPackError(
        'unsafe_modelfile',
        `Remove the unsupported instruction ${instruction} from Modelfile and rebuild the pack.`
      );
    }
    if (!rawValue) {
      throw new ModelPackError(
        'unsafe_modelfile',
        `${instruction} requires a value. Fix the Modelfile and rebuild the pack.`
      );
    }
    if (instruction === 'FROM') {
      if (fromFile !== null) {
        throw new ModelPackError(
          'unsafe_modelfile',
          'Modelfile must contain exactly one FROM instruction.'
        );
      }
      const candidate = rawValue.startsWith('./') ? rawValue.slice(2) : rawValue;
      if (candidate !== expectedGgufFile) {
        throw new ModelPackError(
          'unsafe_modelfile',
          `FROM must reference ${expectedGgufFile} from this Model Pack. ` +
            'Remove external or arbitrary paths and rebuild the pack.'
        );
      }
      fromFile = candidate;
    } else if (instruction === 'PARAMETER') {
      const valueSeparator = rawValue.search(/\s/);
      const name = (valueSeparator < 0 ? rawValue : rawValue.slice(0, valueSeparator)).toLowerCase();
      const value = valueSeparator < 0 ? '' : rawValue.slice(valueSeparator).trim();
      if (!MODEL_PACK_PARAMETER_NAME_PATTERN.test(name) || !value) {
        throw new ModelPackError(
          'unsafe_modelfile',
          'PARAMETER requires a safe name and value. Fix the Modelfile and rebuild the pack.'
        );
      }
      const parsed = parseParameterValue(value);
      if (Object.hasOwn(parameters, name)) {
        parameters[name] = Array.isArray(parameters[name])
          ? [...parameters[name], parsed]
          : [parameters[name], parsed];
      } else {
        parameters[name] = parsed;
      }
    } else {
      const parsed = parseMultilineValue(lines, index, rawValue, instruction);
      index = parsed.nextIndex;
      if (instruction === 'TEMPLATE') {
        if (template !== null) {
          throw new ModelPackError(
            'unsafe_modelfile',
            'Modelfile may contain only one TEMPLATE instruction.'
          );
        }
        template = parsed.value;
      } else {
        if (system !== null) {
          throw new ModelPackError(
            'unsafe_modelfile',
            'Modelfile may contain only one SYSTEM instruction.'
          );
        }
        system = parsed.value;
      }
    }
  }
  if (fromFile === null) {
    throw new ModelPackError(
      'unsafe_modelfile',
      `Modelfile must contain FROM ./${expectedGgufFile}. Rebuild the pack.`
    );
  }
  return Object.freeze({ fromFile, parameters, template, system });
}

async function sha256File(filePath) {
  return new Promise((resolve, reject) => {
    const digest = crypto.createHash('sha256');
    const stream = fs.createReadStream(filePath, { highWaterMark: MODEL_PACK_HASH_CHUNK_SIZE });
    stream.on('data', (chunk) => digest.update(chunk));
    stream.on('error', reject);
    stream.on('end', () => resolve(digest.digest('hex')));
  });
}

function sameFileIdentity(first, second) {
  return first.dev === second.dev && first.ino === second.ino;
}

async function openStableRegularFile(filePath, unsafeMessage) {
  const pathStat = await fs.promises.lstat(filePath);
  if (!pathStat.isFile() || pathStat.isSymbolicLink()) {
    throw new ModelPackError('unsafe_package_entry', unsafeMessage);
  }
  const handle = await fs.promises.open(filePath, 'r');
  try {
    const openedStat = await handle.stat();
    if (!openedStat.isFile() || !sameFileIdentity(pathStat, openedStat)) {
      throw new ModelPackError(
        'unsafe_package_entry',
        `${path.basename(filePath)} changed while it was opened. ` +
          'Stop modifying the Model Pack and try again.'
      );
    }
    return { handle, size: openedStat.size };
  } catch (error) {
    await handle.close();
    throw error;
  }
}

async function readBoundedFile(filePath, maxBytes, code, message) {
  const opened = await openStableRegularFile(
    filePath,
    `${path.basename(filePath)} must be a regular file inside the Model Pack. ` +
      'Build the pack again.'
  );
  try {
    if (opened.size < 1 || opened.size > maxBytes) {
      throw new ModelPackError(code, message);
    }
    const payload = Buffer.alloc(maxBytes + 1);
    let offset = 0;
    while (offset < payload.length) {
      const { bytesRead } = await opened.handle.read(
        payload,
        offset,
        payload.length - offset,
        null
      );
      if (bytesRead === 0) {
        break;
      }
      offset += bytesRead;
    }
    if (offset < 1 || offset > maxBytes) {
      throw new ModelPackError(code, message);
    }
    return payload.subarray(0, offset);
  } finally {
    await opened.handle.close();
  }
}

function validateRoleSize(entry, sizeBytes) {
  if (entry.role === 'modelfile' && sizeBytes > MODEL_PACK_MAX_MODELFILE_BYTES) {
    throw new ModelPackError(
      'unsafe_modelfile',
      `${entry.path} exceeds the safe size limit. Reduce it and rebuild the pack.`
    );
  }
  if (entry.role === 'license' && sizeBytes > MODEL_PACK_MAX_LICENSE_BYTES) {
    throw new ModelPackError(
      'invalid_license_file',
      `${entry.path} exceeds the safe size limit. Use plain-text terms and rebuild the pack.`
    );
  }
}

function validateDeclaredSize(entry, actualSize) {
  if (actualSize !== entry.sizeBytes) {
    throw new ModelPackError(
      'size_mismatch',
      `${entry.path} has the wrong size. Download or build the pack again.`
    );
  }
  validateRoleSize(entry, actualSize);
}

function validateManifestRoleSizes(manifest) {
  for (const entry of manifest.files) {
    validateRoleSize(entry, entry.sizeBytes);
  }
}

async function validatePayload(root, manifest) {
  for (const entry of manifest.files) {
    const filePath = path.join(root, entry.path);
    let fileStat;
    try {
      fileStat = await fs.promises.lstat(filePath);
    } catch (error) {
      if (error && error.code === 'ENOENT') {
        throw new ModelPackError(
          'missing_file',
          `Model Pack is missing ${entry.path}. Download or build the pack again.`
        );
      }
      throw error;
    }
    if (!fileStat.isFile() || fileStat.isSymbolicLink()) {
      throw new ModelPackError(
        'unsafe_package_entry',
        `${entry.path} must be a regular file inside the Model Pack. Build the pack again.`
      );
    }
    validateDeclaredSize(entry, fileStat.size);
    const digest = await sha256File(filePath);
    if (digest !== entry.sha256) {
      throw new ModelPackError(
        'hash_mismatch',
        `${entry.path} failed SHA-256 verification. Download or build the pack again.`
      );
    }
    if (entry.role === 'gguf') {
      const handle = await fs.promises.open(filePath, 'r');
      const magic = Buffer.alloc(4);
      try {
        await handle.read(magic, 0, 4, 0);
      } finally {
        await handle.close();
      }
      if (!magic.equals(Buffer.from('GGUF'))) {
        throw new ModelPackError(
          'invalid_gguf',
          `${entry.path} is not a GGUF model. Select the correct weights and rebuild the pack.`
        );
      }
    }
  }
}

function diskRequiredBytes(payloadSize, archive) {
  const reserve = Math.min(
    MODEL_PACK_DISK_RESERVE_MAX_BYTES,
    Math.max(MODEL_PACK_DISK_RESERVE_MIN_BYTES, Math.floor(payloadSize / 20))
  );
  return payloadSize * (archive ? 2 : 1) + reserve;
}

async function defaultDiskFreeBytes(location) {
  const statfs = await fs.promises.statfs(location, { bigint: true });
  return Number(statfs.bavail * statfs.bsize);
}

async function checkDisk(
  location,
  manifest,
  archive,
  diskFreeProvider,
  verifiedPayloadSize = null
) {
  const payloadSize = verifiedPayloadSize === null
    ? manifest.files.reduce((total, entry) => total + entry.sizeBytes, 0)
    : verifiedPayloadSize;
  let freeBytes;
  try {
    freeBytes = Number(await diskFreeProvider(location));
  } catch (_error) {
    throw new ModelPackError(
      'disk_check_failed',
      'Could not check free disk space. Check the target disk and try again.'
    );
  }
  const required = diskRequiredBytes(payloadSize, archive);
  if (!Number.isFinite(freeBytes) || freeBytes < required) {
    const gib = Math.max(1, Math.ceil((required - Math.max(0, freeBytes || 0)) / (1024 ** 3)));
    throw new ModelPackError(
      'insufficient_disk_space',
      `Not enough disk space to import this Model Pack. Free at least ${gib} GiB and try again.`
    );
  }
}

async function prevalidateDirectoryPayloads(root, manifest) {
  let totalSize = 0;
  for (const entry of manifest.files) {
    const filePath = path.join(root, entry.path);
    let fileStat;
    try {
      fileStat = await fs.promises.lstat(filePath);
    } catch (error) {
      if (error && error.code === 'ENOENT') {
        throw new ModelPackError(
          'missing_file',
          `Model Pack is missing ${entry.path}. Download or build the pack again.`
        );
      }
      throw error;
    }
    if (!fileStat.isFile() || fileStat.isSymbolicLink()) {
      throw new ModelPackError(
        'unsafe_package_entry',
        `${entry.path} must be a regular file inside the Model Pack. Build the pack again.`
      );
    }
    validateDeclaredSize(entry, fileStat.size);
    totalSize += fileStat.size;
    if (totalSize > MODEL_PACK_MAX_BYTES) {
      throw new ModelPackError(
        'model_pack_too_large',
        'This Model Pack exceeds the 64 GiB limit. Build or select a smaller pack.'
      );
    }
  }
  return totalSize;
}

async function writeAll(handle, payload, length) {
  let offset = 0;
  while (offset < length) {
    const { bytesWritten } = await handle.write(
      payload,
      offset,
      length - offset,
      null
    );
    if (bytesWritten < 1) {
      throw new Error('destination write made no progress');
    }
    offset += bytesWritten;
  }
}

async function copyDeclaredFile(sourcePath, destinationPath, entry, copyState) {
  const opened = await openStableRegularFile(
    sourcePath,
    `${entry.path} must be a regular file inside the Model Pack. Build the pack again.`
  );
  let output = null;
  try {
    if (opened.size !== entry.sizeBytes) {
      throw new ModelPackError(
        'size_mismatch',
        `${entry.path} changed while it was copied. ` +
          'Stop modifying the Model Pack and try again.'
      );
    }
    validateDeclaredSize(entry, opened.size);
    output = await fs.promises.open(destinationPath, 'wx', 0o600);
    const digest = crypto.createHash('sha256');
    const chunk = Buffer.alloc(Math.min(MODEL_PACK_HASH_CHUNK_SIZE, entry.sizeBytes));
    let remaining = entry.sizeBytes;
    while (remaining > 0) {
      const requested = Math.min(chunk.length, remaining);
      const { bytesRead } = await opened.handle.read(chunk, 0, requested, null);
      if (bytesRead < 1) {
        throw new ModelPackError(
          'size_mismatch',
          `${entry.path} changed while it was copied. ` +
            'Stop modifying the Model Pack and try again.'
        );
      }
      await writeAll(output, chunk, bytesRead);
      digest.update(chunk.subarray(0, bytesRead));
      remaining -= bytesRead;
      copyState.bytes += bytesRead;
      if (copyState.bytes > MODEL_PACK_MAX_BYTES) {
        throw new ModelPackError(
          'model_pack_too_large',
          'This Model Pack exceeds the 64 GiB limit. Build or select a smaller pack.'
        );
      }
    }
    const extra = Buffer.alloc(1);
    const { bytesRead: extraBytes } = await opened.handle.read(extra, 0, 1, null);
    if (extraBytes > 0) {
      throw new ModelPackError(
        'size_mismatch',
        `${entry.path} changed while it was copied. ` +
          'Stop modifying the Model Pack and try again.'
      );
    }
    if (digest.digest('hex') !== entry.sha256) {
      throw new ModelPackError(
        'hash_mismatch',
        `${entry.path} failed SHA-256 verification. Download or build the pack again.`
      );
    }
  } finally {
    try {
      if (output !== null) {
        await output.close();
      }
    } finally {
      await opened.handle.close();
    }
  }
}

function unexpectedWarning(name) {
  return `Unexpected file is not part of the manifest: ${name}`;
}

async function readDirectoryInventory(root) {
  const files = [];
  const pending = [''];
  let entryCount = 0;
  while (pending.length) {
    const relativeRoot = pending.shift();
    const entries = await fs.promises.readdir(path.join(root, relativeRoot), {
      withFileTypes: true,
    });
    for (const entry of entries) {
      entryCount += 1;
      if (entryCount > MODEL_PACK_MAX_ENTRIES) {
        throw new ModelPackError(
          'invalid_archive',
          'Model Pack contains too many entries. Rebuild it with only declared data.'
        );
      }
      const relativePath = relativeRoot
        ? `${relativeRoot}/${entry.name}`
        : entry.name;
      if (entry.isSymbolicLink()) {
        throw new ModelPackError(
          'unsafe_package_entry',
          `${relativePath} is a symbolic link. Build the pack again.`
        );
      }
      if (entry.isDirectory()) {
        pending.push(relativePath);
      } else if (entry.isFile()) {
        files.push(relativePath);
      } else {
        throw new ModelPackError(
          'unsafe_package_entry',
          `${relativePath} is not a regular file or directory. Build the pack again.`
        );
      }
    }
  }
  return files.sort();
}

function safeArchiveFilename(name) {
  return Boolean(
    name
    && !name.includes('\\')
    && !name.startsWith('/')
    && !path.isAbsolute(name)
    && name !== '.'
    && name !== '..'
    && !name.includes('/')
  );
}

function isZipSymlink(entry) {
  const fileType = (entry.externalFileAttributes >>> 16) & 0o170000;
  return fileType === 0o120000;
}

function normalizeArchiveError(error, fallbackMessage) {
  if (error instanceof ModelPackError) {
    return error;
  }
  const diagnostic = error instanceof Error ? error.message : String(error || '');
  if (/invalid relative path|absolute path|backslash/i.test(diagnostic)) {
    return new ModelPackError(
      'unsafe_archive_entry',
      'Archive contains an unsafe file path. Build the pack again.'
    );
  }
  return new ModelPackError('invalid_archive', fallbackMessage);
}

function openZip(archivePath) {
  return new Promise((resolve, reject) => {
    yauzl.open(
      archivePath,
      { lazyEntries: true, autoClose: true, decodeStrings: true, validateEntrySizes: true },
      (error, zipFile) => (error ? reject(error) : resolve(zipFile))
    );
  });
}

function readZipEntry(zipFile, entry, maxBytes) {
  return new Promise((resolve, reject) => {
    if (entry.uncompressedSize > maxBytes) {
      reject(new ModelPackError('invalid_archive', `${entry.fileName} is too large.`));
      return;
    }
    zipFile.openReadStream(entry, (error, stream) => {
      if (error) {
        reject(error);
        return;
      }
      const chunks = [];
      let total = 0;
      stream.on('data', (chunk) => {
        total += chunk.length;
        if (total > maxBytes) {
          stream.destroy(new ModelPackError('invalid_archive', `${entry.fileName} is too large.`));
          return;
        }
        chunks.push(chunk);
      });
      stream.on('error', reject);
      stream.on('end', () => resolve(Buffer.concat(chunks)));
    });
  });
}

async function readZipInventory(archivePath) {
  const zipFile = await openZip(archivePath);
  return new Promise((resolve, reject) => {
    const inventory = new Map();
    const casefoldNames = new Set();
    let manifestPayload = null;
    let settled = false;
    const fail = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      try {
        zipFile.close();
      } catch (_closeError) {
        // ignore
      }
      reject(normalizeArchiveError(
        error,
        'The selected archive cannot be read. Download the Model Pack again.'
      ));
    };
    zipFile.on('error', fail);
    zipFile.on('entry', async (entry) => {
      try {
        if (inventory.size >= MODEL_PACK_MAX_ENTRIES) {
          throw new ModelPackError(
            'invalid_archive',
            'Model Pack contains too many files. Rebuild it with only declared data.'
          );
        }
        if (!safeArchiveFilename(entry.fileName) || isZipSymlink(entry)) {
          throw new ModelPackError(
            'unsafe_archive_entry',
            `Archive entry ${JSON.stringify(entry.fileName)} is not a safe root-level file. ` +
              'Build the pack again.'
          );
        }
        const identity = entry.fileName.toLowerCase();
        if (casefoldNames.has(identity)) {
          throw new ModelPackError(
            'unsafe_archive_entry',
            'Archive contains duplicate file names. Build the pack again.'
          );
        }
        casefoldNames.add(identity);
        inventory.set(entry.fileName, {
          fileName: entry.fileName,
          uncompressedSize: entry.uncompressedSize,
        });
        if (entry.fileName === MODEL_PACK_MANIFEST_FILENAME) {
          manifestPayload = await readZipEntry(
            zipFile,
            entry,
            MODEL_PACK_MAX_MANIFEST_BYTES
          );
        }
        zipFile.readEntry();
      } catch (error) {
        fail(error);
      }
    });
    zipFile.on('end', () => {
      if (settled) {
        return;
      }
      settled = true;
      if (manifestPayload === null) {
        reject(
          new ModelPackError(
            'missing_manifest',
            'Model Pack is missing manifest.json. Download or build the pack again.'
          )
        );
        return;
      }
      resolve({ inventory, manifestPayload });
    });
    zipFile.readEntry();
  });
}

async function extractZipFiles(archivePath, destination, expectedNames, manifest) {
  const expected = new Set(expectedNames);
  const declared = new Map(manifest.files.map((entry) => [entry.path, entry]));
  const zipFile = await openZip(archivePath);
  return new Promise((resolve, reject) => {
    let settled = false;
    const fail = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      try {
        zipFile.close();
      } catch (_closeError) {
        // ignore
      }
      reject(normalizeArchiveError(
        error,
        'Could not extract the Model Pack. Download it again.'
      ));
    };
    zipFile.on('error', fail);
    zipFile.on('entry', (entry) => {
      if (!expected.has(entry.fileName)) {
        zipFile.readEntry();
        return;
      }
      const manifestEntry = declared.get(entry.fileName);
      if (manifestEntry && entry.uncompressedSize !== manifestEntry.sizeBytes) {
        fail(
          new ModelPackError(
            'size_mismatch',
            `${entry.fileName} has the wrong size. Download or build the pack again.`
          )
        );
        return;
      }
      zipFile.openReadStream(entry, (error, input) => {
        if (error) {
          fail(error);
          return;
        }
        const output = fs.createWriteStream(path.join(destination, entry.fileName), {
          flags: 'wx',
          mode: 0o600,
        });
        input.on('error', fail);
        output.on('error', fail);
        output.on('finish', () => zipFile.readEntry());
        input.pipe(output);
      });
    });
    zipFile.on('end', () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    });
    zipFile.readEntry();
  });
}

async function buildInspection(root, manifest, warnings, cleanup) {
  await validatePayload(root, manifest);
  const modelfilePayload = await readBoundedFile(
    path.join(root, manifest.modelfile),
    MODEL_PACK_MAX_MODELFILE_BYTES,
    'unsafe_modelfile',
    'Modelfile exceeds the safe size limit. Rebuild the pack.'
  );
  const parsedModelfile = parseModelPackModelfile(modelfilePayload, manifest.ggufFile);
  const licensePayload = await readBoundedFile(
    path.join(root, manifest.license.file),
    MODEL_PACK_MAX_LICENSE_BYTES,
    'invalid_license_file',
    'The license text exceeds the safe size limit. Rebuild the pack.'
  );
  try {
    new TextDecoder('utf-8', { fatal: true }).decode(licensePayload);
  } catch (_error) {
    throw new ModelPackError(
      'invalid_license_file',
      'The declared license must be UTF-8 text. Rebuild the pack.'
    );
  }
  return {
    root,
    manifest,
    modelfile: parsedModelfile,
    ggufPath: path.join(root, manifest.ggufFile),
    modelfilePath: path.join(root, manifest.modelfile),
    licensePath: path.join(root, manifest.license.file),
    warnings,
    cleanup,
  };
}

async function inspectDirectory(source, diskFreeProvider) {
  const manifestPath = path.join(source, MODEL_PACK_MANIFEST_FILENAME);
  let manifestPayload;
  try {
    manifestPayload = await readBoundedFile(
      manifestPath,
      MODEL_PACK_MAX_MANIFEST_BYTES,
      'invalid_manifest',
      'manifest.json is too large. Build the pack again.'
    );
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      throw new ModelPackError(
        'missing_manifest',
        'Model Pack is missing manifest.json. Download or build the pack again.'
      );
    }
    throw error;
  }
  const manifest = parseModelPackManifest(manifestPayload);
  validateManifestRoleSizes(manifest);
  const inventory = await readDirectoryInventory(source);
  const expected = new Set([
    MODEL_PACK_MANIFEST_FILENAME,
    ...manifest.files.map((entry) => entry.path),
  ]);
  const warnings = inventory
    .filter((name) => !expected.has(name))
    .map(unexpectedWarning);
  const verifiedPayloadSize = await prevalidateDirectoryPayloads(source, manifest);
  await checkDisk(
    os.tmpdir(),
    manifest,
    true,
    diskFreeProvider,
    verifiedPayloadSize
  );
  const temporaryRoot = await fs.promises.mkdtemp(
    path.join(os.tmpdir(), 'stockpulse-model-pack-')
  );
  let currentName = MODEL_PACK_MANIFEST_FILENAME;
  try {
    await fs.promises.writeFile(
      path.join(temporaryRoot, MODEL_PACK_MANIFEST_FILENAME),
      manifestPayload,
      { flag: 'wx', mode: 0o600 }
    );
    const copyState = { bytes: 0 };
    for (const fileEntry of manifest.files) {
      currentName = fileEntry.path;
      const sourcePath = path.join(source, fileEntry.path);
      await copyDeclaredFile(
        sourcePath,
        path.join(temporaryRoot, fileEntry.path),
        fileEntry,
        copyState
      );
    }
    return await buildInspection(
      temporaryRoot,
      manifest,
      warnings,
      () => fs.promises.rm(temporaryRoot, { recursive: true, force: true })
    );
  } catch (error) {
    await fs.promises.rm(temporaryRoot, { recursive: true, force: true });
    if (error instanceof ModelPackError) {
      throw error;
    }
    if (error && error.code === 'ENOENT') {
      throw new ModelPackError(
        'missing_file',
        `Model Pack is missing ${currentName}. Download or build the pack again.`
      );
    }
    throw new ModelPackError(
      'file_read_failed',
      'Could not snapshot the Model Pack directory. Check permissions and try again.'
    );
  }
}

async function inspectArchive(source, diskFreeProvider) {
  let catalog;
  try {
    catalog = await readZipInventory(source);
  } catch (error) {
    if (error instanceof ModelPackError) {
      throw error;
    }
    throw new ModelPackError(
      'invalid_archive',
      'The selected file is not a readable Model Pack archive. Download it again.'
    );
  }
  const manifest = parseModelPackManifest(catalog.manifestPayload);
  validateManifestRoleSizes(manifest);
  const expected = new Set([
    MODEL_PACK_MANIFEST_FILENAME,
    ...manifest.files.map((entry) => entry.path),
  ]);
  for (const name of expected) {
    if (!catalog.inventory.has(name)) {
      throw new ModelPackError(
        'missing_file',
        `Model Pack is missing ${name}. Download or build the pack again.`
      );
    }
  }
  const warnings = [...catalog.inventory.keys()]
    .filter((name) => !expected.has(name))
    .map(unexpectedWarning)
    .sort();
  await checkDisk(os.tmpdir(), manifest, true, diskFreeProvider);
  const temporaryRoot = await fs.promises.mkdtemp(
    path.join(os.tmpdir(), 'stockpulse-model-pack-')
  );
  try {
    await extractZipFiles(source, temporaryRoot, expected, manifest);
    return await buildInspection(
      temporaryRoot,
      manifest,
      warnings,
      () => fs.promises.rm(temporaryRoot, { recursive: true, force: true })
    );
  } catch (error) {
    await fs.promises.rm(temporaryRoot, { recursive: true, force: true });
    throw error;
  }
}

async function inspectModelPack(source, { diskFreeProvider = defaultDiskFreeBytes } = {}) {
  const sourcePath = path.resolve(String(source || ''));
  let sourceStat;
  try {
    sourceStat = await fs.promises.lstat(sourcePath);
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      throw new ModelPackError(
        'pack_not_found',
        'The selected Model Pack does not exist. Select it again.'
      );
    }
    throw error;
  }
  if (sourceStat.isSymbolicLink()) {
    throw new ModelPackError(
      'unsafe_package_entry',
      'The selected Model Pack cannot be a symbolic link. Select the original pack.'
    );
  }
  if (sourceStat.isDirectory()) {
    return inspectDirectory(sourcePath, diskFreeProvider);
  }
  if (!sourceStat.isFile()) {
    throw new ModelPackError(
      'unsupported_archive',
      'Select a Model Pack directory, .modelpack file, or ZIP archive.'
    );
  }
  if (sourceStat.size > MODEL_PACK_MAX_BYTES) {
    throw new ModelPackError(
      'model_pack_too_large',
      'This Model Pack exceeds the 64 GiB limit. Build or select a smaller pack.'
    );
  }
  return inspectArchive(sourcePath, diskFreeProvider);
}

function spawnOllamaCreate(
  inspected,
  {
    spawnImpl = spawn,
    timeoutMs = MODEL_PACK_CREATE_TIMEOUT_MS,
    env = process.env,
    runtimeCommand = MODEL_PACK_OLLAMA_BINARY,
  } = {}
) {
  if (typeof runtimeCommand !== 'string' || !runtimeCommand.trim() || /[\u0000\r\n]/.test(runtimeCommand)) {
    throw new TypeError('runtimeCommand must be a trusted executable path');
  }
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawnImpl(
        runtimeCommand,
        ['create', inspected.manifest.modelId, '-f', inspected.modelfilePath],
        {
          cwd: inspected.root,
          env: { ...env },
          windowsHide: true,
          shell: false,
          stdio: 'ignore',
        }
      );
    } catch (_error) {
      reject(
        new ModelPackError(
          'ollama_unavailable',
          'Ollama could not be started. Install or start Ollama and try again.'
        )
      );
      return;
    }
    let settled = false;
    const finish = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      if (error) {
        reject(error);
      } else {
        resolve();
      }
    };
    const timer = setTimeout(() => {
      if (child && typeof child.kill === 'function') {
        child.kill();
      }
      finish(
        new ModelPackError(
          'ollama_create_timeout',
          'Ollama did not finish creating the model in time. Check Ollama and try again.'
        )
      );
    }, Math.max(1, Number(timeoutMs) || MODEL_PACK_CREATE_TIMEOUT_MS));
    child.once('error', () => {
      finish(
        new ModelPackError(
          'ollama_unavailable',
          'Ollama could not be started. Install or start Ollama and try again.'
        )
      );
    });
    child.once('exit', (code, signal) => {
      if (code === 0 && !signal) {
        finish();
        return;
      }
      finish(
        new ModelPackError(
          'ollama_create_failed',
          'Ollama could not create this model. Check Ollama logs and try again.'
        )
      );
    });
  });
}

async function importModelPack(
  source,
  {
    spawnImpl = spawn,
    onProgress = () => undefined,
    diskFreeProvider = defaultDiskFreeBytes,
    timeoutMs = MODEL_PACK_CREATE_TIMEOUT_MS,
    env = process.env,
    runtimeCommand = MODEL_PACK_OLLAMA_BINARY,
  } = {}
) {
  const inspected = await inspectModelPack(source, { diskFreeProvider });
  try {
    onProgress(35, 'Model Pack verified');
    await spawnOllamaCreate(inspected, {
      spawnImpl,
      timeoutMs,
      env,
      runtimeCommand,
    });
    onProgress(90, 'Model created in Ollama');
    return {
      modelId: inspected.manifest.modelId,
      displayName: inspected.manifest.displayName,
      minimumMemoryGb: inspected.manifest.minimumMemoryGb,
      licenseId: inspected.manifest.license.id,
      warnings: [...inspected.warnings],
    };
  } finally {
    await inspected.cleanup();
  }
}

module.exports = {
  MODEL_PACK_ALLOWED_INSTRUCTIONS,
  MODEL_PACK_CREATE_TIMEOUT_MS,
  MODEL_PACK_FORMAT_VERSION,
  MODEL_PACK_MANIFEST_FILENAME,
  MODEL_PACK_MAX_BYTES,
  MODEL_PACK_MAX_ENTRIES,
  MODEL_PACK_OLLAMA_BINARY,
  ModelPackError,
  importModelPack,
  inspectModelPack,
  parseModelPackManifest,
  parseModelPackModelfile,
  sha256File,
  spawnOllamaCreate,
};
