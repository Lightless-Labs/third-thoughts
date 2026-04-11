Feature: Export

  Scenario: Export with interpretation
    Given an analysis and an interpretation
    When I run middens export with --format jupyter and -o report.ipynb
    Then it produces a file that validates as nbformat v4
    And it contains a top-level conclusions cell with text from the overall conclusions.md
    And it contains per-technique cells each including the corresponding <slug>-conclusions.md text

  Scenario: Export without interpretation
    Given an analysis
    When I run middens export with --no-interpretation
    Then the notebook renders with all technique sections but no conclusions cells
    And it exits 0

  Scenario: Export default-path discovery
    Given a valid analysis and a matching interpretation
    When I run middens export with no flags
    Then it resolves to the latest valid analysis and latest valid matching interpretation via name-sort descending
    And the produced notebook's metadata.middens object contains matching analysis_run_id and analysis_run_path
    And it contains matching interpretation_id and interpretation_path

  Scenario: Export ignores failed and dry-run interpretations
    Given a valid analysis
    And one valid interpretation
    And one later failed interpretation
    And one later dry-run interpretation
    When I run middens export
    Then it picks the valid interpretation

  Scenario: Export with --interpretation-dir override
    Given a valid analysis and interpretation
    When I run middens export with an explicit --interpretation-dir override
    Then it uses the explicitly provided interpretation directory instead of the default discovery

  Scenario: Export does not validate cross-run pairing
    Given an analysis A1 and an interpretation I2 referencing a different analysis A2
    When I run middens export with --analysis-dir A1 and --interpretation-dir I2
    Then it succeeds
    And it produces a notebook with analysis A1's data and I2's narrative
    And it does not warn or fail

  Scenario: Export fails cleanly on missing analysis
    Given an empty XDG analysis dir
    When I run middens export
    Then it exits non-zero with a message containing "no analysis runs found"

  Scenario: Export refuses to overwrite without --force
    Given a pre-existing report.ipynb file
    When I run middens export with -o report.ipynb
    Then it exits non-zero with a message containing "Use --force to overwrite"

  Scenario: Export overwrites existing output file with --force
    Given a pre-existing report.ipynb file
    When I run middens export with -o report.ipynb --force
    Then it overwrites the existing output file

  Scenario: Export rejects invalid --format values at parse time
    When I run middens export with --format html
    Then it exits non-zero with "invalid value for '--format'" error
    And no partial output is written

  Scenario: Notebook metadata contract
    Given a valid exported notebook
    Then the notebook's top-level metadata.middens object contains analysis_run_id, analysis_run_path, and middens_version
    And if an interpretation was loaded, it contains interpretation_id and interpretation_path

  Scenario: Notebook embeds pre-executed outputs
    Given a valid exported notebook
    Then per-technique code cells loading the technique's single table have non-empty outputs arrays
    And the outputs contain at least one display_data entry with both text/html and text/plain mime bundles
    And the first 10 rows of that table round-trip through the HTML bundle

  Scenario: Notebook is self-contained
    Given a valid exported notebook
    When I open report.ipynb in a viewer that cannot execute Python
    Then it still renders all tables, findings, and conclusions from the embedded pre-executed outputs
