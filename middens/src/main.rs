use std::path::PathBuf;

use clap::{Parser, Subcommand, ValueEnum};
use middens::pipeline::{PipelineResult, TechniqueFilter};

/// Middens — AI agent session log analyzer.
///
/// Archaeological extraction of behavioral patterns from coding agent transcripts.
#[derive(Parser)]
#[command(name = "middens", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Clone, ValueEnum)]
enum ExportFormatCli {
    Jupyter,
}

#[derive(Subcommand)]
enum Commands {
    /// Analyze session logs and run the technique battery.
    Analyze {
        /// Path to session logs directory. If omitted, auto-discovers default locations.
        path: Option<PathBuf>,

        /// Run specific techniques (comma-separated).
        #[arg(long, value_delimiter = ',')]
        techniques: Option<Vec<String>>,

        /// Run all techniques (not just essential 10).
        #[arg(long)]
        all: bool,

        /// Stratify results by interactive vs subagent sessions.
        #[arg(long)]
        split: bool,

        /// Skip Python-dependent techniques.
        #[arg(long)]
        no_python: bool,

        /// Override the auto-computed Python technique timeout (seconds).
        /// Must be within [60, 1800] unless --force is also passed.
        #[arg(long)]
        timeout: Option<u64>,

        /// Bypass timeout floor/ceiling checks. Only meaningful with --timeout.
        #[arg(long)]
        force: bool,

        /// Output directory for results.
        #[arg(short, long, default_value = "middens-results")]
        output: PathBuf,
    },

    /// Generate a consolidated report from technique results.
    Report {
        /// Path to results directory from a previous analyze run.
        results_dir: PathBuf,

        /// Output file for the report.
        #[arg(short, long)]
        output: Option<PathBuf>,
    },

    /// List available techniques.
    ListTechniques {
        /// Show only essential techniques.
        #[arg(long)]
        essential: bool,
    },

    /// Parse and dump a single session file (debug tool).
    Parse {
        /// Path to a session log file.
        file: PathBuf,

        /// Output format.
        #[arg(long, default_value = "json")]
        format: String,
    },

    /// Create a frozen corpus manifest for reproducibility.
    Freeze {
        /// Path to corpus directory.
        path: PathBuf,

        /// Output manifest file.
        #[arg(short, long, default_value = "corpus-manifest.json")]
        output: PathBuf,
    },

    /// Show environment evolution over time.
    Fingerprint {
        /// Path to session logs directory.
        path: PathBuf,
    },

    /// Interpret an analysis run using an LLM runner.
    Interpret {
        /// Analysis run directory. Default: latest valid run under XDG.
        #[arg(long)]
        analysis_dir: Option<PathBuf>,

        /// Runner and model in <runner>/<model-id> format.
        #[arg(long)]
        model: Option<String>,

        /// Output directory for interpretation.
        #[arg(long)]
        output_dir: Option<PathBuf>,

        /// Write prompt without calling a runner.
        #[arg(long)]
        dry_run: bool,
    },

    /// Export an analysis run as a Jupyter notebook.
    Export {
        /// Analysis run directory. Default: latest valid run under XDG.
        #[arg(long)]
        analysis_dir: Option<PathBuf>,

        /// Interpretation directory. Default: latest valid under interpretation/.
        #[arg(long, conflicts_with = "no_interpretation")]
        interpretation_dir: Option<PathBuf>,

        /// Skip interpretation even if present.
        #[arg(long)]
        no_interpretation: bool,

        /// Output format (v1: jupyter only).
        #[arg(long, default_value = "jupyter")]
        format: ExportFormatCli,

        /// Output file path. Default: report.ipynb in cwd.
        #[arg(short, long)]
        output: Option<PathBuf>,

        /// Overwrite output file if it already exists.
        #[arg(long)]
        force: bool,
    },

