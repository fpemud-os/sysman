#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
touch "${D}/usr/lib/tmpfiles.d/portage.conf"
echo "d /var/log/portage 2755 portage portage" >> "${D}/usr/lib/tmpfiles.d/portage.conf"
echo "d /var/log/portage/elog 2755 portage portage" >> "${D}/usr/lib/tmpfiles.d/portage.conf"
## end ####"""
    buf2 = buf2.replace("\n", "\n\t")
    buf2 += "\n"

    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()
        lineList = buf.split("\n")

        # remove "keepdir /var/log/portage/elog" and it's following lines in pkg_preinst()
        for i in range(0, len(lineList)):
            if "/var/log/portage" in lineList[i]:
                while i < len(lineList):
                    if lineList[i].strip() in ["", "}"]:
                        break
                    lineList.pop(i)
                break
        buf = "\n".join(lineList)

        # insert to the end of src_install()
        pos = buf.find("python_install_all() {")
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
except ValueError:
    print("outdated")
