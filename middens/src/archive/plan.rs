//! Dry-run planning and execution summary.

/// Summary of what an archive run would or did do.
#[derive(Debug, Clone, Default)]
pub struct PlanSummary {
    pub candidates_discovered: usize,
    pub objects_to_copy: usize,
    pub objects_deduped: usize,
    pub observations_to_add: usize,
    pub parseable: usize,
    pub unparseable: usize,
    pub parser_errors: usize,
    pub empty_placeholders: usize,
    pub sources_not_present: Vec<String>,
}

impl PlanSummary {
    pub fn print(&self, dry_run: bool) {
        let label = if dry_run { "plan" } else { "result" };
        eprintln!(
            "archive {}: {} candidates discovered",
            label, self.candidates_discovered
        );
        eprintln!("  objects to copy: {}", self.objects_to_copy);
        eprintln!("  objects deduped: {}", self.objects_deduped);
        eprintln!("  observations to add: {}", self.observations_to_add);
        if !self.sources_not_present.is_empty() {
            eprintln!(
                "  sources not present: {}",
                self.sources_not_present.join(", ")
            );
        }
        eprintln!("  parseable: {}", self.parseable);
        eprintln!("  unparseable: {}", self.unparseable);
        eprintln!("  parser errors: {}", self.parser_errors);
        eprintln!("  empty placeholders: {}", self.empty_placeholders);
    }
}
