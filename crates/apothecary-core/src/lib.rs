//! `apothecary_core`: a Rust core inside Python. Exposes nothing yet beyond
//! its own version; see README.md for the hot paths it is for.

use pyo3::prelude::*;

/// The module Python would `import apothecary_core`.
#[pymodule]
mod apothecary_core {
    use pyo3::prelude::*;

    /// This crate's version, so a caller can tell the core it loaded.
    #[pyfunction]
    fn version() -> &'static str {
        env!("CARGO_PKG_VERSION")
    }
}
