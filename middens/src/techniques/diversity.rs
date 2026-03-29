//! Shannon/Simpson diversity indices and species-area analysis for tool usage.

use std::collections::HashMap;

use anyhow::Result;
use serde_json::json;

use crate::session::Session;

use super::{DataTable, Finding, Technique, TechniqueResult};

/// Tool usage diversity indices and species-area analysis.
pub struct Diversity;

/// Per-session diversity metrics.
struct SessionMetrics {
    session_id: String,
    shannon: f64,
    simpson: f64,
    evenness: f64,
    richness: usize,
    abundance: usize,
}

impl Diversity {
    /// Compute diversity metrics for a single session's tool sequence.
    fn compute_metrics(session: &Session) -> SessionMetrics {
        let tools = session.tool_sequence();
        let abundance = tools.len();

        if abundance == 0 {
            return SessionMetrics {
                session_id: session.id.clone(),
                shannon: 0.0,
                simpson: 0.0,
                evenness: 0.0,
                richness: 0,
                abundance: 0,
            };
        }

        // Count occurrences of each tool type.
        let mut counts: HashMap<&str, usize> = HashMap::new();
        for tool in &tools {
            *counts.entry(tool).or_insert(0) += 1;
        }

        let richness = counts.len();
        let n = abundance as f64;

        // Proportions and indices.
        let mut shannon = 0.0f64;
        let mut simpson_sum = 0.0f64;

        for &count in counts.values() {
            let p = count as f64 / n;
            if p > 0.0 {
                shannon -= p * p.ln();
            }
            simpson_sum += p * p;
        }

        let simpson = 1.0 - simpson_sum;

        // Evenness: H / ln(S), undefined (set to 0) if S <= 1.
        let evenness = if richness <= 1 {
            0.0
        } else {
            shannon / (richness as f64).ln()
        };

        SessionMetrics {
            session_id: session.id.clone(),
            shannon,
            simpson,
            evenness,
            richness,
            abundance,
        }
    }

    /// Fit species-area curve S = c * A^z via log-log linear regression.
    /// Returns (z, r_squared). Filters out sessions with A=0 or S=0.
    fn fit_species_area(metrics: &[SessionMetrics]) -> (f64, f64) {
        // Collect valid (log_a, log_s) pairs.
        let points: Vec<(f64, f64)> = metrics
            .iter()
            .filter(|m| m.abundance > 0 && m.richness > 0)
            .map(|m| ((m.abundance as f64).ln(), (m.richness as f64).ln()))
            .collect();

        let n = points.len() as f64;
        if n < 2.0 {
            return (0.0, 0.0);
        }

        let sum_x: f64 = points.iter().map(|(x, _)| x).sum();
        let sum_y: f64 = points.iter().map(|(_, y)| y).sum();
        let sum_xy: f64 = points.iter().map(|(x, y)| x * y).sum();
        let sum_x2: f64 = points.iter().map(|(x, _)| x * x).sum();

        let denom = n * sum_x2 - sum_x * sum_x;
        if denom.abs() < f64::EPSILON {
            return (0.0, 0.0);
        }

        let z = (n * sum_xy - sum_x * sum_y) / denom;
        let intercept = (sum_y - z * sum_x) / n;

        // R^2 = 1 - SS_res / SS_tot
        let mean_y = sum_y / n;
        let ss_tot: f64 = points.iter().map(|(_, y)| (y - mean_y).powi(2)).sum();
        let ss_res: f64 = points
            .iter()
            .map(|(x, y)| {
                let predicted = intercept + z * x;
                (y - predicted).powi(2)
            })
            .sum();

        let r_squared = if ss_tot.abs() < f64::EPSILON {
            0.0
        } else {
            1.0 - ss_res / ss_tot
        };

        (z, r_squared)
    }
}

impl Technique for Diversity {
    fn name(&self) -> &str {
        "diversity"
    }

    fn description(&self) -> &str {
        "Tool usage diversity indices and species-area analysis"
    }

    fn requires_python(&self) -> bool {
        false
    }

    fn is_essential(&self) -> bool {
        true
    }

