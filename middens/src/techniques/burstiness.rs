//! Barabasi burstiness and memory coefficients for tool usage patterns.
//!
//! Computes the burstiness coefficient B and memory coefficient M for each tool
//! type across all sessions, measuring whether tool usage is bursty (clustered),
//! Poisson (random), or periodic (evenly spaced).

use std::collections::HashMap;

use anyhow::Result;
use serde_json::json;

use super::{DataTable, Finding, Technique, TechniqueResult};
use crate::session::Session;

/// Barabasi burstiness and memory coefficients technique.
pub struct Burstiness;

impl Technique for Burstiness {
    fn name(&self) -> &str {
        "burstiness"
    }

    fn description(&self) -> &str {
        "Barab\u{00e1}si burstiness and memory coefficients for tool usage patterns"
    }

    fn requires_python(&self) -> bool {
        false
    }

    fn is_essential(&self) -> bool {
        true
    }

    fn run(&self, sessions: &[Session]) -> Result<TechniqueResult> {
        // Collect all tool sequences across all sessions into one combined sequence.
        let combined_sequence: Vec<&str> =
            sessions.iter().flat_map(|s| s.tool_sequence()).collect();

        if combined_sequence.is_empty() {
            return Ok(TechniqueResult {
                name: self.name().to_string(),
                summary: "No tool calls found in any session.".to_string(),
                findings: vec![Finding {
                    label: "tools_analyzed".to_string(),
                    value: json!(0),
                    description: Some("No tool calls found".to_string()),
                }],
                tables: vec![],
                figures: vec![],
            });
        }

        // Build position lists: for each tool, record the indices where it appears.
        let mut positions: HashMap<&str, Vec<usize>> = HashMap::new();
        for (i, tool) in combined_sequence.iter().enumerate() {
            positions.entry(tool).or_default().push(i);
        }

        // Compute per-tool metrics for tools appearing 3+ times (need at least 2 intervals).
        let mut tool_metrics: Vec<ToolMetrics> = Vec::new();

        for (tool_name, pos) in &positions {
            if pos.len() < 3 {
                if pos.len() == 2 {
                    // Exactly 2 occurrences: 1 interval, can compute B but not M.
                    let interval = pos[1] - pos[0] - 1;
                    // With a single interval, sigma = 0, mu = interval.
                    // B = (0 - mu) / (0 + mu) = -1 if mu > 0, undefined if mu == 0.
                    let b = if interval > 0 {
                        -1.0 // Single interval: sigma=0, perfectly "periodic" by default.
                    } else {
                        // Adjacent: interval=0, sigma=0, mu=0 => 0/0. Treat as maximally bursty.
                        1.0
                    };
                    tool_metrics.push(ToolMetrics {
                        name: tool_name.to_string(),
                        burstiness_b: b,
                        memory_m: None,
                        mean_interval: interval as f64,
                        count: pos.len(),
                    });
                }
                continue;
            }

            // Compute inter-event intervals.
            let intervals: Vec<f64> = pos.windows(2).map(|w| (w[1] - w[0] - 1) as f64).collect();

            let n = intervals.len() as f64;
            let mu = intervals.iter().sum::<f64>() / n;
            let variance = intervals.iter().map(|x| (x - mu).powi(2)).sum::<f64>() / n;
            let sigma = variance.sqrt();

            // B = (sigma - mu) / (sigma + mu)
            let b = if (sigma + mu).abs() < f64::EPSILON {
                // All intervals are zero: tool always adjacent, maximally bursty.
                1.0
            } else {
                (sigma - mu) / (sigma + mu)
            };

            // Memory M: Pearson correlation between consecutive intervals.
            // Need at least 3 intervals (tool appears 4+ times) for meaningful correlation.
            let m = if intervals.len() >= 3 {
                Some(pearson_consecutive(&intervals))
            } else {
                None
            };

            tool_metrics.push(ToolMetrics {
                name: tool_name.to_string(),
                burstiness_b: b,
                memory_m: m,
                mean_interval: mu,
                count: pos.len(),
            });
        }

        // Sort by burstiness descending for consistent output.
        tool_metrics.sort_by(|a, b| {
            b.burstiness_b
                .partial_cmp(&a.burstiness_b)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        // Compute frequency-weighted aggregate B and M.
        let total_weight: f64 = tool_metrics.iter().map(|t| t.count as f64).sum();
        let aggregate_b = if total_weight > 0.0 {
            tool_metrics
                .iter()
                .map(|t| t.burstiness_b * t.count as f64)
                .sum::<f64>()
                / total_weight
        } else {
            0.0
        };

        let m_total_weight: f64 = tool_metrics
            .iter()
            .filter_map(|t| t.memory_m.map(|_| t.count as f64))
            .sum();
        let aggregate_m = if m_total_weight > 0.0 {
            tool_metrics
                .iter()
                .filter_map(|t| t.memory_m.map(|m| m * t.count as f64))
                .sum::<f64>()
                / m_total_weight
        } else {
            f64::NAN
        };

        // Find burstiest and most periodic tools.
        let burstiest = tool_metrics.iter().max_by(|a, b| {
            a.burstiness_b
                .partial_cmp(&b.burstiness_b)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        let most_periodic = tool_metrics.iter().min_by(|a, b| {
            a.burstiness_b
                .partial_cmp(&b.burstiness_b)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        // Build findings.
        let mut findings = vec![
            Finding {
                label: "aggregate_burstiness".to_string(),
                value: json!(round4(aggregate_b)),
                description: Some(
                    "Frequency-weighted mean burstiness across all tools".to_string(),
                ),
            },
            Finding {
                label: "aggregate_memory".to_string(),
                value: if aggregate_m.is_nan() {
                    json!(null)
                } else {
                    json!(round4(aggregate_m))
                },
                description: Some(
                    "Frequency-weighted mean memory coefficient across tools with sufficient data"
                        .to_string(),
                ),
            },
        ];

        if let Some(t) = burstiest {
            findings.push(Finding {
                label: "burstiest_tool".to_string(),
                value: json!({ "name": t.name, "B": round4(t.burstiness_b) }),
                description: Some("Tool with highest burstiness coefficient".to_string()),
            });
        }
        if let Some(t) = most_periodic {
            findings.push(Finding {
                label: "most_periodic_tool".to_string(),
                value: json!({ "name": t.name, "B": round4(t.burstiness_b) }),
                description: Some("Tool with lowest burstiness coefficient".to_string()),
            });
        }
        findings.push(Finding {
            label: "tools_analyzed".to_string(),
            value: json!(tool_metrics.len()),
            description: Some("Number of tool types with sufficient data for analysis".to_string()),
        });

        // Build data table.
        let columns = vec![
            "tool_name".to_string(),
            "burstiness_b".to_string(),
            "memory_m".to_string(),
            "mean_interval".to_string(),
            "count".to_string(),
        ];
        let rows: Vec<Vec<serde_json::Value>> = tool_metrics
            .iter()
            .map(|t| {
                vec![
                    json!(t.name),
                    json!(round4(t.burstiness_b)),
                    t.memory_m.map_or(json!(null), |m| json!(round4(m))),
                    json!(round4(t.mean_interval)),
                    json!(t.count),
                ]
            })
            .collect();

        let table = DataTable {
            name: "per_tool_burstiness".to_string(),
            columns,
            rows,
        };

        let b_interp = if aggregate_b > 0.5 {
            "highly bursty (clustered)"
        } else if aggregate_b > 0.0 {
            "mildly bursty"
        } else if aggregate_b > -0.5 {
            "near-Poisson to mildly periodic"
        } else {
            "strongly periodic"
        };

        let summary = format!(
            "Analyzed {} tool types across {} total tool calls. \
             Aggregate burstiness B={:.4} ({}). {}",
            tool_metrics.len(),
            combined_sequence.len(),
            aggregate_b,
            b_interp,
            if aggregate_m.is_nan() {
                "Insufficient data for aggregate memory coefficient.".to_string()
            } else {
                format!("Aggregate memory M={:.4}.", aggregate_m)
            },
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

/// Per-tool burstiness metrics.
struct ToolMetrics {
    name: String,
    burstiness_b: f64,
    memory_m: Option<f64>,
    mean_interval: f64,
    count: usize,
}

/// Pearson correlation between consecutive elements: corr(tau_i, tau_{i+1}).
fn pearson_consecutive(intervals: &[f64]) -> f64 {
    let n = intervals.len() - 1;
    if n == 0 {
        return 0.0;
    }

    let xs = &intervals[..n];
    let ys = &intervals[1..];

    let n_f = n as f64;
    let mean_x = xs.iter().sum::<f64>() / n_f;
    let mean_y = ys.iter().sum::<f64>() / n_f;

    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;

    for i in 0..n {
        let dx = xs[i] - mean_x;
        let dy = ys[i] - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }

    let denom = (var_x * var_y).sqrt();
    if denom < f64::EPSILON {
        0.0
    } else {
        cov / denom
    }
}

/// Round to 4 decimal places.
fn round4(v: f64) -> f64 {
    (v * 10000.0).round() / 10000.0
}
