use std::path::PathBuf;

use clap::{Parser, Subcommand};

/// Middens — AI agent session log analyzer.
///
/// Archaeological extraction of behavioral patterns from coding agent transcripts.
#[derive(Parser)]
#[command(name = "middens", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
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
            eprintln!("middens analyze: scanning {:?}", path.as_deref().unwrap_or(&PathBuf::from("(auto-discover)")));
            eprintln!("  techniques: {}", if all { "all".to_string() } else { techniques.as_ref().map_or("essential 10".to_string(), |t| t.join(", ")) });
            eprintln!("  split: {split}");
            eprintln!("  python: {}", !no_python);
            eprintln!("  output: {}", output.display());

            // TODO: implement pipeline
            eprintln!("\n[not yet implemented — Phase 1 in progress]");
            Ok(())
        }
        Commands::Report { results_dir, output } => {
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

            Ok(())
        }
        Commands::Parse { file, format } => {
            let sessions = middens::parser::auto_detect::parse_auto(&file)?;
            let json = match format.as_str() {
                "json" => serde_json::to_string(&sessions)?,
                "json-pretty" | _ => serde_json::to_string_pretty(&sessions)?,
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
    }
}
