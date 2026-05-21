#!/usr/bin/env node
import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { copyFile, mkdir, open, readFile, realpath, rename, rm, stat, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, normalize, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SOURCE_DEFAULTS = {
  "claude-code": ".claude/projects",
  codex: ".codex/sessions",
  "pi-coding-agent": ".pi/agent/sessions",
};

const ARCHIVE_VERSION = 1;
const ARCHIVER_VERSION = "middens-archive-plugin-0.1.0";
const DEFAULT_INTERVAL_MINUTES = 60;

export async function archiveSessions(options) {
  const source = options.source;
  if (!SOURCE_DEFAULTS[source]) throw new Error(`unsupported source ${JSON.stringify(source)}`);

  const archiveRootRaw = options.archiveRoot || process.env.MIDDENS_ARCHIVE_ROOT;
  if (!archiveRootRaw || !archiveRootRaw.trim()) {
    return { skipped: true, reason: "MIDDENS_ARCHIVE_ROOT is unset" };
  }

  const archiveRoot = normalizeAbsolute(archiveRootRaw.trim());
  const sourceRoot = normalizeAbsolute(options.sourceRoot || join(homeDir(), SOURCE_DEFAULTS[source]));
  const quiet = Boolean(options.quiet);
  const debounce = Boolean(options.debounce);
  const dryRun = Boolean(options.dryRun);
  const intervalMs = readPositiveNumberEnv("MIDDENS_ARCHIVE_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES, 1) * 60 * 1000;

  if (!(await exists(sourceRoot))) {
    return { skipped: true, reason: `source root does not exist: ${sourceRoot}` };
  }

  await checkOverlap(sourceRoot, archiveRoot);

  if (dryRun) {
    const files = await discoverJsonl(sourceRoot);
    const objects = [];
    for (const originalPath of files) {
      const meta = await stat(originalPath);
      objects.push({ originalPath, sha256: await hashFile(originalPath), sizeBytes: meta.size });
    }
    const result = { skipped: false, dryRun: true, source, files: files.length, objects };
    if (!quiet) printDryRun(result, archiveRoot);
    return result;
  }

  await mkdir(archiveRoot, { recursive: true });
  await checkOverlap(sourceRoot, archiveRoot);

  if (debounce && !(await debounceDue(archiveRoot, source, intervalMs))) {
    return { skipped: true, reason: "debounced" };
  }

  const lock = await acquireLock(archiveRoot);
  try {
    let manifest = await loadOrCreateManifest(archiveRoot);
    await validateDrift(manifest, archiveRoot);
    await writeGitignoreIfInsideWorktree(archiveRoot);

    const files = await discoverJsonl(sourceRoot);
    const observedAt = new Date().toISOString();
    let copied = 0;
    let deduped = 0;
    let observationsAdded = 0;

    for (const originalPath of files) {
      const before = await stat(originalPath);
      const sourceMtime = before.mtime.toISOString();
      const sizeBytes = before.size;
      const sha256 = await hashFile(originalPath);
      const archivePath = objectRelPath(sha256);
      const destination = join(archiveRoot, archivePath);
      const canonicalPath = await realpath(originalPath).catch(() => undefined);
      const basename = originalPath.split(/[\\/]/).pop() || "";
      const observationId = observationIdFor(originalPath, canonicalPath, source, sha256);
      const enrichment = await enrichJsonl(originalPath, source);

      const afterHashStat = await stat(originalPath);
      if (afterHashStat.size !== sizeBytes || afterHashStat.mtime.toISOString() !== sourceMtime) {
        throw new Error(`source changed while archiving: ${originalPath}`);
      }

      const objectAlreadyRecorded = Boolean(manifest.objects[sha256]);
      const objectAlreadyPresent = await exists(destination);
      if (objectAlreadyPresent) {
        const destinationHash = await hashFile(destination);
        if (destinationHash !== sha256) {
          throw new Error(`destination collision: ${destination} already exists with hash ${destinationHash}, expected ${sha256}`);
        }
      }

      if (!objectAlreadyRecorded && !objectAlreadyPresent) {
        await atomicCopy(originalPath, destination, sha256);
        copied += 1;
      } else {
        deduped += 1;
      }

      const afterCopyStat = await stat(originalPath);
      if (afterCopyStat.size !== sizeBytes || afterCopyStat.mtime.toISOString() !== sourceMtime) {
        throw new Error(`source changed while archiving: ${originalPath}`);
      }

      if (!manifest.objects[sha256]) {
        manifest.objects[sha256] = {
          sha256,
          size_bytes: sizeBytes,
          archive_path: archivePath,
          first_archived_at: observedAt,
          parser_status: enrichment.parser_status,
          parser_error: enrichment.parser_error,
          source_tool: source,
          session_count: enrichment.session_count,
          session_ids: enrichment.session_ids,
          first_timestamp: enrichment.first_timestamp,
          last_timestamp: enrichment.last_timestamp,
        };
      }

      if (!manifest.observations.some((obs) => obs.observation_id === observationId)) {
        manifest.observations.push({
          observation_id: observationId,
          source_tool: source,
          original_path: originalPath,
          canonical_path: canonicalPath,
          original_basename: basename,
          archive_path: archivePath,
          sha256,
          size_bytes: sizeBytes,
          source_mtime: sourceMtime,
          observed_at: observedAt,
        });
        observationsAdded += 1;
      }
    }

    manifest.updated_at = new Date().toISOString();
    await writeManifest(archiveRoot, manifest);
    await writeIndex(archiveRoot, manifest);
    await writeDebounceState(archiveRoot, source);

    const result = { skipped: false, source, files: files.length, copied, deduped, observationsAdded };
    if (!quiet) printSummary(result, archiveRoot);
    return result;
  } finally {
    await releaseLock(lock);
  }
}

function parseArgs(argv) {
  const out = { quiet: false, debounce: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const readOptionValue = (flag) => {
      const value = argv[++i];
      if (!value || value.startsWith("-")) {
        throw new Error(`${flag} requires a value; expected ${flag} <path-or-value>. Example: archive.mjs --source pi-coding-agent --to /private/archive-root`);
      }
      return value;
    };
    if (arg === "--source") out.source = readOptionValue("--source");
    else if (arg === "--to") out.archiveRoot = readOptionValue("--to");
    else if (arg === "--from") out.sourceRoot = readOptionValue("--from");
    else if (arg === "--quiet") out.quiet = true;
    else if (arg === "--debounce") out.debounce = true;
    else if (arg === "--dry-run") out.dryRun = true;
    else if (arg === "--help" || arg === "-h") {
      console.log("Usage: archive.mjs --source <claude-code|codex|pi-coding-agent> --to <archive-root> [--from <source-root>] [--quiet] [--debounce] [--dry-run]");
      process.exit(0);
    } else {
      throw new Error(`unknown argument ${arg}`);
    }
  }
  return out;
}

function homeDir() {
  const home = process.env.HOME || process.env.USERPROFILE;
  if (!home) throw new Error("HOME is unset; cannot discover source session directory");
  return home;
}

function normalizeAbsolute(path) {
  return normalize(isAbsolute(path) ? path : resolve(process.cwd(), path));
}

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function discoverJsonl(root) {
  const entries = [];
  async function walk(dir) {
    const dirents = await import("node:fs/promises").then((fs) => fs.readdir(dir, { withFileTypes: true }));
    dirents.sort((a, b) => a.name.localeCompare(b.name));
    for (const dirent of dirents) {
      const path = join(dir, dirent.name);
      if (dirent.isDirectory()) await walk(path);
      else if (dirent.isFile() && path.endsWith(".jsonl")) entries.push(normalizeAbsolute(path));
    }
  }
  await walk(root);
  return entries.sort();
}

async function hashFile(path) {
  const hash = createHash("sha256");
  await new Promise((resolvePromise, reject) => {
    createReadStream(path).on("data", (chunk) => hash.update(chunk)).on("error", reject).on("end", resolvePromise);
  });
  return hash.digest("hex");
}

function objectRelPath(sha256) {
  return join("objects", "sha256", sha256.slice(0, 2), `${sha256}.jsonl`);
}

async function atomicCopy(source, destination, expectedHash) {
  await mkdir(dirname(destination), { recursive: true });
  const tmp = `${destination}.tmp-${process.pid}-${randomUUID()}`;
  await copyFile(source, tmp);
  const actualHash = await hashFile(tmp);
  if (actualHash !== expectedHash) {
    await rm(tmp, { force: true });
    throw new Error(`copy verification failed for ${source}`);
  }
  await rename(tmp, destination);
}

async function loadOrCreateManifest(archiveRoot) {
  const path = join(archiveRoot, "manifest.json");
  if (await exists(path)) {
    const manifest = JSON.parse(await readFile(path, "utf8"));
    if (manifest.archive_manifest_version !== ARCHIVE_VERSION) {
      throw new Error(`manifest version mismatch: expected ${ARCHIVE_VERSION}, got ${manifest.archive_manifest_version}`);
    }
    manifest.objects ||= {};
    manifest.observations ||= [];
    return manifest;
  }
  const now = new Date().toISOString();
  return {
    archive_manifest_version: ARCHIVE_VERSION,
    created_at: now,
    updated_at: now,
    middens_version: ARCHIVER_VERSION,
    archive_root: archiveRoot,
    objects: {},
    observations: [],
  };
}

async function writeManifest(archiveRoot, manifest) {
  const tmp = join(archiveRoot, `.tmp-manifest-${process.pid}-${randomUUID()}`);
  await writeFile(tmp, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  await rename(tmp, join(archiveRoot, "manifest.json"));
}

async function writeIndex(archiveRoot, manifest) {
  const dir = join(archiveRoot, "indexes");
  await mkdir(dir, { recursive: true });
  const lines = [];
  for (const obs of manifest.observations) {
    const obj = manifest.objects[obs.sha256];
    if (!obj) continue;
    lines.push(JSON.stringify({
      observation_id: obs.observation_id,
      sha256: obs.sha256,
      source_tool: obs.source_tool,
      original_path: obs.original_path,
      archive_path: obs.archive_path,
      parser_status: obj.parser_status,
      session_count: obj.session_count,
      session_ids: obj.session_ids,
      first_timestamp: obj.first_timestamp,
      last_timestamp: obj.last_timestamp,
    }));
  }
  const tmp = join(dir, `.tmp-index-${process.pid}-${randomUUID()}`);
  await writeFile(tmp, lines.length ? `${lines.join("\n")}\n` : "", "utf8");
  await rename(tmp, join(dir, "sessions.jsonl"));
}

async function validateDrift(manifest, archiveRoot) {
  for (const [sha, obj] of Object.entries(manifest.objects || {})) {
    const path = join(archiveRoot, obj.archive_path);
    if (!(await exists(path))) throw new Error(`archive drift detected: object ${sha} missing at ${path}`);
    const actual = await hashFile(path);
    if (actual !== sha) throw new Error(`archive drift detected: object ${sha} hashes to ${actual}`);
  }
}

async function acquireLock(archiveRoot) {
  const path = join(archiveRoot, ".archive.lock");
  try {
    const handle = await open(path, "wx");
    await handle.writeFile(JSON.stringify({ pid: process.pid, started_at: new Date().toISOString() }));
    await handle.close();
    return path;
  } catch (error) {
    if (error?.code === "EEXIST") throw new Error(`archive lock exists at ${path}`);
    throw error;
  }
}

async function releaseLock(path) {
  await rm(path, { force: true });
}

async function checkOverlap(sourceRoot, archiveRoot) {
  const variants = new Set([sourceRoot, await canonicalizeExistingOrNearest(sourceRoot)]);
  const archiveVariants = new Set([archiveRoot, await canonicalizeExistingOrNearest(archiveRoot)]);
  for (const source of variants) {
    for (const archive of archiveVariants) {
      if (containsPath(source, archive)) throw new Error(`archive root overlaps source root: ${archiveRoot}`);
      if (containsPath(archive, source)) throw new Error(`source root overlaps archive root: ${sourceRoot}`);
    }
  }
}

async function canonicalizeExistingOrNearest(path) {
  const absolute = normalizeAbsolute(path);
  let current = absolute;
  while (!(await exists(current))) {
    const parent = dirname(current);
    if (parent === current) return absolute;
    current = parent;
  }
  const canonicalBase = await realpath(current).catch(() => current);
  const remainder = relative(current, absolute);
  return remainder ? join(canonicalBase, remainder) : canonicalBase;
}

function containsPath(parent, child) {
  const rel = relative(parent, child);
  return rel === "" || (rel !== "" && !rel.startsWith("..") && !isAbsolute(rel));
}

async function writeGitignoreIfInsideWorktree(archiveRoot) {
  let current = archiveRoot;
  while (current && current !== dirname(current)) {
    if (await exists(join(current, ".git"))) {
      const gitignore = join(archiveRoot, ".gitignore");
      const marker = "# middens archive plugin: raw transcripts";
      const block = `${marker}\n*\n!.gitignore\n`;
      const existing = await readFile(gitignore, "utf8").catch((error) => {
        if (error?.code === "ENOENT") return "";
        throw error;
      });
      if (existing.includes(marker)) return;
      const separator = existing.length === 0 || existing.endsWith("\n") ? "" : "\n";
      const next = existing.length === 0 ? block : `${existing}${separator}\n${block}`;
      const tmp = `${gitignore}.tmp-${process.pid}-${randomUUID()}`;
      await writeFile(tmp, next, "utf8");
      await rename(tmp, gitignore);
      return;
    }
    current = dirname(current);
  }
}

async function enrichJsonl(path, source) {
  const raw = await readFile(path, "utf8");
  if (!raw.trim()) return { parser_status: "empty_placeholder", parser_error: null, session_count: 0, session_ids: [], first_timestamp: null, last_timestamp: null };
  const sessionIds = new Set();
  const timestamps = [];
  let parsed = 0;
  for (const line of raw.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      const value = JSON.parse(line);
      parsed += 1;
      if (source === "pi-coding-agent") collectPiSessionIds(value, sessionIds);
      else collectSessionIds(value, sessionIds);
      collectTimestamps(value, timestamps);
    } catch (error) {
      return { parser_status: "unparseable", parser_error: error.message, session_count: 0, session_ids: [], first_timestamp: null, last_timestamp: null };
    }
  }
  timestamps.sort();
  const ids = [...sessionIds].sort();
  return {
    parser_status: parsed > 0 ? "parsed" : "empty_placeholder",
    parser_error: null,
    session_count: ids.length || (parsed > 0 ? 1 : 0),
    session_ids: ids,
    first_timestamp: timestamps[0] || null,
    last_timestamp: timestamps[timestamps.length - 1] || null,
  };
}

function collectPiSessionIds(value, out) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return;
  if (
    value.type === "session" &&
    typeof value.id === "string" &&
    value.id.length <= 200 &&
    typeof value.cwd === "string" &&
    typeof value.version === "number"
  ) {
    out.add(value.id);
  }
}

function collectSessionIds(value, out) {
  if (!value || typeof value !== "object") return;
  for (const key of ["session_id", "sessionId", "sessionID", "conversation_id", "conversationId", "id"]) {
    if (typeof value[key] === "string" && value[key].length <= 200) out.add(value[key]);
  }
  for (const child of Object.values(value)) {
    if (child && typeof child === "object" && !Array.isArray(child)) collectSessionIds(child, out);
  }
}

function collectTimestamps(value, out) {
  if (!value || typeof value !== "object") return;
  for (const key of ["timestamp", "created_at", "createdAt", "time"]) {
    if (typeof value[key] === "string") {
      const date = new Date(value[key]);
      if (!Number.isNaN(date.valueOf())) out.push(date.toISOString());
    }
  }
}

function observationIdFor(originalPath, canonicalPath, source, sha256) {
  const hash = createHash("sha256");
  hash.update(originalPath);
  hash.update("\0");
  if (canonicalPath) hash.update(canonicalPath);
  hash.update("\0");
  hash.update(source);
  hash.update("\0");
  hash.update(sha256);
  return hash.digest("hex");
}

function readPositiveNumberEnv(name, defaultValue, minValue) {
  const raw = process.env[name];
  if (!raw || !raw.trim()) return defaultValue;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < minValue) throw new Error(`${name} must be a number >= ${minValue}; got ${JSON.stringify(raw)}`);
  return value;
}

