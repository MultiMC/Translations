#!/usr/bin/env python3
"""Validate MultiMC .po translations and optionally write sanitized copies.

    validate_po.py [--fix OUTDIR] FILE.po...

Each file is checked with `msgfmt -c` (newline mismatches between msgid and msgstr,
missing/extra %1 style placeholders, duplicates...) and for the X-Qt-Contexts header
that lconvert needs to keep message contexts.

Without --fix: report problems, exit 1 if there are any. Used to check Crowdin PRs.

With --fix OUTDIR: write a copy of every usable file to OUTDIR with the broken entries
blanked (an empty msgstr falls back to the English text at runtime), report what was
dropped, and exit 0. A file that can't be repaired (no X-Qt-Contexts header, or still
failing after the broken entries are blanked) is reported, left out, and listed in
OUTDIR/skipped.txt, so release.py can keep that language at its previous release
instead of stopping the release of all the others.
"""

import os
import re
import subprocess
import sys

QT_CONTEXTS_HEADER = '"X-Qt-Contexts: true\\n"'
# Only errors matter: msgfmt still compiles a file that has warnings (e.g. the
# 'Last-Translator' header, which Crowdin never writes). Older gettext prints that
# one without the "warning: " prefix.
IGNORED = ("header field 'Last-Translator' missing in header",)
ERROR_RE = re.compile(r'^(?P<file>[^:]+):(?P<line>\d+): (?P<msg>.*)$')


def msgfmt_errors(path):
    """Return [(line, message)] reported by msgfmt -c, minus ignored noise."""
    proc = subprocess.run(
        ["msgfmt", "-c", "-o", os.devnull, path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
    )
    errors = []
    for raw in proc.stdout.splitlines():
        m = ERROR_RE.match(raw)
        if not m or m.group("msg") in IGNORED or m.group("msg").startswith("warning: "):
            continue
        errors.append((int(m.group("line")), m.group("msg")))
    unexplained = proc.returncode != 0 and not errors
    return errors, unexplained, proc.stdout


def split_entries(lines):
    """Group lines into entries: [(first_line_no, last_line_no)], 1-based, separated by blank lines."""
    entries, start = [], None
    for i, line in enumerate(lines, 1):
        if line.strip():
            if start is None:
                start = i
        elif start is not None:
            entries.append((start, i - 1))
            start = None
    if start is not None:
        entries.append((start, len(lines)))
    return entries


def describe(lines, first, last):
    """Short 'context | msgid' label for a report line."""
    block = "".join(lines[first - 1:last])
    ctx = re.search(r'^msgctxt "(.*)"', block, re.M)
    mid = re.search(r'^msgid "(.*)"((?:\n".*")*)', block, re.M)
    text = ""
    if mid:
        text = mid.group(1) + "".join(re.findall(r'"(.*)"', mid.group(2)))
    return "%s | %s" % (ctx.group(1) if ctx else "", text[:70])


def blank_entry(lines, first, last):
    """Replace every msgstr / msgstr[n] (and its continuation lines) in the entry with ""."""
    out, i = [], first - 1
    while i < last:
        line = lines[i]
        m = re.match(r'^(msgstr(\[\d+\])?) ', line)
        if m:
            out.append('%s ""\n' % m.group(1))
            i += 1
            while i < last and lines[i].startswith('"'):
                i += 1
            continue
        out.append(line)
        i += 1
    lines[first - 1:last] = out
    return len(out) - (last - first + 1)


def annotate(name, line, msg):
    """On GitHub Actions, also report the problem as an annotation on that line.
    Annotations show on the run summary and the PR diff without signing in to read logs."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    msg = msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::error file=%s,line=%d,title=Translation dropped::%s" % (name, line, msg))


def process(path, outdir):
    """Validate one file; with outdir, write a repaired copy. Returns (ok_to_ship, report lines)."""
    report = []
    name = os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    if QT_CONTEXTS_HEADER not in "".join(lines):
        report.append("%s: missing X-Qt-Contexts header, language skipped" % name)
        annotate(name, 1, "Missing X-Qt-Contexts header: the whole language keeps its previous release")
        return False, report

    errors, unexplained, raw = msgfmt_errors(path)
    if unexplained:
        report.append("%s: msgfmt failed without a usable error, language skipped:\n%s" % (name, raw))
        return False, report
    if not errors:
        if outdir:
            with open(os.path.join(outdir, name), "w", encoding="utf-8") as fh:
                fh.writelines(lines)
        return True, report

    entries = split_entries(lines)
    bad = []
    for line_no, msg in errors:
        for first, last in entries:
            if first <= line_no <= last:
                if first == entries[0][0]:
                    report.append("%s:%d: %s (in the header, can't drop)" % (name, line_no, msg))
                else:
                    report.append("%s:%d: %s -- %s" % (name, line_no, msg, describe(lines, first, last)))
                    annotate(name, line_no, "%s. This entry will be shown in English until fixed in Crowdin: %s"
                             % (msg, describe(lines, first, last)))
                    if (first, last) not in bad:
                        bad.append((first, last))
                break

    if not outdir:
        return False, report

    # Blank from the bottom up so earlier line numbers stay valid.
    for first, last in sorted(bad, reverse=True):
        blank_entry(lines, first, last)
    target = os.path.join(outdir, name)
    with open(target, "w", encoding="utf-8") as fh:
        fh.writelines(lines)

    remaining, unexplained, raw = msgfmt_errors(target)
    if remaining or unexplained:
        os.remove(target)
        report.append("%s: still invalid after dropping %d entries, language skipped:\n%s" % (name, len(bad), raw))
        return False, report
    report.append("%s: dropped %d broken entries (they fall back to English)" % (name, len(bad)))
    return True, report


def main(argv):
    outdir = None
    if len(argv) >= 2 and argv[0] == "--fix":
        outdir, argv = argv[1], argv[2:]
        os.makedirs(outdir, exist_ok=True)
    if not argv:
        print(__doc__)
        return 2

    problems = 0
    skipped = []
    for path in argv:
        ok, report = process(path, outdir)
        for line in report:
            print(line)
        if report:
            problems += 1
        if not ok:
            skipped.append(os.path.basename(path))
    if outdir:
        with open(os.path.join(outdir, "skipped.txt"), "w", encoding="utf-8") as fh:
            fh.writelines(name + "\n" for name in skipped)
    print("%d of %d files had problems" % (problems, len(argv)))
    return 1 if problems and not outdir else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
