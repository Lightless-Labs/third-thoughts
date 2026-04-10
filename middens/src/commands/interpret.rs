use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{bail, ensure, Context, Result};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::storage::discovery::{discover_latest_analysis, xdg_app_root};
use crate::storage::{AnalysisManifest, AnalysisRun};

pub const TEMPLATE_VERSION: &str = "1";

const PROMPT_TEMPLATE: &str = include_str!("interpret/prompt-template.md");

const RUNNER_SLUGS: &[&str] = &["claude-code", "codex", "gemini", "opencode"];

pub trait Runner {
    fn slug(&self) -> &str;
    fn binary(&self) -> &str;
    fn build_command(
        &self,
        prompt_path: &Path,
        model_id: Option<&str>,
        work_dir: &Path,
    ) -> Result<Command>;
}

pub struct ClaudeCodeRunner;

impl Runner for ClaudeCodeRunner {
    fn slug(&self) -> &str {
        "claude-code"
    }

    fn binary(&self) -> &str {
        "claude"
    }

    fn build_command(
        &self,
        prompt_path: &Path,
        model_id: Option<&str>,
        _work_dir: &Path,
    ) -> Result<Command> {
        let prompt =
            std::fs::read_to_string(prompt_path).context("reading prompt for claude-code")?;
        let mut cmd = Command::new(self.binary());
        cmd.arg("-p").arg(&prompt);
        if let Some(mid) = model_id {
            cmd.arg("--model").arg(mid);
        }
        Ok(cmd)
    }
}

pub struct CodexRunner;

impl Runner for CodexRunner {
    fn slug(&self) -> &str {
        "codex"
    }

    fn binary(&self) -> &str {
        "codex"
    }

    fn build_command(
        &self,
        prompt_path: &Path,
        model_id: Option<&str>,
        work_dir: &Path,
    ) -> Result<Command> {
        let prompt = std::fs::read_to_string(prompt_path).context("reading prompt for codex")?;
        let mut cmd = Command::new(self.binary());
        cmd.arg("exec")
            .arg("--skip-git-repo-check")
            .arg("--full-auto")
            .arg("-o")
            .arg(work_dir.join("response.md"))
            .arg(&prompt);
        if let Some(mid) = model_id {
            cmd.arg("--model").arg(mid);
        }
        Ok(cmd)
    }
}

pub struct GeminiRunner;

impl Runner for GeminiRunner {
    fn slug(&self) -> &str {
        "gemini"
    }

    fn binary(&self) -> &str {
        "gemini"
    }

    fn build_command(
        &self,
        prompt_path: &Path,
        model_id: Option<&str>,
        _work_dir: &Path,
    ) -> Result<Command> {
        let prompt = std::fs::read_to_string(prompt_path).context("reading prompt for gemini")?;
        let mut cmd = Command::new(self.binary());
        cmd.arg("-y")
            .arg("-s")
            .arg("false")
            .arg("--prompt")
            .arg(&prompt);
        if let Some(mid) = model_id {
            cmd.arg("-m").arg(mid);
        }
        Ok(cmd)
    }
}

pub struct OpencodeRunner;

impl Runner for OpencodeRunner {
    fn slug(&self) -> &str {
        "opencode"
    }

    fn binary(&self) -> &str {
        "opencode"
    }

    fn build_command(
        &self,
        prompt_path: &Path,
        model_id: Option<&str>,
        _work_dir: &Path,
    ) -> Result<Command> {
        let mid = model_id.ok_or_else(|| {
            anyhow::anyhow!(
                "opencode requires an explicit --model (<runner>/<model-id>). \
                 opencode's CLI has no native default model."
            )
        })?;
        let prompt = std::fs::read_to_string(prompt_path).context("reading prompt for opencode")?;
        let mut cmd = Command::new(self.binary());
        cmd.arg("run")
            .arg("--format")
            .arg("json")
            .arg("--model")
            .arg(mid)
            .arg(&prompt);
        Ok(cmd)
    }
}

