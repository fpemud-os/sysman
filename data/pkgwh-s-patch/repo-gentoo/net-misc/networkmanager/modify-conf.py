#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import glob
import pathlib
import subprocess


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


try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
dodir /etc/NetworkManager
echo "[main]" > "${ED}"/etc/NetworkManager/NetworkManager.conf
echo "no-auto-default=*" >> "${ED}"/etc/NetworkManager/NetworkManager.conf
## end ####"""
    buf2 = buf2.replace("\n", "\n\t")
    buf2 += "\n"

    bFound = False
    for fn in glob.glob("*.ebuild"):
        m = re.fullmatch(".*?-([0-9-r\\.]+)\\.ebuild", fn)
        if m is None:
            raise ValueError()

        if compareVersion(m.group(1), "1.26.0") < 0:
            os.remove(fn)
            removeFileInManifest(fn)
            bFound = True
            continue

        buf = pathlib.Path(fn).read_text()

        # insert to the end of multilib_src_install_all()
        pos = buf.find("multilib_src_install_all() {")
        if pos == -1:
            raise ValueError()
        pos = buf.find("\n}\n", pos)
        if pos == -1:
            raise ValueError()
        pos += 1

        # do insert
        buf = buf[:pos] + buf2 + buf[pos:]
        with open(fn, "w") as f:
            f.write(buf)
        subprocess.run(["ebuild", fn, "manifest"], stdout=subprocess.DEVNULL)
    if not bFound:
        raise ValueError()
except ValueError:
    print("outdated")
