//! Message classifier: categorize user messages by intent.
//!
//! Port of the validated Python classifier (98% accuracy) to Rust.
//! Uses a priority-based classification pipeline:
//!   1. Structural: tool_result blocks → SystemMessage
//!   2. Tags: system-reminder, command-name, etc. → SystemMessage
//!   3. Lexical (length-gated): correction/approval/question patterns
//!   4. Positional: first message defaults
//!   5. Fallback: short → HumanDirective, long → Other

use crate::session::{ContentBlock, Message, MessageClassification, MessageRole};

/// System tag markers that indicate injected/system content.
const SYSTEM_TAGS: &[&str] = &[
    "<system-reminder>",
    "<command-name>",
    "<run_context>",
    "<environment_details>",
    "<tool_response>",
    "<feedback>",
    "<automated_reminder>",
];

/// Correction patterns (matched case-insensitively at word boundaries).
const CORRECTION_PATTERNS: &[&str] = &[
    "no,",
    "no.",
    "no!",
    "no ",
    "that's wrong",
    "that is wrong",
    "that's not",
    "that is not",
    "not what i",
    "wrong",
    "fix ",
    "fix.",
    "don't",
    "do not",
    "stop",
    "undo",
    "revert",
    "instead,",
    "instead ",
    "actually,",
    "actually ",
    "wait,",
    "wait ",
    "hold on",
    "try again",
    "not quite",
    "not right",
    "should be",
    "should have",
    "shouldn't",
    "change that",
    "go back",
    "roll back",
    "i said",
    "i meant",
    "i wanted",
];

/// Approval patterns (matched case-insensitively).
const APPROVAL_PATTERNS: &[&str] = &[
    "yes",
    "yep",
    "yeah",
    "yea",
    "perfect",
    "looks good",
    "lgtm",
    "approved",
    "approve",
    "great",
    "thanks",
    "thank you",
    "good",
    "nice",
    "correct",
    "exactly",
    "right",
    "ok",
    "okay",
    "sure",
    "go ahead",
    "proceed",
    "ship it",
    "merge",
    "👍",
];

/// Question starters (matched case-insensitively).
const QUESTION_STARTERS: &[&str] = &[
    "how", "what", "why", "when", "where", "which", "who", "can you", "could you", "would you",
    "is there", "are there", "do you", "does it", "will it", "should i", "should we",
];

/// Maximum message length for lexical pattern matching (Priority 3).
/// Longer messages are unlikely to be simple corrections/approvals.
const LEXICAL_MAX_LEN: usize = 1000;

/// Classify a single message based on its content and position.
///
/// Only classifies `User` role messages; `Assistant` and `System` messages
/// are returned as `Other`.
pub fn classify_message(msg: &Message, is_first: bool) -> MessageClassification {
    // Only classify user messages.
    if msg.role != MessageRole::User {
        return MessageClassification::Other;
    }

    // --- Priority 1: Structural (tool_result blocks) ---
    if has_tool_result_blocks(msg) {
        return MessageClassification::SystemMessage;
    }

    // --- Priority 2: System tags in text ---
    if has_system_tags(&msg.text) {
        return MessageClassification::SystemMessage;
    }

    // Also check raw content blocks for system tags.
    for block in &msg.raw_content {
        if let ContentBlock::Text { text } = block {
            if has_system_tags(text) {
                return MessageClassification::SystemMessage;
            }
        }
    }

    // --- Priority 3: Lexical patterns (length-gated) ---
    let text = msg.text.trim();
    if text.len() < LEXICAL_MAX_LEN {
        let lower = text.to_lowercase();

        // Check correction patterns first (most specific).
        if matches_any(&lower, CORRECTION_PATTERNS) {
            return MessageClassification::HumanCorrection;
        }

        // Check approval patterns.
        if matches_any(&lower, APPROVAL_PATTERNS) {
            return MessageClassification::HumanApproval;
        }

        // Check question patterns.
        if text.contains('?') || starts_with_any(&lower, QUESTION_STARTERS) {
            return MessageClassification::HumanQuestion;
        }
    }

    // --- Priority 4: Positional default ---
    if is_first {
        return MessageClassification::HumanDirective;
    }

    // --- Priority 5: Fallback by length ---
    if text.len() < LEXICAL_MAX_LEN {
        MessageClassification::HumanDirective
    } else {
        MessageClassification::Other
    }
}

/// Check whether the message contains tool_result content blocks (has `tool_use_id`).
fn has_tool_result_blocks(msg: &Message) -> bool {
    // Check raw content blocks for tool_result type.
    for block in &msg.raw_content {
        if matches!(block, ContentBlock::ToolResultBlock { .. }) {
            return true;
        }
    }
    // Also check if there are parsed tool results.
    !msg.tool_results.is_empty()
}

/// Check if text contains any of the system tag markers.
fn has_system_tags(text: &str) -> bool {
    SYSTEM_TAGS.iter().any(|tag| text.contains(tag))
}

/// Check if the lowercased text matches any of the given patterns at word boundaries.
///
/// A match is valid only if the pattern occurrence is preceded and followed by
/// a non-alphanumeric character (or string boundary). This prevents false
/// positives like "ok" matching inside "token" or "good" inside "goody".
///
/// Patterns that already contain trailing punctuation (e.g. "no," or "fix.")
/// are exempt from the trailing-boundary check because the punctuation itself
/// serves as a natural delimiter.
fn matches_any(lower: &str, patterns: &[&str]) -> bool {
    patterns.iter().any(|p| {
        let mut start = 0;
        while let Some(pos) = lower[start..].find(p) {
            let abs_pos = start + pos;
            let end_pos = abs_pos + p.len();

            // Check leading word boundary: start of string or non-alphanumeric char.
            let leading_ok = abs_pos == 0
                || !lower.as_bytes()[abs_pos - 1].is_ascii_alphanumeric();

            // Check trailing word boundary: end of string or non-alphanumeric char.
            // Skip if the pattern itself ends with punctuation (it's already bounded).
            let pattern_ends_with_punct = p
                .as_bytes()
                .last()
                .map(|&b| !b.is_ascii_alphanumeric())
                .unwrap_or(false);
            let trailing_ok = pattern_ends_with_punct
                || end_pos >= lower.len()
                || !lower.as_bytes()[end_pos].is_ascii_alphanumeric();

            if leading_ok && trailing_ok {
                return true;
            }

            start = abs_pos + 1;
        }
        false
    })
}

/// Check if the lowercased text starts with any of the given prefixes.
fn starts_with_any(lower: &str, prefixes: &[&str]) -> bool {
    prefixes.iter().any(|p| lower.starts_with(p))
}