    /// Run the full pipeline: analyze -> interpret -> export.
    Run {
        /// Path to session logs directory. If omitted, auto-discovers default locations.
        path: Option<PathBuf>,

        /// Runner and model in <runner>/<model-id> format.
        /// If omitted, the interpret step is skipped.
        #[arg(long)]
        model: Option<String>,

        /// Output file for the exported notebook.
        #[arg(short, long)]
        output: Option<PathBuf>,

        /// Output format (v1: jupyter only).
        #[arg(long, default_value = "jupyter")]
        format: ExportFormatCli,

        /// Run all techniques (not just essential 10).
        #[arg(long)]
        all: bool,

        /// Run specific techniques (comma-separated).
        #[arg(long, value_delimiter = ',')]
        techniques: Option<Vec<String>>,

        /// Skip Python-dependent techniques.
        #[arg(long)]
        no_python: bool,

        /// Override the auto-computed Python technique timeout (seconds).
        #[arg(long)]
        timeout: Option<u64>,

        /// Bypass timeout floor/ceiling checks. Only meaningful with --timeout.
        #[arg(long)]
        force: bool,

        /// Skip the interpret step even when --model is given.
        #[arg(long)]
        no_interpretation: bool,

        /// Write interpret prompt to disk without calling a runner.
        #[arg(long)]
        dry_run: bool,
    },
}

fn validate_timeout_force(force: bool, timeout: Option<u64>) -> anyhow::Result<()> {
    if force && timeout.is_none() {
        anyhow::bail!(
            "--force only applies to --timeout; pass --timeout <seconds> alongside it, \
             e.g. `--timeout 3600 --force`"
        );
    }

    Ok(())
}

fn select_technique_filter(all: bool, techniques: Option<Vec<String>>) -> TechniqueFilter {
    if all {
        TechniqueFilter::All
    } else if let Some(techniques) = techniques {
        TechniqueFilter::Named(techniques)
    } else {
        TechniqueFilter::Essential
    }
}

fn print_analysis_summary(result: &PipelineResult, split: bool) {
    eprintln!("\nAnalysis complete:");
    eprintln!("  sessions discovered: {}", result.sessions_discovered);
    eprintln!("  sessions parsed: {}", result.sessions_parsed);
    if split {
        eprintln!("  interactive sessions: {}", result.interactive_sessions);
        eprintln!("  subagent sessions: {}", result.subagent_sessions);
    }
    eprintln!("  parse errors: {}", result.parse_errors);
    eprintln!("  techniques run: {}", result.techniques_run);
    eprintln!("  technique errors: {}", result.technique_errors);
    eprintln!("  results written to: {}", result.output_dir.display());
    if let Some(ref storage) = result.storage_dir {
        eprintln!("  storage (parquet + manifest): {}", storage.display());
    }
}

