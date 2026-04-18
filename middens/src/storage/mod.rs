// Storage layer for middens analysis runs.
//
// Parquet library decision: polars (v0.46+)
//
// Rationale: polars provides a high-level DataFrame API with first-class
// Parquet read/write support and excellent ergonomics — converting from
// `Vec<Vec<serde_json::Value>>` to a typed DataFrame is straightforward.
// The alternative (arrow2) would require manual Arrow array construction,
// which is more error-prone and harder to maintain. Binary-size impact
// should be measured after integration; if the release binary grows >5 MB
// beyond baseline, fall back to arrow2 per the NLSpec risk mitigation.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail, ensure};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::techniques::{ColumnType, DataTable, FigureSpec, Finding};

// PII blocklist: tokenized exact-match on column name tokens (split on non-alnum).
// Only block tokens that unambiguously indicate raw content columns.
// Aggregate/statistical names like "user_messages" (a count) or "text_length"
// are legitimate — the blocklist targets raw-content indicators, not derived metrics.
const PII_BLOCKLIST: &[&str] = &[
    "body", "content", "cwd", "excerpt", "filepath", "prompt", "raw", "snippet",
];

// 500 chars: catches raw session content (typically thousands of chars) while
// allowing analytical summaries (deduplicated token lists, state sequences).
// NLSpec originally said 200; real-corpus run showed that even deduplicated
// risk token lists can reach ~300 chars. 500 gives headroom without allowing
// raw content to leak through.
const VALUE_LENGTH_CAP: usize = 500;

