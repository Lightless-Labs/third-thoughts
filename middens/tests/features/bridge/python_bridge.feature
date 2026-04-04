Feature: Python Bridge Infrastructure

  The Python bridge allows middens to run complex analytical techniques implemented in Python
  via the uv-managed environment.

  @allow.skipped
  Scenario: uv detection
    Given uv is available in the environment
    Then the bridge should detect uv successfully

  Scenario: PythonTechnique wrapper - successful execution
    Given the echo Python technique is available
    And a set of test sessions
    When the echo technique is run
    Then it should successfully serialize sessions to a temporary file
    And the subprocess should execute successfully
    And it should parse the stdout into a TechniqueResult
    And the finding "session_count" should be equal to the number of test sessions

  Scenario: PythonTechnique wrapper - subprocess failure
    Given a Python technique that exits with code 1
    And a set of test sessions
    When the technique is run
    Then it should return an error
    And the error should contain the subprocess stderr

  Scenario: PythonTechnique wrapper - subprocess timeout
    Given a Python technique that hangs
    And a set of test sessions
    When the technique is run
    Then it should return a timeout error

  Scenario: --no-python flag filtering
    Given a Python technique named "echo"
    And a Rust technique named "burstiness"
    When the pipeline is run with --no-python
    Then the "burstiness" technique should be run
    And the "echo" technique should not be run

  Scenario: Python stderr capture
    Given a Python technique that prints to stderr and fails
    When the technique is run
    Then the captured stderr should contain the diagnostic message
