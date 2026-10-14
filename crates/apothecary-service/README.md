# apothecary-service

A Rust service to run beside the Python server (`apothecary serve`). It is a
stub: the binary says so and exits 1 (`src/main.rs`). It exists so the
workspace, the licence headers and the checks are settled before there is
anything in it.

## What it is for

One of two jobs, undecided; the first it takes is the whole of its first
version.

- **The serial and printer daemon.** The Python server holds the serial port,
  streams G-code and polls a printer's temperatures (`apothecary/firmware/`;
  `docs/firmware.md` says what it does). A long print should not depend on a
  web server that restarts when its code changes. A daemon owns the port, the
  server and the viewer talk to it, and a restart of either leaves a print
  running.
- **A fast renderer the viewer talks to.** A process that takes a scene's JSON
  and returns an STL without OpenSCAD, on one of the kernels the 2026-10-09
  survey compared ([the kernel spike](../../docs/plans/rust-geometry-kernels-2026-10-09.md));
  the first to try is Manifold through its Rust bindings. The comparison
  tests in `tests/test_kernel_comparison.py` decide whether it earns the job.
  It would be a command reading the scene JSON `apothecary render` reads and
  writing an STL, called with `subprocess` as OpenSCAD is and fetched at
  install time as OpenSCAD is; the Rust side owns the translation
  `apothecary/jscad.py` does for JSCAD. A kernel whose build fetches something
  -- `manifold-csg`'s first build clones Manifold with cmake -- has that fetch
  written into the personal-data record's install-time list, or its source
  vendored, before it is built.

It is not in the wheel, and neither the Python suites nor CI build or run it;
`cargo check --workspace` checks it locally. A crate that does something
needs a CI job of its own: Rust installed (`dtolnay/rust-toolchain` or
`rustup`), `cargo check --workspace`, `cargo clippy --workspace -- -D
warnings`, `cargo fmt --check` and `cargo test --workspace`, and `cargo
license` against the allowlist the Python licence check uses (see
`.github/workflows/license-check.yml` and the open-license record in the
governance submodule).

## Build

```bash
cargo build -p apothecary-service
cargo run -p apothecary-service     # prints "not built yet" and exits 1
```