pub fn parse_model_flag(model: &str) -> Result<(&str, &str)> {
    let Some(slash_pos) = model.find('/') else {
        bail!(
            "invalid --model value: '{}'. \
             Expected form: <runner>/<model-id> (split on first '/').\n\n\
             Examples:\n  \
               claude-code/claude-opus-4-6\n  \
               codex/gpt-5.4-codex\n  \
               gemini/gemini-3.1-pro-preview\n  \
               opencode/kimi-for-coding/k2p5\n\n\
             The value must contain at least one '/'. \
             No runner-only auto-resolution.",
            model
        );
    };
    let runner_slug = &model[..slash_pos];
    let model_id = &model[slash_pos + 1..];
    ensure!(
        !runner_slug.is_empty(),
        "runner prefix before '/' is empty in --model '{}'",
        model
    );
    ensure!(
        !model_id.is_empty(),
        "model-id after '/' is empty in --model '{}'",
        model
    );
    Ok((runner_slug, model_id))
}

pub fn detect_runner(model_flag: Option<&str>) -> Result<Box<dyn Runner>> {
    if let Some(model) = model_flag {
        let (runner_slug, _model_id) = parse_model_flag(model)?;
        let runner: Box<dyn Runner> = match runner_slug {
            "claude-code" => Box::new(ClaudeCodeRunner),
            "codex" => Box::new(CodexRunner),
            "gemini" => Box::new(GeminiRunner),
            "opencode" => Box::new(OpencodeRunner),
            unknown => {
                bail!(
                    "unknown runner '{}'. Supported runners: {}",
                    unknown,
                    RUNNER_SLUGS.join(", ")
                );
            }
        };
        return Ok(runner);
    }

    let fallback_chain: Vec<Box<dyn Runner>> = vec![
        Box::new(ClaudeCodeRunner),
        Box::new(CodexRunner),
        Box::new(GeminiRunner),
        Box::new(OpencodeRunner),
    ];

    for runner in fallback_chain {
        if which::which(runner.binary()).is_ok() {
            return Ok(runner);
        }
    }

    bail!(
        "no LLM runner found on PATH. Tried: {}. \
         Install one of these CLIs and try again.",
        RUNNER_SLUGS.join(", ")
    );
}

