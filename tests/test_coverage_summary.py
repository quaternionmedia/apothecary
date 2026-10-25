"""What a run of the suite covered, read for a pull request (apothecary/cli/coverage_summary.py):
the package's statements, and those a change adds or changes."""

import os

import coverage
from click.testing import CliRunner

from apothecary.cli import cli, coverage_summary, testing

DIFF = """\
diff --git a/apothecary/new.py b/apothecary/new.py
new file mode 100644
--- /dev/null
+++ b/apothecary/new.py
@@ -0,0 +1,3 @@
+a = 1
+b = 2
+c = 3
diff --git a/apothecary/old.py b/apothecary/old.py
--- a/apothecary/old.py
+++ b/apothecary/old.py
@@ -10 +10 @@ def f():
-    x = 1
+    x = 2
@@ -20,2 +19,0 @@ def g():
-    gone = 1
-    gone = 2
@@ -30,0 +29,2 @@ def h():
+    y = 1
+    z = 2
diff --git a/apothecary/removed.py b/apothecary/removed.py
deleted file mode 100644
--- a/apothecary/removed.py
+++ /dev/null
@@ -1,2 +0,0 @@
-a
-b
"""


def test_a_change_is_the_lines_each_hunk_adds_numbered_as_the_new_file_has_them():
    """A hunk that only removes lines adds none, and a removed file has no lines."""
    assert coverage_summary.changed_lines(DIFF) == {
        "apothecary/new.py": {1, 2, 3},
        "apothecary/old.py": {10, 29, 30},
    }


def test_line_numbers_are_said_as_runs():
    assert coverage_summary.ranges([9, 3, 4, 5, 12, 13]) == "3-5, 9, 12-13"
    assert coverage_summary.ranges([]) == ""


MODULE = """\
def run():
    return 1


def never():
    return 2
"""


def _a_run(tmp_path):
    """A project of one module whose import and run() ran: every statement but never()'s
    return. The data is written as a run writes it, without measuring this test."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text(MODULE)
    (tmp_path / "pyproject.toml").write_text('[tool.coverage.run]\nsource = ["pkg"]\n')
    data = coverage.CoverageData(basename=str(tmp_path / ".coverage"))
    data.add_lines({str(tmp_path / "pkg" / "mod.py"): [1, 2, 5], str(tmp_path / "pkg" / "__init__.py"): []})
    data.write()
    return tmp_path / ".coverage"


def test_a_change_is_measured_by_the_statements_on_its_lines_that_ran(tmp_path):
    data = _a_run(tmp_path)
    # Line 3 is blank: not a statement, so not counted either way.
    measured = coverage_summary.measure({"pkg/mod.py": {2, 3, 6}}, data=data, root=tmp_path)
    assert measured.total == 75.0
    assert (measured.changed, measured.run, measured.missed) == (2, 1, {"pkg/mod.py": [6]})
    assert measured.share() == "50%"


def test_what_is_not_python_or_is_omitted_is_not_counted(tmp_path):
    data = _a_run(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.coverage.run]\nsource = ["pkg"]\nomit = ["pkg/mod.py"]\n'
    )
    measured = coverage_summary.measure({"pkg/mod.py": {6}, "pkg/notes.md": {1}}, data=data, root=tmp_path)
    assert (measured.changed, measured.run) == (0, 0)
    assert measured.share() == "--"


def test_it_is_said_for_the_terminal_and_for_a_pull_requests_body():
    measured = coverage_summary.Measured(
        total=88.04, changed=8, run=6, missed={"apothecary/api.py": [120, 121, 140]}
    )
    said = coverage_summary.said(measured, "origin/main")
    assert "88.0% of the package's statements ran" in said
    assert "since origin/main: 6 of its 8 statements ran (75%)" in said
    assert "not run: apothecary/api.py 120-121, 140" in said
    markdown = coverage_summary.markdown(measured, "origin/main")
    assert markdown.startswith("Coverage (`apothecary test all --coverage`): the package's statements, 88.0%;")
    assert "6 of 8 (75%)" in markdown and "Not run: `apothecary/api.py` 120-121, 140." in markdown


def test_test_all_with_coverage_measures_both_parts_into_one_and_says_it(monkeypatch):
    ran, envs = [], []
    monkeypatch.setattr(testing, "_pytest", lambda argv, env=None: ran.append(argv) or envs.append(env) or 0)
    monkeypatch.setattr(testing, "_covered", lambda since, markdown=False: f"covered since {since}")
    result = CliRunner().invoke(cli, ["test", "all", "--coverage", "--since", "origin/x"])
    assert result.exit_code == 0
    unit, browser = ran
    assert unit[-2:] == ["--cov", "--cov-report="]
    assert browser[-3:] == ["--cov", "--cov-report=", "--cov-append"]
    assert "covered since origin/x" in result.output
    # Both measured with the environment coverage_env gives (sys.monitoring from 3.12).
    assert envs == [testing.coverage_env()] * 2
    # Without --coverage, nothing is measured.
    ran.clear()
    envs.clear()
    CliRunner().invoke(cli, ["test", "all"])
    assert not any("--cov" in argv for argv in ran) and envs == [None, None]


def test_a_measured_run_uses_sys_monitoring_where_python_has_it(monkeypatch):
    monkeypatch.setattr(testing.sys, "version_info", (3, 12, 0))
    assert testing.coverage_env()["COVERAGE_CORE"] == "sysmon"
    monkeypatch.setattr(testing.sys, "version_info", (3, 11, 9))
    assert testing.coverage_env() is None


def test_test_coverage_with_no_run_names_the_command_that_measures(monkeypatch, tmp_path):
    monkeypatch.setattr(coverage_summary, "DATA", tmp_path / ".coverage")
    monkeypatch.setattr(coverage_summary, "change_against", lambda since: {})
    result = CliRunner().invoke(cli, ["test", "coverage"])
    assert result.exit_code == 1
    assert "`apothecary test all --coverage` writes it" in result.output


def test_what_the_settings_omit_stays_out_of_the_total_though_a_process_measured_it(tmp_path):
    """A process that started somewhere else measured an omitted file (a pattern relative
    to the checkout matches nothing there); the total leaves it out still."""
    data = _a_run(tmp_path)
    (tmp_path / "pkg" / "skip").mkdir()
    (tmp_path / "pkg" / "skip" / "__init__.py").write_text("x = 1\ny = 2\n")
    more = coverage.CoverageData(basename=str(data))
    more.read()
    more.add_lines({str(tmp_path / "pkg" / "skip" / "__init__.py"): [1, 2]})
    more.write()
    (tmp_path / "pyproject.toml").write_text(
        '[tool.coverage.run]\nsource = ["pkg"]\nomit = ["*/pkg/skip/*"]\n'
    )
    assert coverage_summary.measure({}, data=data, root=tmp_path).total == 75.0


def test_a_changed_file_written_after_the_run_is_named(tmp_path):
    data = _a_run(tmp_path)
    module = tmp_path / "pkg" / "mod.py"
    later = data.stat().st_mtime + 60
    os.utime(module, (later, later))
    measured = coverage_summary.measure({"pkg/mod.py": {2}}, data=data, root=tmp_path)
    assert measured.newer == ["pkg/mod.py"]
    assert "changed since the run" in coverage_summary.said(measured, "origin/main")
    assert "Changed since the run: `pkg/mod.py`." in coverage_summary.markdown(measured, "origin/main")
