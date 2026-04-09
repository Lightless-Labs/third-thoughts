Feature: Storage

  Scenario: Round-trip a minimal analysis
    Given a fixture corpus with 2 sessions
    When I run middens analyze on the fixture corpus
    Then manifest.json exists
    And at least one data/*.parquet file exists
    And the manifest validates against the schema
    And AnalysisRun::load reads them back with matching technique count, row counts, and scalar findings

  Scenario: Corpus fingerprint is stable
    Given a fixture corpus
    When I run middens analyze twice against the same corpus
    Then the corpus_fingerprint.manifest_hash is the same between runs
    And the corpus_fingerprint.short is the same between runs
    And the run_id differs between runs

  Scenario: One table per technique, round-trips through Parquet
    Given a single-table technique
    When I run middens analyze
    Then data/<technique_slug>.parquet exists
    And AnalysisRun::load reads it back with matching row count, column count, column types, and first-row values

  Scenario: Type-homogeneous columns survive round-trip
    Given a technique that declares column_types as Int, Float, String
    When I run middens analyze
    Then the Parquet file schema matches the declared types
    And loading it back preserves the types

  Scenario: column_types mismatch is rejected
    Given a technique that declares column_types as Int but supplies a Float column at position 0
    When I run middens analyze
    Then it fails loudly naming the column index, declared type, and actual type
    And no partial output is written

  Scenario: PII tokenised column-name blocklist — blocked cases
    Given a test technique declaring a column named "raw_data"
    When I run middens analyze
    Then it fails loudly naming the offending technique, column, and matched blocklist token
    And it suggests a rename
    And no partial run directory is left on disk

  Scenario: PII tokenised column-name blocklist — permitted cases
    Given a test technique declaring columns named "context_length", "n_turns", and "msg_count"
    When I run middens analyze
    Then the PII check passes
    And the run succeeds

  Scenario: PII value-length cap
    Given a test technique that emits a String column whose values exceed 200 characters
    When I run middens analyze
    Then it fails with an error naming the technique, column, and row index of the first offending cell
    And no partial output is written
