//! Entropy rate and anomaly detection in tool sequences.
//!
//! Computes conditional entropy H(X_t | X_{t-1}) over sliding windows of tool-call
//! sequences, then flags windows whose entropy deviates by more than 2 sigma from
//! the session mean (high = chaos, low = rigidity).

use std::collections::HashMap;

use anyhow::Result;
use serde_json::json;

use crate::session::Session;

use super::{DataTable, Finding, Technique, TechniqueResult};

/// Default sliding window size (number of tool events per window).
const DEFAULT_WINDOW_SIZE: usize = 20;

/// Number of standard deviations for anomaly threshold.
const SIGMA_THRESHOLD: f64 = 2.0;

/// Entropy rate and anomaly detection technique.
pub struct EntropyRate;

/// Per-session analysis results (internal).
struct SessionEntropy {
    session_id: String,
    mean_entropy: f64,
    stddev: f64,
    num_anomalies: usize,
    low_anomalies: usize,
    high_anomalies: usize,
}

/// Compute conditional entropy H(X_t | X_{t-1}) for a window of tool names.
///
/// H(X_t | X_{t-1}) = -sum_{x,y} p(x,y) * log2(p(y|x))
///
/// where p(x,y) is the joint probability of the bigram (x, y) and p(y|x) = p(x,y) / p(x).
fn conditional_entropy(window: &[&str]) -> f64 {
    if window.len() < 2 {
        return 0.0;
    }

    let num_bigrams = window.len() - 1;

    // Count bigrams and unigram prefixes.
    let mut bigram_counts: HashMap<(&str, &str), usize> = HashMap::new();
    let mut prefix_counts: HashMap<&str, usize> = HashMap::new();

    for pair in window.windows(2) {
        let x = pair[0];
        let y = pair[1];
        *bigram_counts.entry((x, y)).or_insert(0) += 1;
        *prefix_counts.entry(x).or_insert(0) += 1;
    }

    let mut h = 0.0;
    for (&(x, _y), &count) in &bigram_counts {
        let p_xy = count as f64 / num_bigrams as f64;
        let p_y_given_x = count as f64 / prefix_counts[x] as f64;
        h -= p_xy * p_y_given_x.log2();
    }

    h
}

/// Compute mean and standard deviation for a slice of f64 values.
fn mean_stddev(values: &[f64]) -> (f64, f64) {
    if values.is_empty() {
        return (0.0, 0.0);
    }
    let n = values.len() as f64;
    let mean = values.iter().sum::<f64>() / n;
    if values.len() == 1 {
        return (mean, 0.0);
    }
    let variance = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n;
    (mean, variance.sqrt())
}

/// Analyze a single session, returning None if the session has too few tool calls.
fn analyze_session(session: &Session, window_size: usize) -> Option<SessionEntropy> {
    let tools = session.tool_sequence();
    if tools.len() < window_size {
        return None;
    }

    // Compute conditional entropy for each sliding window.
    let window_entropies: Vec<f64> = tools
        .windows(window_size)
        .map(|w| conditional_entropy(w))
        .collect();

    if window_entropies.is_empty() {
        return None;
    }

    let (mean, stddev) = mean_stddev(&window_entropies);

    let mut low_anomalies = 0usize;
    let mut high_anomalies = 0usize;

    // Only flag anomalies if there is non-zero variance.
    if stddev > 0.0 {
        for &h in &window_entropies {
            if h > mean + SIGMA_THRESHOLD * stddev {
                high_anomalies += 1;
            } else if h < mean - SIGMA_THRESHOLD * stddev {
                low_anomalies += 1;
            }
        }
    }

    Some(SessionEntropy {
        session_id: session.id.clone(),
        mean_entropy: mean,
        stddev,
        num_anomalies: low_anomalies + high_anomalies,
        low_anomalies,
        high_anomalies,
    })
}

impl Technique for EntropyRate {
    fn name(&self) -> &str {
        "entropy"
    }

    fn description(&self) -> &str {
        "Entropy rate and anomaly detection in tool sequences"
    }

    fn requires_python(&self) -> bool {
        false
    }

    fn is_essential(&self) -> bool {
        true
    }

    fn run(&self, sessions: &[Session]) -> Result<TechniqueResult> {
        let results: Vec<SessionEntropy> = sessions
            .iter()
            .filter_map(|s| analyze_session(s, DEFAULT_WINDOW_SIZE))
            .collect();

        let sessions_analyzed = results.len();

        // Aggregate across all sessions.
        let all_means: Vec<f64> = results.iter().map(|r| r.mean_entropy).collect();
        let (overall_mean, _) = mean_stddev(&all_means);

        let total_anomalies: usize = results.iter().map(|r| r.num_anomalies).sum();
        let total_low: usize = results.iter().map(|r| r.low_anomalies).sum();
        let total_high: usize = results.iter().map(|r| r.high_anomalies).sum();

        let low_high_ratio = if total_high > 0 {
            total_low as f64 / total_high as f64
        } else if total_low > 0 {
            f64::INFINITY
        } else {
            0.0
        };

        // Build findings.
        let findings = vec![
            Finding {
                label: "mean_entropy".to_string(),
                value: json!(overall_mean),
                description: Some(
                    "Overall mean conditional entropy H(X_t|X_{t-1}) across sessions".to_string(),
                ),
            },
            Finding {
                label: "anomaly_count".to_string(),
                value: json!(total_anomalies),
                description: Some("Total number of anomalous windows (>2 sigma)".to_string()),
            },
            Finding {
                label: "low_entropy_anomalies".to_string(),
                value: json!(total_low),
                description: Some(
                    "Windows with entropy >2 sigma below mean (rigidity)".to_string(),
                ),
            },
            Finding {
                label: "high_entropy_anomalies".to_string(),
                value: json!(total_high),
                description: Some("Windows with entropy >2 sigma above mean (chaos)".to_string()),
            },
            Finding {
                label: "low_high_ratio".to_string(),
                value: if low_high_ratio.is_infinite() {
                    json!("Infinity")
                } else {
                    json!(low_high_ratio)
                },
                description: Some("Ratio of low-entropy to high-entropy anomalies".to_string()),
            },
            Finding {
                label: "sessions_analyzed".to_string(),
                value: json!(sessions_analyzed),
                description: Some(
                    "Number of sessions with enough tool calls for analysis".to_string(),
                ),
            },
        ];

        // Build per-session data table.
        let columns = vec![
            "session_id".to_string(),
            "mean_entropy".to_string(),
            "stddev".to_string(),
            "num_anomalies".to_string(),
        ];
        let rows: Vec<Vec<serde_json::Value>> = results
            .iter()
            .map(|r| {
                vec![
                    json!(r.session_id),
                    json!(r.mean_entropy),
                    json!(r.stddev),
                    json!(r.num_anomalies),
                ]
            })
            .collect();

        let tables = vec![DataTable {
            name: "per_session_entropy".to_string(),
            columns,
            rows,
        }];

        let summary = format!(
            "Analyzed {} sessions. Mean conditional entropy: {:.4}. \
             Total anomalies: {} (low: {}, high: {}). Low:high ratio: {:.2}.",
            sessions_analyzed,
            overall_mean,
            total_anomalies,
            total_low,
            total_high,
            if low_high_ratio.is_infinite() {
                f64::NAN
            } else {
                low_high_ratio
            },
        );

        Ok(TechniqueResult {
            name: self.name().to_string(),
            summary,
            findings,
            tables,
            figures: vec![],
        })
    }
}

