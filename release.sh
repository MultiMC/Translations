#!/bin/sh

set -e
set -o pipefail

ROOT=$PWD
OUTPUT=$ROOT/build

LCONVERT_BIN=${LCONVERT_BIN:-lconvert-qt5}
LRELEASE_BIN=${LRELEASE_BIN:-lrelease-qt5}
LUPDATE_BIN=${LUPDATE_BIN:-lupdate-qt5}

if [ ! -d $OUTPUT ]
then
    mkdir $OUTPUT
fi

echo "Cleaning old .qm files..."
rm -f $OUTPUT/*

echo "Creating .qm files..."
for po_file in $(ls *.po)
do
    echo "Considering ${po_file}"
    if cat "${po_file}" | grep '\"X-Qt-Contexts: true\\n\"' > /dev/null ; then
        echo "Translation ${po_file} is OK"
    else
        echo "Translation ${po_file} is bad (missing X-Qt-Contexts)"
        exit 1
    fi

    # gets everything up to the first dot
    lang=$(echo $po_file | grep -oP "^[^\.]*")
    echo "    Converting $po_file to $lang.ts"
    $LCONVERT_BIN -locations relative $po_file -o $lang.ts
    echo "    Create $lang.qm"
    $LRELEASE_BIN $lang.ts -qm $OUTPUT/$lang.qm

    # Create an index file with info about the amount of strings translated and expected hashes of the files (for local caching purposes)
    PO_STATS=`msgfmt --statistics --output=/dev/null ${po_file} 2>&1`
    UNTRANSLATED=`echo "$PO_STATS" | grep -o '[0-9]\+ untranslated messages\?' | sed 's/[a-z ]//g'` || UNTRANSLATED=0
    FUZZY=`echo "$PO_STATS" | grep -o '[0-9]\+ fuzzy translations\?' | sed 's/[a-z ]//g'` || FUZZY=0
    TRANSLATED=`echo "$PO_STATS" | grep -o '[0-9]\+ translated messages\?' | sed 's/[a-z ]//g'` || TRANSLATED=0
    SHA1=`sha1sum $OUTPUT/$lang.qm | awk '{ print $1 }'`
    echo "$lang.qm,$SHA1,$TRANSLATED,$FUZZY,$UNTRANSLATED" >> $OUTPUT/index_v2

    # Create an index file with just the files (legacy)
    echo "$lang.qm" >> $OUTPUT/index
done

echo "Removing intermediate files..."
rm *.ts

echo "All done!"
