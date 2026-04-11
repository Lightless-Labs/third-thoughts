use std::path::PathBuf;

use clap::{Parser, Subcommand, ValueEnum};

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
            output,
        } => {
            use middens::pipeline::{self, PipelineConfig, TechniqueFilter};

            let technique_filter = if all {
                TechniqueFilter::All
            } else if let Some(t) = techniques {
                TechniqueFilter::Named(t)
            } else {
                TechniqueFilter::Essential
            };

            let config = PipelineConfig {
                corpus_path: path,
                output_dir: output,
                technique_filter,
                no_python,
                split,
            };

            let result = pipeline::run(config)?;

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
    }
}
