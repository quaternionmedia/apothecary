"""The project's documentation, served by the same server as the viewer.

``/docs`` is ``docs/`` and ``/walkthrough`` is ``walkthrough/``: a Markdown
file is rendered to a page, anything else (a screenshot, a GIF, a
recording, a G-code file) is served as it is, and a relative link between
two files works the way it does on disk, because the URL is the path.

The renderer is a small one written here for the Markdown these docs use
-- headings, paragraphs, lists (nested, with task boxes), fenced code,
tables, blockquotes, rules, links, images, emphasis, inline code -- rather
than a dependency: a documentation page is not a runtime path worth a
component audit, and nothing is fetched while a person is using the tool.
Raw HTML in a page is shown as text, not run.

``apothecary serve`` regenerates the generated walkthroughs in the
background when it starts (``apothecary docs generate``: the doc-workflow
browser tests against a scripted server), and the index says whether that
run is still going or how it ended; ``--no-refresh-docs`` skips it.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .projects.parts.skeleton import ROOT

DOCS_ROOT = ROOT / "docs"
WALKTHROUGH_ROOT = ROOT / "walkthrough"
GENERATED_ROOT = DOCS_ROOT / "generated"
REFRESH_STATE = GENERATED_ROOT / ".refresh.json"  # written by `apothecary docs generate`
SERVED = {"/docs": DOCS_ROOT, "/walkthrough": WALKTHROUGH_ROOT}

router = APIRouter()


# --- the refresh record -------------------------------------------------------------


def note_refresh(**fields) -> None:
    """Merge ``fields`` into the refresh record (started, finished, ok, error, log)."""
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    current = refresh_state()
    current.update(fields)
    REFRESH_STATE.write_text(json.dumps(current, indent=2), encoding="utf-8")


def refresh_state() -> dict:
    try:
        return json.loads(REFRESH_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# --- a small Markdown renderer ----------------------------------------------------------

INLINE_CODE = re.compile(r"`([^`]+)`")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITALIC = re.compile(
    r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])"
)
STRIKE = re.compile(r"~~(.+?)~~")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RULE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
TASK = re.compile(r"^\[([ xX])\]\s+(.*)$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
FENCE = re.compile(r"^(`{3,}|~{3,})\s*(\w[\w+-]*)?\s*$")
COMMENT = re.compile(r"<!--.*?-->", re.S)


def slug(text: str) -> str:
    """A heading's anchor, the way GitHub makes one."""
    plain = re.sub(r"[`*_~]", "", text)
    plain = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", plain)
    plain = re.sub(r"[^\w\s-]", "", plain.lower())
    return re.sub(r"\s+", "-", plain.strip())


def inline(text: str) -> str:
    """Inline Markdown to HTML, with everything else escaped."""
    out: List[str] = []
    pos = 0
    for m in INLINE_CODE.finditer(text):
        out.append(_inline_no_code(text[pos : m.start()]))
        out.append(f"<code>{html.escape(m.group(1))}</code>")
        pos = m.end()
    out.append(_inline_no_code(text[pos:]))
    return "".join(out)


def _local(url: str) -> bool:
    """A URL a page here may load: relative, or this server's own."""
    return not re.match(r"^(?:[a-z][a-z0-9+.-]*:)?//", url, re.I)


def _link(text: str, url: str) -> str:
    """A link a person may click: relative, this server's, http(s) or mailto. A
    `javascript:` or other scheme is not a link; it is shown as the text it was."""
    scheme = re.match(r"^([a-z][a-z0-9+.-]*):", url, re.I)
    if scheme and scheme.group(1).lower() not in ("http", "https", "mailto"):
        return f"{text} ({html.escape(url, quote=False)})"
    return f'<a href="{html.escape(url, quote=True)}">{text}</a>'


