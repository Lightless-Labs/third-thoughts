use std::path::PathBuf;

use cucumber::{given, then, when};

use middens::session::{
    ContentBlock, EnvironmentFingerprint, Message, MessageClassification, MessageRole, Session,
    SessionMetadata, SessionType, SourceTool,
};
use middens::techniques::thinking_divergence::ThinkingDivergence;
use middens::techniques::{Technique, all_techniques};

use super::world::MiddensWorld;

fn assistant_message(thinking: Option<&str>, text: &str) -> Message {
    let mut raw_content = Vec::new();

    if let Some(thinking) = thinking {
        raw_content.push(ContentBlock::Thinking {
            thinking: thinking.to_string(),
        });
    }

    raw_content.push(ContentBlock::Text {
        text: text.to_string(),
    });

    Message {
        role: MessageRole::Assistant,
        timestamp: None,
        text: text.to_string(),
        thinking: thinking.map(ToOwned::to_owned),
        tool_calls: vec![],
        tool_results: vec![],
        classification: MessageClassification::Other,
        raw_content,
    }
}

fn directive_message(text: &str) -> Message {
    Message {
        role: MessageRole::User,
        timestamp: None,
        text: text.to_string(),
        thinking: None,
        tool_calls: vec![],
        tool_results: vec![],
        classification: MessageClassification::HumanDirective,
        raw_content: vec![ContentBlock::Text {
            text: text.to_string(),
        }],
    }
}

fn session_with_thinking_and_text(id: &str, thinking: Option<&str>, text: &str) -> Session {
    Session {
        id: id.to_string(),
        source_path: PathBuf::from("/tmp/thinking_divergence.jsonl"),
        source_tool: SourceTool::ClaudeCode,
        session_type: SessionType::Interactive,
        messages: vec![
            directive_message("Analyze the session transcript."),
            assistant_message(thinking, text),
        ],
        metadata: SessionMetadata::default(),
        environment: EnvironmentFingerprint::default(),
        thinking_visibility: middens::session::ThinkingVisibility::Visible,
    }
}

fn numeric_finding(world: &MiddensWorld, label: &str) -> f64 {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let finding = result
        .findings
        .iter()
        .find(|finding| finding.label == label)
        .unwrap_or_else(|| panic!("finding '{}' not found", label));

    finding
        .value
        .as_f64()
        .unwrap_or_else(|| panic!("finding '{}' is not numeric: {}", label, finding.value))
}

#[given("a session with suppressed thinking risk tokens")]
fn given_session_with_suppressed_thinking_risk_tokens(world: &mut MiddensWorld) {
    world.sessions = vec![session_with_thinking_and_text(
        "suppressed-risk-tokens",
        Some("password secret token"),
        "I reviewed the request and will proceed carefully.",
    )];
}

#[given("a session with no thinking blocks")]
fn given_session_with_no_thinking_blocks(world: &mut MiddensWorld) {
    world.sessions = vec![session_with_thinking_and_text(
        "no-thinking-blocks",
        None,
        "Public answer without any private reasoning block.",
    )];
}

#[given("a session with mirrored thinking risk tokens in text")]
fn given_session_with_mirrored_thinking_risk_tokens_in_text(world: &mut MiddensWorld) {
    world.sessions = vec![session_with_thinking_and_text(
        "mirrored-risk-tokens",
        Some("password secret token"),
        "password secret token",
    )];
}

#[given(expr = "a session with thinking length {int} and text length {int}")]
fn given_session_with_thinking_length_and_text_length(
    world: &mut MiddensWorld,
    thinking_length: usize,
    text_length: usize,
) {
    let thinking = "t".repeat(thinking_length);
    let text = "x".repeat(text_length);

    world.sessions = vec![session_with_thinking_and_text(
        "length-ratio",
        Some(&thinking),
        &text,
    )];
}

#[when("I run the thinking divergence technique")]
fn when_run_the_thinking_divergence_technique(world: &mut MiddensWorld) {
    let technique = ThinkingDivergence;
    world.technique_result = Some(technique.run(&world.sessions).unwrap());
}

#[then(expr = "finding {string} should be greater than {float}")]
fn then_finding_should_be_greater_than(world: &mut MiddensWorld, label: String, threshold: f64) {
    let actual = numeric_finding(world, &label);
    assert!(
        actual > threshold,
        "finding '{}' should be greater than {}, got {}",
        label,
        threshold,
        actual
    );
}

#[then("the thinking divergence result should have zero analyzed counts")]
fn then_thinking_divergence_result_should_have_zero_analyzed_counts(world: &mut MiddensWorld) {
    let result = world
        .technique_result
        .as_ref()
        .expect("no technique result");
    let sessions_analyzed = result
        .findings
        .iter()
        .find(|finding| finding.label == "sessions_analyzed")
        .unwrap_or_else(|| panic!("finding 'sessions_analyzed' not found"));

    assert_eq!(
        sessions_analyzed.value.as_u64(),
        Some(0),
        "expected sessions_analyzed to be 0, got {}",
        sessions_analyzed.value
    );

    for finding in &result.findings {
        if finding.label == "sessions_skipped" {
            continue;
        }

        let is_count_like = finding.label.contains("count")
            || finding.label.contains("length")
            || finding.label.contains("tokens");

        if is_count_like {
            let value = finding.value.as_f64().unwrap_or_else(|| {
                panic!(
                    "count-like finding '{}' is not numeric: {}",
                    finding.label, finding.value
                )
            });

            assert_eq!(
                value, 0.0,
                "expected count-like finding '{}' to be 0, got {}",
                finding.label, value
            );
        }
    }
}

#[then("the thinking divergence technique should be registered as essential")]
fn then_thinking_divergence_technique_should_be_registered_as_essential(_world: &mut MiddensWorld) {
    let technique = all_techniques()
        .into_iter()
        .find(|technique| technique.name() == "thinking-divergence")
        .expect("thinking-divergence should be registered");

    assert!(
        technique.is_essential(),
        "thinking-divergence should be marked essential"
    );
}
