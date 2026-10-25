#!/usr/bin/env python3
"""Build a translations release: one .qm per language, and the indexes the Launcher reads.

    release.py [--output DIR] [--previous-index PATH_OR_URL]

Runs in the translations image (multimc/toolchains/translations: Qt 5.15.2 lconvert and
lrelease, gettext's msgfmt), in this directory. From the .po files here, plus Qt's own
strings in qt/<lang>.po (see qt_strings.py):

1. validate_po.py checks them and writes sanitized copies: broken entries are blanked
   (shown in English), a file that can't be used at all is skipped.
2. For each language: <lang>.qm in OUTPUT (default build/, emptied first). Qt's strings
   for the language go into the same .qm.
3. index_v2.json: for each language its file, sha1, size, and how many of MultiMC's own
   strings are translated, fuzzy and untranslated. index: the legacy list of <lang>.qm
   files (very old Launchers).

A skipped language keeps its entry from the previous release's index_v2.json (default:
the live one, https://files.multimc.org/translations/index_v2.json), and its file from
the previous release stays where it is: this release has no file for it. If the previous
index can't be read, the release stops rather than drop those languages.

Files have fixed names (until 2026-10 they were also copied as <sha1>.class, named so
because Cloudflare once cached .class files for free; those piled up, one set per release).
The Launcher takes the name from index_v2.json and checks the sha1, so it works either way.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

import validate_po

ROOT = os.path.dirname(os.path.abspath(__file__))
LIVE_INDEX = "https://files.multimc.org/translations/index_v2.json"
LCONVERT = os.environ.get("LCONVERT_BIN", "lconvert")
LRELEASE = os.environ.get("LRELEASE_BIN", "lrelease")

# .po file names whose language code differs from the name
RENAMED = {"en": "en_GB", "pt": "pt_PT"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=os.path.join(ROOT, "build"))
    parser.add_argument("--previous-index", default=LIVE_INDEX)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    print("Cleaning old .qm files...")
    for name in os.listdir(args.output):
        os.remove(os.path.join(args.output, name))

    with tempfile.TemporaryDirectory() as work:
        validated = os.path.join(work, "validated")
        print("Validating translations...")
        validate_po.main(["--fix", validated] + sorted(po_files(ROOT)))
        if po_files(os.path.join(ROOT, "qt")):
            print("Validating Qt string translations...")
            validate_po.main(["--fix", os.path.join(validated, "qt")]
                             + sorted(po_files(os.path.join(ROOT, "qt"))))

        print("Creating .qm files...")
        languages = {}
        for po_file in sorted(os.listdir(validated)):
            if po_file.endswith(".po"):
                lang = language(po_file)
                languages[lang] = build_language(po_file, lang, validated, work, args.output)

        skipped = read_lines(os.path.join(validated, "skipped.txt"))
        carried = keep_previous([language(name) for name in skipped], languages, args.previous_index)

    # In the order of the .po file names, as the index has always been (pt.po's pt_PT before
    # pt_BR), carried languages included.
    order = sorted(skipped + [name for name in os.listdir(ROOT) if name.endswith(".po")])
    languages = {language(name): languages[language(name)] for name in dict.fromkeys(order)
                 if language(name) in languages}
    write_index_v2(os.path.join(args.output, "index_v2.json"), languages)
    with open(os.path.join(args.output, "index"), "w", encoding="utf-8") as f:
        f.writelines(lang + ".qm\n" for lang in list(languages) if lang not in carried)
        f.writelines(lang + ".qm\n" for lang in carried)
    print("All done!")


def po_files(directory):
    if not os.path.isdir(directory):
        return []
    return [os.path.join(directory, name) for name in os.listdir(directory) if name.endswith(".po")]


def language(po_file):
    """The language code for a .po file name: everything up to the first dot, renamed."""
    lang = po_file.split(".", 1)[0]
    return RENAMED.get(lang, lang)


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def build_language(po_file, lang, validated, work, output):
    """lang.qm from the validated .po (plus Qt's strings); its index entry."""
    print("Considering %s" % po_file)
    inputs = ["-i", os.path.join(validated, po_file)]
    # Qt's built-in strings for this language, if there are any, go into the same .qm. A broken
    # qt/<lang>.po is skipped by the validator; the language then ships without them.
    qt_po = os.path.join(validated, "qt", po_file)
    if os.path.exists(qt_po):
        inputs += ["-i", qt_po]

    ts = os.path.join(work, lang + ".ts")
    qm = os.path.join(output, lang + ".qm")
    print("    Converting %s to %s.ts" % (po_file, lang))
    subprocess.run([LCONVERT, "-locations", "relative", *inputs, "-o", ts], check=True)
    print("    Create %s.qm" % lang)
    subprocess.run([LRELEASE, ts, "-qm", qm], check=True)

    with open(qm, "rb") as f:
        sha1 = hashlib.sha1(f.read()).hexdigest()
    counts = statistics(os.path.join(validated, po_file))
    return {"file": lang + ".qm", "sha1": sha1, "size": os.path.getsize(qm), **counts}


def statistics(po_path):
    """Translated, fuzzy and untranslated counts from `msgfmt --statistics`. MultiMC's own
    strings only: Qt's don't change how complete a language looks."""
    text = subprocess.run(["msgfmt", "--statistics", "--output=/dev/null", po_path],
                          stderr=subprocess.PIPE, text=True, check=True).stderr

    def count(pattern):
        match = re.search(r"(\d+) " + pattern, text)
        return int(match.group(1)) if match else 0
    return {"translated": count(r"translated messages?"), "fuzzy": count(r"fuzzy translations?"),
            "untranslated": count(r"untranslated messages?")}


def keep_previous(skipped, languages, previous_index):
    """Give each skipped language its entry from the previous index; returns those carried."""
    if not skipped:
        return []

    print("Keeping skipped languages at their previous release...")
    try:
        if re.match(r"https?://", previous_index):
            with urllib.request.urlopen(previous_index, timeout=60) as response:
                previous = json.load(response)
        else:
            with open(previous_index, encoding="utf-8") as f:
                previous = json.load(f)
    except Exception as e:
        sys.exit("Can't load the previous index (%s), refusing to drop languages: %s" % (previous_index, e))

    carried = []
    for lang in skipped:
        if lang in previous["languages"]:
            languages[lang] = previous["languages"][lang]
            carried.append(lang)
            print("    %s: kept previous release %s" % (lang, previous["languages"][lang]["file"]))
        else:
            print("    %s: no previous release, left out" % lang)
    return carried


def write_index_v2(path, languages):
    """index_v2.json, in the layout it has always had."""
    entries = []
    for lang in languages:
        fields = ",\n".join('            "%s" : %s' % (key, json.dumps(value))
                            for key, value in languages[lang].items())
        entries.append('        "%s" : {\n%s\n        }' % (lang, fields))
    with open(path, "w", encoding="utf-8") as f:
        f.write('{\n    "file_type" : "MMC-TRANSLATION-INDEX",\n    "version" : 2,\n'
                '    "languages" : {\n%s\n    }\n}\n' % ",\n".join(entries))


if __name__ == "__main__":
    main()
