#!/bin/sh

set -e

ROOT=$PWD
OUTPUT=$ROOT/build

LCONVERT_BIN=${LCONVERT_BIN:-lconvert-qt5}
LRELEASE_BIN=${LRELEASE_BIN:-lrelease-qt5}
LUPDATE_BIN=${LUPDATE_BIN:-lupdate-qt5}

if [ ! -d $OUTPUT ]
then
	mkdir $OUTPUT
fi

echo "Creating .qm files..."
for po_file in $(ls *.po)
do
	# gets everything up to the first dot
	lang=$(echo $po_file | grep -oP "^[^\.]*")
	echo "    Converting $po_file to $lang.ts"
	$LCONVERT_BIN -locations relative $po_file -o $lang.ts
	echo "    Create $lang.qm"
	$LRELEASE_BIN $lang.ts -qm $OUTPUT/$lang.qm
done

ls $OUTPUT/ | grep -v index > $OUTPUT/index

echo "Removing intermediate files..."
rm *.ts

echo "All done!"
