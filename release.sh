#!/bin/sh

set -e

ROOT=$PWD
OUTPUT=$ROOT/build
# Sanitized copies of the .po files: broken entries blanked, unusable languages left out.
# Qt's built-in strings (qt/<lang>.po, see qt_strings.py) go to $VALIDATED/qt.
VALIDATED=$ROOT/.validated

LCONVERT_BIN=${LCONVERT_BIN:-lconvert}
LRELEASE_BIN=${LRELEASE_BIN:-lrelease}
LUPDATE_BIN=${LUPDATE_BIN:-lupdate}


if [ ! -d $OUTPUT ]
then
    mkdir $OUTPUT
fi

echo "Cleaning old .qm files..."
rm -f $OUTPUT/*

grep_count()
{
    local PIECE=`echo "$1" | grep -o "$2"`
    if [ -n "$PIECE" ]; then
        RETVAL=`echo $PIECE | sed 's/[a-z ]//g'`
        echo $RETVAL
        return
    fi
    echo 0
}

# Language code for a .po file name: everything up to the first dot, with a few renames.
lang_for_po()
{
    local lang=$(echo $1 | grep -oP "^[^\.]*")
    case "$lang" in
        en) echo "en_GB" ;;
        pt) echo "pt_PT" ;;
        *) echo "$lang" ;;
    esac
}

echo "{" >> $OUTPUT/index_v2.json
echo "    \"file_type\" : \"MMC-TRANSLATION-INDEX\"," >> $OUTPUT/index_v2.json
echo "    \"version\" : 2," >> $OUTPUT/index_v2.json
echo "    \"languages\" : {" >> $OUTPUT/index_v2.json

echo "Validating translations..."
rm -rf "$VALIDATED"
python3 "$ROOT/validate_po.py" --fix "$VALIDATED" *.po
if ls qt/*.po > /dev/null 2>&1
then
    echo "Validating Qt string translations..."
    python3 "$ROOT/validate_po.py" --fix "$VALIDATED/qt" qt/*.po
fi

echo "Creating .qm files..."

FIRST=true

for po_path in "$VALIDATED"/*.po
do
    po_file=$(basename "$po_path")
    echo "Considering ${po_file}"

    lang=$(lang_for_po "$po_file")
    # Qt's built-in strings for this language, if there are any, go into the same .qm.
    # A broken qt/<lang>.po is skipped by the validator; the language then ships without them.
    QT_INPUT=""
    if [ -f "$VALIDATED/qt/$po_file" ]; then
        QT_INPUT="-i $VALIDATED/qt/$po_file"
    fi
    echo "    Converting $po_file to $lang.ts"
    $LCONVERT_BIN -locations relative -i "$po_path" $QT_INPUT -o $lang.ts
    echo "    Create $lang.qm"
    $LRELEASE_BIN $lang.ts -qm $OUTPUT/$lang.qm

    SHA1=`sha1sum $OUTPUT/$lang.qm | awk '{ print $1 }'`
    FILENAME="${SHA1}.class"
    cp "$OUTPUT/$lang.qm" "$OUTPUT/$FILENAME"

    # Create an index file with info about the amount of strings translated and expected hashes of the files (for local caching purposes)
    # The counts are for MultiMC's own strings only; Qt's don't change how complete a language looks.
    PO_STATS=`msgfmt --statistics --output=/dev/null "$po_path" 2>&1`
    UNTRANSLATED=$(grep_count "$PO_STATS" '[0-9]\+ untranslated messages\?')
    FUZZY=$(grep_count "$PO_STATS" '[0-9]\+ fuzzy translations\?')
    TRANSLATED=$(grep_count "$PO_STATS" '[0-9]\+ translated messages\?')

    FILESIZE=$(stat -c%s "$OUTPUT/$lang.qm")

    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        # close previous scope
        echo "        }," >> $OUTPUT/index_v2.json
    fi
    echo "        \"$lang\" : {" >> $OUTPUT/index_v2.json
    echo "            \"file\" : \"$FILENAME\"," >> $OUTPUT/index_v2.json
    echo "            \"sha1\" : \"$SHA1\"," >> $OUTPUT/index_v2.json
    echo "            \"size\" : $FILESIZE," >> $OUTPUT/index_v2.json
    echo "            \"translated\" : $TRANSLATED," >> $OUTPUT/index_v2.json
    echo "            \"fuzzy\" : $FUZZY," >> $OUTPUT/index_v2.json
    echo "            \"untranslated\" : $UNTRANSLATED" >> $OUTPUT/index_v2.json
    # Create an index file with just the files (legacy)
    echo "$lang.qm" >> $OUTPUT/index
done
echo "        }" >> $OUTPUT/index_v2.json
echo "    }" >> $OUTPUT/index_v2.json
echo "}" >> $OUTPUT/index_v2.json

if [ -s "$VALIDATED/skipped.txt" ]
then
    echo "Keeping skipped languages at their previous release..."
    SKIPPED_LANGS=""
    for po_file in $(cat "$VALIDATED/skipped.txt")
    do
        SKIPPED_LANGS="$SKIPPED_LANGS $(lang_for_po "$po_file")"
    done
    python3 - "$OUTPUT" $SKIPPED_LANGS <<'PYEOF'
# A language whose .po couldn't be used keeps its entry from the previous index.
# The .class file that entry points to is still on the server: deploys never delete.
import json, os, sys, urllib.request
output, skipped_langs = sys.argv[1], sys.argv[2:]
url = os.environ.get("PREVIOUS_INDEX_URL", "https://files.multimc.org/translations/index_v2.json")
path = os.environ.get("PREVIOUS_INDEX")
try:
    if path:
        previous = json.load(open(path, encoding="utf-8"))
    else:
        with urllib.request.urlopen(url, timeout=60) as resp:
            previous = json.load(resp)
except Exception as e:
    sys.exit("Can't load the previous index (%s), refusing to drop languages: %s" % (path or url, e))

index_path = os.path.join(output, "index_v2.json")
index = json.load(open(index_path, encoding="utf-8"))
carried = []
for lang in skipped_langs:
    if lang in previous["languages"]:
        index["languages"][lang] = previous["languages"][lang]
        carried.append(lang)
        print("    %s: kept previous release %s" % (lang, previous["languages"][lang]["file"]))
    else:
        print("    %s: no previous release, left out" % lang)
if carried:
    index["languages"] = dict(sorted(index["languages"].items()))
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=4)
        fh.write("\n")
    with open(os.path.join(output, "index"), "a", encoding="utf-8") as fh:
        fh.writelines(lang + ".qm\n" for lang in carried)
PYEOF
fi

echo "Removing intermediate files..."
rm *.ts
rm -rf "$VALIDATED"

echo "All done!"
