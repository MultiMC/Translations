#!/bin/sh

set -e

ROOT=`pwd`
SRC=${ROOT}/src
TEMPLATE_PO="$ROOT/template.pot"
TEMPLATE_TS="$ROOT/template.ts"
BASE_LST_FILE="$ROOT/base_lst_file"

LCONVERT_BIN=${LCONVERT_BIN:-lconvert}
LRELEASE_BIN=${LRELEASE_BIN:-lrelease}
LUPDATE_BIN=${LUPDATE_BIN:-lupdate}

# Extract with the Qt 5.15.2 tools (the multimc/toolchains/translations image).
# Qt 5.6's lupdate stops parsing a file at the first C++11 raw string literal R"(...)"
# and silently misses every string after it.
if ! $LUPDATE_BIN -version | grep -q "5\.15\."; then
    echo "lupdate must be Qt 5.15.x, found: $($LUPDATE_BIN -version)"
    exit 1
fi

###############################################################################

echo "Checking for translatable strings in files lupdate won't see..."
cd $SRC
UNSCANNED=$(grep -rlE '\b(tr|translate|QT_TR_NOOP|QT_TRANSLATE_NOOP)\(' . \
    --include='*.mm' --include='*.m' --include='*.c' --include='*.hpp' --include='*.cxx' --include='*.cc' || true)
if [ -n "$UNSCANNED" ]; then
    echo "These files use tr() but are not scanned (only .h, .cpp, .ui are):"
    echo "$UNSCANNED"
    exit 1
fi
cd $ROOT

echo "Writing lst file..."
cd $SRC
find . -type f \( -iname \*.h -o -iname \*.cpp -o -iname \*.ui \) > $BASE_LST_FILE
cd $ROOT
echo "    $(cat $BASE_LST_FILE | wc -l) files found"

if [ -f $TEMPLATE_PO ]
then
    cp $TEMPLATE_PO $ROOT/template.pot.old
fi

echo "Generating new template..."

if [ -f $TEMPLATE_PO ]
then
    echo "    Converting .pot to .ts"
    $LCONVERT_BIN -locations relative $TEMPLATE_PO -o $TEMPLATE_TS
fi

echo "    Generating .ts"
rm -f "$TEMPLATE_TS"
cd $SRC
$LUPDATE_BIN "@$BASE_LST_FILE" -ts $TEMPLATE_TS
cd $ROOT

echo "    Converting .ts to .pot"
$LCONVERT_BIN -locations relative $TEMPLATE_TS -o $TEMPLATE_PO

if [ -f $ROOT/template.pot.old ]
then
    echo "Template changes:"
    python3 - "$ROOT/template.pot.old" "$TEMPLATE_PO" <<'PYEOF'
import re, sys
def strings(path):
    text = open(path, encoding="utf-8").read()
    found = set()
    for block in text.split("\n\n"):
        ctx = re.search(r'^msgctxt "(.*)"', block, re.M)
        mid = re.search(r'^msgid "(.*)"((?:\n".*")*)', block, re.M)
        if mid:
            msgid = mid.group(1) + "".join(re.findall(r'"(.*)"', mid.group(2)))
            if msgid:
                found.add(((ctx.group(1) if ctx else ""), msgid))
    return found
old, new = strings(sys.argv[1]), strings(sys.argv[2])
print("    %d strings, %d added, %d removed" % (len(new), len(new - old), len(old - new)))
for title, items in (("added", new - old), ("removed", old - new)):
    for ctx, msgid in sorted(items):
        print("    %s: %s | %s" % (title, ctx, msgid[:80]))
PYEOF
    rm -f $ROOT/template.pot.old
fi
