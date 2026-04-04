mod steps;

use cucumber::{World, given, then};
use steps::world::MiddensWorld;

// Import all step modules so the cucumber proc macros register their steps.
#[allow(unused_imports)]
use steps::classifier;
#[allow(unused_imports)]
use steps::cli;
#[allow(unused_imports)]
use steps::corpus;
#[allow(unused_imports)]
use steps::output;
#[allow(unused_imports)]
use steps::parser;
#[allow(unused_imports)]
use steps::pipeline;
#[allow(unused_imports)]
use steps::split;
#[allow(unused_imports)]
use steps::techniques;
#[allow(unused_imports)]
use steps::thinking_divergence;
#[allow(unused_imports)]
use steps::python_bridge;

// Smoke test steps
#[given("the test harness is initialized")]
fn harness_initialized(_world: &mut MiddensWorld) {
    // World is auto-constructed — nothing to do.
}

#[then("the harness should be operational")]
fn harness_operational(_world: &mut MiddensWorld) {
    // If we got here, the harness works.
}

fn main() {
    futures::executor::block_on(
        MiddensWorld::cucumber()
            .fail_on_skipped()
            .run_and_exit("tests/features"),
    );
}
