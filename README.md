MultiMC5-translate
==================

Translations for MultiMC5

To participate in the translation effort, go to [the MultiMC crowdin site](https://translate.multimc.org) and join the project and get in touch on [discord](https://discord.gg/rjpzCxvAPQ).
(If you don't have a Crowdin account, you can create one using your Facebook, Google, Twitter, Github, GitLab or any other email.)

You may want to use [POEdit](https://poedit.net/) to work on the translations. MultiMC allows putting a `.po` file in the translations folder and see changes in the application as you translate. Combined with its Crowdin integration, this is pretty powerful and comfortable to use.

Some setup is required to add completely new translations, so please get in touch.

## Tooling

`update.sh` regenerates `template.pot` from the Launcher source (checked out to `src/`).
`release.sh` turns the `.po` files into the `.qm` files and `index_v2.json` the Launcher
downloads. Both run in the `multimc/toolchains/translations` image (Qt 5.15.2 linguist
tools, gettext, python3), defined in the MultiMC Toolchains repository.

- Extraction needs Qt 5.15's `lupdate`: Qt 5.6's stops parsing a file at the first C++11
  raw string literal and silently misses the strings after it. `update.sh` refuses other
  versions, fails if a source type it doesn't scan uses `tr()`, and prints which strings
  were added or removed.
- `.qm` files from Qt 5.15's `lrelease` only add a language tag, which the Qt 5.6 runtime
  skips; they load and translate the same.
- `validate_po.py` checks each translation with `msgfmt -c`. `release.sh` drops broken
  entries (mismatched newlines, missing `%1` placeholders, ...) so they show in English,
  and releases the rest. A language that can't be repaired keeps its previous release:
  its entry is copied from the live `index_v2.json` (or `PREVIOUS_INDEX`, a local file);
  if that can't be loaded, the release fails rather than drop the language. The pull request
  check runs the same validator and lists what would be dropped.

### Qt's own strings

Qt's built-in dialogs, standard buttons and context menus (OK/Cancel, Copy/Paste, the
file dialog, wizard buttons, the macOS application menu...) have their own strings.
`qt_strings.py` collects the ones the Launcher shows into `qt.pot`, so they can be
translated here like ours, and writes `qt/<lang>.po` pre-filled with Qt's own
translations where the Qt project has one.

    python3 qt_strings.py    # in the translations tools image

It downloads the pinned `qttranslations` source packages of the Qt versions we ship
(5.15.2 and 5.6.3, checked by SHA-256) into `.qt-sources/`. The output is deterministic.
The list of Qt contexts and the language mapping are at the top of the script. Rerun it
when either changes, or when moving to another Qt version.

`crowdin.yml` sends `qt.pot` to Crowdin as its own file, labelled `qt-builtin`.
`release.sh` merges each `qt/<lang>.po` into that language's `.qm`, so the Launcher
needs no changes; the translated/untranslated counts in `index_v2.json` still only count
MultiMC's own strings. A broken `qt/<lang>.po` is left out and the language ships
without Qt's strings.

