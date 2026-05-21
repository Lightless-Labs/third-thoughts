//! Archive manifest types and I/O.

use std::collections::BTreeMap;
use std::path::Path;

use anyhow::{Context, Result, bail, ensure};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Top-level archive manifest.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ArchiveManifest {
    pub archive_manifest_version: u32,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub middens_version: String,
    pub archive_root: String,
    pub objects: BTreeMap<String, ArchivedObject>,
    pub observations: Vec<SourceObservation>,
}

/// A single deduplicated object in the archive.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct ArchivedObject {
    pub sha256: String,
    pub size_bytes: u64,
    pub archive_path: String,
    pub first_archived_at: DateTime<Utc>,
    pub parser_status: ParserStatus,
    pub parser_error: Option<String>,
    pub source_tool: String,
    pub session_count: u64,
    pub session_ids: Vec<String>,
    pub first_timestamp: Option<DateTime<Utc>>,
    pub last_timestamp: Option<DateTime<Utc>>,
}

/// A discovery observation linking a source file to an archived object.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct SourceObservation {
    pub observation_id: String,
    pub source_tool: String,
    pub original_path: String,
    pub canonical_path: Option<String>,
    pub original_basename: String,
    pub archive_path: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub source_mtime: DateTime<Utc>,
    pub observed_at: DateTime<Utc>,
}

/// Result of parsing a candidate file for metadata enrichment.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ParserStatus {
    Parsed,
    Unparseable,
    EmptyPlaceholder,
    ParserError,
}

impl std::fmt::Display for ParserStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Parsed => write!(f, "parsed"),
            Self::Unparseable => write!(f, "unparseable"),
            Self::EmptyPlaceholder => write!(f, "empty_placeholder"),
            Self::ParserError => write!(f, "parser_error"),
        }
    }
}

/// Load an existing manifest from disk, or return a fresh one if absent.
pub fn load_or_create(archive_root: &Path, middens_version: &str) -> Result<ArchiveManifest> {
    let manifest_path = archive_root.join("manifest.json");
    if manifest_path.exists() {
        let raw = std::fs::read_to_string(&manifest_path)
            .with_context(|| format!("reading {}", manifest_path.display()))?;
        let manifest: ArchiveManifest = serde_json::from_str(&raw).with_context(|| {
            format!(
                "corrupt or schema-invalid manifest at {}",
                manifest_path.display()
            )
        })?;
        ensure!(
            manifest.archive_manifest_version == 1,
            "manifest version mismatch: expected 1, got {}",
            manifest.archive_manifest_version
        );
        Ok(manifest)
    } else {
        let now = Utc::now();
        Ok(ArchiveManifest {
            archive_manifest_version: 1,
            created_at: now,
            updated_at: now,
            middens_version: middens_version.to_string(),
            archive_root: archive_root.to_string_lossy().to_string(),
            objects: BTreeMap::new(),
            observations: Vec::new(),
        })
    }
}

/// Validate that every object referenced in the manifest still exists on disk
/// and hashes to its recorded SHA-256.
pub fn validate_drift(manifest: &ArchiveManifest, archive_root: &Path) -> Result<()> {
    for (sha, obj) in &manifest.objects {
        let path = archive_root.join(&obj.archive_path);
        ensure!(
            path.exists(),
            "archive drift detected: object {} is missing at {}",
            sha,
            path.display()
        );
        let actual_hash = crate::archive::copy::hash_file(&path)
            .with_context(|| format!("hashing {} for drift check", path.display()))?;
        ensure!(
            actual_hash == *sha,
            "archive drift detected: object {} at {} has hash {} (expected {})",
            sha,
            path.display(),
            actual_hash,
            sha
        );
    }
    Ok(())
}

/// Write the manifest atomically via a temp file + rename.
pub fn write_atomic(manifest: &ArchiveManifest, archive_root: &Path) -> Result<()> {
    let manifest_path = archive_root.join("manifest.json");
    let tmp_name = format!(".tmp-manifest-{}", uuid7::uuid7());
    let tmp_path = archive_root.join(&tmp_name);

    let json = serde_json::to_string_pretty(manifest).context("serializing manifest")?;
    std::fs::write(&tmp_path, json)
        .with_context(|| format!("writing temp manifest {}", tmp_path.display()))?;

    // Test hook: manifest-rename
    if std::env::var("MIDDENS_ARCHIVE_TEST_HOOK").ok().as_deref() == Some("manifest-rename") {
        bail!("test hook triggered: manifest-rename");
    }

    std::fs::rename(&tmp_path, &manifest_path).with_context(|| {
        format!(
            "renaming {} -> {}",
            tmp_path.display(),
            manifest_path.display()
        )
    })?;
    Ok(())
}

/// Check whether an observation with the given ID already exists.
pub fn has_observation(manifest: &ArchiveManifest, observation_id: &str) -> bool {
    manifest
        .observations
        .iter()
        .any(|o| o.observation_id == observation_id)
}

/// Compute an observation ID from source metadata.
pub fn observation_id(
    original_path: &str,
    canonical_path: Option<&str>,
    source_tool: &str,
    sha256: &str,
) -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(original_path.as_bytes());
    hasher.update(b"\0");
    if let Some(cp) = canonical_path {
        hasher.update(cp.as_bytes());
    }
    hasher.update(b"\0");
    hasher.update(source_tool.as_bytes());
    hasher.update(b"\0");
    hasher.update(sha256.as_bytes());
    format!("{:x}", hasher.finalize())
}
