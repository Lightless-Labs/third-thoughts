//! Parser enrichment wrapper that preserves status distinctions.

use std::io::BufRead;
use std::path::Path;

use anyhow::Result;

use crate::parser::auto_detect::detect_format;
use crate::session::{Session, SourceTool};

/// Result of parser enrichment for a single candidate file.
#[derive(Debug, Clone)]
pub struct ParseEnrichment {
    pub status: super::manifest::ParserStatus,
    pub error: Option<String>,
    pub session_count: u64,
    pub session_ids: Vec<String>,
    pub first_timestamp: Option<chrono::DateTime<chrono::Utc>>,
    pub last_timestamp: Option<chrono::DateTime<chrono::Utc>>,
}

impl Default for ParseEnrichment {
    fn default() -> Self {
        Self {
            status: super::manifest::ParserStatus::Unparseable,
            error: None,
            session_count: 0,
            session_ids: Vec::new(),
            first_timestamp: None,
            last_timestamp: None,
        }
    }
}

/// Enrich a candidate file by attempting to parse it.
///
/// Returns the enrichment result. Never errors on parse failure unless
/// `--require-parseable` is handled at the caller level.
pub fn enrich(path: &Path, source_tool: SourceTool) -> Result<ParseEnrichment> {
    use super::manifest::ParserStatus;

    // Empty file check.
    let metadata = match std::fs::metadata(path) {
        Ok(m) => m,
        Err(e) => {
            return Ok(ParseEnrichment {
                status: ParserStatus::ParserError,
                error: Some(format!("cannot stat file: {}", e)),
                ..Default::default()
            });
        }
    };

    if metadata.len() == 0 {
        return Ok(ParseEnrichment {
            status: ParserStatus::EmptyPlaceholder,
            ..Default::default()
        });
    }

    // Try to detect format.
    let detected_tool = detect_format(path);

    // If no format detected, mark as unparseable.
    if detected_tool.is_none() {
        return Ok(ParseEnrichment {
            status: ParserStatus::Unparseable,
            ..Default::default()
        });
    }

    if let Some(line_number) = first_invalid_jsonl_line(path)? {
        return Ok(ParseEnrichment {
            status: ParserStatus::ParserError,
            error: Some(format!("invalid JSONL at line {}", line_number)),
            ..Default::default()
        });
    }

    // Try to parse.
    let sessions = match crate::parser::auto_detect::parse_auto(path) {
        Ok(sessions) => sessions,
        Err(e) => {
            return Ok(ParseEnrichment {
                status: ParserStatus::ParserError,
                error: Some(format!("{} parser failed: {}", source_tool, e)),
                ..Default::default()
            });
        }
    };

    // If parse_auto returns empty but a format was detected, this is a parser error
    // (the file wasn't empty but parsing yielded nothing).
    if sessions.is_empty() {
        return Ok(ParseEnrichment {
            status: ParserStatus::ParserError,
            error: Some(format!("{} parser returned no sessions", source_tool)),
            ..Default::default()
        });
    }

    // Successfully parsed.
    let session_count = sessions.len() as u64;
    let session_ids: Vec<String> = sessions.iter().map(|s| s.id.clone()).collect();
    let (first_timestamp, last_timestamp) = extract_timestamps(&sessions);

    Ok(ParseEnrichment {
        status: ParserStatus::Parsed,
        error: None,
        session_count,
        session_ids,
        first_timestamp,
        last_timestamp,
    })
}

fn extract_timestamps(
    sessions: &[Session],
) -> (
    Option<chrono::DateTime<chrono::Utc>>,
    Option<chrono::DateTime<chrono::Utc>>,
) {
    let mut first: Option<chrono::DateTime<chrono::Utc>> = None;
    let mut last: Option<chrono::DateTime<chrono::Utc>> = None;

    for session in sessions {
        for msg in &session.messages {
            if let Some(ts) = msg.timestamp {
                if first.map_or(true, |f| ts < f) {
                    first = Some(ts);
                }
                if last.map_or(true, |l| ts > l) {
                    last = Some(ts);
                }
            }
        }
    }

    (first, last)
}

fn first_invalid_jsonl_line(path: &Path) -> Result<Option<usize>> {
    let file = std::fs::File::open(path)?;
    let reader = std::io::BufReader::new(file);

    for (index, line) in reader.lines().enumerate() {
        let line = line?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if serde_json::from_str::<serde_json::Value>(trimmed).is_err() {
            return Ok(Some(index + 1));
        }
    }

    Ok(None)
}