fn resolve_export_output_path(output: Option<PathBuf>) -> PathBuf {
    output.unwrap_or_else(|| {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join("report.ipynb")
    })
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Analyze {
            path,
            techniques,
            all,
            split,
            no_python,
            timeout,
            force,
            output,
        } => {
            use middens::pipeline::{self, PipelineConfig};

            validate_timeout_force(force, timeout)?;

            let technique_filter = select_technique_filter(all, techniques);

            let config = PipelineConfig {
                corpus_path: path,
                output_dir: output,
                technique_filter,
                no_python,
                split,
                explicit_timeout: timeout,
                force,
            };

            let result = pipeline::run(config)?;

            print_analysis_summary(&result, split);

            if result.sessions_parsed == 0 {
                std::process::exit(1);
            }

            Ok(())
        }
        Commands::Report {
            results_dir,
            output: _,
        } => {
            eprintln!("middens report: {}", results_dir.display());
            eprintln!("[not yet implemented]");
            Ok(())
        }
        Commands::ListTechniques { essential } => {
            let all = middens::techniques::all_techniques();
            let techniques: Vec<_> = if essential {
                all.into_iter().filter(|t| t.is_essential()).collect()
            } else {
                all
            };

            println!(
                "{:<30} {:<10} {:<8} {}",
                "NAME", "ESSENTIAL", "PYTHON", "DESCRIPTION"
            );
            println!("{}", "-".repeat(80));

            if techniques.is_empty() {
                println!("No techniques registered yet.");
            } else {
                for t in &techniques {
                    println!(
                        "{:<30} {:<10} {:<8} {}",
                        t.name(),
                        if t.is_essential() { "yes" } else { "no" },
                        if t.requires_python() { "yes" } else { "no" },
                        t.description(),
                    );
                }
            }

            if !essential {
                for (name, desc, _filename) in middens::techniques::PYTHON_TECHNIQUE_MANIFEST {
                    println!("{:<30} {:<10} {:<8} {}", name, "no", "yes", desc,);
                }
            }

            Ok(())
        }
        Commands::Parse { file, format } => {
            let sessions = middens::parser::auto_detect::parse_auto(&file)?;
            let json = match format.as_str() {
                "json" => serde_json::to_string(&sessions)?,
                "json-pretty" => serde_json::to_string_pretty(&sessions)?,
                other => anyhow::bail!("unsupported format: {other}. Use 'json' or 'json-pretty'"),
            };
            println!("{}", json);
            Ok(())
        }
        Commands::Freeze { path, output } => {
            middens::corpus::manifest::create_manifest(&path, &output)?;
            Ok(())
        }
        Commands::Fingerprint { path } => {
            eprintln!("middens fingerprint: {}", path.display());
            eprintln!("[not yet implemented]");
            Ok(())
        }
        Commands::Interpret {
            analysis_dir,
            model,
            output_dir,
            dry_run,
        } => {
            use middens::commands::interpret::{self, InterpretConfig};

            let config = InterpretConfig {
                analysis_dir,
                model,
                output_dir,
                dry_run,
            };

            interpret::run_interpret(config)
        }
        Commands::Export {
            analysis_dir,
            interpretation_dir,
            no_interpretation,
            format,
            output,
            force,
        } => {
            use middens::commands::export::{self, ExportConfig, ExportFormat};

            let export_format = match format {
                ExportFormatCli::Jupyter => ExportFormat::Jupyter,
            };

            let config = ExportConfig {
                analysis_dir,
                interpretation_dir,
                no_interpretation,
                format: export_format,
                output,
                force,
            };

            export::run_export(config)
        }
        Commands::Run {
            path,
            model,
            output,
            format,
            all,
            techniques,
            no_python,
            timeout,
            force,
            no_interpretation,
            dry_run,
        } => {
            use middens::commands::{
                export::{self, ExportConfig, ExportFormat},
                interpret::{self, InterpretConfig},
            };
            use middens::pipeline::{self, PipelineConfig};

            validate_timeout_force(force, timeout)?;

            let analyze_target = path
                .as_ref()
                .map(|path| path.display().to_string())
                .unwrap_or_else(|| "auto".to_string());
            let technique_filter = select_technique_filter(all, techniques);

            eprintln!("→ analyzing {}...", analyze_target);
            let result = pipeline::run(PipelineConfig {
                corpus_path: path,
                output_dir: PathBuf::from("middens-results"),
                technique_filter,
                no_python,
                split: false,
                explicit_timeout: timeout,
                force,
            })?;

            if result.sessions_parsed == 0 {
                anyhow::bail!("analyze step: no sessions parsed");
            }

            let analysis_dir = result.output_dir.clone();
            let do_interpret = model.is_some() && !no_interpretation;

            if do_interpret {
                let model_name = model.as_deref().unwrap_or_default();
                eprintln!("→ interpreting with {}...", model_name);
                interpret::run_interpret(InterpretConfig {
                    analysis_dir: Some(analysis_dir.clone()),
                    model: model.clone(),
                    output_dir: None,
                    dry_run,
                })
                .map_err(|err| anyhow::anyhow!("interpret step failed: {err}"))?;
            }

            let output_path = resolve_export_output_path(output);
            eprintln!("→ exporting to {}...", output_path.display());

            let export_format = match format {
                ExportFormatCli::Jupyter => ExportFormat::Jupyter,
            };

            export::run_export(ExportConfig {
                analysis_dir: Some(analysis_dir),
                interpretation_dir: None,
                no_interpretation: !do_interpret,
                format: export_format,
                output: Some(output_path.clone()),
                force: true,
            })
            .map_err(|err| anyhow::anyhow!("export step failed: {err}"))?;

            eprintln!(
                "done: sessions discovered {}, sessions parsed {}, techniques run {}, output {}",
                result.sessions_discovered,
                result.sessions_parsed,
                result.techniques_run,
                output_path.display()
            );

            Ok(())
        }
    }
}
