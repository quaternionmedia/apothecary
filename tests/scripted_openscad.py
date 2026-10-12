"""A scripted OpenSCAD for the part-editing tests: a Python script standing in for
the executable, answering as a development snapshot (which lists a SCAD's
parameters, ``--export-format=param``) or as 2021.01 (which cannot) would.

It reads the SCAD it is given, so a draft is answered by what is in it:

- ``name = 12;`` (``// [lo:hi]`` or ``// [lo:step:hi]`` after it), ``= true``,
  ``= "text"`` and ``= [1, 2]`` before the first module or function are the
  parameters it lists;
- a line holding ``SYNTAX ERROR`` is a parser error there; ``assert(false)`` a
  failed assertion, and ``assert(name < N)`` one when ``name`` (as ``-D`` sets
  it, else as the text assigns it) is N or more; ``WARN`` a warning -- each said by file and line, as
  OpenSCAD says them; ``SLEEP`` makes a render take half a minute;
- a render with a failed assertion exits 1 and writes nothing, as 2021.01
  does, or, as a snapshot does, writes its geometry and exits 0 (``partial``);
- the CSG export (``--export-format=csg``) prints the text without its
  comments or echoes, and the ``-D`` definitions: what it compiled; an
  ``echo("__apothecary_value__", "name", name);`` line has the name's value
  (its expression read as Python arithmetic) echoed as OpenSCAD echoes it;
- a render writes an ASCII STL whose name holds the sha256 of the text it
  rendered and the ``-D`` definitions, so a test can tell which text was drawn
  (``stl_names``); its help names no ``binstl``, so the cache turns it binary.

Every call is logged to ``<script>.calls``, one JSON object a line: its
arguments, the folder it ran in, the SCAD it was given, that file's text and
whether it was there.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from typing import List, Optional

SCRIPT = r"""
import hashlib, json, os, re, sys, time
here = os.path.abspath(__file__)
args = sys.argv[1:]
VERSION = {version!r}
LISTS = {lists!r}
PARTIAL = {partial!r}

def log(**kw):
    with open(here + ".calls", "a") as f:
        f.write(json.dumps(kw) + "\n")

if args[:1] == ["--version"]:
    print("OpenSCAD version " + VERSION, file=sys.stderr)
    sys.exit(0)
if args[:1] == ["--help"]:
    formats = "stl, off, 3mf, csg, echo, ast, term" + (", param, pov" if LISTS else "")
    print("  -o [ --o ] arg   output specified file; the type: " + formats + ". Use '-' for stdout.", file=sys.stderr)
    print("  -p [ --p ] arg   customizer parameter file", file=sys.stderr)
    sys.exit(0)

scad = args[-1]
there = os.path.exists(scad)
text = open(scad, encoding="utf-8").read() if there else ""
defs = [args[i + 1] for i, a in enumerate(args) if a == "-D"]
fmt = next((a.split("=", 1)[1] for a in args if a.startswith("--export-format=")), None)
out = args[args.index("-o") + 1] if "-o" in args else None
log(args=args, cwd=os.getcwd(), scad=scad, there=there, text=text, format=fmt)
name = os.path.basename(scad)

def value_of(key):
    # A number as -D sets it, else as the text assigns it; None for neither.
    for d in defs:
        if d.split("=", 1)[0] == key:
            return float(d.split("=", 1)[1])
    found = re.search(r"^" + re.escape(key) + r"\s*=\s*([-\d.]+)\s*;", text, re.M)
    return float(found.group(1)) if found else None

said = []
for n, line in enumerate(text.splitlines(), 1):
    if "SYNTAX ERROR" in line:
        said.append("ERROR: Parser error: syntax error in file %s, line %d" % (name, n))
    if "assert(false)" in line:
        said.append("ERROR: Assertion 'false' failed in file %s, line %d" % (name, n))
        said.append("TRACE: called by 'assert' in file %s, line %d" % (name, n))
    below = re.search(r"assert\((\$?\w+) < ([-\d.]+)\)", line)
    if below and (value_of(below.group(1)) or 0) >= float(below.group(2)):
        said.append("ERROR: Assertion '(%s < %s)' failed in file %s, line %d"
                    % (below.group(1), below.group(2), name, n))
        said.append("TRACE: called by 'assert' in file %s, line %d" % (name, n))
    if "WARN" in line:
        said.append('WARNING: Ignoring unknown variable "w" in file %s, line %d' % (name, n))
unreadable = any("Parser error" in s for s in said)
failed = unreadable or any("Assertion" in s for s in said)

