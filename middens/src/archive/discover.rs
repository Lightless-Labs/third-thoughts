//! Source discovery for archive: default roots, file walking, symlink policy.

use std::path::Component;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, anyhow, bail};
use clap::ValueEnum;
use walkdir::{Error as WalkError, WalkDir};

/// Known agent tool sources that can be archived.
#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum)]
pub enum ArchiveSource {
    #[value(name = "claude-code")]
    ClaudeCode,
    #[value(name = "codex")]
    Codex,
    #[value(name = "pi-coding-agent")]
    PiCodingAgent,
    #[value(name = "openclaw")]
    OpenClaw,
    #[value(name = "gemini")]
    Gemini,
}

impl ArchiveSource {
    /// Human-readable tool name.
    pub fn tool_name(&self) -> &'static str {
        match self {
            Self::ClaudeCode => "claude-code",
            Self::Codex => "codex",
            Self::PiCodingAgent => "pi-coding-agent",
            Self::OpenClaw => "openclaw",
            Self::Gemini => "gemini",
        }
    }

    /// Default root directory for this source.
    pub fn default_root(&self) -> PathBuf {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
        match self {
            Self::ClaudeCode => PathBuf::from(&home).join(".claude/projects"),
            Self::Codex => PathBuf::from(&home).join(".codex/sessions"),
            Self::PiCodingAgent => PathBuf::from(&home).join(".pi/agent/sessions"),
            Self::OpenClaw => PathBuf::from(&home).join("openclaw-sessions"),
            Self::Gemini => PathBuf::from(&home).join(".gemini/history"),
        }
    }

    /// All known sources.
    pub fn all() -> Vec<ArchiveSource> {
        vec![
            Self::ClaudeCode,
            Self::Codex,
            Self::PiCodingAgent,
            Self::OpenClaw,
            Self::Gemini,
        ]
    }
}

/// A candidate file discovered during scanning.
#[derive(Debug, Clone)]
pub struct Candidate {
    pub source: ArchiveSource,
    pub original_path: PathBuf,
    pub canonical_path: Option<PathBuf>,
    pub basename: String,
}

/// Discover all candidate `.jsonl` files for the given sources.
///
/// Returns `(candidates, not_present)` where `not_present` lists source names
/// whose default roots do not exist.
pub fn discover_candidates(
    sources: &[(ArchiveSource, Option<PathBuf>)],
) -> Result<(Vec<Candidate>, Vec<String>)> {
    let mut candidates = Vec::new();
    let mut not_present = Vec::new();

    for (source, override_root) in sources {
        let root = override_root
            .clone()
            .unwrap_or_else(|| source.default_root());
        let display_root = normalize_absolute_path(&root)?;
        let canonical_root = root.canonicalize().ok();

        if !root.exists() {
            if override_root.is_some() {
                bail!(
                    "source '{}' was requested, but {} does not exist.\n\
                     Expected a readable directory of .jsonl session logs.\n\
                     Example: middens archive --source {} --from /path/to/projects --to /path/to/archive --dry-run",
                    source.tool_name(),
                    root.display(),
                    source.tool_name()
                );
            } else {
                not_present.push(source.tool_name().to_string());
                continue;
            }
        }

        if !root.is_dir() {
            if override_root.is_some() {
                bail!(
                    "source '{}' was requested, but {} is not a directory.\n\
                     Expected a readable directory of .jsonl session logs.\n\
                     Example: middens archive --source {} --from /path/to/projects --to /path/to/archive --dry-run",
                    source.tool_name(),
                    root.display(),
                    source.tool_name()
                );
            } else {
                bail!(
                    "source '{}' default root {} exists but is not a readable directory",
                    source.tool_name(),
                    root.display()
                );
            }
        }

        // Try to read directory — fail if unreadable.
        let _ = std::fs::read_dir(&root)
            .with_context(|| format!("cannot read source directory {}", root.display()))?;

        for entry in WalkDir::new(&root).follow_links(true).sort_by_file_name() {
            let entry = match entry {
                Ok(entry) => entry,
                Err(err) => return Err(format_walk_error(&root, err)),
            };
            let path = entry.path();

            if path.is_dir() {
                continue;
            }

            if path.extension().and_then(|e| e.to_str()) != Some("jsonl") {
                continue;
            }

            let original_path = normalize_absolute_path(path)?;
            let canonical = path.canonicalize().ok().map(|canonical| {
                canonical_with_display_root(canonical, &display_root, canonical_root.as_deref())
            });
            let basename = path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();

            candidates.push(Candidate {
                source: *source,
                original_path,
                canonical_path: canonical,
                basename,
            });
        }
    }

    // Sort by (source_tool_slug, original_path) for determinism.
    candidates.sort_by(|a, b| {
        a.source
            .tool_name()
            .cmp(&b.source.tool_name())
            .then_with(|| a.original_path.cmp(&b.original_path))
    });

    Ok((candidates, not_present))
}

pub(crate) fn normalize_absolute_path(path: &Path) -> Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .context("resolving current directory for archive path")?
            .join(path)
    };

    Ok(normalize_lexical_path(&absolute))
}

fn normalize_lexical_path(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();

    for component in path.components() {
        match component {
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            Component::Normal(segment) => normalized.push(segment),
        }
    }

    normalized
}

fn canonical_with_display_root(
    canonical_path: PathBuf,
    display_root: &Path,
    canonical_root: Option<&Path>,
) -> PathBuf {
    if let Some(canonical_root) = canonical_root {
        if let Ok(relative) = canonical_path.strip_prefix(canonical_root) {
            return display_root.join(relative);
        }
    }

    canonical_path
}

fn format_walk_error(root: &Path, err: WalkError) -> anyhow::Error {
    let walked_path = err
        .path()
        .map(|path| path.display().to_string())
        .unwrap_or_else(|| root.display().to_string());

    if let Some(ancestor) = err.loop_ancestor() {
        return anyhow!(
            "symlink loop detected while walking {}: loop reaches {}",
            walked_path,
            ancestor.display()
        );
    }

    anyhow!("failed while walking {}: {}", walked_path, err)
}
