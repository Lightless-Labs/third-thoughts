//! `middens archive` — local session log backup.

pub mod copy;
pub mod discover;
pub mod manifest;
pub mod parse;
pub mod plan;

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use chrono::{DateTime, Utc};

use crate::session::SourceTool;

use copy::{atomic_copy, hash_file, object_rel_path};
use discover::{ArchiveSource, Candidate, discover_candidates, normalize_absolute_path};
use manifest::{
    ArchiveManifest, ArchivedObject, ParserStatus, SourceObservation, has_observation,
    observation_id, validate_drift, write_atomic,
};
use parse::{ParseEnrichment, enrich};
use plan::PlanSummary;

/// Configuration for an archive run.
#[derive(Debug, Clone)]
pub struct ArchiveConfig {
    pub archive_root: PathBuf,
    pub sources: Vec<SourceSpec>,
    pub dry_run: bool,
    pub yes: bool,
    pub require_parseable: bool,
}

/// A source specification with optional root override.
#[derive(Debug, Clone)]
pub struct SourceSpec {
    pub source: ArchiveSource,
    pub override_root: Option<PathBuf>,
}

/// Result of an archive run.
#[derive(Debug, Clone)]
pub struct ArchiveResult {
    pub objects_copied: usize,
    pub objects_deduped: usize,
    pub observations_added: usize,
    pub parseable: usize,
    pub unparseable: usize,
    pub parser_errors: usize,
    pub empty_placeholders: usize,
}

#[derive(Debug, Clone)]
struct PlannedCandidate {
    candidate: Candidate,
    source_tool_slug: String,
    sha256: String,
    size_bytes: u64,
    source_mtime: DateTime<Utc>,
    archive_path: PathBuf,
    observation_id: String,
    enrichment: ParseEnrichment,
    copy_required: bool,
    object_required: bool,
    observation_required: bool,
}

