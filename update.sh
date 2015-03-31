#!/bin/sh

set -e

ROOT="$PWD"
SRC="$ROOT/src"
TEMPLATE_PO="$ROOT/template.pot"
TEMPLATE_TS="$ROOT/template.ts"
BASE_LST_FILE="$ROOT/base_lst_file"

LCONVERT_BIN=${LCONVERT_BIN:-lconvert-qt5}
LRELEASE_BIN=${LRELEASE_BIN:-lrelease-qt5}
LUPDATE_BIN=${LUPDATE_BIN:-lupdate-qt5}

###############################################################################

echo "Updating sources..."
if [ -d $SRC ]
then
	echo "    Updating existing sources"
	cd $SRC
	git fetch
	git reset --hard origin/stable
	cd $ROOT
else
	echo "    Cloning repo from scratch"
	git clone https://github.com/MultiMC/MultiMC5.git $SRC
	cd $SRC
	git reset --hard origin/stable
	cd $ROOT
fi

###############################################################################

echo "Writing lst file..."
cd $SRC
find -type f \( -iname \*.h -o -iname \*.cpp -o -iname \*.ui \) > $BASE_LST_FILE
cd $ROOT
echo "    $(cat $BASE_LST_FILE | wc -l) files found"

###############################################################################

echo "Updating po template..."

if [ -f $TEMPLATE_PO ]
then
	echo "    Converting .pot to .ts"
	$LCONVERT_BIN -locations relative $TEMPLATE_PO -o $TEMPLATE_TS
fi

echo "    Updating .ts"
cd $SRC
$LUPDATE_BIN "@$BASE_LST_FILE" -ts $TEMPLATE_TS
cd $ROOT

echo "    Converting .ts to .pot"
$LCONVERT_BIN -locations relative $TEMPLATE_TS -o $TEMPLATE_PO

echo "    Removing .ts"
rm $TEMPLATE_TS

###############################################################################

echo "Updating .po files..."
for po_file in $(ls *.po)
do
	# gets everything up to the first dot
	lang=$(echo $po_file | grep -oP "^[^\.]*")
	echo "    Updating $po_file ($lang)"
	msgmerge --lang=$lang --update --force-po $po_file $TEMPLATE_PO
done

###############################################################################

if [ -n "$MMC_TRANSLATIONS_REMOTE" ]
then
	echo "Pushing changes to git"
	git add $TEMPLATE_PO *.po
	git commit -m "Update translations"
	git push $MMC_TRANSLATIONS_REMOTE $(git rev-parse --abbrev-ref HEAD)
fi

###############################################################################

echo "All good!"