fn generate_uuidv7() -> String {
    uuid7::uuid7().to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InterpretationManifest {
    pub interpretation_id: String,
    pub created_at: chrono::DateTime<chrono::Utc>,
    pub analysis_run_id: String,
    pub analysis_run_path: String,
    pub runner: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model_id: Option<String>,
    pub prompt_hash: String,
    pub template_version: String,
    pub conclusions: ConclusionsIndex,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConclusionsIndex {
    pub overall: String,
    #[serde(default)]
    pub per_technique: BTreeMap<String, String>,
}

#[derive(Debug)]
struct ParsedResponse {
    conclusions: String,
    per_technique: Vec<(String, String)>,
}

fn parse_response(response: &str) -> Result<ParsedResponse> {
    let marker_re = regex::Regex::new(r"<!--\s*technique:\s*(.+?)\s*-->").unwrap();

    let mut per_technique: Vec<(String, String)> = Vec::new();

    let markers: Vec<_> = marker_re
        .captures_iter(response)
        .filter_map(|cap| {
            let m = cap.get(0)?;
            Some((cap[1].trim().to_string(), m.start(), m.end()))
        })
        .collect();

    if markers.is_empty() {
        bail!(
            "response contains no '<!-- technique: <slug> -->' markers. \
             The model ignored the prompt format; interpretation failed."
        );
    }

    let first_marker_start = markers[0].1;
    let conclusions = response[..first_marker_start].trim().to_string();

    for (i, (slug, _start, end)) in markers.iter().enumerate() {
        let content_start = *end;
        let content_end = if i + 1 < markers.len() {
            markers[i + 1].1
        } else {
            response.len()
        };
        let content = response[content_start..content_end].trim().to_string();
        per_technique.push((slug.clone(), content));
    }

    Ok(ParsedResponse {
        conclusions,
        per_technique,
    })
}

fn build_prompt(manifest: &AnalysisManifest, run: &AnalysisRun) -> Result<String> {
    let manifest_json = serde_json::to_string_pretty(manifest)
        .context("failed to serialize analysis manifest for prompt")?;

    let mut technique_sections = String::new();
    for entry in &manifest.techniques {
        technique_sections.push_str(&format!("### Technique: {}\n\n", entry.name));
        technique_sections.push_str(&format!("{}\n\n", entry.summary));

        if !entry.findings.is_empty() {
            technique_sections.push_str("**Findings:**\n\n");
            for f in &entry.findings {
                technique_sections.push_str(&format!("- **{}**: {}\n", f.label, f.value));
                if let Some(desc) = &f.description {
                    technique_sections.push_str(&format!("  {}\n", desc));
                }
            }
            technique_sections.push('\n');
        }

        if let Some(table_ref) = &entry.table {
            match run.load_table(table_ref) {
                Ok(table) => {
                    let max_rows = 10.min(table.rows.len());
                    let mut md = String::new();
                    md.push_str("| ");
                    md.push_str(&table.columns.join(" | "));
                    md.push_str(" |\n| ");
                    for _ in &table.columns {
                        md.push_str("--- | ");
                    }
                    md.push('\n');
                    for row in &table.rows[..max_rows] {
                        md.push_str("| ");
                        for val in row {
                            md.push_str(&format!("{} | ", val));
                        }
                        md.push('\n');
                    }
                    if table.rows.len() > 10 {
                        md.push_str(&format!("\n... {} more rows\n", table.rows.len() - 10));
                    }
                    technique_sections.push_str(&format!(
                        "**Table excerpt (first {} of {} rows):**\n\n{}\n",
                        max_rows, table_ref.row_count, md
                    ));
                }
                Err(e) => {
                    technique_sections.push_str(&format!("**Table load error:** {}\n\n", e));
                }
            }
        }

        if !entry.errors.is_empty() {
            technique_sections.push_str("**Errors:**\n\n");
            for err in &entry.errors {
                technique_sections.push_str(&format!("- {}\n", err));
            }
            technique_sections.push('\n');
        }
    }

    let prompt = PROMPT_TEMPLATE
        .replace("{{TEMPLATE_VERSION}}", TEMPLATE_VERSION)
        .replace("{{MANIFEST}}", &manifest_json)
        .replace("{{TECHNIQUE_SECTIONS}}", &technique_sections);

    Ok(prompt)
}

fn sha256_hex(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    format!("{:x}", hasher.finalize())
}

pub struct InterpretConfig {
    pub analysis_dir: Option<PathBuf>,
    pub model: Option<String>,
    pub output_dir: Option<PathBuf>,
    pub dry_run: bool,
}

pub fn run_interpret(config: InterpretConfig) -> Result<()> {
    let analysis_path = discover_latest_analysis(config.analysis_dir.as_deref())?;
    let run = AnalysisRun::load(&analysis_path)?;
    let manifest = run.manifest();

    let (runner, model_id): (Box<dyn Runner>, Option<String>) = if let Some(ref m) = config.model {
        let r = detect_runner(Some(m))?;
        let (_, mid) = parse_model_flag(m)?;
        (r, Some(mid.to_string()))
    } else {
        let r = detect_runner(None)?;
        if r.slug() == "opencode" {
            bail!(
                "opencode requires an explicit --model (<runner>/<model-id>). \
                 opencode's CLI has no native default model."
            );
        }
        (r, None)
    };

    let now = Utc::now();
    let uuid = generate_uuidv7();
    let interp_slug = format!("{}-{}", uuid, runner.slug());

    let xdg_root = xdg_app_root();
    let analysis_run_slug = analysis_path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "unknown".into());

    let tmp_dir_name = format!(".tmp-{}", uuid);
    let tmp_path = xdg_root.join(&tmp_dir_name);
    std::fs::create_dir_all(&tmp_path)
        .with_context(|| format!("creating temp dir {}", tmp_path.display()))?;

    let prompt = build_prompt(manifest, &run)?;
    let prompt_path = tmp_path.join("prompt.md");
    std::fs::write(&prompt_path, &prompt).context("writing prompt.md")?;

    if config.dry_run {
        let dryrun_dest = xdg_root
            .join("interpretation-dryruns")
            .join(&analysis_run_slug)
            .join(&interp_slug);
        if let Some(parent) = dryrun_dest.parent() {
            std::fs::create_dir_all(parent)?;
        }
        std::fs::rename(&tmp_path, &dryrun_dest).with_context(|| {
            format!(
                "renaming {} -> {}",
                tmp_path.display(),
                dryrun_dest.display()
            )
        })?;
        println!("{}", dryrun_dest.display());
        return Ok(());
    }

    let mock_runner = std::env::var("MIDDENS_MOCK_RUNNER").ok();

    let response_result: Result<String> = if let Some(ref mock_script) = mock_runner {
        let mut cmd = Command::new(mock_script);
        cmd.arg(&prompt_path);
        if let Some(ref mid) = model_id {
            cmd.arg("--model").arg(mid);
        }
        let output = cmd.output().context("executing mock runner")?;
        if !output.status.success() {
            bail!(
                "mock runner exited with {}: {}",
                output.status,
                String::from_utf8_lossy(&output.stderr)
            );
        }
        Ok(String::from_utf8(output.stdout).context("mock runner output is not valid UTF-8")?)
    } else {
        let mut cmd = runner.build_command(&prompt_path, model_id.as_deref(), &tmp_path)?;
        let output = cmd
            .output()
            .context(format!("executing runner '{}'", runner.slug()))?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            let error_msg = format!(
                "runner '{}' exited with {}: {}",
                runner.slug(),
                output.status,
                stderr
            );

            let err_path = tmp_path.join("error.txt");
            std::fs::write(&err_path, &error_msg).context("writing error.txt")?;
            if !output.stdout.is_empty() {
                let raw_path = tmp_path.join("raw-response.txt");
                std::fs::write(&raw_path, &output.stdout).context("writing raw-response.txt")?;
            }

            let fail_dest = xdg_root
                .join("interpretation-failures")
                .join(&analysis_run_slug)
                .join(&interp_slug);
            if let Some(parent) = fail_dest.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::rename(&tmp_path, &fail_dest).with_context(|| {
                format!("renaming {} -> {}", tmp_path.display(), fail_dest.display())
            })?;
            bail!("{}", error_msg);
        }

        if runner.slug() == "codex" {
            let response_path = tmp_path.join("response.md");
            if response_path.exists() {
                std::fs::read_to_string(&response_path).context("reading codex response")
            } else {
                Ok(String::from_utf8(output.stdout).context("reading codex stdout as fallback")?)
            }
        } else if runner.slug() == "opencode" {
            let raw =
                String::from_utf8(output.stdout).context("opencode output is not valid UTF-8")?;
            extract_opencode_text(&raw)
        } else {
            Ok(String::from_utf8(output.stdout).context("runner output is not valid UTF-8")?)
        }
    };

    let response = match response_result {
        Ok(r) => r,
        Err(e) => {
            let err_path = tmp_path.join("error.txt");
            std::fs::write(&err_path, e.to_string()).ok();
            let fail_dest = xdg_root
                .join("interpretation-failures")
                .join(&analysis_run_slug)
                .join(&interp_slug);
            if let Some(parent) = fail_dest.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::rename(&tmp_path, &fail_dest).ok();
            return Err(e);
        }
    };

    let parsed = match parse_response(&response) {
        Ok(p) => p,
        Err(e) => {
            let err_path = tmp_path.join("error.txt");
            std::fs::write(&err_path, e.to_string()).context("writing error.txt")?;
            let raw_path = tmp_path.join("raw-response.txt");
            std::fs::write(&raw_path, &response).context("writing raw-response.txt")?;

            let fail_dest = xdg_root
                .join("interpretation-failures")
                .join(&analysis_run_slug)
                .join(&interp_slug);
            if let Some(parent) = fail_dest.parent() {
                std::fs::create_dir_all(parent)?;
            }
            std::fs::rename(&tmp_path, &fail_dest).with_context(|| {
                format!("renaming {} -> {}", tmp_path.display(), fail_dest.display())
            })?;
            bail!("response parse failed: {}", e);
        }
    };

    std::fs::write(tmp_path.join("conclusions.md"), &parsed.conclusions)
        .context("writing conclusions.md")?;

    let mut per_technique_map: BTreeMap<String, String> = BTreeMap::new();
    for (slug, content) in &parsed.per_technique {
        let filename = format!("{}-conclusions.md", slug);
        std::fs::write(tmp_path.join(&filename), content)
            .with_context(|| format!("writing {}", filename))?;
        per_technique_map.insert(slug.clone(), filename);
    }

    let prompt_bytes = std::fs::read(&prompt_path).context("reading prompt for hashing")?;
    let prompt_hash = sha256_hex(&prompt_bytes);

    let interp_manifest = InterpretationManifest {
        interpretation_id: interp_slug.clone(),
        created_at: now,
        analysis_run_id: manifest.run_id.clone(),
        analysis_run_path: analysis_path.to_string_lossy().to_string(),
        runner: runner.slug().to_string(),
        model_id,
        prompt_hash,
        template_version: TEMPLATE_VERSION.to_string(),
        conclusions: ConclusionsIndex {
            overall: "conclusions.md".into(),
            per_technique: per_technique_map,
        },
    };

    let manifest_json = serde_json::to_string_pretty(&interp_manifest)
        .context("serializing interpretation manifest")?;
    std::fs::write(tmp_path.join("manifest.json"), manifest_json)
        .context("writing interpretation manifest")?;

    let output_dest = if let Some(ref out) = config.output_dir {
        out.clone()
    } else {
        xdg_root
            .join("interpretation")
            .join(&analysis_run_slug)
            .join(&interp_slug)
    };
    if let Some(parent) = output_dest.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::rename(&tmp_path, &output_dest).with_context(|| {
        format!(
            "renaming {} -> {}",
            tmp_path.display(),
            output_dest.display()
        )
    })?;

    println!("{}", output_dest.display());
    Ok(())
}

