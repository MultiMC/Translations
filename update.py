#!/usr/bin/env python3
"""Update template.pot, the strings to translate, from the Launcher source.

    update.py [--src DIR]

Runs in the translations image (multimc/toolchains/translations: Qt 5.15.2 lupdate and
lconvert), in this directory. The Launcher source is in src/ (or --src DIR, which must be
src/ for the locations in template.pot to stay the same). Prints how many strings were
added and removed. Committing and pushing the new template is up to the caller.

Extraction needs Qt 5.15's lupdate: Qt 5.6's stops parsing a file at the first C++11 raw
string literal R"(...)" and silently misses every string after it. lupdate only scans .h,
.cpp and .ui files, so a tr() call in any other kind of source file stops the update
instead of being missed.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
LCONVERT = os.environ.get("LCONVERT_BIN", "lconvert")
LUPDATE = os.environ.get("LUPDATE_BIN", "lupdate")

SCANNED = (".h", ".cpp", ".ui")
UNSCANNED = (".mm", ".m", ".c", ".hpp", ".cxx", ".cc")
TR_CALL = re.compile(r"\b(tr|translate|QT_TR_NOOP|QT_TRANSLATE_NOOP)\(")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--src", default=os.path.join(ROOT, "src"))
    args = parser.parse_args()
    src = os.path.abspath(args.src)
    template_pot = os.path.join(ROOT, "template.pot")
    template_ts = os.path.join(ROOT, "template.ts")
    file_list = os.path.join(ROOT, "base_lst_file")

    version = subprocess.run([LUPDATE, "-version"], stdout=subprocess.PIPE, text=True, check=True).stdout
    if "5.15." not in version:
        sys.exit("lupdate must be Qt 5.15.x, found: %s" % version.strip())

    print("Checking for translatable strings in files lupdate won't see...")
    sources = source_files(src)
    unscanned = [path for path in sources if path.endswith(UNSCANNED) and uses_tr(os.path.join(src, path))]
    if unscanned:
        sys.exit("These files use tr() but are not scanned (only %s are):\n%s"
                 % (", ".join(SCANNED), "\n".join(unscanned)))

    print("Writing lst file...")
    scanned = [path for path in sources if path.lower().endswith(SCANNED)]
    with open(file_list, "w", encoding="utf-8") as f:
        f.writelines(path + "\n" for path in scanned)
    print("    %d files found" % len(scanned))

    old = strings(template_pot) if os.path.exists(template_pot) else set()
    print("Generating new template...")
    print("    Generating .ts")
    if os.path.exists(template_ts):
        os.remove(template_ts)
    subprocess.run([LUPDATE, "@" + file_list, "-ts", template_ts], cwd=src, check=True)
    print("    Converting .ts to .pot")
    subprocess.run([LCONVERT, "-locations", "relative", template_ts, "-o", template_pot], check=True)
    os.remove(template_ts)
    os.remove(file_list)

    new = strings(template_pot)
    print("Template changes:")
    print("    %d strings, %d added, %d removed" % (len(new), len(new - old), len(old - new)))
    for title, items in (("added", new - old), ("removed", old - new)):
        for context, msgid in sorted(items):
            print("    %s: %s | %s" % (title, context, msgid[:80]))


def source_files(src):
    """Every file under src, as ./relative/path (the form lupdate gets them in)."""
    found = []
    for directory, dirs, files in os.walk(src):
        dirs.sort()
        for name in sorted(files):
            if not os.path.islink(os.path.join(directory, name)):
                found.append("./" + os.path.relpath(os.path.join(directory, name), src))
    return found


def uses_tr(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return bool(TR_CALL.search(f.read()))


def strings(pot_path):
    """The (context, msgid) pairs in a .pot file."""
    with open(pot_path, encoding="utf-8") as f:
        text = f.read()
    found = set()
    for block in text.split("\n\n"):
        context = re.search(r'^msgctxt "(.*)"', block, re.M)
        msgid = re.search(r'^msgid "(.*)"((?:\n".*")*)', block, re.M)
        if msgid:
            value = msgid.group(1) + "".join(re.findall(r'"(.*)"', msgid.group(2)))
            if value:
                found.add((context.group(1) if context else "", value))
    return found


if __name__ == "__main__":
    main()
