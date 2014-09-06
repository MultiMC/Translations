#!/bin/sh

set -e

ROOT=$PWD
OUTPUT=$ROOT/build

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
	lconvert-qt5 -locations relative $po_file -o $lang.ts
	echo "    Create $lang.qm"
	lrelease-qt5 $lang.ts -qm $OUTPUT/$lang.qm
done

echo "Removing intermediate files..."
rm *.ts

echo "All done!"