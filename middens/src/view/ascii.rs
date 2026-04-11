//! ASCII renderers — sparklines, bar charts, and tables.

use crate::techniques::DataTable;

use super::markdown::format_value;

/// Unicode block characters for sparklines, from lowest to highest.
const SPARK_CHARS: [char; 8] = [
    '\u{2581}', '\u{2582}', '\u{2583}', '\u{2584}', '\u{2585}', '\u{2586}', '\u{2587}', '\u{2588}',
];

/// Render a sparkline from a slice of f64 values.
///
/// Maps values to Unicode block characters (8 levels, linearly scaled between
/// min and max). Downsamples by averaging bins when `values.len() > width`.
pub fn render_ascii_sparkline(values: &[f64], width: usize) -> String {
    if values.is_empty() || width == 0 {
        return String::new();
    }

    // Downsample or use as-is
    let sampled: Vec<f64> = if values.len() > width {
        // Downsample by averaging bins
        let bin_size = values.len() as f64 / width as f64;
        (0..width)
            .map(|i| {
                let start = (i as f64 * bin_size) as usize;
                let end = (((i + 1) as f64 * bin_size) as usize).min(values.len());
                let slice = &values[start..end];
                if slice.is_empty() {
                    0.0
                } else {
                    slice.iter().sum::<f64>() / slice.len() as f64
                }
            })
            .collect()
    } else {
        values.to_vec()
    };

    let min = sampled.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = sampled.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let range = max - min;

    sampled
        .iter()
        .map(|&v| {
            if range == 0.0 {
                // All equal -> mid-level
                SPARK_CHARS[3] // ▄ = mid-level
            } else {
                let normalized = (v - min) / range;
                // Map to 0..7
                let idx = ((normalized * 7.0).round() as usize).min(7);
                SPARK_CHARS[idx]
            }
        })
        .collect()
}

/// Render a horizontal bar chart line.
///
/// Format: `label                ████████░░░░  0.7500`
/// - Label left-padded to 20 chars
/// - Filled portion = `(value / max) * width` using `█`
/// - Unfilled portion = remaining width using `░`
/// - Value right-aligned with 4 decimal places
pub fn render_ascii_bar(label: &str, value: f64, max: f64, width: usize) -> String {
    let padded_label = format!("{:>20}", label);

    let filled = if max == 0.0 {
        0
    } else if value < 0.0 {
        0
    } else {
        let ratio = (value / max).min(1.0);
        (ratio * width as f64).round() as usize
    };
    let unfilled = width.saturating_sub(filled);

    let bar: String = "\u{2588}".repeat(filled) + &"\u{2591}".repeat(unfilled);

    format!("{}  {}  {:.4}", padded_label, bar, value)
}

/// Render a `DataTable` as a plain ASCII table.
///
/// Column widths are capped at `max_col_width`. Values exceeding the width are
/// truncated with an ellipsis. Rows are capped at 30; if more, the first 20
/// and last 5 are shown with a `... (N more rows)` separator.
pub fn render_ascii_table(table: &DataTable, max_col_width: usize) -> String {
    if table.columns.is_empty() {
        return String::new();
    }

    let num_cols = table.columns.len();

    // Compute column widths: min(max_col_width, max(header_len, max_value_len_in_column))
    let mut col_widths: Vec<usize> = table
        .columns
        .iter()
        .enumerate()
        .map(|(i, header)| {
            let max_val_len = table
                .rows
                .iter()
                .map(|row| {
                    if i < row.len() {
                        format_value(&row[i]).len()
                    } else {
                        0
                    }
                })
                .max()
                .unwrap_or(0);
            header.len().max(max_val_len).min(max_col_width)
        })
        .collect();

    // Ensure minimum width of 1
    for w in &mut col_widths {
        if *w == 0 {
            *w = 1;
        }
    }

    let mut output = String::new();

    // Header row
    let header_parts: Vec<String> = table
        .columns
        .iter()
        .enumerate()
        .map(|(i, col)| {
            format!(
                "{:<width$}",
                truncate_str(col, col_widths[i]),
                width = col_widths[i]
            )
        })
        .collect();
    output.push_str(&header_parts.join("  "));
    output.push('\n');

    // Separator row
    let sep_parts: Vec<String> = col_widths.iter().map(|&w| "-".repeat(w)).collect();
    output.push_str(&sep_parts.join("  "));
    output.push('\n');

    let total_rows = table.rows.len();
    let cap = 30;

    if total_rows <= cap {
        for row in &table.rows {
            output.push_str(&format_row(row, &col_widths, num_cols));
            output.push('\n');
        }
    } else {
        // First 20 rows
        for row in &table.rows[..20] {
            output.push_str(&format_row(row, &col_widths, num_cols));
            output.push('\n');
        }

        let remaining = total_rows - 25; // 20 shown + 5 at end
        output.push_str(&format!("... ({} more rows)\n", remaining));

        // Last 5 rows
        for row in &table.rows[total_rows - 5..] {
            output.push_str(&format_row(row, &col_widths, num_cols));
            output.push('\n');
        }
    }

    output
}

/// Format a single row of values, padding and truncating as needed.
fn format_row(row: &[serde_json::Value], col_widths: &[usize], num_cols: usize) -> String {
    let parts: Vec<String> = (0..num_cols)
        .map(|i| {
            let val = if i < row.len() {
                format_value(&row[i])
            } else {
                String::new()
            };
            let truncated = truncate_str(&val, col_widths[i]);
            format!("{:<width$}", truncated, width = col_widths[i])
        })
        .collect();
    parts.join("  ")
}

/// Truncate a string to `max_len` characters, appending "…" if truncated.
fn truncate_str(s: &str, max_len: usize) -> String {
    if max_len == 0 {
        return String::new();
    }
    let chars: Vec<char> = s.chars().collect();
    if chars.len() <= max_len {
        s.to_string()
    } else {
        if max_len <= 1 {
            "\u{2026}".to_string()
        } else {
            let mut result: String = chars[..max_len - 1].iter().collect();
            result.push('\u{2026}');
            result
        }
    }
}
