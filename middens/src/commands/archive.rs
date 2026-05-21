//! `middens archive` command handler.

use std::path::PathBuf;

use anyhow::{Result, bail};

use crate::archive::discover::ArchiveSource;
use crate::archive::{ArchiveConfig, SourceSpec};

/// Arguments for the `archive` subcommand.
#[derive(Debug, Clone)]
pub struct ArchiveArgs {
    pub to: PathBuf,
    pub source: Vec<ArchiveSource>,
    pub from: Option<PathBuf>,
    pub dry_run: bool,
    pub yes: bool,
    pub require_parseable: bool,
}

/// Validate arguments and run the archive operation.
pub fn run_archive(args: ArchiveArgs) -> Result<()> {
    // --from requires exactly one --source.
    if args.from.is_some() && args.source.len() != 1 {
        bail!(
            "--from requires exactly one --source.\n\
             Expected form: middens archive --source <SOURCE> --from <DIR> --to <DIR> [--dry-run]\n\
             Example: middens archive --source claude-code --from ~/.claude/projects --to ~/archive --dry-run"
        );
    }

    // Build source specs.
    let sources: Vec<SourceSpec> = if args.source.is_empty() {
        // Default: all known sources.
        ArchiveSource::all()
            .into_iter()
            .map(|s| SourceSpec {
                source: s,
                override_root: None,
            })
            .collect()
    } else {
        args.source
            .into_iter()
            .map(|s| SourceSpec {
                source: s,
                override_root: args.from.clone(),
            })
            .collect()
    };

    let config = ArchiveConfig {
        archive_root: args.to,
        sources,
        dry_run: args.dry_run,
        yes: args.yes,
        require_parseable: args.require_parseable,
    };

    crate::archive::run(config)?;
    Ok(())
}