def _image(alt: str, url: str) -> str:
    # A picture from elsewhere is not fetched (the page's policy would refuse
    # it anyway); it is named, so a reader knows what the page meant.
    if not _local(url):
        return f"[picture elsewhere: {html.escape(alt or url, quote=False)}]"
    return '<img src="{}" alt="{}">'.format(
        html.escape(url, quote=True), html.escape(alt, quote=True)
    )


def _inline_no_code(text: str) -> str:
    s = html.escape(text, quote=False)
    s = IMAGE.sub(lambda m: _image(m.group(1), m.group(2)), s)
    s = LINK.sub(lambda m: _link(m.group(1), m.group(2)), s)
    s = AUTOLINK.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', s)
    s = BOLD.sub(r"<strong>\1</strong>", s)
    s = STRIKE.sub(r"<del>\1</del>", s)
    s = ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", s)
    s = re.sub(r"  \n", "<br>\n", s)
    return s


def render_markdown(text: str) -> Tuple[str, Optional[str]]:
    """The page body for ``text`` and its title (the first heading), if any."""
    lines = COMMENT.sub("", text).splitlines()
    out: List[str] = []
    title: Optional[str] = None
    i = 0
    n = len(lines)
    para: List[str] = []

    def flush_para() -> None:
        if para:
            out.append(f"<p>{inline(chr(10).join(s.lstrip() for s in para))}</p>")
            para.clear()

    while i < n:
        line = lines[i]
        fence = FENCE.match(line)
        if fence:
            flush_para()
            mark = fence.group(1)[0]
            lang = fence.group(2) or ""
            code: List[str] = []
            i += 1
            while i < n and not (
                lines[i].startswith(mark * 3) and lines[i].strip(mark).strip() == ""
            ):
                code.append(lines[i])
                i += 1
            i += 1
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(code))}</code></pre>")
            continue
        heading = HEADING.match(line)
        if heading:
            flush_para()
            level = len(heading.group(1))
            body = heading.group(2)
            if title is None and level == 1:
                title = re.sub(r"[`*_]", "", body)
            out.append(f'<h{level} id="{slug(body)}">{inline(body)}</h{level}>')
            i += 1
            continue
        if RULE.match(line):
            flush_para()
            out.append("<hr>")
            i += 1
            continue
        if line.startswith(">"):
            flush_para()
            quote: List[str] = []
            while i < n and lines[i].startswith(">"):
                quote.append(lines[i][1:].lstrip())
                i += 1
            body_html, _ = render_markdown("\n".join(quote))
            out.append(f"<blockquote>{body_html}</blockquote>")
            continue
        if "|" in line and i + 1 < n and TABLE_SEP.match(lines[i + 1]) and line.count("|") >= 1:
            flush_para()
            header = _cells(line)
            i += 2
            rows: List[List[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_cells(lines[i]))
                i += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in header)
            body_rows = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows
            )
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table>")
            continue
        if LIST_ITEM.match(line):
            flush_para()
            block: List[str] = []
            while i < n and (
                LIST_ITEM.match(lines[i])
                or (lines[i].startswith((" ", "\t")) and lines[i].strip())
                or (
                    lines[i].strip() == ""
                    and i + 1 < n
                    and (LIST_ITEM.match(lines[i + 1]) or lines[i + 1].startswith("  "))
                )
            ):
                block.append(lines[i])
                i += 1
            out.append(_render_list(block))
            continue
        if not line.strip():
            flush_para()
            i += 1
            continue
        para.append(line)
        i += 1
    flush_para()
    return "\n".join(out), title