// ── Data model ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisManifest {
    pub run_id: String,
    pub created_at: DateTime<Utc>,
    pub analyzer_fingerprint: AnalyzerFingerprint,
    pub corpus_fingerprint: CorpusFingerprint,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub strata: Option<Vec<StratumRef>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub stratum: Option<String>,
    pub techniques: Vec<TechniqueEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalyzerFingerprint {
    pub middens_version: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub git_sha: Option<String>,
    #[serde(default)]
    pub technique_versions: BTreeMap<String, String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub python_bridge: Option<PythonBridgeInfo>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PythonBridgeInfo {
    pub uv_version: String,
    pub requirements_hash: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CorpusFingerprint {
    pub manifest_hash: String,
    pub short: String,
    pub session_count: i64,
    pub source_paths: Vec<String>,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct RedactionConfig {
    pub include_source_paths: bool,
    pub include_project_names: bool,
}

impl RedactionConfig {
    pub fn display_source_path(&self, path: &Path) -> String {
        if self.include_source_paths {
            path.to_string_lossy().to_string()
        } else {
            path.file_name()
                .or_else(|| {
                    path.components()
                        .next_back()
                        .map(|component| component.as_os_str())
                })
                .unwrap_or(path.as_os_str())
                .to_string_lossy()
                .to_string()
        }
    }

    pub fn analysis_run_path(&self, run_id: &str, path: &Path) -> String {
        if self.include_source_paths {
            path.to_string_lossy().to_string()
        } else {
            format!("analysis/{}", run_id)
        }
    }

    pub fn interpretation_path(&self, interpretation_id: &str, path: &Path) -> String {
        if self.include_source_paths {
            path.to_string_lossy().to_string()
        } else {
            format!("interpretation/{}", interpretation_id)
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StratumRef {
    pub name: String,
    pub session_count: i64,
    pub manifest_ref: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TechniqueEntry {
    pub name: String,
    pub version: String,
    pub summary: String,
    #[serde(default)]
    pub findings: Vec<Finding>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub table: Option<TableRef>,
    #[serde(default)]
    pub figures: Vec<FigureSpec>,
    #[serde(default)]
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TableRef {
    pub name: String,
    pub parquet: String,
    pub row_count: i64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub column_types: Option<Vec<ColumnType>>,
}

// ── PII validation ───────────────────────────────────────────────────────────

fn tokenize_column_name(name: &str) -> Vec<String> {
    name.split(|c: char| !c.is_alphanumeric())
        .map(|t| t.to_lowercase())
        .filter(|t| !t.is_empty())
        .collect()
}

fn check_pii_column_names(table: &DataTable, technique_name: &str) -> Result<()> {
    for col_name in &table.columns {
        let tokens = tokenize_column_name(col_name);
        for token in &tokens {
            if PII_BLOCKLIST.contains(&token.as_str()) {
                bail!(
                    "PII blocklist violation in technique '{}', table '{}', \
                     column '{}': token '{}' matches blocklist entry. \
                     Rename the column (e.g., 'msg_count' instead of \
                     'total_messages') to suppress this error.",
                    technique_name,
                    table.name,
                    col_name,
                    token,
                );
            }
        }
    }
    Ok(())
}

fn check_value_length_cap(table: &DataTable, technique_name: &str) -> Result<()> {
    for (col_idx, _col_name) in table.columns.iter().enumerate() {
        let is_string_col = table
            .column_types
            .as_ref()
            .and_then(|ct| ct.get(col_idx).copied())
            .map(|ct| matches!(ct, ColumnType::String))
            // When column_types is absent, check all columns (any value could be a string)
            .unwrap_or(true);

        if is_string_col {
            for (row_idx, row) in table.rows.iter().enumerate() {
                if let Some(val) = row.get(col_idx).and_then(|v| v.as_str()) {
                    ensure!(
                        val.len() <= VALUE_LENGTH_CAP,
                        "PII value-length cap violation in technique '{}', \
                         table '{}', column '{}', row {}: value is {} chars \
                         (max {}). No partial output on disk.",
                        technique_name,
                        table.name,
                        table.columns.get(col_idx).unwrap_or(&"?".to_string()),
                        row_idx,
                        val.len(),
                        VALUE_LENGTH_CAP,
                    );
                }
            }
        }
    }
    Ok(())
}

fn json_type_name(v: &serde_json::Value) -> &'static str {
    match v {
        serde_json::Value::Null => "null",
        serde_json::Value::Bool(_) => "bool",
        serde_json::Value::Number(_) => "number",
        serde_json::Value::String(_) => "string",
        serde_json::Value::Array(_) => "array",
        serde_json::Value::Object(_) => "object",
    }
}

fn check_column_type_consistency(table: &DataTable, technique_name: &str) -> Result<()> {
    if let Some(types) = &table.column_types {
        ensure!(
            types.len() == table.columns.len(),
            "column_types length ({}) doesn't match columns length ({}) \
             in technique '{}', table '{}'",
            types.len(),
            table.columns.len(),
            technique_name,
            table.name,
        );
        for (col_idx, declared) in types.iter().enumerate() {
            for (row_idx, row) in table.rows.iter().enumerate() {
                let actual = match row.get(col_idx) {
                    Some(v) => v,
                    None => continue,
                };
                let matches = match declared {
                    ColumnType::String => actual.is_string() || actual.is_null(),
                    ColumnType::Int => actual.is_i64() || actual.is_null(),
                    ColumnType::Float => actual.is_number() || actual.is_null(),
                    ColumnType::Bool => actual.is_boolean() || actual.is_null(),
                    ColumnType::Timestamp => actual.is_i64() || actual.is_null(),
                };
                ensure!(
                    matches,
                    "column_types mismatch in technique '{}', table '{}', \
                     column {} ('{}'): declared {:?} but row {} has actual \
                     type {}. No partial output on disk.",
                    technique_name,
                    table.name,
                    col_idx,
                    table.columns.get(col_idx).unwrap_or(&"?".to_string()),
                    declared,
                    row_idx,
                    json_type_name(actual),
                );
            }
        }
    }
    Ok(())
}

pub fn validate_table_for_storage(table: &DataTable, technique_name: &str) -> Result<()> {
    check_pii_column_names(table, technique_name).context("PII column-name check failed")?;
    check_column_type_consistency(table, technique_name)
        .context("column_types consistency check failed")?;
    check_value_length_cap(table, technique_name).context("PII value-length cap check failed")?;
    Ok(())
}

// ── ManifestWriter ───────────────────────────────────────────────────────────

pub struct ManifestWriter;

impl ManifestWriter {
    pub fn write(manifest: &AnalysisManifest, path: &Path) -> Result<()> {
        let json =
            serde_json::to_string_pretty(manifest).context("failed to serialize manifest")?;
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).context("failed to create manifest directory")?;
        }
        std::fs::write(path, json).context("failed to write manifest")?;
        Ok(())
    }
}

// ── ParquetWriter ────────────────────────────────────────────────────────────

pub struct ParquetWriter;

impl ParquetWriter {
    pub fn write_table(table: &DataTable, technique_name: &str, path: &Path) -> Result<()> {
        validate_table_for_storage(table, technique_name)?;

        let df =
            datatable_to_dataframe(table).context("failed to convert DataTable to DataFrame")?;

        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).context("failed to create parquet directory")?;
        }

        let file = std::fs::File::create(path).context("failed to create parquet file")?;

        use polars::prelude::ParquetWriter as PolarsParquetWriter;
        PolarsParquetWriter::new(file)
            .finish(&mut df.clone())
            .context("failed to write parquet")?;

        Ok(())
    }
}

// ── AnalysisRun reader ───────────────────────────────────────────────────────

pub struct AnalysisRun {
    dir: PathBuf,
    manifest: AnalysisManifest,
}

impl AnalysisRun {
    pub fn load(dir: &Path) -> Result<Self> {
        let manifest_path = dir.join("manifest.json");
        let raw = std::fs::read_to_string(&manifest_path)
            .with_context(|| format!("failed to read manifest at {}", manifest_path.display()))?;
        let manifest: AnalysisManifest = serde_json::from_str(&raw)
            .with_context(|| format!("failed to parse manifest at {}", manifest_path.display()))?;
        Ok(Self {
            dir: dir.to_path_buf(),
            manifest,
        })
    }

    pub fn dir(&self) -> &Path {
        &self.dir
    }

    pub fn manifest(&self) -> &AnalysisManifest {
        &self.manifest
    }

    pub fn load_table(&self, table_ref: &TableRef) -> Result<DataTable> {
        let parquet_path = self.dir.join(&table_ref.parquet);
        let file = std::fs::File::open(&parquet_path)
            .with_context(|| format!("failed to open parquet at {}", parquet_path.display()))?;

        use polars::prelude::{ParquetReader, SerReader};
        let df = ParquetReader::new(file)
            .finish()
            .context("failed to read parquet")?;

        dataframe_to_datatable(&df, table_ref)
    }

    pub fn load_technique_table(&self, technique_name: &str) -> Result<Option<DataTable>> {
        let entry = self
            .manifest
            .techniques
            .iter()
            .find(|t| t.name == technique_name);

        match entry.and_then(|e| e.table.as_ref()) {
            Some(table_ref) => Ok(Some(self.load_table(table_ref)?)),
            None => Ok(None),
        }
    }
}

pub mod discovery;

// ── Conversion helpers ───────────────────────────────────────────────────────

fn infer_column_type(values: &[&serde_json::Value]) -> ColumnType {
    use serde_json::Value;
    let mut has_int = false;
    let mut has_float = false;
    let mut has_bool = false;
    let mut has_string = false;

    for v in values {
        match v {
            Value::Null => continue,
            Value::Bool(_) => has_bool = true,
            Value::Number(n) => {
                if n.is_f64() && !n.is_i64() && !n.is_u64() {
                    has_float = true;
                } else {
                    has_int = true;
                }
            }
            Value::String(_) => has_string = true,
            _ => has_string = true,
        }
    }

    // Supertype resolution: String absorbs everything, Float absorbs Int
    if has_string || (has_bool && (has_int || has_float)) {
        ColumnType::String
    } else if has_float || (has_int && has_float) {
        ColumnType::Float
    } else if has_int {
        ColumnType::Int
    } else if has_bool {
        ColumnType::Bool
    } else {
        ColumnType::String // all nulls
    }
}

fn datatable_to_dataframe(table: &DataTable) -> Result<polars::frame::DataFrame> {
    use polars::frame::DataFrame;
    use polars::prelude::Column;

    let ncols = table.columns.len();
    if ncols == 0 {
        return Ok(DataFrame::empty());
    }

    let mut columns: Vec<Column> = Vec::with_capacity(ncols);

    for (col_idx, col_name) in table.columns.iter().enumerate() {
        let values: Vec<&serde_json::Value> = table
            .rows
            .iter()
            .map(|row| row.get(col_idx).unwrap_or(&serde_json::Value::Null))
            .collect();

        let col_type = table
            .column_types
            .as_ref()
            .and_then(|ct| ct.get(col_idx).copied())
            .unwrap_or_else(|| infer_column_type(&values));

        let col = make_column(col_name, &values, col_type)?;
        columns.push(col);
    }

    let df = DataFrame::new(columns)
        .map_err(|e| anyhow::anyhow!("failed to create DataFrame: {}", e))?;
    Ok(df)
}

fn make_column(
    name: &str,
    values: &[&serde_json::Value],
    col_type: ColumnType,
) -> Result<polars::prelude::Column> {
    use polars::prelude::{NamedFrom, Series};

    let series: Series = match col_type {
        ColumnType::String => {
            let vals: Vec<Option<String>> = values
                .iter()
                .map(|v| match v {
                    serde_json::Value::String(s) => Some(s.clone()),
                    serde_json::Value::Null => None,
                    other => Some(other.to_string()),
                })
                .collect();
            Series::new(name.into(), vals)
        }
        ColumnType::Int => {
            let vals: Vec<Option<i64>> = values.iter().map(|v| v.as_i64()).collect();
            Series::new(name.into(), vals)
        }
        ColumnType::Float => {
            let vals: Vec<Option<f64>> = values.iter().map(|v| v.as_f64()).collect();
            Series::new(name.into(), vals)
        }
        ColumnType::Bool => {
            let vals: Vec<Option<bool>> = values.iter().map(|v| v.as_bool()).collect();
            Series::new(name.into(), vals)
        }
        ColumnType::Timestamp => {
            let vals: Vec<Option<i64>> = values.iter().map(|v| v.as_i64()).collect();
            Series::new(name.into(), vals)
        }
    };
    Ok(series.into())
}

fn dataframe_to_datatable(
    df: &polars::frame::DataFrame,
    table_ref: &TableRef,
) -> Result<DataTable> {
    let columns: Vec<String> = df
        .get_column_names()
        .iter()
        .map(|n| n.to_string())
        .collect();
    let nrows = df.height();

    let mut rows: Vec<Vec<serde_json::Value>> = Vec::with_capacity(nrows);
    for row_idx in 0..nrows {
        let mut row = Vec::with_capacity(columns.len());
        for col_idx in 0..columns.len() {
            let series = df
                .select_at_idx(col_idx)
                .ok_or_else(|| anyhow::anyhow!("column index {} out of bounds", col_idx))?;
            let av = series
                .get(row_idx)
                .map_err(|e| anyhow::anyhow!("row {} col {}: {}", row_idx, col_idx, e))?;
            row.push(anyvalue_to_json(&av));
        }
        rows.push(row);
    }

    Ok(DataTable {
        name: table_ref.name.clone(),
        columns,
        rows,
        column_types: table_ref.column_types.clone(),
    })
}

fn anyvalue_to_json(av: &polars::datatypes::AnyValue) -> serde_json::Value {
    use polars::datatypes::AnyValue;
    use serde_json::json;

    match av {
        AnyValue::Null => serde_json::Value::Null,
        AnyValue::Boolean(b) => json!(b),
        AnyValue::Int8(i) => json!(i),
        AnyValue::Int16(i) => json!(i),
        AnyValue::Int32(i) => json!(i),
        AnyValue::Int64(i) => json!(i),
        AnyValue::UInt8(u) => json!(u),
        AnyValue::UInt16(u) => json!(u),
        AnyValue::UInt32(u) => json!(u),
        AnyValue::UInt64(u) => json!(u),
        AnyValue::Float32(f) => json!(f),
        AnyValue::Float64(f) => json!(f),
        AnyValue::String(s) => json!(s),
        AnyValue::StringOwned(s) => json!(s.as_str()),
        _ => json!(format!("{:?}", av)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn make_test_table(
        name: &str,
        columns: Vec<&str>,
        rows: Vec<Vec<serde_json::Value>>,
    ) -> DataTable {
        DataTable {
            name: name.to_string(),
            columns: columns.into_iter().map(String::from).collect(),
            rows,
            column_types: None,
        }
    }

    #[test]
    fn pii_check_allows_safe_column_names() {
        let table = make_test_table(
            "test",
            vec!["context_length", "n_turns", "msg_count"],
            vec![],
        );
        assert!(check_pii_column_names(&table, "test_technique").is_ok());
    }

    #[test]
    fn pii_check_blocks_raw_data() {
        let table = make_test_table("test", vec!["raw_data"], vec![]);
        let err = check_pii_column_names(&table, "test_technique").unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("raw_data"), "error should name the column");
        assert!(msg.contains("raw"), "error should name the token");
        assert!(
            msg.contains("test_technique"),
            "error should name the technique"
        );
    }

    #[test]
    fn pii_check_blocks_prompt_column() {
        let table = make_test_table("test", vec!["user_prompt"], vec![]);
        let err = check_pii_column_names(&table, "t").unwrap_err();
        assert!(err.to_string().contains("prompt"));
    }

    #[test]
    fn pii_check_blocks_body_column() {
        let table = make_test_table("test", vec!["response_body"], vec![]);
        let err = check_pii_column_names(&table, "t").unwrap_err();
        assert!(err.to_string().contains("body"));
    }

    #[test]
    fn pii_check_allows_aggregate_names() {
        // Statistical/aggregate column names should NOT be blocked
        let table = make_test_table(
            "test",
            vec![
                "user_messages",
                "text_length",
                "message_count",
                "file_path_count",
            ],
            vec![],
        );
        assert!(check_pii_column_names(&table, "t").is_ok());
    }

    #[test]
    fn column_type_consistency_passes_for_matching_types() {
        let table = DataTable {
            name: "test".into(),
            columns: vec!["a".into(), "b".into()],
            rows: vec![vec![json!(42), json!(3.14)]],
            column_types: Some(vec![ColumnType::Int, ColumnType::Float]),
        };
        assert!(check_column_type_consistency(&table, "t").is_ok());
    }

    #[test]
    fn column_type_consistency_rejects_mismatch() {
        let table = DataTable {
            name: "test".into(),
            columns: vec!["a".into()],
            rows: vec![vec![json!(3.14)]],
            column_types: Some(vec![ColumnType::Int]),
        };
        let err = check_column_type_consistency(&table, "t").unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("mismatch"));
        assert!(msg.contains("column 0"));
    }

    #[test]
    fn column_type_consistency_allows_nulls() {
        let table = DataTable {
            name: "test".into(),
            columns: vec!["a".into()],
            rows: vec![vec![serde_json::Value::Null]],
            column_types: Some(vec![ColumnType::Int]),
        };
        assert!(check_column_type_consistency(&table, "t").is_ok());
    }

    #[test]
    fn value_length_cap_allows_short_strings() {
        let table = DataTable {
            name: "test".into(),
            columns: vec!["label".into()],
            rows: vec![vec![json!("ok")]],
            column_types: Some(vec![ColumnType::String]),
        };
        assert!(check_value_length_cap(&table, "t").is_ok());
    }

    #[test]
    fn value_length_cap_rejects_long_strings() {
        let long_val = "x".repeat(VALUE_LENGTH_CAP + 1);
        let table = DataTable {
            name: "test".into(),
            columns: vec!["label".into()],
            rows: vec![vec![json!(long_val)]],
            column_types: Some(vec![ColumnType::String]),
        };
        let err = check_value_length_cap(&table, "t").unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains(&format!("{} chars", VALUE_LENGTH_CAP + 1)));
        assert!(msg.contains("row 0"));
    }

    #[test]
    fn column_type_length_mismatch_rejected() {
        let table = DataTable {
            name: "test".into(),
            columns: vec!["a".into(), "b".into()],
            rows: vec![],
            column_types: Some(vec![ColumnType::Int]),
        };
        let err = check_column_type_consistency(&table, "t").unwrap_err();
        assert!(err.to_string().contains("doesn't match columns length"));
    }

    #[test]
    fn manifest_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        let manifest = AnalysisManifest {
            run_id: "run-0190e4b4-7e1c-7c4a-9f2b-5c9ab3f12de0".into(),
            created_at: DateTime::parse_from_rfc3339("2026-04-09T12:00:00Z")
                .unwrap()
                .to_utc(),
            analyzer_fingerprint: AnalyzerFingerprint {
                middens_version: "0.1.0".into(),
                git_sha: Some("abc1234".into()),
                technique_versions: BTreeMap::new(),
                python_bridge: None,
            },
            corpus_fingerprint: CorpusFingerprint {
                manifest_hash: "abcdef1234567890".into(),
                short: "abcdef12".into(),
                session_count: 100,
                source_paths: vec!["/corpus".into()],
            },
            strata: None,
            stratum: None,
            techniques: vec![TechniqueEntry {
                name: "entropy".into(),
                version: "1.0".into(),
                summary: "test summary".into(),
                findings: vec![],
                table: None,
                figures: vec![],
                errors: vec![],
            }],
        };

        let path = dir.path().join("manifest.json");
        ManifestWriter::write(&manifest, &path).unwrap();

        let loaded: AnalysisManifest =
            serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(loaded.run_id, manifest.run_id);
        assert_eq!(loaded.techniques.len(), 1);
        assert_eq!(loaded.techniques[0].name, "entropy");
        assert!(loaded.strata.is_none());
    }

    #[test]
    fn parquet_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        let table = DataTable {
            name: "test_table".into(),
            columns: vec!["name".into(), "count".into(), "rate".into()],
            rows: vec![
                vec![json!("alpha"), json!(10), json!(0.5)],
                vec![json!("beta"), json!(20), json!(1.5)],
            ],
            column_types: Some(vec![ColumnType::String, ColumnType::Int, ColumnType::Float]),
        };

        let path = dir.path().join("test.parquet");
        ParquetWriter::write_table(&table, "test_tech", &path).unwrap();

        let table_ref = TableRef {
            name: "test_table".into(),
            parquet: "test.parquet".into(),
            row_count: 2,
            column_types: Some(vec![ColumnType::String, ColumnType::Int, ColumnType::Float]),
        };

        let run = AnalysisRun {
            dir: dir.path().to_path_buf(),
            manifest: AnalysisManifest {
                run_id: "run-test".into(),
                created_at: DateTime::parse_from_rfc3339("2026-04-09T12:00:00Z")
                    .unwrap()
                    .to_utc(),
                analyzer_fingerprint: AnalyzerFingerprint {
                    middens_version: "0.1.0".into(),
                    git_sha: None,
                    technique_versions: BTreeMap::new(),
                    python_bridge: None,
                },
                corpus_fingerprint: CorpusFingerprint {
                    manifest_hash: "abc".into(),
                    short: "abc".into(),
                    session_count: 0,
                    source_paths: vec![],
                },
                strata: None,
                stratum: None,
                techniques: vec![],
            },
        };

        let loaded = run.load_table(&table_ref).unwrap();
        assert_eq!(loaded.name, "test_table");
        assert_eq!(loaded.columns.len(), 3);
        assert_eq!(loaded.rows.len(), 2);
        assert_eq!(loaded.rows[0][0], json!("alpha"));
        assert_eq!(loaded.rows[0][1], json!(10));
        assert_eq!(loaded.rows[0][2], json!(0.5));
    }

    #[test]
    fn manifest_stable_field_order() {
        let manifest = AnalysisManifest {
            run_id: "run-test".into(),
            created_at: DateTime::parse_from_rfc3339("2026-04-09T12:00:00Z")
                .unwrap()
                .to_utc(),
            analyzer_fingerprint: AnalyzerFingerprint {
                middens_version: "0.1.0".into(),
                git_sha: None,
                technique_versions: BTreeMap::new(),
                python_bridge: None,
            },
            corpus_fingerprint: CorpusFingerprint {
                manifest_hash: "abc".into(),
                short: "ab".into(),
                session_count: 5,
                source_paths: vec![],
            },
            strata: None,
            stratum: None,
            techniques: vec![],
        };

        let json = serde_json::to_string_pretty(&manifest).unwrap();
        let lines: Vec<&str> = json.lines().collect();
        let run_id_pos = lines.iter().position(|l| l.contains("run_id")).unwrap();
        let created_pos = lines.iter().position(|l| l.contains("created_at")).unwrap();
        let analyzer_pos = lines
            .iter()
            .position(|l| l.contains("analyzer_fingerprint"))
            .unwrap();
        let corpus_pos = lines
            .iter()
            .position(|l| l.contains("corpus_fingerprint"))
            .unwrap();
        let techniques_pos = lines.iter().position(|l| l.contains("techniques")).unwrap();

        assert!(
            run_id_pos < created_pos,
            "run_id should come before created_at"
        );
        assert!(
            created_pos < analyzer_pos,
            "created_at should come before analyzer_fingerprint"
        );
        assert!(
            corpus_pos < techniques_pos,
            "corpus_fingerprint should come before techniques"
        );
    }
}