fn extract_opencode_text(raw: &str) -> Result<String> {
    let mut parts = Vec::new();
    for line in raw.lines() {
        if let Ok(obj) = serde_json::from_str::<serde_json::Value>(line) {
            if obj.get("type").and_then(|v| v.as_str()) == Some("text") {
                if let Some(text) = obj
                    .get("part")
                    .and_then(|p| p.get("text"))
                    .and_then(|t| t.as_str())
                {
                    parts.push(text.to_string());
                }
            }
        }
    }
    Ok(parts.join("\n"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_model_flag_splits_on_first_slash() {
        let (runner, model_id) = parse_model_flag("opencode/kimi-for-coding/k2p5").unwrap();
        assert_eq!(runner, "opencode");
        assert_eq!(model_id, "kimi-for-coding/k2p5");
    }

    #[test]
    fn parse_model_flag_simple() {
        let (runner, model_id) = parse_model_flag("claude-code/claude-opus-4-6").unwrap();
        assert_eq!(runner, "claude-code");
        assert_eq!(model_id, "claude-opus-4-6");
    }

    #[test]
    fn parse_model_flag_no_slash_fails() {
        let err = parse_model_flag("claude-code").unwrap_err();
        let msg = err.to_string();
        assert!(
            msg.contains("must contain at least one '/'"),
            "got: {}",
            msg
        );
        assert!(msg.contains("claude-code/claude-opus-4-6"), "got: {}", msg);
        assert!(msg.contains("codex/gpt-5.4-codex"), "got: {}", msg);
    }

    #[test]
    fn parse_model_flag_empty_runner_fails() {
        let err = parse_model_flag("/some-model").unwrap_err();
        assert!(err.to_string().contains("empty"));
    }

    #[test]
    fn parse_model_flag_empty_model_id_fails() {
        let err = parse_model_flag("claude-code/").unwrap_err();
        assert!(err.to_string().contains("empty"));
    }

    #[test]
    fn detect_runner_unknown_prefix_fails() {
        let result = detect_runner(Some("foo/bar"));
        assert!(result.is_err());
        let msg = result.err().unwrap().to_string();
        assert!(msg.contains("unknown runner 'foo'"), "got: {}", msg);
        assert!(msg.contains("claude-code"), "got: {}", msg);
    }

    #[test]
    fn detect_runner_explicit_with_opencode() {
        let runner = detect_runner(Some("opencode/kimi-for-coding/k2p5")).unwrap();
        assert_eq!(runner.slug(), "opencode");
        assert_eq!(runner.binary(), "opencode");
    }

    #[test]
    fn response_parse_basic() {
        let response = "Overall conclusions here.\n\n<!-- technique: entropy -->\nEntropy analysis.\n\n<!-- technique: markov -->\nMarkov analysis.\n";
        let parsed = parse_response(response).unwrap();
        assert_eq!(parsed.conclusions, "Overall conclusions here.");
        assert_eq!(parsed.per_technique.len(), 2);
        assert_eq!(parsed.per_technique[0].0, "entropy");
        assert_eq!(parsed.per_technique[0].1, "Entropy analysis.");
        assert_eq!(parsed.per_technique[1].0, "markov");
        assert_eq!(parsed.per_technique[1].1, "Markov analysis.");
    }

    #[test]
    fn response_parse_leading_marker_empty_conclusions() {
        let response = "<!-- technique: entropy -->\nEntropy stuff.\n";
        let parsed = parse_response(response).unwrap();
        assert_eq!(parsed.conclusions, "");
        assert_eq!(parsed.per_technique.len(), 1);
    }

    #[test]
    fn response_parse_no_markers_fails() {
        let response = "Just text, no markers at all.";
        let err = parse_response(response).unwrap_err();
        assert!(err.to_string().contains("no"));
        assert!(err.to_string().contains("markers"));
    }

    #[test]
    fn response_parse_unknown_slug_passes_through() {
        let response = "Conclusions.\n\n<!-- technique: phantom -->\nPhantom stuff.\n";
        let parsed = parse_response(response).unwrap();
        assert_eq!(parsed.per_technique[0].0, "phantom");
    }

    #[test]
    fn response_parse_partial_coverage() {
        let response = "Conclusions.\n\n<!-- technique: entropy -->\nEntropy.\n";
        let parsed = parse_response(response).unwrap();
        assert_eq!(parsed.per_technique.len(), 1);
    }

    #[test]
    fn sha256_produces_hex() {
        let hash = sha256_hex(b"hello");
        assert_eq!(hash.len(), 64);
        assert!(hash.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn opencode_ndjson_parsing() {
        let raw = r#"{"type":"text","part":{"text":"Hello "}}
{"type":"tool_use","part":{}}
{"type":"text","part":{"text":"World"}}"#;
        let text = extract_opencode_text(raw).unwrap();
        assert_eq!(text, "Hello \nWorld");
    }

    #[test]
    fn prompt_template_has_required_placeholders() {
        assert!(PROMPT_TEMPLATE.contains("{{TEMPLATE_VERSION}}"));
        assert!(PROMPT_TEMPLATE.contains("{{MANIFEST}}"));
        assert!(PROMPT_TEMPLATE.contains("{{TECHNIQUE_SECTIONS}}"));
    }
}
