Feature: Archive CLI command
  The `middens archive` subcommand copies raw session logs into a private,
  reproducible archive with explicit consent, content-hash dedupe, and a
  canonical manifest.

  Background:
    Given a temporary archive sandbox

  Scenario: --to is required
    When I run middens archive with arguments "--dry-run"
    Then the exit code should not be 0
    And stderr should contain "archive destination is required"
    And stderr should contain "middens archive --to ~/agent-session-archive --dry-run"

  Scenario: Dry-run writes nothing
    Given an explicit Claude source root containing one parseable session
    And the archive root path does not exist
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --dry-run"
    Then the exit code should be 0
    And the combined archive output should contain "claude-primary.jsonl"
    And the archive root should not exist

  Scenario: Non-dry-run requires consent
    Given an explicit Claude source root containing one parseable session
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source>"
    Then the exit code should not be 0
    And stderr should contain "WARNING: middens archive copies raw agent session transcripts"
    And the archive root should not exist

  Scenario: Successful archive copies bytes, writes manifest and index, and leaves sources untouched
    Given an explicit Claude source root containing one parseable session
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    And stderr should contain "WARNING: middens archive copies raw agent session transcripts"
    And the archive object for "claude_primary" should match the source bytes
    And the archive manifest should satisfy the required schema minimums
    And the archive manifest should contain 1 object and 1 observation
    And the archive index should reference a manifest object hash
    And the source fixture files should be unchanged

  Scenario: Re-running the same archive command is idempotent
    Given an explicit Claude source root containing one parseable session
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    When I remember the archived object bytes for "claude_primary"
    And I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    And the combined archive output should contain "0 copied"
    And the archive manifest should contain 1 object and 1 observation
    And the remembered archived object bytes for "claude_primary" should be unchanged

  Scenario: Same-content duplicates are deduped into one object
    Given an explicit Claude source root containing two identical sessions
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    And the archive manifest should contain 1 object and 2 observation
    And all archive observations should point to the same archive path

  Scenario: Changed source contents produce a new object without deleting the old one
    Given an explicit Claude source root containing one parseable session
    When I remember the source file hash for "claude_primary"
    And I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    When I replace the "claude_primary" source file with a different parseable Claude fixture
    And I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    And the archive manifest should contain 2 object and 2 observation
    And both archived object files for the changed source should exist

  Scenario: Destination collision fails clearly without manifest update
    Given an explicit Claude source root containing one parseable session
    And the archive root contains a destination collision for "claude_primary"
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And the combined archive output should contain "destination collision"
    And manifest.json should not exist under the archive root

  Scenario: Corrupt manifest fails before copying
    Given an explicit Claude source root containing one parseable session
    And the archive root contains a corrupt manifest
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And the combined archive output should contain "manifest.json"
    And the final archive object for "claude_primary" should not exist

  Scenario: Archive drift fails before copying new files
    Given an explicit Claude source root containing one parseable session
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    When I delete the archived object for "claude_primary"
    And I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And the combined archive output should contain "archive drift detected"

  Scenario: Unparseable files are archived by default
    Given an explicit Claude source root containing one unparseable JSONL file
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    And the archive manifest should contain 1 object and 1 observation
    And the archive manifest should record parser status "unparseable"

  Scenario: Parser errors do not leak transcript content
    Given an explicit Claude source root containing one parser-error Claude fixture
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    And the archive manifest should record parser status "parser_error"
    And the parser diagnostic should be non-empty
    And the parser diagnostic should not contain "LEAK_ME_SECRET_PAYLOAD"

  Scenario: --require-parseable rejects unparseable fixtures before manifest update
    Given an explicit Claude source root containing one unparseable JSONL file
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --require-parseable --yes"
    Then the exit code should not be 0
    And manifest.json should not exist under the archive root
    And the final archive object for "unparseable_file" should not exist

  Scenario: --source limits discovery to the requested default root
    Given the sandbox home contains one default Claude session and one default Codex session
    When I run middens archive with arguments "--to <archive> --source codex --yes"
    Then the exit code should be 0
    And the archive manifest should contain 1 object and 1 observation
    And all archive observations should have source tool "codex"
    And no archive observation should have basename "claude-default.jsonl"

  Scenario: --from without --source fails validation
    Given an explicit Claude source root containing one parseable session
    When I run middens archive with arguments "--to <archive> --from <claude_source> --dry-run"
    Then the exit code should not be 0
    And the combined archive output should contain "--from"
    And the combined archive output should contain "--source"

  Scenario: --from with multiple sources fails validation
    Given an explicit Claude source root containing one parseable session
    When I run middens archive with arguments "--to <archive> --source claude-code --source codex --from <claude_source> --dry-run"
    Then the exit code should not be 0
    And the combined archive output should contain "--from"
    And the combined archive output should contain "exactly one --source"

  Scenario: Explicit missing source fails helpfully
    Given the explicit source path does not exist
    When I run middens archive with arguments "--to <archive> --source claude-code --from <missing_source> --dry-run"
    Then the exit code should not be 0
    And the combined archive output should contain "<missing_source>"
    And the combined archive output should contain "readable directory of .jsonl session logs"
    And the combined archive output should contain "--source claude-code --from"

  Scenario: Unreadable source fails helpfully
    Given an unreadable explicit Claude source root
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --dry-run"
    Then the exit code should not be 0
    And the combined archive output should contain "<claude_source>"

  Scenario: Symlinked files archive target bytes and record canonical paths
    Given an explicit Claude source root containing a symlinked session
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    And the archive object for "claude_symlink_target" should match the source bytes
    And the archive observation for basename "claude-symlink.jsonl" should record canonical path "<claude_symlink_target>"

  Scenario: Symlink loops fail clearly
    Given an explicit Claude source root containing a symlink loop
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And the combined archive output should contain "loop"
    And manifest.json should not exist under the archive root

  Scenario: Overlap is rejected when archive equals source
    Given an explicit Claude source root containing one parseable session
    And the archive root equals the explicit Claude source root
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And the combined archive output should contain "must not overlap"

  Scenario: Overlap is rejected when archive is inside source
    Given an explicit Claude source root containing one parseable session
    And the archive root is inside the explicit Claude source root
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And the combined archive output should contain "must not overlap"

  Scenario: Overlap is rejected when archive is an ancestor of source
    Given an explicit Claude source root containing one parseable session
    And the archive root is an ancestor of the explicit Claude source root
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And the combined archive output should contain "must not overlap"

  Scenario: Manifest writes are atomic under interruption hooks
    Given an explicit Claude source root containing one parseable session
    And archive write hook "manifest-rename" is enabled
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And manifest.json should be absent or valid JSON

  Scenario: Object writes are atomic under interruption hooks
    Given an explicit Claude source root containing one parseable session
    And archive write hook "object-copy" is enabled
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And the final archive object for "claude_primary" should not exist

  Scenario: Lock file prevents concurrent writers
    Given an explicit Claude source root containing one parseable session
    And the archive lock file already exists
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should not be 0
    And the combined archive output should contain ".archive.lock"
    And manifest.json should not exist under the archive root

  Scenario: Git worktree safety creates a deny-all archive .gitignore
    Given an explicit Claude source root containing one parseable session
    And the archive root is inside a git worktree
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    And the archive .gitignore should deny all contents

  Scenario: Existing archive .gitignore is not overwritten
    Given an explicit Claude source root containing one parseable session
    And the archive root is inside a git worktree
    And the archive root already has a user-authored .gitignore
    When I run middens archive with arguments "--to <archive> --source claude-code --from <claude_source> --yes"
    Then the exit code should be 0
    And the archive .gitignore should remain unchanged