async function debounceDue(archiveRoot, source, intervalMs) {
  const statePath = join(archiveRoot, ".middens-archive-state.json");
  try {
    const state = JSON.parse(await readFile(statePath, "utf8"));
    const last = Date.parse(state[source]?.last_run_at || "");
    return !Number.isFinite(last) || Date.now() - last >= intervalMs;
  } catch {
    return true;
  }
}

async function writeDebounceState(archiveRoot, source) {
  const statePath = join(archiveRoot, ".middens-archive-state.json");
  let state = {};
  try { state = JSON.parse(await readFile(statePath, "utf8")); } catch {}
  state[source] = { last_run_at: new Date().toISOString() };
  const tmp = `${statePath}.tmp-${process.pid}-${randomUUID()}`;
  await writeFile(tmp, `${JSON.stringify(state, null, 2)}\n`, "utf8");
  await rename(tmp, statePath);
}

function printDryRun(result, archiveRoot) {
  console.error(`archive dry-run: ${result.source} -> ${archiveRoot}`);
  console.error(`  files discovered: ${result.files}`);
  for (const object of result.objects) {
    console.error(`  would archive ${object.originalPath} (${object.sizeBytes} bytes, sha256 ${object.sha256})`);
  }
}

function printSummary(result, archiveRoot) {
  console.error(`archive complete: ${result.source} -> ${archiveRoot}`);
  console.error(`  files discovered: ${result.files}`);
  console.error(`  objects copied: ${result.copied}`);
  console.error(`  objects deduped: ${result.deduped}`);
  console.error(`  observations added: ${result.observationsAdded}`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(`middens archive plugin error: ${error.message}`);
    process.exit(1);
  }
  archiveSessions(options).then((result) => {
    if (result.skipped && !process.argv.includes("--quiet")) console.error(`archive skipped: ${result.reason}`);
  }).catch((error) => {
    console.error(`middens archive plugin error: ${error.message}`);
    process.exit(1);
  });
}
