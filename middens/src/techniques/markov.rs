//! Markov chain tool transition analysis.
//!
//! Builds a first-order Markov chain from consecutive tool-call bigrams across
//! all sessions, then computes transition probabilities, self-loop rates,
//! stationary distribution, and entry tool frequencies.

use std::collections::{BTreeMap, HashMap};

use anyhow::Result;
use serde_json::json;

use super::{DataTable, Finding, Technique, TechniqueResult};
use crate::session::Session;

/// Markov chain tool transition analysis.
pub struct MarkovChain;

impl Technique for MarkovChain {
    fn name(&self) -> &str {
        "markov"
    }

    fn description(&self) -> &str {
        "Markov chain tool transition analysis"
    }

    fn requires_python(&self) -> bool {
        false
    }

    fn is_essential(&self) -> bool {
        true
    }

    fn run(&self, sessions: &[Session]) -> Result<TechniqueResult> {
        // Collect bigrams and entry tools.
        let mut bigram_counts: HashMap<(String, String), usize> = HashMap::new();
        let mut entry_counts: HashMap<String, usize> = HashMap::new();
        let mut total_bigrams: usize = 0;

        for session in sessions {
            let seq = session.tool_sequence();
            if seq.is_empty() {
                continue;
            }

            // Record entry tool (first tool in the session).
            *entry_counts.entry(seq[0].to_string()).or_default() += 1;

            // Record consecutive bigrams.
            for pair in seq.windows(2) {
                let from = pair[0].to_string();
                let to = pair[1].to_string();
                *bigram_counts.entry((from, to)).or_default() += 1;
                total_bigrams += 1;
            }
        }

        // If no bigrams at all, return a trivial result.
        if total_bigrams == 0 {
            return Ok(TechniqueResult {
                name: self.name().to_string(),
                summary: "No tool bigrams found (sessions had 0 or 1 tool calls each).".into(),
                findings: vec![Finding {
                    label: "total_bigrams".into(),
                    value: json!(0),
                    description: Some("Total bigrams analyzed".into()),
                }],
                tables: vec![],
                figures: vec![],
            });
        }

        // Build sorted tool index using BTreeMap for deterministic ordering.
        let mut tool_set: BTreeMap<&str, ()> = BTreeMap::new();
        for (from, to) in bigram_counts.keys() {
            tool_set.insert(from.as_str(), ());
            tool_set.insert(to.as_str(), ());
        }
        let tools: Vec<String> = tool_set.keys().map(|s| s.to_string()).collect();
        let tool_idx: HashMap<&str, usize> = tools
            .iter()
            .enumerate()
            .map(|(i, t)| (t.as_str(), i))
            .collect();
        let n = tools.len();

        // Build count matrix.
        let mut counts = vec![vec![0usize; n]; n];
        for ((from, to), &count) in &bigram_counts {
            let i = tool_idx[from.as_str()];
            let j = tool_idx[to.as_str()];
            counts[i][j] = count;
        }

        // Normalize rows to get transition probabilities.
        let mut prob = vec![vec![0.0f64; n]; n];
        for i in 0..n {
            let row_sum: usize = counts[i].iter().sum();
            if row_sum > 0 {
                for j in 0..n {
                    prob[i][j] = counts[i][j] as f64 / row_sum as f64;
                }
            }
        }

        // Self-loop rates (diagonal entries).
        let self_loops: Vec<(String, f64)> = tools
            .iter()
            .enumerate()
            .map(|(i, t)| (t.clone(), prob[i][i]))
            .collect();

        // Top-5 transitions by probability.
        let mut all_transitions: Vec<(String, String, f64)> = Vec::new();
        for i in 0..n {
            for j in 0..n {
                if prob[i][j] > 0.0 {
                    all_transitions.push((tools[i].clone(), tools[j].clone(), prob[i][j]));
                }
            }
        }
        all_transitions.sort_by(|a, b| b.2.partial_cmp(&a.2).unwrap_or(std::cmp::Ordering::Equal));
        let top5: Vec<_> = all_transitions.iter().take(5).collect();

        // Stationary distribution via power iteration.
        let stationary = compute_stationary(&prob, n);

        // Entry tool frequencies (sorted descending).
        let total_sessions_with_tools: usize = entry_counts.values().sum();
        let mut entry_freq: Vec<(String, f64)> = entry_counts
            .iter()
            .map(|(t, &c)| (t.clone(), c as f64 / total_sessions_with_tools as f64))
            .collect();
        entry_freq.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        // Build findings.
        let mut findings = Vec::new();

        findings.push(Finding {
            label: "total_bigrams".into(),
            value: json!(total_bigrams),
            description: Some("Total bigrams analyzed".into()),
        });

        // Top-5 transitions.
        for (rank, (from, to, p)) in top5.iter().enumerate() {
            findings.push(Finding {
                label: format!("top_transition_{}", rank + 1),
                value: json!({
                    "from": from,
                    "to": to,
                    "probability": p,
                }),
                description: Some(format!(
                    "#{} transition: {} -> {} (p={:.4})",
                    rank + 1,
                    from,
                    to,
                    p
                )),
            });
        }

        // Self-loop rates.
        for (tool, rate) in &self_loops {
            findings.push(Finding {
                label: format!("self_loop_{}", tool),
                value: json!(rate),
                description: Some(format!("Self-loop rate for {}: {:.4}", tool, rate)),
            });
        }

        // Entry tools (top entries).
        let entry_limit = entry_freq.len().min(5);
        for (tool, freq) in entry_freq.iter().take(entry_limit) {
            findings.push(Finding {
                label: format!("entry_tool_{}", tool),
                value: json!(freq),
                description: Some(format!("Entry frequency for {}: {:.4}", tool, freq)),
            });
        }

        // Stationary distribution.
        for (i, &pi) in stationary.iter().enumerate() {
            findings.push(Finding {
                label: format!("stationary_{}", tools[i]),
                value: json!(pi),
                description: Some(format!(
                    "Stationary probability for {}: {:.6}",
                    tools[i], pi
                )),
            });
        }

        // Build the data table: full transition matrix.
        let mut columns = vec!["from_tool".to_string()];
        columns.extend(tools.iter().cloned());

        let mut rows = Vec::new();
        for i in 0..n {
            let mut row: Vec<serde_json::Value> = vec![json!(tools[i])];
            for j in 0..n {
                row.push(json!(prob[i][j]));
            }
            rows.push(row);
        }

        let table = DataTable {
            name: "transition_matrix".into(),
            columns,
            rows,
            column_types: None,
        };

        // Build summary.
        let summary = format!(
            "Analyzed {} tool bigrams across {} unique tools. \
             Top transition: {} -> {} (p={:.4}). \
             Highest self-loop: {} ({:.4}).",
            total_bigrams,
            n,
            top5.first().map(|(f, _, _)| f.as_str()).unwrap_or("?"),
            top5.first().map(|(_, t, _)| t.as_str()).unwrap_or("?"),
            top5.first().map(|(_, _, p)| *p).unwrap_or(0.0),
            self_loops
                .iter()
                .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
                .map(|(t, _)| t.as_str())
                .unwrap_or("?"),
            self_loops.iter().map(|(_, r)| *r).fold(0.0f64, f64::max),
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

/// Compute stationary distribution via power iteration.
///
/// Starts with a uniform distribution and repeatedly multiplies by the
/// transition matrix until convergence (L1 norm change < epsilon) or
/// `max_iter` iterations.
fn compute_stationary(prob: &[Vec<f64>], n: usize) -> Vec<f64> {
    if n == 0 {
        return vec![];
    }

    let mut pi = vec![1.0 / n as f64; n];
    let max_iter = 1000;
    let epsilon = 1e-8;

    for _ in 0..max_iter {
        let mut next = vec![0.0f64; n];
        // pi_next[j] = sum_i pi[i] * P[i][j]
        for i in 0..n {
            for j in 0..n {
                next[j] += pi[i] * prob[i][j];
            }
        }

        // Check convergence (L1 norm).
        let diff: f64 = pi.iter().zip(next.iter()).map(|(a, b)| (a - b).abs()).sum();

        pi = next;

        if diff < epsilon {
            break;
        }
    }

    pi
}
