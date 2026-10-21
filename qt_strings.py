#!/usr/bin/env python3
"""Generate qt.pot and pre-filled qt/<lang>.po from Qt's own translations.

    python3 qt_strings.py

Qt's built-in dialogs, buttons and context menus have their own strings, translated by
the Qt project for only some languages and never shipped by MultiMC. This collects the
ones the Launcher shows (CONTEXTS) so they can be translated in Crowdin like our own:

  qt.pot          source strings, Qt's context kept as msgctxt, marked with a comment
  qt/<lang>.po    Qt's existing translation for each string, where Qt has one

Sources are the qttranslations source packages of the Qt versions we ship with (pinned
in SOURCES, downloaded once into .qt-sources/ and checked by SHA-256). Strings are the
union of both versions so the catalogs match either runtime. Translations come, in order
of preference, from the newer qtbase_<lang>.ts, the older one, then Qt 4 era qt_<lang>.ts
catalogs; only finished translations are used, and any that fail validate_po.py (Qt's
own catalogs have a few broken placeholders) are left out.

Run it in the translations tools image (needs lconvert, python3). Output is deterministic.
"""

import hashlib
import shutil
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

sys.dont_write_bytecode = True
import validate_po  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, ".qt-sources")

# Newest first: earlier sources win when picking a translation.
SOURCES = [
    ("https://download.qt.io/archive/qt/5.15/5.15.2/submodules/qttranslations-everywhere-src-5.15.2.tar.xz",
     "d5788e86257b21d5323f1efd94376a213e091d1e5e03b45a95dd052b5f570db8"),
    ("https://download.qt.io/archive/qt/5.6/5.6.3/submodules/qttranslations-opensource-src-5.6.3.tar.xz",
     "6ded4e0162c2e4f092f824f98cd35bc46d0b0d4b08e21ca200b3af14ab776cab"),
]

# Qt contexts whose strings the Launcher shows: standard buttons, message/input/progress
# dialogs, wizard, text field and text area context menus, file dialog, small widgets,
# and the macOS application menu. Not included: QShortcut (key names), colour and font
# dialogs (unused).
CONTEXTS = [
    "QAbstractSpinBox",
    "QCocoaMenuItem",
    "QCocoaTheme",
    "QComboBox",
    "QDialogButtonBox",
    "QDockWidget",
    "QErrorMessage",
    "QFileDialog",
    "QFileSystemModel",
    "QGnomeTheme",
    "QInputDialog",
    "QLineEdit",
    "QMessageBox",
    "QPlatformTheme",
    "QProgressDialog",
    "QScrollBar",
    "QTabBar",
    "QUnicodeControlCharacterMenu",
    "QWidgetTextControl",
    "QWizard",
]

# Our language (file name) -> Qt languages to take translations from, in order.
# Default is the same code. Empty list: no Qt translation is a good fit.
QT_LANGUAGES = {
    "en": [],           # en_GB; Qt's "en" catalogs only hold plural rules
    "de_CH": ["de"],
    "es_UY": ["es"],
    "ja_KANJI": ["ja"],
    "pt": ["pt"],       # Qt's Portuguese is European Portuguese
    "pt_BR": [],
    "zh": ["zh_CN"],
}

COMMENT = ("Qt built-in string (%s), shown in Qt's own dialogs and menus. "
           "Pre-filled from Qt's translation where Qt has one.")


