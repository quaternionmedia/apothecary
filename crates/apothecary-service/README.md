# apothecary-service

A Rust service that runs beside the Python server (`apothecary serve`). **Not
built yet**: the binary prints that and exits non-zero. It is a stub for
[the Rust plan](../../docs/plans/rust-2026-10-08.md) ("Planned and stubbed
only"), here so the workspace, the licence headers and the checks are settled
before there is anything in it.

## What it is for

One of two jobs, and the plan leaves the choice open until it is made with the
owner; the first job it gets is the whole of its first version.

- **The serial and printer daemon.** Today the Python server holds the serial
  port, streams G-code and polls a printer's temperatures (`apothecary/firmware/`).
  A long print should not depend on a web server that restarts when its code
  changes. A daemon owns the port, the server and the viewer talk to it, and a
  restart of either leaves a print running (see `docs/firmware.md` for what the Python side does
  today).
- **A fast renderer the viewer talks to.** A process that takes a scene's JSON
  and returns an STL without OpenSCAD, on one of the kernels in
  [the kernel spike](../../docs/plans/rust-geometry-kernels-2026-10-09.md);
  the first to try there is Manifold through its Rust bindings. The comparison
  tests in `tests/test_kernel_comparison.py` are what decides whether it earns
  the job.

It is not in the wheel, is not built or run by the Python suites, and is not
built by CI. When it does something, CI needs a job that installs Rust
(`dtolnay/rust-toolchain` or `rustup`), runs `cargo check --workspace`,
`cargo clippy --workspace -- -D warnings`, `cargo fmt --check` and
`cargo test --workspace`, and `cargo license` against the allowlist the
Python license check uses (see `.github/workflows/license-check.yml` and the
open-license record in the governance submodule).

## Build

```bash
cargo build -p apothecary-service
cargo run -p apothecary-service     # prints that it is not built yet; exits 1
```
