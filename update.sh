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

###############################################################################

echo "Writing lst file..."
cd $SRC
find -type f \( -iname \*.h -o -iname \*.cpp -o -iname \*.ui \) > $BASE_LST_FILE
cd $ROOT
echo "    $(cat $BASE_LST_FILE | wc -l) files found"

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