def fetch(url, sha256):
    """Return the path of the cached, verified source package."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, url.rsplit("/", 1)[1])
    if not os.path.exists(path):
        print("Downloading", url)
        with urllib.request.urlopen(url, timeout=120) as resp, open(path + ".part", "wb") as fh:
            fh.write(resp.read())
        os.rename(path + ".part", path)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if digest != sha256:
        sys.exit("%s: SHA-256 %s, expected %s" % (path, digest, sha256))
    return path


def read_catalogs(path):
    """{file name: parsed .ts root} for qtbase_*.ts and qt_<lang>.ts in a package."""
    out = {}
    with tarfile.open(path) as tar:
        for member in tar.getmembers():
            name = os.path.basename(member.name)
            if "/translations/" not in member.name or not name.endswith(".ts"):
                continue
            if name.startswith("qtbase_") or (name.startswith("qt_") and not name.startswith("qt_help_")):
                out[name] = ET.fromstring(tar.extractfile(member).read())
    return out


def messages(root, want_translation):
    """Yield (context, source, comment, translation) for the wanted contexts."""
    for ctx in root.iter("context"):
        name = ctx.findtext("name")
        if name not in CONTEXTS:
            continue
        for msg in ctx.iter("message"):
            if msg.get("numerus") == "yes":
                continue
            tr = msg.find("translation")
            kind = tr.get("type") if tr is not None else None
            if kind in ("obsolete", "vanished"):
                continue
            text = None
            if want_translation and tr is not None and kind is None and (tr.text or "").strip():
                text = tr.text
            yield name, msg.findtext("source") or "", msg.findtext("comment") or "", text


def write_ts(path, language, keys, translations):
    """Write a Qt .ts file with the given messages (translations may be empty)."""
    lines = ['<?xml version="1.0" encoding="utf-8"?>', '<!DOCTYPE TS>',
             '<TS version="2.1"%s>' % (' language="%s"' % language if language else "")]
    current = None
    for ctx, source, comment in keys:
        if ctx != current:
            if current is not None:
                lines.append("</context>")
            lines += ["<context>", "    <name>%s</name>" % escape(ctx)]
            current = ctx
        lines.append("    <message>")
        lines.append("        <source>%s</source>" % escape(source))
        if comment:
            lines.append("        <comment>%s</comment>" % escape(comment))
        lines.append("        <extracomment>%s</extracomment>" % escape(COMMENT % ctx))
        text = translations.get((ctx, source, comment))
        if text is None:
            lines.append('        <translation type="unfinished"></translation>')
        else:
            lines.append("        <translation>%s</translation>" % escape(text))
        lines.append("    </message>")
    if current is not None:
        lines.append("</context>")
    lines.append("</TS>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def lconvert(ts, po):
    subprocess.run(["lconvert", "-locations", "none", "-i", ts, "-o", po], check=True)


def main():
    packages = [read_catalogs(fetch(url, sha)) for url, sha in SOURCES]

    # Source strings: union of every qtbase catalog in every package.
    keys = set()
    for catalogs in packages:
        for name, root in catalogs.items():
            if name.startswith("qtbase_"):
                keys.update((c, s, m) for c, s, m, _ in messages(root, False))
    keys = sorted(keys)

    our_languages = sorted(f[:-3] for f in os.listdir(ROOT) if f.endswith(".po"))
    os.makedirs(os.path.join(ROOT, "qt"), exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        ts = os.path.join(tmp, "qt.ts")
        write_ts(ts, None, keys, {})
        lconvert(ts, os.path.join(ROOT, "qt.pot"))
        print("qt.pot: %d strings in %d contexts" % (len(keys), len({k[0] for k in keys})))

        for lang in our_languages:
            found = {}
            for qt_lang in QT_LANGUAGES.get(lang, [lang]):
                for prefix in ("qtbase_", "qt_"):
                    for catalogs in packages:
                        root = catalogs.get("%s%s.ts" % (prefix, qt_lang))
                        if root is None:
                            continue
                        for c, s, m, text in messages(root, True):
                            if text is not None and (c, s, m) in keys:
                                found.setdefault((c, s, m), text)
            target = os.path.join(ROOT, "qt", lang + ".po")
            if not found:
                if os.path.exists(target):
                    os.remove(target)
                continue
            ts = os.path.join(tmp, lang + ".ts")
            po = os.path.join(tmp, lang + ".po")
            write_ts(ts, lang, keys, found)
            lconvert(ts, po)
            # Blank Qt translations that our release would drop anyway.
            checked = os.path.join(tmp, "checked")
            os.makedirs(checked, exist_ok=True)
            ok, report = validate_po.process(po, checked)
            if not ok:
                sys.exit("qt/%s.po can't be repaired:\n%s" % (lang, "\n".join(report)))
            for line in report[:-1]:
                print("    " + line)
            shutil.copyfile(os.path.join(checked, lang + ".po"), target)
            dropped = len(report) - 1 if report else 0
            print("qt/%s.po: %d of %d pre-filled" % (lang, len(found) - dropped, len(keys)))


if __name__ == "__main__":
    main()
