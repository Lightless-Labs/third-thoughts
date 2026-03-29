//! Correction rate metrics per session, project, and session position.

use anyhow::Result;
use serde_json::json;

use crate::session::{MessageClassification, MessageRole, Session};

use super::{DataTable, Finding, Technique, TechniqueResult};

/// Correction rate metrics technique.
pub struct CorrectionRate;

impl Technique for CorrectionRate {
    fn name(&self) -> &str {
        "correction-rate"
    }

    fn description(&self) -> &str {
        "Correction rate metrics per session, project, and session position"
    }

    fn requires_python(&self) -> bool {
        false
    }

    fn is_essential(&self) -> bool {
        true
    }

    fn run(&self, sessions: &[Session]) -> Result<TechniqueResult> {
        // --- Per-session metrics ---
        struct SessionMetrics {
            session_id: String,
            correction_rate: f64,
            first_third_rate: f64,
            middle_third_rate: f64,
            last_third_rate: f64,
            degradation_ratio: f64,
            corrections: usize,
            user_messages: usize,
            project: String,
        }

        let mut per_session: Vec<SessionMetrics> = Vec::with_capacity(sessions.len());

        for session in sessions {
            let user_msgs: Vec<&crate::session::Message> = session
                .messages
                .iter()
                .filter(|m| m.role == MessageRole::User)
                .collect();

            let user_count = user_msgs.len();
            // Count corrections only among user-role messages (not all messages)
            // to keep numerator and denominator consistent.
            let correction_count = user_msgs
                .iter()
                .filter(|m| m.classification == MessageClassification::HumanCorrection)
                .count();

            let correction_rate = if user_count == 0 {
                0.0
            } else {
                correction_count as f64 / user_count as f64
            };

            // Divide user messages into thirds and compute correction rate per third
            let (first_third_rate, middle_third_rate, last_third_rate) = if user_count == 0 {
                (0.0, 0.0, 0.0)
            } else {
                let third = user_count / 3;
                // For very short sessions, ensure at least 1 message per bucket where possible
                let (first_end, middle_end) = if third == 0 {
                    // Fewer than 3 messages: put all in first third
                    (user_count, user_count)
                } else {
                    (third, third * 2)
                };

                let first_corrections = user_msgs[..first_end]
                    .iter()
                    .filter(|m| m.classification == MessageClassification::HumanCorrection)
                    .count();
                let middle_corrections = user_msgs[first_end..middle_end]
                    .iter()
                    .filter(|m| m.classification == MessageClassification::HumanCorrection)
                    .count();
                let last_corrections = user_msgs[middle_end..]
                    .iter()
                    .filter(|m| m.classification == MessageClassification::HumanCorrection)
                    .count();

                let first_count = first_end;
                let middle_count = middle_end - first_end;
                let last_count = user_count - middle_end;

                let fr = if first_count == 0 {
                    0.0
                } else {
                    first_corrections as f64 / first_count as f64
                };
                let mr = if middle_count == 0 {
                    0.0
                } else {
                    middle_corrections as f64 / middle_count as f64
                };
                let lr = if last_count == 0 {
                    0.0
                } else {
                    last_corrections as f64 / last_count as f64
                };

                (fr, mr, lr)
            };

            // degradation_ratio = last_third_rate / first_third_rate
            // Handle gracefully: if first_third_rate is 0, ratio is 0 (no baseline to degrade from)
            let degradation_ratio = if first_third_rate == 0.0 {
                if last_third_rate > 0.0 {
                    f64::INFINITY
                } else {
                    0.0
                }
            } else {
                last_third_rate / first_third_rate
            };

            let project = session
                .metadata
                .project
                .clone()
                .unwrap_or_else(|| "unknown".to_string());

            per_session.push(SessionMetrics {
                session_id: session.id.clone(),
                correction_rate,
                first_third_rate,
                middle_third_rate,
                last_third_rate,
                degradation_ratio,
                corrections: correction_count,
                user_messages: user_count,
                project,
            });
        }

        // --- Per-project metrics ---
        struct ProjectMetrics {
            project: String,
            corrections: usize,
            user_messages: usize,
            correction_rate: f64,
            session_count: usize,
        }

        let mut project_map: std::collections::BTreeMap<String, (usize, usize, usize)> =
            std::collections::BTreeMap::new();
        for sm in &per_session {
            let entry = project_map
                .entry(sm.project.clone())
                .or_insert((0, 0, 0));
            entry.0 += sm.corrections;
            entry.1 += sm.user_messages;
            entry.2 += 1;
        }

        let per_project: Vec<ProjectMetrics> = project_map
            .into_iter()
            .map(|(project, (corrections, user_messages, session_count))| {
                let correction_rate = if user_messages == 0 {
                    0.0
                } else {
                    corrections as f64 / user_messages as f64
                };
                ProjectMetrics {
                    project,
                    corrections,
                    user_messages,
                    correction_rate,
                    session_count,
                }
            })
            .collect();

        // --- Overall metrics ---
        let total_sessions = per_session.len();
        let sessions_with_corrections = per_session.iter().filter(|s| s.corrections > 0).count();

        let mean_correction_rate = if total_sessions == 0 {
            0.0
        } else {
            per_session.iter().map(|s| s.correction_rate).sum::<f64>() / total_sessions as f64
        };

        let median_correction_rate = if total_sessions == 0 {
            0.0
        } else {
            let mut rates: Vec<f64> = per_session.iter().map(|s| s.correction_rate).collect();
            rates.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
            let mid = rates.len() / 2;
            if rates.len() % 2 == 0 && rates.len() >= 2 {
                (rates[mid - 1] + rates[mid]) / 2.0
            } else {
                rates[mid]
            }
        };

        // Mean of per-third rates across all sessions (for findings)
        let (mean_first_third, mean_middle_third, mean_last_third, mean_degradation) =
            if total_sessions == 0 {
                (0.0, 0.0, 0.0, 0.0)
            } else {
                let f: f64 = per_session.iter().map(|s| s.first_third_rate).sum::<f64>()
                    / total_sessions as f64;
                let m: f64 = per_session.iter().map(|s| s.middle_third_rate).sum::<f64>()
                    / total_sessions as f64;
                let l: f64 = per_session.iter().map(|s| s.last_third_rate).sum::<f64>()
                    / total_sessions as f64;
                // For mean degradation, exclude infinite values
                let finite_degradations: Vec<f64> = per_session
                    .iter()
                    .map(|s| s.degradation_ratio)
                    .filter(|d| d.is_finite())
                    .collect();
                let d = if finite_degradations.is_empty() {
                    0.0
                } else {
                    finite_degradations.iter().sum::<f64>() / finite_degradations.len() as f64
                };
                (f, m, l, d)
            };

        // --- Build findings ---
        let findings = vec![
            Finding {
                label: "overall_mean_rate".to_string(),
                value: json!(mean_correction_rate),
                description: Some("Mean correction rate across all sessions".to_string()),
            },
            Finding {
                label: "overall_median_rate".to_string(),
                value: json!(median_correction_rate),
                description: Some("Median correction rate across all sessions".to_string()),
            },
            Finding {
                label: "sessions_with_corrections".to_string(),
                value: json!(format!(
                    "{}/{}",
                    sessions_with_corrections, total_sessions
                )),
                description: Some("Sessions containing at least one correction".to_string()),
            },
            Finding {
                label: "mean_degradation_ratio".to_string(),
                value: json!(mean_degradation),
                description: Some(
                    "Mean ratio of last-third to first-third correction rate (the 7.24x finding)"
                        .to_string(),
                ),
            },
            Finding {
                label: "first_third_rate".to_string(),
                value: json!(mean_first_third),
                description: Some(
                    "Mean correction rate in the first third of sessions".to_string(),
                ),
            },
            Finding {
                label: "middle_third_rate".to_string(),
                value: json!(mean_middle_third),
                description: Some(
                    "Mean correction rate in the middle third of sessions".to_string(),
                ),
            },
            Finding {
                label: "last_third_rate".to_string(),
                value: json!(mean_last_third),
                description: Some(
                    "Mean correction rate in the last third of sessions".to_string(),
                ),
            },
        ];

        // --- Build data tables ---
        let per_session_table = DataTable {
            name: "per_session".to_string(),
            columns: vec![
                "session_id".to_string(),
                "correction_rate".to_string(),
                "first_third_rate".to_string(),
                "last_third_rate".to_string(),
                "degradation_ratio".to_string(),
                "corrections".to_string(),
                "user_messages".to_string(),
            ],
            rows: per_session
                .iter()
                .map(|s| {
                    vec![
                        json!(s.session_id),
                        json!(s.correction_rate),
                        json!(s.first_third_rate),
                        json!(s.last_third_rate),
                        if s.degradation_ratio.is_finite() {
                            json!(s.degradation_ratio)
                        } else {
                            json!(null)
                        },
                        json!(s.corrections),
                        json!(s.user_messages),
                    ]
                })
                .collect(),
        };

        let per_project_table = DataTable {
            name: "per_project".to_string(),
            columns: vec![
                "project".to_string(),
                "correction_rate".to_string(),
                "corrections".to_string(),
                "user_messages".to_string(),
                "session_count".to_string(),
            ],
            rows: per_project
                .iter()
                .map(|p| {
                    vec![
                        json!(p.project),
                        json!(p.correction_rate),
                        json!(p.corrections),
                        json!(p.user_messages),
                        json!(p.session_count),
                    ]
                })
                .collect(),
        };

        // --- Summary ---
        let summary = format!(
            "Correction rate analysis across {} sessions: mean={:.4}, median={:.4}, \
             {}/{} sessions have corrections. Position analysis: first-third={:.4}, \
             middle-third={:.4}, last-third={:.4}, mean degradation ratio={:.2}x.",
            total_sessions,
            mean_correction_rate,
            median_correction_rate,
            sessions_with_corrections,
            total_sessions,
            mean_first_third,
            mean_middle_third,
            mean_last_third,
            mean_degradation,
        );

        Ok(TechniqueResult {
            name: self.name().to_string(),
            summary,
            findings,
            tables: vec![per_session_table, per_project_table],
            figures: vec![],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::session::*;
    use std::path::PathBuf;

    /// Helper to create a user message with a given classification.
    fn user_msg(classification: MessageClassification) -> Message {
        Message {
            role: MessageRole::User,
            timestamp: None,
            text: "test".to_string(),
            thinking: None,
            tool_calls: vec![],
            tool_results: vec![],
            classification,
            raw_content: vec![],
        }
    }

    /// Helper to create an assistant message.
    fn assistant_msg() -> Message {
        Message {
            role: MessageRole::Assistant,
            timestamp: None,
            text: "response".to_string(),
            thinking: None,
            tool_calls: vec![],
            tool_results: vec![],
            classification: MessageClassification::Other,
            raw_content: vec![],
        }
    }

    /// Helper to build a session with given user message classifications and optional project.
    fn make_session(
        id: &str,
        classifications: &[MessageClassification],
        project: Option<&str>,
    ) -> Session {
        let mut messages = Vec::new();
        for c in classifications {
            messages.push(user_msg(*c));
            messages.push(assistant_msg());
        }
        Session {
            id: id.to_string(),
            source_path: PathBuf::from("/test"),
            source_tool: SourceTool::ClaudeCode,
            session_type: SessionType::Interactive,
            messages,
            metadata: SessionMetadata {
                project: project.map(|s| s.to_string()),
                ..Default::default()
            },
            environment: EnvironmentFingerprint::default(),
        }
    }

    #[test]
    fn session_with_2_corrections_in_10_user_messages() {
        // 2 corrections, 8 other user messages = rate 0.2
        let mut classifications = vec![MessageClassification::HumanCorrection; 2];
        classifications.extend(vec![MessageClassification::HumanDirective; 8]);

        let session = make_session("s1", &classifications, Some("proj-a"));
        let technique = CorrectionRate;
        let result = technique.run(&[session]).unwrap();

        let mean_rate = result
            .findings
            .iter()
            .find(|f| f.label == "overall_mean_rate")
            .unwrap();
        let rate: f64 = serde_json::from_value(mean_rate.value.clone()).unwrap();
        assert!(
            (rate - 0.2).abs() < 1e-9,
            "Expected rate 0.2, got {}",
            rate
        );

        // Check per_session table row
        let per_session_table = result.tables.iter().find(|t| t.name == "per_session").unwrap();
        assert_eq!(per_session_table.rows.len(), 1);
        let row = &per_session_table.rows[0];
        // correction_rate is column index 1
        let cr: f64 = serde_json::from_value(row[1].clone()).unwrap();
        assert!((cr - 0.2).abs() < 1e-9);
        // corrections is column index 5
        let corrections: usize = serde_json::from_value(row[5].clone()).unwrap();
        assert_eq!(corrections, 2);
        // user_messages is column index 6
        let user_messages: usize = serde_json::from_value(row[6].clone()).unwrap();
        assert_eq!(user_messages, 10);
    }

    #[test]
    fn session_with_corrections_only_in_last_third() {
        // 9 user messages: first 3 = directive, middle 3 = directive, last 3 = correction
        let mut classifications = vec![MessageClassification::HumanDirective; 6];
        classifications.extend(vec![MessageClassification::HumanCorrection; 3]);

        let session = make_session("s2", &classifications, None);
        let technique = CorrectionRate;
        let result = technique.run(&[session]).unwrap();

        let per_session_table = result.tables.iter().find(|t| t.name == "per_session").unwrap();
        let row = &per_session_table.rows[0];
        // first_third_rate is column index 2
        let first_rate: f64 = serde_json::from_value(row[2].clone()).unwrap();
        // last_third_rate is column index 3
        let last_rate: f64 = serde_json::from_value(row[3].clone()).unwrap();
        assert!(
            first_rate == 0.0,
            "Expected first_third_rate 0.0, got {}",
            first_rate
        );
        assert!(
            last_rate == 1.0,
            "Expected last_third_rate 1.0, got {}",
            last_rate
        );
        // degradation_ratio (column index 4) should be null (infinity not representable in JSON)
        assert!(
            row[4].is_null(),
            "Expected degradation_ratio to be null for infinity, got {}",
            row[4]
        );
    }

    #[test]
    fn session_with_zero_user_messages() {
        // Session with no messages at all
        let session = Session {
            id: "empty".to_string(),
            source_path: PathBuf::from("/test"),
            source_tool: SourceTool::ClaudeCode,
            session_type: SessionType::Interactive,
            messages: vec![],
            metadata: SessionMetadata::default(),
            environment: EnvironmentFingerprint::default(),
        };

        let technique = CorrectionRate;
        let result = technique.run(&[session]).unwrap();

        let mean_rate = result
            .findings
            .iter()
            .find(|f| f.label == "overall_mean_rate")
            .unwrap();
        let rate: f64 = serde_json::from_value(mean_rate.value.clone()).unwrap();
        assert!(rate == 0.0, "Expected rate 0.0, got {}", rate);
    }

    #[test]
    fn session_with_no_corrections() {
        // 6 user messages, none are corrections
        let classifications = vec![MessageClassification::HumanDirective; 6];
        let session = make_session("s3", &classifications, Some("proj-b"));
        let technique = CorrectionRate;
        let result = technique.run(&[session]).unwrap();

        let mean_rate = result
            .findings
            .iter()
            .find(|f| f.label == "overall_mean_rate")
            .unwrap();
        let rate: f64 = serde_json::from_value(mean_rate.value.clone()).unwrap();
        assert!(rate == 0.0, "Expected rate 0.0, got {}", rate);

        let per_session_table = result.tables.iter().find(|t| t.name == "per_session").unwrap();
        let row = &per_session_table.rows[0];
        // degradation_ratio should be 0.0 (both first and last are 0)
        let degradation: f64 = serde_json::from_value(row[4].clone()).unwrap();
        assert!(
            degradation == 0.0,
            "Expected degradation_ratio 0.0, got {}",
            degradation
        );
    }

    #[test]
    fn multiple_sessions_same_project_aggregate_correctly() {
        // Session A: 1 correction in 4 user messages (project "alpha")
        let mut class_a = vec![MessageClassification::HumanCorrection; 1];
        class_a.extend(vec![MessageClassification::HumanDirective; 3]);
        let session_a = make_session("sa", &class_a, Some("alpha"));

        // Session B: 3 corrections in 6 user messages (project "alpha")
        let mut class_b = vec![MessageClassification::HumanCorrection; 3];
        class_b.extend(vec![MessageClassification::HumanDirective; 3]);
        let session_b = make_session("sb", &class_b, Some("alpha"));

        let technique = CorrectionRate;
        let result = technique.run(&[session_a, session_b]).unwrap();

        // Per-project table should have 1 row for "alpha"
        let per_project_table = result.tables.iter().find(|t| t.name == "per_project").unwrap();
        assert_eq!(per_project_table.rows.len(), 1);

        let row = &per_project_table.rows[0];
        // project name
        let project: String = serde_json::from_value(row[0].clone()).unwrap();
        assert_eq!(project, "alpha");
        // aggregate correction_rate = (1+3) / (4+6) = 0.4
        let agg_rate: f64 = serde_json::from_value(row[1].clone()).unwrap();
        assert!(
            (agg_rate - 0.4).abs() < 1e-9,
            "Expected aggregate rate 0.4, got {}",
            agg_rate
        );
        // total corrections = 4
        let total_corrections: usize = serde_json::from_value(row[2].clone()).unwrap();
        assert_eq!(total_corrections, 4);
        // total user_messages = 10
        let total_user_msgs: usize = serde_json::from_value(row[3].clone()).unwrap();
        assert_eq!(total_user_msgs, 10);
        // session_count = 2
        let session_count: usize = serde_json::from_value(row[4].clone()).unwrap();
        assert_eq!(session_count, 2);

        // Overall mean rate should be mean of 0.25 and 0.5 = 0.375
        let mean_rate = result
            .findings
            .iter()
            .find(|f| f.label == "overall_mean_rate")
            .unwrap();
        let rate: f64 = serde_json::from_value(mean_rate.value.clone()).unwrap();
        assert!(
            (rate - 0.375).abs() < 1e-9,
            "Expected mean rate 0.375, got {}",
            rate
        );
    }

    #[test]
    fn unknown_project_when_none() {
        let classifications = vec![MessageClassification::HumanDirective; 3];
        let session = make_session("s4", &classifications, None);
        let technique = CorrectionRate;
        let result = technique.run(&[session]).unwrap();

        let per_project_table = result.tables.iter().find(|t| t.name == "per_project").unwrap();
        let project: String =
            serde_json::from_value(per_project_table.rows[0][0].clone()).unwrap();
        assert_eq!(project, "unknown");
    }

    #[test]
    fn median_with_even_number_of_sessions() {
        // Two sessions with rates 0.0 and 0.5 → median = 0.25
        let session_a = make_session(
            "sa",
            &[MessageClassification::HumanDirective; 4],
            Some("p"),
        );
        let mut class_b = vec![MessageClassification::HumanCorrection; 2];
        class_b.extend(vec![MessageClassification::HumanDirective; 2]);
        let session_b = make_session("sb", &class_b, Some("p"));

        let technique = CorrectionRate;
        let result = technique.run(&[session_a, session_b]).unwrap();

        let median = result
            .findings
            .iter()
            .find(|f| f.label == "overall_median_rate")
            .unwrap();
        let m: f64 = serde_json::from_value(median.value.clone()).unwrap();
        assert!(
            (m - 0.25).abs() < 1e-9,
            "Expected median 0.25, got {}",
            m
        );
    }

    #[test]
    fn empty_sessions_slice() {
        let technique = CorrectionRate;
        let result = technique.run(&[]).unwrap();

        let mean_rate = result
            .findings
            .iter()
            .find(|f| f.label == "overall_mean_rate")
            .unwrap();
        let rate: f64 = serde_json::from_value(mean_rate.value.clone()).unwrap();
        assert!(rate == 0.0);

        assert!(result.tables.iter().find(|t| t.name == "per_session").unwrap().rows.is_empty());
        assert!(result.tables.iter().find(|t| t.name == "per_project").unwrap().rows.is_empty());
    }
}