def listed():
    found = []
    for line in text.splitlines():
        if re.match(r"\s*(module|function)\b", line):
            break
        m = re.match(r'^(\$?\w+)\s*=\s*([^;]+);\s*(?://\s*\[([^\]]*)\])?', line)
        if not m:
            continue
        key, value, note = m.group(1), m.group(2).strip(), m.group(3)
        entry = {{"name": key, "group": "Parameters"}}
        if value in ("true", "false"):
            entry.update(type="boolean", initial=value == "true")
        elif value.startswith('"'):
            entry.update(type="string", initial=value.strip('"'))
        elif value.startswith("["):
            entry.update(type="number", initial=[float(v) for v in value.strip("[]").split(",")])
        else:
            try:
                entry.update(type="number", initial=float(value), step=1.0)
            except ValueError:
                continue
        if note and entry["type"] == "number":
            bits = [float(b) for b in note.split(":")]
            if len(bits) == 2:
                entry.update(min=bits[0], max=bits[1])
            elif len(bits) == 3:
                entry.update(min=bits[0], step=bits[1], max=bits[2])
        found.append(entry)
    return found

if fmt == "param":
    if not LISTS:
        print("Unknown --export-format option 'param'.  Use -h to list available options.", file=sys.stderr)
        sys.exit(1)
    for s in said:
        print(s, file=sys.stderr)
    if unreadable:
        print("Can't parse file '%s'!" % name, file=sys.stderr)
        sys.exit(1)
    title = os.path.splitext(name)[0]
    found = listed()
    print(json.dumps({{"parameters": found, "title": title}} if found else {{"title": title}}))
    sys.exit(0)
if fmt == "echo":
    for s in said:
        print(s)
    sys.exit(1 if unreadable else 0)
def shown(value):
    # A value as OpenSCAD's echo prints it.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str):
        return '"' + value + '"'
    if isinstance(value, list):
        return "[" + ", ".join(shown(v) for v in value) + "]"
    return repr(value)

def evaluated(name):
    # A top-level assignment's value: its expression, with the numbers assigned
    # before it (and -D's), as Python reads arithmetic.
    known = {{}}
    for m in re.finditer(r"^(\$?\w+)\s*=\s*([^;]+);", text, re.M):
        key, expr = m.group(1), m.group(2).strip()
        try:
            known[key] = value_of(key) if any(d.split("=", 1)[0] == key for d in defs) else eval(
                expr.replace("true", "True").replace("false", "False"), {{"__builtins__": {{}}}}, dict(known)
            )
        except Exception:
            known[key] = None
    return known.get(name)

if fmt == "csg":
    # What it compiled: the text without its comments or echoes, and the -D values;
    # each echo of a value printed as OpenSCAD prints one.
    for s in said:
        print(s, file=sys.stderr)
    if unreadable:
        sys.exit(1)
    for m in re.finditer(r'^echo\("(__apothecary_value__)", "(\$?\w+)", \$?\w+\);$', text, re.M):
        print('ECHO: "%s", "%s", %s' % (m.group(1), m.group(2), shown(evaluated(m.group(2)))), file=sys.stderr)
    if not failed:
        bare = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
        lines = [l.strip() for l in bare.splitlines() if l.strip()]
        print("\n".join(l for l in lines if not l.startswith("echo(")))
        print("defined: " + json.dumps(defs))
    sys.exit(0)

for s in said:
    print(s, file=sys.stderr)
if "SLEEP" in text:
    time.sleep(30)
if failed and not PARTIAL:
    print("Current top level object is empty.", file=sys.stderr)
    sys.exit(1)
for a in args:
    if a.startswith("--summary-file="):
        with open(a.split("=", 1)[1], "w") as f:
            f.write('{{"geometry":{{"bounding_box":{{"min":[0,0,0],"max":[10,20,30],"size":[10,20,30]}}}}}}')
digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
with open(out, "w") as f:
    f.write("solid %s %s\nfacet normal 0 0 0\nouter loop\nvertex 0 0 0\nvertex 4 0 0\n"
            "vertex 0 5 6\nendloop\nendfacet\nendsolid\n" % (digest, json.dumps(defs)))
"""


def scripted_openscad(
    path: Path, version: str = "2026.09.27", lists: bool = True, partial: Optional[bool] = None
) -> Path:
    """An executable at ``path`` answering as OpenSCAD ``version``; ``lists``:
    whether it exports a SCAD's parameters, as a snapshot does and 2021.01 not;
    ``partial``: whether a render with a failed assertion still writes its
    geometry and exits 0, as a snapshot does (by default, when it lists)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = SCRIPT.format(
        version=version, lists=lists, partial=lists if partial is None else partial
    )
    path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def calls(executable: Path) -> List[dict]:
    """Every call the scripted OpenSCAD answered, in order."""
    log = Path(f"{executable}.calls")
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def renders(executable: Path) -> List[dict]:
    """The calls that rendered (not a check, a listing, --version or --help)."""
    return [c for c in calls(executable) if c["format"] is None]


def stl_names(data: bytes) -> str:
    """The name of an STL the scripted OpenSCAD wrote: the digest of the text it
    rendered, then its -D definitions. The variant cache keeps STLs binary, the
    name in the header's eighty bytes (the digest first, so it is never cut)."""
    if len(data) >= 84 and 84 + int.from_bytes(data[80:84], "little") * 50 == len(data):
        return data[:80].rstrip(b"\0").decode("ascii", errors="replace").strip()
    first = data.decode("utf-8").splitlines()[0]
    return first[len("solid ") :] if first.startswith("solid ") else first