/// Run the archive operation.
pub fn run(config: ArchiveConfig) -> Result<ArchiveResult> {
    let archive_root = normalize_absolute_path(&config.archive_root)?;

    // Validate overlap: archive must not be equal to, inside, or above any source root.
    for spec in &config.sources {
        let source_root = spec
            .override_root
            .clone()
            .unwrap_or_else(|| spec.source.default_root());
        if source_root.exists() {
            check_overlap(&source_root, &archive_root).with_context(|| {
                format!(
                    "overlap check failed for source '{}'",
                    spec.source.tool_name()
                )
            })?;
        }
    }

    // Dry-run: discover + plan only, writes nothing.
    if config.dry_run {
        let (candidates, not_present) = discover_candidates(
            &config
                .sources
                .iter()
                .map(|s| (s.source, s.override_root.clone()))
                .collect::<Vec<_>>(),
        )?;

        let (mut summary, planned) =
            prepare_candidates(&candidates, &archive_root, None, config.require_parseable)?;
        summary.sources_not_present = not_present;

        for plan in &planned {
            let action = if plan.copy_required { "copy" } else { "dedupe" };
            eprintln!(
                "  {} {} -> {}",
                action,
                plan.candidate.basename,
                plan.archive_path.display()
            );
        }

        summary.print(true);
        return Ok(result_from_summary(&summary));
    }

    // Non-dry-run: require consent.
    if !config.yes {
        eprintln!(
            "WARNING: middens archive copies raw agent session transcripts, including prompts,\n\
             tool outputs, paths, and possibly secrets, into {}.\n\
             Keep this directory private. Re-run with --dry-run to inspect the plan first.",
            archive_root.display()
        );
        bail!("archive aborted: re-run with --yes to confirm");
    }

    // Print warning even with --yes.
    eprintln!(
        "WARNING: middens archive copies raw agent session transcripts, including prompts,\n\
         tool outputs, paths, and possibly secrets, into {}.\n\
         Keep this directory private. Re-run with --dry-run to inspect the plan first.",
        archive_root.display()
    );

    // Ensure archive root exists.
    std::fs::create_dir_all(&archive_root)
        .with_context(|| format!("creating archive root {}", archive_root.display()))?;

    // Acquire lock.
    let _lock = ArchiveLock::acquire(&archive_root)?;

    // Load or create manifest.
    let middens_version = env!("CARGO_PKG_VERSION");
    let mut manifest = manifest::load_or_create(&archive_root, middens_version)?;

    // Validate drift.
    validate_drift(&manifest, &archive_root).context("archive drift detected")?;

    // Git worktree safety.
    if is_inside_git_worktree(&archive_root) {
        let gitignore = archive_root.join(".gitignore");
        if !gitignore.exists() {
            std::fs::write(&gitignore, "*\n!.gitignore\n")
                .with_context(|| format!("writing {}", gitignore.display()))?;
        } else {
            let contents = std::fs::read_to_string(&gitignore)
                .with_context(|| format!("reading {}", gitignore.display()))?;
            if !contents.trim().lines().any(|l| l.trim() == "*") {
                eprintln!(
                    "warn: {} exists but does not contain a blanket ignore rule. Review it to ensure archived transcripts are not committed.",
                    gitignore.display()
                );
            }
        }
    }

    // Discover candidates.
    let (candidates, not_present) = discover_candidates(
        &config
            .sources
            .iter()
            .map(|s| (s.source, s.override_root.clone()))
            .collect::<Vec<_>>(),
    )?;

    let (summary, planned) = prepare_candidates(
        &candidates,
        &archive_root,
        Some(&manifest),
        config.require_parseable,
    )?;
    let result = result_from_summary(&summary);

    let mut objects_in_run: BTreeMap<String, ArchivedObject> = BTreeMap::new();

    for plan in &planned {
        if !plan.copy_required {
            continue;
        }

        atomic_copy(&plan.candidate.original_path, &plan.sha256, &archive_root)?;

        let post_copy_meta =
            std::fs::metadata(&plan.candidate.original_path).with_context(|| {
                format!(
                    "re-statting {} after copy",
                    plan.candidate.original_path.display()
                )
            })?;
        if post_copy_meta.len() != plan.size_bytes
            || mtime_to_datetime(&post_copy_meta) != plan.source_mtime
        {
            bail!(
                "source changed while archiving: {} (size or mtime changed). retry",
                plan.candidate.original_path.display()
            );
        }
    }

    for plan in planned {
        if plan.object_required {
            let obj = ArchivedObject {
                sha256: plan.sha256.clone(),
                size_bytes: plan.size_bytes,
                archive_path: plan.archive_path.to_string_lossy().to_string(),
                first_archived_at: Utc::now(),
                parser_status: plan.enrichment.status,
                parser_error: plan.enrichment.error.clone(),
                source_tool: plan.source_tool_slug.clone(),
                session_count: plan.enrichment.session_count,
                session_ids: plan.enrichment.session_ids.clone(),
                first_timestamp: plan.enrichment.first_timestamp,
                last_timestamp: plan.enrichment.last_timestamp,
            };
            objects_in_run.insert(plan.sha256.clone(), obj);
        }

        if plan.observation_required {
            manifest.observations.push(SourceObservation {
                observation_id: plan.observation_id,
                source_tool: plan.source_tool_slug,
                original_path: plan.candidate.original_path.to_string_lossy().to_string(),
                canonical_path: plan
                    .candidate
                    .canonical_path
                    .as_ref()
                    .map(|path| path.to_string_lossy().to_string()),
                original_basename: plan.candidate.basename,
                archive_path: plan.archive_path.to_string_lossy().to_string(),
                sha256: plan.sha256,
                size_bytes: plan.size_bytes,
                source_mtime: plan.source_mtime,
                observed_at: Utc::now(),
            });
        }
    }

    // Merge new objects into manifest.
    for (sha, obj) in objects_in_run {
        manifest.objects.insert(sha, obj);
    }

    manifest.updated_at = Utc::now();

    // Write manifest atomically.
    write_atomic(&manifest, &archive_root)?;

    // Write derived index.
    write_index(&manifest, &archive_root)?;

    // Print summary.
    eprintln!("archive complete:");
    eprintln!("  {} copied", result.objects_copied);
    eprintln!("  objects copied: {}", result.objects_copied);
    eprintln!("  objects deduped: {}", result.objects_deduped);
    eprintln!("  observations added: {}", result.observations_added);
    if !not_present.is_empty() {
        eprintln!("  sources not present: {}", not_present.join(", "));
    }
    eprintln!("  parseable: {}", result.parseable);
    eprintln!("  unparseable: {}", result.unparseable);
    eprintln!("  parser errors: {}", result.parser_errors);
    eprintln!("  empty placeholders: {}", result.empty_placeholders);

    Ok(result)
}

