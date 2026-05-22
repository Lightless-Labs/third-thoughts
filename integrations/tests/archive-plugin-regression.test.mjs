import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { archiveSessions } from "../pi/middens-archive/scripts/archive.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const integrationsRoot = join(__dirname, "..");
const piScript = join(integrationsRoot, "pi", "middens-archive", "scripts", "archive.mjs");
const claudeScript = join(integrationsRoot, "claude-code", "middens-archive", "scripts", "archive.mjs");
const codexScript = join(integrationsRoot, "codex", "middens-archive", "scripts", "archive.mjs");

async function tempDir(t) {
  const dir = await mkdtemp(join(tmpdir(), "middens-archive-plugin-test-"));
  t.after(async () => {
    await rm(dir, { recursive: true, force: true });
  });
  return dir;
}

async function writePiSession(sourceRoot, name = "session.jsonl") {
  await mkdir(sourceRoot, { recursive: true });
  const path = join(sourceRoot, name);
  await writeFile(
    path,
    [
      JSON.stringify({ type: "session", id: "session-header-id", cwd: "/tmp/project", version: 1, timestamp: "2026-05-21T00:00:00Z" }),
      JSON.stringify({ type: "message", id: "entry-id-one", timestamp: "2026-05-21T00:00:01Z", message: { role: "user", content: "hello" } }),
      JSON.stringify({ type: "message", id: "entry-id-two", timestamp: "2026-05-21T00:00:02Z", message: { role: "assistant", content: "hi" } }),
      "",
    ].join("\n"),
    "utf8",
  );
  return path;
}

function runNode(args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, {
      cwd: integrationsRoot,
      env: { ...process.env, ...options.env },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code, stdout, stderr }));
  });
}

async function readManifest(archiveRoot) {
  return JSON.parse(await readFile(join(archiveRoot, "manifest.json"), "utf8"));
}

function objectPathFor(archiveRoot, sha256) {
  return join(archiveRoot, "objects", "sha256", sha256.slice(0, 2), `${sha256}.jsonl`);
}

function sha256(text) {
  return createHash("sha256").update(text).digest("hex");
}

test("bundled archiver scripts stay byte-for-byte identical", async () => {
  const pi = await readFile(piScript, "utf8");
  assert.equal(await readFile(claudeScript, "utf8"), pi);
  assert.equal(await readFile(codexScript, "utf8"), pi);
});

test("CLI rejects missing or flag-looking option values clearly", async () => {
  const missingTo = await runNode([piScript, "--source", "pi-coding-agent", "--to", "--quiet"]);
  assert.notEqual(missingTo.code, 0);
  assert.match(missingTo.stderr, /--to requires a value/);
  assert.doesNotMatch(missingTo.stderr, /\n\s+at /);

  const missingSource = await runNode([piScript, "--source", "--to", "/tmp/archive"]);
  assert.notEqual(missingSource.code, 0);
  assert.match(missingSource.stderr, /--source requires a value/);
  assert.doesNotMatch(missingSource.stderr, /\n\s+at /);
});

test("archiver runs self-contained without middens on PATH", async (t) => {
  const root = await tempDir(t);
  const sourceRoot = join(root, "source");
  const archiveRoot = join(root, "archive");
  await writePiSession(sourceRoot);

  const result = await runNode(
    [piScript, "--source", "pi-coding-agent", "--from", sourceRoot, "--to", archiveRoot, "--quiet"],
    { env: { PATH: join(root, "empty-path") } },
  );

  assert.equal(result.code, 0, result.stderr);
  const manifest = await readManifest(archiveRoot);
  assert.equal(Object.keys(manifest.objects).length, 1);
});

test("existing worktree .gitignore receives managed raw-transcript protection", async (t) => {
  const root = await tempDir(t);
  const sourceRoot = join(root, "source");
  const worktree = join(root, "worktree");
  const archiveRoot = join(worktree, "archive");
  await writePiSession(sourceRoot);
  await mkdir(join(worktree, ".git"), { recursive: true });
  await mkdir(archiveRoot, { recursive: true });
  await writeFile(join(archiveRoot, ".gitignore"), "keep-this-line\n", "utf8");

  await archiveSessions({ source: "pi-coding-agent", sourceRoot, archiveRoot, quiet: true });

  const gitignore = await readFile(join(archiveRoot, ".gitignore"), "utf8");
  assert.match(gitignore, /keep-this-line/);
  assert.match(gitignore, /# middens archive plugin: raw transcripts/);
  assert.match(gitignore, /^\*$/m);
  assert.match(gitignore, /^!\.gitignore$/m);
});

test("symlinked parents cannot hide source/archive overlap", async (t) => {
  const root = await tempDir(t);
  const sourceRoot = join(root, "source-real");
  const archiveViaSymlink = join(root, "source-link", "archive");
  await mkdir(sourceRoot, { recursive: true });
  await symlink(sourceRoot, join(root, "source-link"), "dir");

  await assert.rejects(
    () => archiveSessions({ source: "pi-coding-agent", sourceRoot, archiveRoot: archiveViaSymlink, quiet: true }),
    /archive root overlaps source root/,
  );
});

test("Pi enrichment uses the session header ID instead of every entry ID", async (t) => {
  const root = await tempDir(t);
  const sourceRoot = join(root, "source");
  const archiveRoot = join(root, "archive");
  await writePiSession(sourceRoot);

  await archiveSessions({ source: "pi-coding-agent", sourceRoot, archiveRoot, quiet: true });

  const manifest = await readManifest(archiveRoot);
  const object = Object.values(manifest.objects)[0];
  assert.equal(object.session_count, 1);
  assert.deepEqual(object.session_ids, ["session-header-id"]);
});

test("archive drift stays loud", async (t) => {
  const root = await tempDir(t);
  const sourceRoot = join(root, "source");
  const archiveRoot = join(root, "archive");
  await writePiSession(sourceRoot);
  await archiveSessions({ source: "pi-coding-agent", sourceRoot, archiveRoot, quiet: true });

  const manifest = await readManifest(archiveRoot);
  const object = Object.values(manifest.objects)[0];
  await rm(join(archiveRoot, object.archive_path));

  await assert.rejects(
    () => archiveSessions({ source: "pi-coding-agent", sourceRoot, archiveRoot, quiet: true }),
    /archive drift detected/,
  );
});

test("destination collisions stay loud", async (t) => {
  const root = await tempDir(t);
  const sourceRoot = join(root, "source");
  const archiveRoot = join(root, "archive");
  const sourceContent = "{\"type\":\"session\",\"id\":\"collision-session\",\"cwd\":\"/tmp/project\",\"version\":1}\n";
  await mkdir(sourceRoot, { recursive: true });
  await writeFile(join(sourceRoot, "session.jsonl"), sourceContent, "utf8");

  const digest = sha256(sourceContent);
  const destination = objectPathFor(archiveRoot, digest);
  await mkdir(dirname(destination), { recursive: true });
  await writeFile(destination, "not the source content\n", "utf8");

  await assert.rejects(
    () => archiveSessions({ source: "pi-coding-agent", sourceRoot, archiveRoot, quiet: true }),
    /destination collision/,
  );
});
