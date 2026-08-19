"""Testing-related CLI commands: test group and subcommands."""

import os
import subprocess
import sys
import time
from datetime import datetime

import click

from ..projects.parts.skeleton import ROOT
from .utils import _safe_echo


@click.group()
def test():
    """Commands for testing and test setup."""


@test.command("setup-e2e")
def test_setup_e2e():
    """Set up Playwright browsers for E2E testing."""
    click.secho("Playwright E2E Test Setup", bold=True)
    click.echo("")

    # Check if playwright is installed
    try:
        import importlib.util

        if importlib.util.find_spec("playwright") is not None:
            try:
                from importlib.metadata import version

                pw_version = version("playwright")
                _safe_echo(f"✓ Playwright installed (version {pw_version})")
            except Exception:
                _safe_echo("✓ Playwright installed")
    except ImportError:
        _safe_echo("✗ Playwright not installed", fg="red")
        click.echo("  Run: uv sync")
        return 1

    click.echo("")
    click.echo("Installing Playwright browsers (chromium)...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            _safe_echo("✓ Chromium browser installed successfully", fg="green", bold=True)
            click.echo("")
            click.echo("Setup complete! Run E2E tests with:")
            click.echo("  apothecary test run-e2e")
            click.echo("  or: pytest tests/e2e/ -v")
        else:
            _safe_echo("✗ Browser installation failed", fg="red")
            if result.stderr:
                click.echo(f"  Error: {result.stderr[:200]}")
            return 1
    except subprocess.TimeoutExpired:
        _safe_echo("✗ Installation timed out after 5 minutes", fg="red")
        return 1
    except Exception as e:
        _safe_echo(f"✗ Error: {e}", fg="red")
        return 1


@test.command("validate-e2e")
def test_validate_e2e():
    """Validate E2E test setup."""
    click.secho("Validating E2E Test Setup", bold=True)
    click.echo("=" * 50)
    click.echo("")

    all_checks_passed = True

    # Check files
    click.echo("Checking required files...")
    required_files = [
        "tests/e2e/conftest.py",
        "tests/e2e/test_viewer.py",
        "tests/e2e/test_api.py",
    ]

    missing_files = []
    for file in required_files:
        file_path = ROOT / file
        if not file_path.exists():
            missing_files.append(file)

    if missing_files:
        _safe_echo("✗ Missing files:", fg="red")
        for f in missing_files:
            click.echo(f"   - {f}")
        all_checks_passed = False
    else:
        _safe_echo("✓ All required files present")
    click.echo("")

    # Check Playwright dependency
    click.echo("Checking Playwright installation...")
    try:
        import importlib.util

        if importlib.util.find_spec("playwright") is not None:
            try:
                from importlib.metadata import version

                pw_version = version("playwright")
                _safe_echo(f"✓ Playwright installed (version {pw_version})")
            except Exception:
                _safe_echo("✓ Playwright installed")
    except ImportError:
        _safe_echo("✗ Playwright not installed", fg="red")
        click.echo("   Run: uv sync")
        all_checks_passed = False
    click.echo("")

    # Check browsers
    click.echo("Checking Playwright browsers...")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                _safe_echo("✓ Chromium browser installed")
            except Exception as e:
                _safe_echo(f"✗ Chromium not installed: {e}", fg="red")
                click.echo("   Run: apothecary test:setup-e2e")
                all_checks_passed = False
    except Exception as e:
        _safe_echo(f"✗ Error checking browsers: {e}", fg="red")
        all_checks_passed = False
    click.echo("")

    # Summary
    click.echo("=" * 50)
    if all_checks_passed:
        _safe_echo("✓ All checks passed!", fg="green", bold=True)
        click.echo("")
        click.echo("Run E2E tests with:")
        click.echo("  apothecary test run-e2e")
        return 0
    else:
        _safe_echo("✗ Some checks failed", fg="red", bold=True)
        click.echo("")
        click.echo("Run setup with:")
        click.echo("  apothecary test setup-e2e")
        return 1


@test.command("run-e2e")
@click.option("--headed", is_flag=True, help="Run tests with visible browser")
@click.option("--slowmo", type=int, default=0, help="Slow down operations by N milliseconds")
@click.option("--browser", default="chromium", help="Browser to use (chromium, firefox, webkit)")
@click.option("--base-url", default="http://127.0.0.1:8765", help="Base URL for test server")
def test_run_e2e(headed: bool, slowmo: int, browser: str, base_url: str):
    """Run E2E tests with Playwright.

    Note: Server must be running before tests. Start with:
        apothecary serve --port 8765
    """
    click.secho("Running E2E Tests", bold=True)
    click.echo(f"Server URL: {base_url}")
    click.echo("")

    # Build pytest command
    cmd = [sys.executable, "-m", "pytest", "tests/e2e/", "-v", f"--base-url={base_url}"]

    if headed:
        cmd.append("--headed")

    if slowmo > 0:
        cmd.append(f"--slowmo={slowmo}")

    if browser != "chromium":
        cmd.append(f"--browser={browser}")

    click.echo(f"Running: {' '.join(cmd)}")
    click.echo("")

    try:
        result = subprocess.run(cmd, cwd=ROOT)
        return result.returncode
    except Exception as e:
        _safe_echo(f"✗ Error running tests: {e}", fg="red")
        return 1


@test.command("run")
@click.option("--e2e", is_flag=True, help="Include E2E tests")
@click.option("--coverage", is_flag=True, help="Run with coverage report")
def test_run(e2e: bool, coverage: bool):
    """Run unit tests (and optionally E2E tests)."""
    click.secho("Running Tests", bold=True)
    click.echo("")

    # Build pytest command
    cmd = [sys.executable, "-m", "pytest", "-v"]

    if not e2e:
        cmd.extend(["tests/", "--ignore=tests/e2e"])
        click.echo("Running unit tests only...")
    else:
        cmd.append("tests/")
        click.echo("Running all tests (unit + E2E)...")

    if coverage:
        cmd.extend(["--cov=apothecary", "--cov-report=html"])

    click.echo("")

    try:
        result = subprocess.run(cmd, cwd=ROOT)

        if coverage and result.returncode == 0:
            click.echo("")
            click.echo("Coverage report generated: htmlcov/index.html")

        return result.returncode
    except Exception as e:
        _safe_echo(f"✗ Error running tests: {e}", fg="red")
        return 1


@test.command("all")
@click.option("--port", default=8765, type=int, help="Port for test server")
@click.option("--coverage", is_flag=True, help="Run with coverage report")
@click.option("--headed", is_flag=True, help="Run E2E tests with visible browser")
@click.option("--fail-fast", "-x", is_flag=True, help="Stop on first failure")
def test_all(port: int, coverage: bool, headed: bool, fail_fast: bool):
    """Run full test suite (unit + E2E) with aggregate summary.

    Automatically starts a test server, runs all tests, and produces
    a combined report for velocity review.
    """
    import re
    import urllib.request

    click.secho("=" * 60, fg="cyan", bold=True)
    click.secho("  APOTHECARY FULL TEST SUITE", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan", bold=True)
    click.echo(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"  Test server port: {port}")
    click.echo("")

    results = {
        "unit": {"passed": 0, "failed": 0, "skipped": 0, "time": 0},
        "e2e": {"passed": 0, "failed": 0, "skipped": 0, "time": 0},
    }
    server_proc = None
    overall_start = time.time()

    try:
        # ─────────────────────────────────────────────────────────────
        # Phase 1: Unit Tests
        # ─────────────────────────────────────────────────────────────
        click.secho("─" * 60, fg="blue")
        click.secho("  PHASE 1: Unit Tests", fg="blue", bold=True)
        click.secho("─" * 60, fg="blue")
        click.echo("")

        unit_start = time.time()
        unit_cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--ignore=tests/e2e",
            "-v",
            "--tb=short",
            "-q",  # Quieter output
        ]
        if fail_fast:
            unit_cmd.append("-x")
        if coverage:
            unit_cmd.extend(["--cov=apothecary", "--cov-report=term-missing:skip-covered"])

        unit_result = subprocess.run(unit_cmd, cwd=ROOT, capture_output=True, text=True)
        results["unit"]["time"] = time.time() - unit_start

        # Parse pytest output for counts
        for line in unit_result.stdout.split("\n"):
            if "passed" in line or "failed" in line or "error" in line:
                click.echo(line)
            # Parse summary line like "55 passed in 0.97s"
            if " passed" in line:
                match = re.search(r"(\d+) passed", line)
                if match:
                    results["unit"]["passed"] = int(match.group(1))
                match = re.search(r"(\d+) failed", line)
                if match:
                    results["unit"]["failed"] = int(match.group(1))
                match = re.search(r"(\d+) skipped", line)
                if match:
                    results["unit"]["skipped"] = int(match.group(1))

        unit_ok = unit_result.returncode == 0

        if unit_ok:
            _safe_echo(f"\n✓ Unit tests PASSED ({results['unit']['time']:.1f}s)")
        else:
            _safe_echo(f"\n✗ Unit tests FAILED ({results['unit']['time']:.1f}s)", fg="red")
            if fail_fast:
                click.echo("\nStopping due to --fail-fast")
                raise SystemExit(1)

        click.echo("")

        # ─────────────────────────────────────────────────────────────
        # Phase 2: Start Test Server
        # ─────────────────────────────────────────────────────────────
        click.secho("─" * 60, fg="blue")
        click.secho("  PHASE 2: Starting Test Server", fg="blue", bold=True)
        click.secho("─" * 60, fg="blue")
        click.echo("")

        # Set environment for viewer
        env = os.environ.copy()
        env["APOTHECARY_VIEWER_PATH"] = ""  # Disable viewer for faster startup

        server_cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "apothecary.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]

        # DEVNULL, not PIPE: nothing here ever reads server_proc.stdout/stderr,
        # and an unread PIPE deadlocks once its OS buffer fills -- confirmed by
        # direct reproduction, the server stops responding after ~68 requests'
        # worth of uvicorn access-log lines once background STL generation
        # lets the E2E phase actually run long enough to hit it.
        server_proc = subprocess.Popen(
            server_cmd,
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for server to be ready
        base_url = f"http://127.0.0.1:{port}"
        for _attempt in range(30):
            try:
                urllib.request.urlopen(f"{base_url}/health", timeout=1)
                _safe_echo(f"✓ Server ready at {base_url}")
                break
            except Exception:
                time.sleep(0.5)
        else:
            _safe_echo("✗ Server failed to start", fg="red")
            raise SystemExit(1)

        click.echo("")

        # ─────────────────────────────────────────────────────────────
        # Phase 3: E2E Tests
        # ─────────────────────────────────────────────────────────────
        click.secho("─" * 60, fg="blue")
        click.secho("  PHASE 3: E2E Tests", fg="blue", bold=True)
        click.secho("─" * 60, fg="blue")
        click.echo("")

        e2e_start = time.time()
        e2e_cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/e2e/",
            "-v",
            "--tb=short",
            f"--base-url={base_url}",
        ]
        if fail_fast:
            e2e_cmd.append("-x")
        if headed:
            e2e_cmd.append("--headed")

        e2e_result = subprocess.run(e2e_cmd, cwd=ROOT, capture_output=True, text=True)
        results["e2e"]["time"] = time.time() - e2e_start

        # Parse E2E results
        for line in e2e_result.stdout.split("\n"):
            if "passed" in line or "failed" in line or "PASSED" in line or "FAILED" in line:
                click.echo(line)
            if " passed" in line:
                match = re.search(r"(\d+) passed", line)
                if match:
                    results["e2e"]["passed"] = int(match.group(1))
                match = re.search(r"(\d+) failed", line)
                if match:
                    results["e2e"]["failed"] = int(match.group(1))

        e2e_ok = e2e_result.returncode == 0

        if e2e_ok:
            _safe_echo(f"\n✓ E2E tests PASSED ({results['e2e']['time']:.1f}s)")
        else:
            _safe_echo(f"\n✗ E2E tests FAILED ({results['e2e']['time']:.1f}s)", fg="red")
            click.echo(e2e_result.stderr[-500:] if e2e_result.stderr else "")

    finally:
        # Cleanup server
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()

    # ─────────────────────────────────────────────────────────────
    # Aggregate Summary
    # ─────────────────────────────────────────────────────────────
    total_time = time.time() - overall_start
    total_passed = results["unit"]["passed"] + results["e2e"]["passed"]
    total_failed = results["unit"]["failed"] + results["e2e"]["failed"]

    click.echo("")
    click.secho("=" * 60, fg="cyan", bold=True)
    click.secho("  AGGREGATE TEST SUMMARY", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan", bold=True)
    click.echo("")
    click.echo(f"  {'Test Suite':<15} {'Passed':>10} {'Failed':>10} {'Time':>10}")
    click.echo(f"  {'-'*15} {'-'*10} {'-'*10} {'-'*10}")
    click.echo(
        f"  {'Unit':<15} {results['unit']['passed']:>10} {results['unit']['failed']:>10} {results['unit']['time']:>9.1f}s"
    )
    click.echo(
        f"  {'E2E':<15} {results['e2e']['passed']:>10} {results['e2e']['failed']:>10} {results['e2e']['time']:>9.1f}s"
    )
    click.echo(f"  {'-'*15} {'-'*10} {'-'*10} {'-'*10}")
    click.echo(f"  {'TOTAL':<15} {total_passed:>10} {total_failed:>10} {total_time:>9.1f}s")
    click.echo("")

    if total_failed == 0:
        _safe_echo(f"  ✓ ALL {total_passed} TESTS PASSED", fg="green", bold=True)
        click.echo("")
        return 0
    else:
        _safe_echo(f"  ✗ {total_failed} TEST(S) FAILED", fg="red", bold=True)
        click.echo("")
        return 1