    fn run(&self, sessions: &[Session]) -> Result<TechniqueResult> {
        let metrics: Vec<SessionMetrics> = sessions
            .iter()
            .map(|s| Self::compute_metrics(s))
            .collect();

        let analyzed = metrics.len();

        // Aggregate statistics.
        let (mean_shannon, median_shannon, mean_simpson, mean_evenness, monoculture_count) =
            if metrics.is_empty() {
                (0.0, 0.0, 0.0, 0.0, 0usize)
            } else {
                let sum_shannon: f64 = metrics.iter().map(|m| m.shannon).sum();
                let sum_simpson: f64 = metrics.iter().map(|m| m.simpson).sum();
                let sum_evenness: f64 = metrics.iter().map(|m| m.evenness).sum();
                let n = metrics.len() as f64;

                let mean_sh = sum_shannon / n;
                let mean_si = sum_simpson / n;
                let mean_ev = sum_evenness / n;

                // Median Shannon.
                let mut shannons: Vec<f64> = metrics.iter().map(|m| m.shannon).collect();
                shannons.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
                let median_sh = if shannons.len() % 2 == 0 {
                    let mid = shannons.len() / 2;
                    (shannons[mid - 1] + shannons[mid]) / 2.0
                } else {
                    shannons[shannons.len() / 2]
                };

                let mono = metrics.iter().filter(|m| m.evenness < 0.3).count();

                (mean_sh, median_sh, mean_si, mean_ev, mono)
            };

        let monoculture_fraction = if analyzed > 0 {
            monoculture_count as f64 / analyzed as f64
        } else {
            0.0
        };

        // Species-area curve.
        let (species_area_z, species_area_r_squared) = Self::fit_species_area(&metrics);

        // Build findings.
        let findings = vec![
            Finding {
                label: "mean_shannon".to_string(),
                value: json!(mean_shannon),
                description: Some("Mean Shannon entropy across sessions".to_string()),
            },
            Finding {
                label: "median_shannon".to_string(),
                value: json!(median_shannon),
                description: Some("Median Shannon entropy across sessions".to_string()),
            },
            Finding {
                label: "mean_simpson".to_string(),
                value: json!(mean_simpson),
                description: Some("Mean Simpson diversity index across sessions".to_string()),
            },
            Finding {
                label: "mean_evenness".to_string(),
                value: json!(mean_evenness),
                description: Some("Mean evenness (H/ln(S)) across sessions".to_string()),
            },
            Finding {
                label: "species_area_z".to_string(),
                value: json!(species_area_z),
                description: Some(
                    "Species-area exponent z from S = c * A^z fit".to_string(),
                ),
            },
            Finding {
                label: "species_area_r_squared".to_string(),
                value: json!(species_area_r_squared),
                description: Some("R-squared of species-area log-log fit".to_string()),
            },
            Finding {
                label: "monoculture_count".to_string(),
                value: json!(monoculture_count),
                description: Some(
                    "Number of sessions with evenness < 0.3 (monoculture)".to_string(),
                ),
            },
            Finding {
                label: "monoculture_fraction".to_string(),
                value: json!(monoculture_fraction),
                description: Some("Fraction of sessions that are monocultures".to_string()),
            },
            Finding {
                label: "sessions_analyzed".to_string(),
                value: json!(analyzed),
                description: Some("Total sessions analyzed".to_string()),
            },
        ];

        // Build per-session data table.
        let columns = vec![
            "session_id".to_string(),
            "shannon".to_string(),
            "simpson".to_string(),
            "evenness".to_string(),
            "richness".to_string(),
            "abundance".to_string(),
        ];

        let rows: Vec<Vec<serde_json::Value>> = metrics
            .iter()
            .map(|m| {
                vec![
                    json!(m.session_id),
                    json!(m.shannon),
                    json!(m.simpson),
                    json!(m.evenness),
                    json!(m.richness),
                    json!(m.abundance),
                ]
            })
            .collect();

        let table = DataTable {
            name: "per_session_diversity".to_string(),
            columns,
            rows,
        };

        // Summary text.
        let summary = format!(
            "Analyzed {} sessions. Mean Shannon entropy: {:.3}, median: {:.3}. \
             Mean Simpson diversity: {:.3}. Mean evenness: {:.3}. \
             Species-area exponent z={:.3} (R²={:.3}). \
             {} monoculture sessions ({:.1}%).",
            analyzed,
            mean_shannon,
            median_shannon,
            mean_simpson,
            mean_evenness,
            species_area_z,
            species_area_r_squared,
            monoculture_count,
            monoculture_fraction * 100.0,
        );

        Ok(TechniqueResult {
            name: self.name().to_string(),
            summary,
            findings,
            tables: vec![table],
            figures: vec![],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::session::*;
    use std::path::PathBuf;

    /// Helper to create a minimal session with the given tool calls.
    fn make_session(id: &str, tool_names: &[&str]) -> Session {
        let tool_calls: Vec<ToolCall> = tool_names
            .iter()
            .map(|name| ToolCall {
                id: String::new(),
                name: name.to_string(),
                input: serde_json::Value::Null,
            })
            .collect();

        // Put all tool calls in a single assistant message.
        let messages = if tool_calls.is_empty() {
            vec![]
        } else {
            vec![Message {
                role: MessageRole::Assistant,
                timestamp: None,
                text: String::new(),
                thinking: None,
                tool_calls,
                tool_results: vec![],
                classification: MessageClassification::Unclassified,
                raw_content: vec![],
            }]
        };

        Session {
            id: id.to_string(),
            source_path: PathBuf::from("test"),
            source_tool: SourceTool::ClaudeCode,
            session_type: SessionType::Interactive,
            messages,
            metadata: SessionMetadata::default(),
            environment: EnvironmentFingerprint::default(),
        }
    }

    #[test]
    fn single_tool_bash_only() {
        let session = make_session("mono", &["Bash", "Bash", "Bash", "Bash"]);
        let metrics = Diversity::compute_metrics(&session);

        assert_eq!(metrics.richness, 1);
        assert_eq!(metrics.abundance, 4);
        assert!((metrics.shannon - 0.0).abs() < 1e-10, "Shannon should be 0 for single tool");
        assert!((metrics.simpson - 0.0).abs() < 1e-10, "Simpson should be 0 for single tool");
        assert!((metrics.evenness - 0.0).abs() < 1e-10, "Evenness should be 0 when S=1");
    }

    #[test]
    fn equal_four_tools() {
        // 4 tools, each used 3 times = 12 total, perfectly even.
        let tools: Vec<&str> = ["Bash", "Read", "Edit", "Write"]
            .iter()
            .flat_map(|t| std::iter::repeat_n(*t, 3))
            .collect();
        let session = make_session("even4", &tools);
        let metrics = Diversity::compute_metrics(&session);

        let expected_shannon = (4.0f64).ln();
        let expected_simpson = 0.75;

        assert_eq!(metrics.richness, 4);
        assert_eq!(metrics.abundance, 12);
        assert!(
            (metrics.shannon - expected_shannon).abs() < 1e-10,
            "Shannon should be ln(4)={expected_shannon}, got {}",
            metrics.shannon
        );
        assert!(
            (metrics.simpson - expected_simpson).abs() < 1e-10,
            "Simpson should be 0.75, got {}",
            metrics.simpson
        );
        // Evenness should be 1.0 for perfectly even distribution.
        assert!(
            (metrics.evenness - 1.0).abs() < 1e-10,
            "Evenness should be 1.0 for uniform distribution, got {}",
            metrics.evenness
        );
    }

    #[test]
    fn species_area_synthetic() {
        // Synthetic data: 3 sessions with known (A, S) pairs.
        // S = c * A^z  =>  log(S) = log(c) + z * log(A)
        // We want z ~ 0.35. With (10,3), (100,7), (1000,15):
        //   log(10)=2.303, log(3)=1.099
        //   log(100)=4.605, log(7)=1.946
        //   log(1000)=6.908, log(15)=2.708
        // These give z ~ 0.35.

        // Build sessions with the right abundances and richnesses.
        // Session 1: 10 tool calls, 3 unique tools.
        let mut tools1 = vec!["Bash"; 8];
        tools1.extend(["Read", "Edit"]);
        assert_eq!(tools1.len(), 10);

        // Session 2: 100 tool calls, 7 unique tools.
        let mut tools2 = vec!["Bash"; 94];
        tools2.extend(["Read", "Edit", "Write", "Grep", "Glob", "Search"]);
        assert_eq!(tools2.len(), 100);

        // Session 3: 1000 tool calls, 15 unique tools.
        let mut tools3 = vec!["Bash"; 985];
        tools3.extend([
            "Read", "Edit", "Write", "Grep", "Glob", "Search", "Agent", "Skill", "WebFetch",
            "WebSearch", "NotebookEdit", "TodoWrite", "Lint", "Format",
        ]);
        assert_eq!(tools3.len(), 999);
        tools3.push("Bash"); // 1000 total, still 15 unique
        assert_eq!(tools3.len(), 1000);

        let sessions = vec![
            make_session("s1", &tools1),
            make_session("s2", &tools2),
            make_session("s3", &tools3),
        ];

        let metrics: Vec<SessionMetrics> =
            sessions.iter().map(|s| Diversity::compute_metrics(s)).collect();

        // Verify richness/abundance.
        assert_eq!(metrics[0].richness, 3);
        assert_eq!(metrics[0].abundance, 10);
        assert_eq!(metrics[1].richness, 7);
        assert_eq!(metrics[1].abundance, 100);
        assert_eq!(metrics[2].richness, 15);
        assert_eq!(metrics[2].abundance, 1000);

        let (z, r_squared) = Diversity::fit_species_area(&metrics);

        assert!(
            (z - 0.35).abs() < 0.05,
            "Species-area z should be ~0.35, got {z}"
        );
        assert!(
            r_squared > 0.95,
            "R-squared should be >0.95 for well-fitted data, got {r_squared}"
        );
    }

    #[test]
    fn empty_session_returns_zeroes() {
        let session = make_session("empty", &[]);
        let metrics = Diversity::compute_metrics(&session);

        assert_eq!(metrics.richness, 0);
        assert_eq!(metrics.abundance, 0);
        assert!((metrics.shannon).abs() < 1e-10);
        assert!((metrics.simpson).abs() < 1e-10);
        assert!((metrics.evenness).abs() < 1e-10);
    }

    #[test]
    fn run_produces_complete_result() {
        let sessions = vec![
            make_session("s1", &["Bash", "Bash", "Read"]),
            make_session("s2", &["Edit", "Edit", "Edit", "Edit"]),
        ];

        let technique = Diversity;
        let result = technique.run(&sessions).unwrap();

        assert_eq!(result.name, "diversity");

        // Check all expected findings are present.
        let finding_labels: Vec<&str> = result.findings.iter().map(|f| f.label.as_str()).collect();
        assert!(finding_labels.contains(&"mean_shannon"));
        assert!(finding_labels.contains(&"median_shannon"));
        assert!(finding_labels.contains(&"mean_simpson"));
        assert!(finding_labels.contains(&"mean_evenness"));
        assert!(finding_labels.contains(&"species_area_z"));
        assert!(finding_labels.contains(&"species_area_r_squared"));
        assert!(finding_labels.contains(&"monoculture_count"));
        assert!(finding_labels.contains(&"monoculture_fraction"));
        assert!(finding_labels.contains(&"sessions_analyzed"));

        // Check sessions_analyzed.
        let analyzed = result
            .findings
            .iter()
            .find(|f| f.label == "sessions_analyzed")
            .unwrap();
        assert_eq!(analyzed.value, json!(2));

        // Check data table.
        assert_eq!(result.tables.len(), 1);
        assert_eq!(result.tables[0].name, "per_session_diversity");
        assert_eq!(result.tables[0].rows.len(), 2);
        assert_eq!(
            result.tables[0].columns,
            vec!["session_id", "shannon", "simpson", "evenness", "richness", "abundance"]
        );
    }

    #[test]
    fn monoculture_detection() {
        // Session with only one tool type has evenness=0 < 0.3 => monoculture.
        // Session with two tools, very uneven: e.g., 99 Bash + 1 Read.
        let sessions = vec![
            make_session("mono1", &["Bash"; 10]),
            make_session("mono2", &{
                let mut v = vec!["Bash"; 99];
                v.push("Read");
                v
            }),
            make_session(
                "diverse",
                &["Bash", "Read", "Edit", "Write", "Bash", "Read", "Edit", "Write"],
            ),
        ];

        let technique = Diversity;
        let result = technique.run(&sessions).unwrap();

        let mono_count = result
            .findings
            .iter()
            .find(|f| f.label == "monoculture_count")
            .unwrap();
        // mono1 has evenness=0, mono2 has very low evenness, diverse has high evenness.
        // mono2: H = -(0.99*ln(0.99) + 0.01*ln(0.01)) ≈ 0.056, ln(2) ≈ 0.693, E ≈ 0.081 < 0.3
        assert_eq!(mono_count.value, json!(2), "Two sessions should be monocultures");
    }

    #[test]
    fn empty_sessions_slice() {
        let technique = Diversity;
        let result = technique.run(&[]).unwrap();

        let analyzed = result
            .findings
            .iter()
            .find(|f| f.label == "sessions_analyzed")
            .unwrap();
        assert_eq!(analyzed.value, json!(0));
    }
}
