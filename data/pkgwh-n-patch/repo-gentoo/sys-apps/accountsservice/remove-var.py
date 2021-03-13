#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import glob
import pathlib


def compareVersion(verstr1, verstr2):
    """eg: 3.9.11-r1 or 3.10.7"""

    partList1 = verstr1.split("-")
    partList2 = verstr2.split("-")

    verList1 = partList1[0].split(".")
    verList2 = partList2[0].split(".")
    assert len(verList1) == 3 and len(verList2) == 3

    ver1 = int(verList1[0]) * 10000 + int(verList1[1]) * 100 + int(verList1[2])
    ver2 = int(verList2[0]) * 10000 + int(verList2[1]) * 100 + int(verList2[2])
    if ver1 > ver2:
        return 1
    elif ver1 < ver2:
        return -1

    if len(partList1) >= 2 and len(partList2) == 1:
        return 1
    elif len(partList1) == 1 and len(partList2) >= 2:
        return -1

    p1 = "-".join(partList1[1:])
    p2 = "-".join(partList2[1:])
    if p1 > p2:
        return 1
    elif p1 < p2:
        return -1

    return 0


def removeFileInManifest(s):
    filename = "Manifest"
    buf = pathlib.Path(filename).read_text()
    lineList = []
    for line in buf.split("\n"):
        if " " + s + " " not in line:
            lineList.append(line)
    with open(filename, "w") as f:
        f.write("\n".join(lineList))


bFound = False
bBad = False
for fn in glob.glob("*.ebuild"):
    m = re.fullmatch(".*?-([0-9-r\\.]+)\\.ebuild", fn)
    if m is None:
        bBad = True
        break

    if compareVersion(m.group(1), "0.6.55") < 0:
        os.remove(fn)
        removeFileInManifest(fn)
        bFound = True
        continue

    buf = pathlib.Path(fn).read_text()
    if r'rm -r "${ED}"/var/lib' not in buf:
        bBad = True
        break

    buf = buf.replace(r'rm -r "${ED}"/var/lib', r'rm -r "${ED}"/var')
    with open(fn, "w") as f:
        f.write(buf)

if bBad or not bFound:
    print("outdated")