fn prepare_candidates(
    candidates: &[Candidate],
    archive_root: &Path,
    manifest: Option<&ArchiveManifest>,
    require_parseable: bool,
) -> Result<(PlanSummary, Vec<PlannedCandidate>)> {
    let mut summary = PlanSummary {
        candidates_discovered: candidates.len(),
        ..Default::default()
    };
    let mut seen_hashes = BTreeSet::new();
    let mut object_hashes_in_run = BTreeSet::new();
    let mut planned = Vec::with_capacity(candidates.len());

    for candidate in candidates {
        let pre_meta = std::fs::metadata(&candidate.original_path)
            .with_context(|| format!("stating {}", candidate.original_path.display()))?;
        let size_bytes = pre_meta.len();
        let source_mtime = mtime_to_datetime(&pre_meta);

        let sha256 = hash_file(&candidate.original_path)
            .with_context(|| format!("hashing {}", candidate.original_path.display()))?;
        let archive_path = object_rel_path(&sha256);
        let archive_object_path = archive_root.join(&archive_path);

        let source_tool = map_archive_source_to_source_tool(candidate.source);
        let source_tool_slug = candidate.source.tool_name().to_string();
        let enrichment = enrich(&candidate.original_path, source_tool)?;
        update_parse_counts(&mut summary, enrichment.status);

        if require_parseable && enrichment.status != ParserStatus::Parsed {
            bail!(
                "--require-parseable: {} is {} ({}). aborting before copying any objects or updating the manifest.",
                candidate.original_path.display(),
                enrichment.status,
                enrichment.error.as_deref().unwrap_or("no diagnostic")
            );
        }

        let post_meta = std::fs::metadata(&candidate.original_path)
            .with_context(|| format!("re-statting {}", candidate.original_path.display()))?;
        if post_meta.len() != size_bytes || mtime_to_datetime(&post_meta) != source_mtime {
            bail!(
                "source changed while archiving: {} (size or mtime changed). retry",
                candidate.original_path.display()
            );
        }

        let already_in_manifest =
            manifest.map_or(false, |manifest| manifest.objects.contains_key(&sha256));
        let already_in_archive = if archive_object_path.exists() {
            let existing_hash = hash_file(&archive_object_path).with_context(|| {
                format!("hashing existing object {}", archive_object_path.display())
            })?;
            if existing_hash != sha256 {
                bail!(
                    "destination collision: {} already exists but hashes to {} (expected {})",
                    archive_object_path.display(),
                    existing_hash,
                    sha256
                );
            }
            true
        } else {
            false
        };
        let already_seen = seen_hashes.contains(&sha256);
        let copy_required = !(already_in_manifest || already_in_archive || already_seen);

        if copy_required {
            summary.objects_to_copy += 1;
        } else {
            summary.objects_deduped += 1;
        }
        let object_required = !already_in_manifest && !object_hashes_in_run.contains(&sha256);
        seen_hashes.insert(sha256.clone());
        object_hashes_in_run.insert(sha256.clone());

        let canonical_path = candidate
            .canonical_path
            .as_ref()
            .map(|path| path.to_string_lossy().to_string());
        let observation_id = observation_id(
            &candidate.original_path.to_string_lossy(),
            canonical_path.as_deref(),
            &source_tool_slug,
            &sha256,
        );
        let observation_required =
            manifest.map_or(true, |manifest| !has_observation(manifest, &observation_id));
        if observation_required {
            summary.observations_to_add += 1;
        }

        planned.push(PlannedCandidate {
            candidate: candidate.clone(),
            source_tool_slug,
            sha256,
            size_bytes,
            source_mtime,
            archive_path,
            observation_id,
            enrichment,
            copy_required,
            object_required,
            observation_required,
        });
    }

    Ok((summary, planned))
}

fn update_parse_counts(summary: &mut PlanSummary, status: ParserStatus) {
    match status {
        ParserStatus::Parsed => summary.parseable += 1,
        ParserStatus::Unparseable => summary.unparseable += 1,
        ParserStatus::ParserError => summary.parser_errors += 1,
        ParserStatus::EmptyPlaceholder => summary.empty_placeholders += 1,
    }
}

fn result_from_summary(summary: &PlanSummary) -> ArchiveResult {
    ArchiveResult {
        objects_copied: summary.objects_to_copy,
        objects_deduped: summary.objects_deduped,
        observations_added: summary.observations_to_add,
        parseable: summary.parseable,
        unparseable: summary.unparseable,
        parser_errors: summary.parser_errors,
        empty_placeholders: summary.empty_placeholders,
    }
}