def _cells(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def _render_list(block: List[str]) -> str:
    """A list block (possibly nested by indentation) to nested <ul>/<ol>."""
    items: List[Tuple[int, bool, List[str]]] = []  # (indent, ordered, lines of the item)
    for raw in block:
        m = LIST_ITEM.match(raw)
        if m:
            indent = len(m.group(1).expandtabs(4))
            items.append((indent, m.group(2)[0].isdigit(), [m.group(3)]))
        elif items:
            items[-1][2].append(raw.strip())
    out: List[str] = []
    start = 0
    while start < len(items):  # a list of one kind, then the next kind at the same indent
        rendered, start = _nest(items, start, len(items))
        out.append(rendered)
    return "".join(out)


def _nest(items, start, end, level_indent=None) -> Tuple[str, int]:
    if start >= end:
        return "", start
    indent = items[start][0] if level_indent is None else level_indent
    ordered = items[start][1]
    tag = "ol" if ordered else "ul"
    out = [f"<{tag}>"]
    i = start
    while i < end and items[i][0] >= indent:
        if items[i][0] == indent and items[i][1] != ordered:
            break  # a list of the other kind follows; the caller starts it
        if items[i][0] > indent:
            sub, i = _nest(items, i, end, items[i][0])
            out[-1] = (
                out[-1][: -len("</li>")] + sub + "</li>"
                if out[-1].endswith("</li>")
                else out[-1] + sub
            )
            continue
        text_lines = items[i][2]
        first = text_lines[0]
        task = TASK.match(first)
        rest = " ".join(text_lines[1:])
        body = (first if not task else task.group(2)) + (" " + rest if rest else "")
        box = ""
        if task:
            checked = " checked" if task.group(1).lower() == "x" else ""
            box = f'<input type="checkbox" disabled{checked}> '
        out.append(f"<li>{box}{inline(body)}</li>")
        i += 1
    out.append(f"</{tag}>")
    return "".join(out), i


# --- the pages ---------------------------------------------------------------------------

STYLE = """
:root { color-scheme: dark; }
body { margin: 0; background: #141614; color: #d8e6d8;
       font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
.bar { display: flex; gap: 1rem; align-items: center; padding: 0.5rem 1rem; background: #0f120f;
       border-bottom: 1px solid #2a332a; font-size: 0.85rem; position: sticky; top: 0; }
.bar a { color: #8fc78f; text-decoration: none; }
.bar .crumb { color: #8a9a8a; }
.bar .spacer { flex: 1; }
.bar .refresh { color: #8a9a8a; font-variant-numeric: tabular-nums; }
.bar .refresh.running { color: #e8b04a; }
.bar .refresh.failed { color: #ff8080; }
main { max-width: 58rem; margin: 0 auto; padding: 1.5rem 1.25rem 4rem; }
h1, h2, h3, h4 { line-height: 1.25; margin: 1.6em 0 0.5em; color: #eef5ee; }
h1 { font-size: 1.7rem; margin-top: 0.4em; }
h2 { font-size: 1.3rem; border-bottom: 1px solid #2a332a; padding-bottom: 0.25rem; }
h3 { font-size: 1.08rem; }
a { color: #6fb3e8; }
a:hover { text-decoration: underline; }
code { font: 0.88em ui-monospace, SFMono-Regular, Menlo, monospace; background: #1f261f;
       padding: 0.05em 0.3em; border-radius: 3px; }
pre { background: #0f120f; border: 1px solid #2a332a; border-radius: 6px; padding: 0.75rem 1rem;
      overflow: auto; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; margin: 1rem 0; font-size: 0.92em; display: block;
        overflow-x: auto; }
th, td { border: 1px solid #2a332a; padding: 0.35rem 0.6rem; vertical-align: top;
         text-align: left; }
th { background: #1a1f1a; }
img { max-width: 100%; height: auto; border-radius: 4px; border: 1px solid #2a332a; }
blockquote { margin: 1rem 0; padding: 0.2rem 1rem; border-left: 3px solid #4a6fa8; color: #b8c6b8; }
li { margin: 0.2rem 0; }
ul ul, ol ul, ul ol { margin-top: 0.2rem; }
hr { border: 0; border-top: 1px solid #2a332a; margin: 2rem 0; }
input[type=checkbox] { vertical-align: middle; }
"""

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{title} · Apothecary docs</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{style}</style></head>
<body>
<div class="bar"><a href="/viewer">🧪 Apothecary</a> <a href="/docs/README.md">docs</a>
<span class="crumb">{crumb}</span><span class="spacer"></span>
<span class="refresh {refresh_class}" title="{refresh_title}">{refresh_text}</span>
<a href="/openapi.json" title="The HTTP API, as OpenAPI">API</a></div>
<main>{body}</main>
</body></html>"""


def refresh_note() -> Tuple[str, str, str]:
    """Class, text and title for the bar: what the last `docs generate` did."""
    state = refresh_state()
    started, finished = state.get("started"), state.get("finished")

    def when(ts: Optional[str]) -> str:
        try:
            return datetime.fromisoformat(ts).astimezone().strftime("%H:%M:%S") if ts else "?"
        except ValueError:
            return str(ts)

    if started and not finished:
        return (
            "running",
            f"generated docs: refreshing since {when(started)}…",
            "apothecary docs generate is running; the walkthrough pages update when it finishes",
        )
    if finished and state.get("ok") is False:
        return (
            "failed",
            f"generated docs: refresh failed at {when(finished)}",
            state.get("error") or "see docs/generated/refresh.log",
        )
    if finished:
        return (
            "",
            f"generated docs: refreshed {when(finished)}",
            "the walkthrough pages were regenerated by the last apothecary docs generate",
        )
    return (
        "",
        "generated docs: not refreshed yet",
        "run apothecary docs generate, or restart apothecary serve",
    )


def _resolve(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise HTTPException(status_code=404, detail="not a documentation path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"no such page: {rel}")
    return target


def render_page(root: Path, prefix: str, rel: str) -> HTMLResponse:
    target = _resolve(root, rel)
    body, title = render_markdown(target.read_text(encoding="utf-8"))
    cls, text, tip = refresh_note()
    crumb = html.escape(f"{prefix.strip('/')}/{rel}")
    return HTMLResponse(
        PAGE.format(
            style=STYLE,
            title=html.escape(title or target.stem),
            crumb=crumb,
            body=body,
            refresh_class=cls,
            refresh_text=html.escape(text),
            refresh_title=html.escape(tip, quote=True),
        )
    )


@router.get("/docs")
async def docs_index():
    return RedirectResponse("/docs/README.md")


@router.get("/docs/")
async def docs_index_slash():
    return RedirectResponse("/docs/README.md")


@router.get("/docs/{rel:path}")
async def docs_page(rel: str):
    return _serve(DOCS_ROOT, "/docs", rel)


@router.get("/walkthrough/{rel:path}")
async def walkthrough_page(rel: str):
    return _serve(WALKTHROUGH_ROOT, "/walkthrough", rel)


def _serve(root: Path, prefix: str, rel: str):
    if rel.endswith("/") or not rel:
        rel = rel + "README.md"
    if rel.lower().endswith((".md", ".markdown")):
        return render_page(root, prefix, rel)
    target = _resolve(root, rel)
    media = {".gcode": "text/plain; charset=utf-8", ".webm": "video/webm", ".gif": "image/gif"}
    return FileResponse(target, media_type=media.get(target.suffix.lower()))


def pages() -> List[str]:
    """Every Markdown page under the two roots, as its URL path."""
    found: List[str] = []
    for prefix, root in SERVED.items():
        if root.is_dir():
            for p in sorted(root.rglob("*.md")):
                found.append(f"{prefix}/{p.relative_to(root).as_posix()}")
    return found


def written_at() -> Optional[str]:
    """When the generated docs were last written (their newest page), ISO, or None."""
    newest = 0.0
    if GENERATED_ROOT.is_dir():
        for p in GENERATED_ROOT.rglob("*.md"):
            newest = max(newest, p.stat().st_mtime)
    return datetime.fromtimestamp(newest, timezone.utc).isoformat() if newest else None
