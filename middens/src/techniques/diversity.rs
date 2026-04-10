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
        let metrics: Vec<SessionMetrics> =
            sessions.iter().map(|s| Self::compute_metrics(s)).collect();

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
                description: Some("Species-area exponent z from S = c * A^z fit".to_string()),
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
            column_types: None,
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
