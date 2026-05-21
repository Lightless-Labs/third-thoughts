//! Hash and copy primitives with atomic writes.

use std::fs::File;
use std::io::{BufReader, Read, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use sha2::{Digest, Sha256};

/// Compute SHA-256 of a file by streaming.
pub fn hash_file(path: &Path) -> Result<String> {
    let file =
        File::open(path).with_context(|| format!("opening {} for hashing", path.display()))?;
    let mut reader = BufReader::new(file);
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 8192];
    loop {
        let n = reader
            .read(&mut buf)
            .with_context(|| format!("reading {} for hashing", path.display()))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

/// Compute SHA-256 of a reader by streaming.
pub fn hash_reader<R: Read>(reader: &mut R) -> Result<String> {
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 8192];
    loop {
        let n = reader.read(&mut buf).context("reading for hashing")?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

/// Copy a file to the archive object store atomically.
///
/// Writes to a temp file in the destination directory, then renames.
/// Returns the final archive path relative to archive_root.
pub fn atomic_copy(source: &Path, sha256: &str, archive_root: &Path) -> Result<PathBuf> {
    let rel_path = object_rel_path(sha256);
    let dest = archive_root.join(&rel_path);

    if dest.exists() {
        let existing_hash = hash_file(&dest)
            .with_context(|| format!("hashing existing object {}", dest.display()))?;
        if existing_hash != sha256 {
            bail!(
                "destination collision: {} already exists but hashes to {} (expected {})",
                dest.display(),
                existing_hash,
                sha256
            );
        }
        // Existing object matches — no need to rewrite.
        return Ok(rel_path);
    }

    if let Some(parent) = dest.parent() {
        std::fs::create_dir_all(parent)
            .with_context(|| format!("creating object directory {}", parent.display()))?;
    }

    let tmp_name = format!(".tmp-object-{}", uuid7::uuid7());
    let tmp_path = dest.parent().unwrap_or(archive_root).join(&tmp_name);

    {
        let mut src =
            File::open(source).with_context(|| format!("opening source {}", source.display()))?;
        let mut dst = File::create(&tmp_path)
            .with_context(|| format!("creating temp file {}", tmp_path.display()))?;
        std::io::copy(&mut src, &mut dst)
            .with_context(|| format!("copying {} -> {}", source.display(), tmp_path.display()))?;
        dst.flush().context("flushing temp object file")?;
    }

    // Test hook: object-copy
    if std::env::var("MIDDENS_ARCHIVE_TEST_HOOK").ok().as_deref() == Some("object-copy") {
        bail!("test hook triggered: object-copy");
    }

    std::fs::rename(&tmp_path, &dest)
        .with_context(|| format!("renaming {} -> {}", tmp_path.display(), dest.display()))?;

    Ok(rel_path)
}

/// Build the relative object path from a SHA-256 hex string.
pub fn object_rel_path(sha256: &str) -> PathBuf {
    let prefix = &sha256[..2.min(sha256.len())];
    PathBuf::from("objects/sha256")
        .join(prefix)
        .join(format!("{}.jsonl", sha256))
}