/// Check that source and archive roots do not overlap.
fn check_overlap(source_root: &Path, archive_root: &Path) -> Result<()> {
    let source_absolute = normalize_absolute_path(source_root)?;
    let archive_absolute = normalize_absolute_path(archive_root)?;
    let source_canonical = source_root.canonicalize().ok();
    let archive_canonical = archive_root.canonicalize().ok();

    let mut source_variants = vec![source_absolute.clone()];
    if let Some(canonical) = source_canonical {
        if !source_variants.contains(&canonical) {
            source_variants.push(canonical);
        }
    }

    let mut archive_variants = vec![archive_absolute.clone()];
    if let Some(canonical) = archive_canonical {
        if !archive_variants.contains(&canonical) {
            archive_variants.push(canonical);
        }
    }

    for source_variant in &source_variants {
        for archive_variant in &archive_variants {
            if source_variant == archive_variant {
                bail!(
                    "source and archive roots must not overlap: {} is equal to {}",
                    source_root.display(),
                    archive_root.display()
                );
            }

            if archive_variant.starts_with(source_variant) {
                bail!(
                    "source and archive roots must not overlap: archive {} is inside source {}",
                    archive_root.display(),
                    source_root.display()
                );
            }

            if source_variant.starts_with(archive_variant) {
                bail!(
                    "source and archive roots must not overlap: source {} is inside archive {}",
                    source_root.display(),
                    archive_root.display()
                );
            }
        }
    }

    Ok(())
}

/// Convert filesystem mtime to DateTime<Utc>.
fn mtime_to_datetime(meta: &std::fs::Metadata) -> DateTime<Utc> {
    use std::time::UNIX_EPOCH;
    let mtime = meta.modified().unwrap_or(UNIX_EPOCH);
    let dur = mtime.duration_since(UNIX_EPOCH).unwrap_or_default();
    DateTime::from_timestamp(dur.as_secs() as i64, dur.subsec_nanos())
        .unwrap_or_else(|| DateTime::UNIX_EPOCH)
}

/// Map ArchiveSource to the parser's SourceTool.
fn map_archive_source_to_source_tool(source: ArchiveSource) -> SourceTool {
    match source {
        ArchiveSource::ClaudeCode => SourceTool::ClaudeCode,
        ArchiveSource::Codex => SourceTool::CodexCli,
        ArchiveSource::PiCodingAgent => SourceTool::PiCodingAgent,
        ArchiveSource::OpenClaw => SourceTool::OpenClaw,
        ArchiveSource::Gemini => SourceTool::GeminiCli,
    }
}

/// Check whether the given path is inside a git worktree.
fn is_inside_git_worktree(path: &Path) -> bool {
    let mut current = Some(path);
    while let Some(dir) = current {
        if dir.join(".git").exists() {
            return true;
        }
        current = dir.parent();
    }
    false
}

/// Lock guard that creates `.archive.lock` and removes it on drop.
struct ArchiveLock {
    path: PathBuf,
}

impl ArchiveLock {
    fn acquire(archive_root: &Path) -> Result<Self> {
        let path = archive_root.join(".archive.lock");
        match std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
        {
            Ok(_file) => Ok(Self { path }),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                bail!(
                    "archive lock exists at {}. another archive run may be active. if the lock is stale, delete it manually and retry.",
                    path.display()
                );
            }
            Err(e) => {
                bail!("cannot create archive lock at {}: {}", path.display(), e);
            }
        }
    }
}

impl Drop for ArchiveLock {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}

/// Write the derived `indexes/sessions.jsonl` from the manifest.
fn write_index(manifest: &ArchiveManifest, archive_root: &Path) -> Result<()> {
    let index_dir = archive_root.join("indexes");
    std::fs::create_dir_all(&index_dir)
        .with_context(|| format!("creating {}", index_dir.display()))?;

    let index_path = index_dir.join("sessions.jsonl");
    let tmp_name = format!(".tmp-index-{}", uuid7::uuid7());
    let tmp_path = index_dir.join(&tmp_name);

    let mut lines = Vec::new();
    for obs in &manifest.observations {
        let obj = match manifest.objects.get(&obs.sha256) {
            Some(o) => o,
            None => continue,
        };

        let record = serde_json::json!({
            "observation_id": obs.observation_id,
            "sha256": obs.sha256,
            "source_tool": obs.source_tool,
            "original_path": obs.original_path,
            "archive_path": obs.archive_path,
            "parser_status": obj.parser_status,
            "session_count": obj.session_count,
            "session_ids": obj.session_ids,
            "first_timestamp": obj.first_timestamp,
            "last_timestamp": obj.last_timestamp,
        });
        lines.push(serde_json::to_string(&record).context("serializing index record")?);
    }

    std::fs::write(&tmp_path, lines.join("\n"))
        .with_context(|| format!("writing temp index {}", tmp_path.display()))?;

    std::fs::rename(&tmp_path, &index_path).with_context(|| {
        format!(
            "renaming {} -> {}",
            tmp_path.display(),
            index_path.display()
        )
    })?;

    Ok(())
}
