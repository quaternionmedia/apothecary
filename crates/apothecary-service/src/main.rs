//! `apothecary-service`: a Rust service beside the Python server. Not built yet.
//!
//! See README.md for what it is for. Until it does something it says so and
//! exits non-zero, so nothing can mistake it for a service that is running.

use std::process::ExitCode;

fn main() -> ExitCode {
    eprintln!(
        "apothecary-service {}: not built yet (see crates/apothecary-service/README.md)",
        env!("CARGO_PKG_VERSION")
    );
    ExitCode::FAILURE
}
