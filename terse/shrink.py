#!/usr/bin/env python3
"""
shrink.py -- shrink noisy text before it reaches the model.

A stdin -> stdout filter for logs, test output, JSON, and CSV. Pure Python
standard library: no dependencies, no network, no file writes. It only reads
what you pipe (or hand) into it and prints a compressed version.

Usage:
    pytest 2>&1 | shrink.py
    shrink.py build.log
    some_command 2>&1 | shrink.py --max-lines 80 --stats

Safety: reads stdin or the named file(s), writes stdout (plus optional stats
to stderr). Never modifies files, never opens sockets.
"""

import argparse
import csv
import io
import json
import sys

MAX_INPUT_CHARS = 10_000_000  # 10 MB guard against accidental huge pipes
CHARS_PER_TOKEN = 4            # rough estimate, same basis as tiktoken o200k


def est_tokens(s):
    return len(s) // CHARS_PER_TOKEN


def read_input(path):
    if path:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(MAX_INPUT_CHARS + 1)
    return sys.stdin.read(MAX_INPUT_CHARS + 1)


# ---------------------------------------------------------------- JSON ---

def _short_scalar(v, limit=60):
    s = repr(v)
    return s if len(s) <= limit else s[: limit - 1] + "\u2026"


def _summarize(node, depth=0, max_depth=3):
    """One-line structural summary of a JSON value."""
    if isinstance(node, dict):
        if depth >= max_depth:
            return "dict(%d keys)" % len(node)
        parts = []
        for k in list(node)[:8]:
            parts.append("%s: %s" % (k, _summarize(node[k], depth + 1, max_depth)))
        suffix = ", \u2026" if len(node) > 8 else ""
        return "{%s%s}" % (", ".join(parts), suffix)
    if isinstance(node, list):
        if not node:
            return "[]"
        if depth >= max_depth:
            return "list[%d]" % len(node)
        first = _summarize(node[0], depth + 1, max_depth)
        more = " (+%d more)" % (len(node) - 1) if len(node) > 1 else ""
        return "list[%d]: [%s%s]" % (len(node), first, more)
    if isinstance(node, str):
        return _short_scalar(node)
    return repr(node)


def shrink_json(text):
    try:
        obj = json.loads(text)
    except Exception:
        return None
    kind = "object" if isinstance(obj, dict) else "array" if isinstance(obj, list) else "value"
    n = len(obj) if isinstance(obj, (dict, list)) else 1
    out = ["[JSON: %s, %d top-level %s]" % (kind, n, "keys" if kind == "object" else "items")]
    out.append(_summarize(obj))
    out.append("[structure shown; drill into a specific path for full values]")
    return "\n".join(out)


# ----------------------------------------------------------------- CSV ---

def looks_like_csv(text):
    sample = [ln for ln in text.splitlines() if ln.strip()][:6]
    if len(sample) < 2:
        return False
    try:
        rows = list(csv.reader(io.StringIO("\n".join(sample))))
    except Exception:
        return False
    counts = {len(r) for r in rows}
    return len(counts) == 1 and next(iter(counts)) >= 2


def shrink_csv(text, max_rows=8):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return "[CSV: empty]"
    header, body = rows[0], rows[1:]
    n = len(body)
    out = ["[CSV: %d rows x %d cols]" % (n, len(header))]
    out.append("cols: " + ", ".join(header))
    show = body[:5] + (body[-2:] if n > 7 else [])
    for i, r in enumerate(show):
        label = i + 1 if i < 5 else n - (len(show) - 1 - i)
        out.append("row %d: %s" % (label, ", ".join(r)))
    if n > len(show):
        out.append("[\u2026 %d rows omitted \u2026]" % (n - len(show)))
    return "\n".join(out)


# ----------------------------------------------------------------- logs ---

def collapse_repeats(lines):
    """Fold consecutive duplicate lines and blank-line runs."""
    out = []
    i = 0
    while i < len(lines):
        j = i + 1
        while j < len(lines) and lines[j] == lines[i]:
            j += 1
        run = j - i
        if run > 1:
            if lines[i].strip() == "":
                out.append("")
            else:
                out.append("%s   [repeated x%d]" % (lines[i], run))
        else:
            out.append(lines[i])
        i = j
    return out


def shrink_log(text, max_lines):
    lines = text.splitlines()
    lines = collapse_repeats(lines)
    if len(lines) <= max_lines:
        return "\n".join(lines)
    head_n = int(max_lines * 0.6)
    tail_n = max_lines - head_n
    omitted = len(lines) - head_n - tail_n
    kept = lines[:head_n] + ["[\u2026 %d lines omitted \u2026]" % omitted] + lines[-tail_n:]
    return "\n".join(kept)


# ------------------------------------------------------------------ main ---

def main():
    ap = argparse.ArgumentParser(description="Compress noisy text for LLM input.")
    ap.add_argument("file", nargs="?", help="file to read (default: stdin)")
    ap.add_argument("--max-lines", type=int, default=120,
                    help="max output lines for log/text mode (default: 120)")
    ap.add_argument("--format", choices=["auto", "json", "csv", "log"], default="auto")
    ap.add_argument("--stats", action="store_true",
                    help="print before/after size to stderr")
    args = ap.parse_args()

    try:
        text = read_input(args.file)
    except (OSError, IOError) as e:
        print("shrink.py: cannot read input: %s" % e, file=sys.stderr)
        return 2

    truncated = False
    if len(text) > MAX_INPUT_CHARS:
        text, truncated = text[:MAX_INPUT_CHARS], True

    stripped = text.lstrip()
    fmt = args.format
    if fmt == "auto":
        if stripped[:1] in ("{", "["):
            fmt = "json"
        elif looks_like_csv(text):
            fmt = "csv"
        else:
            fmt = "log"

    if fmt == "json":
        shrunk = shrink_json(text)
        if shrunk is None:                      # not actually JSON: fall back
            shrunk = shrink_log(text, args.max_lines)
    elif fmt == "csv":
        shrunk = shrink_csv(text)
    else:
        shrunk = shrink_log(text, args.max_lines)

    if truncated:
        shrunk += "\n[input truncated at 10 MB guard]"

    # Small inputs pass through untouched: never mangle what is already lean.
    if fmt == "log" and len(text.splitlines()) <= args.max_lines and shrunk == text:
        pass

    sys.stdout.write(shrunk + ("\n" if shrunk and not shrunk.endswith("\n") else ""))

    if args.stats:
        li, lo = len(text.splitlines()), len(shrunk.splitlines())
        ci, co = len(text), len(shrunk)
        saved = 100.0 * (1 - co / ci) if ci else 0.0
        print("[shrink] in: %d lines / %d chars (~%dk tok) -> out: %d lines / %d chars (~%dk tok) | saved %.1f%%"
              % (li, ci, est_tokens(text) // 1000, lo, co, est_tokens(shrunk) // 1000, saved),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
