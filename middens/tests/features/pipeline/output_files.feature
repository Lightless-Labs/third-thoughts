Feature: Analyze output files
  Generated analyze artifacts should be structurally valid and named after the
  techniques that produced them.

  Scenario: Output markdown files have YAML frontmatter with corpus_size
    Given a temporary analyze output directory
    When I run middens analyze on the fixtures directory
    Then the exit code should be 0
    And all markdown output files should have valid YAML frontmatter with corpus_size

  Scenario: Output JSON files are valid JSON
    Given a temporary analyze output directory
    When I run middens analyze on the fixtures directory
    Then the exit code should be 0
    And all JSON output files should be valid JSON

  Scenario: Output file names match technique names
    Given a temporary analyze output directory
    When I run middens analyze on the fixtures directory
    Then the exit code should be 0
    And the analyze output file basenames should match technique names "burstiness,correction-rate,diversity,entropy,markov,thinking-divergence"
