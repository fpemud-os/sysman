#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    installMask = """
## patched by fpemud-refsystem ####
rm -f ${D}/usr/bin/*-config
rm -f ${D}/usr/share/eselect/modules/kernel.eselect
rm -f ${D}/usr/share/eselect/modules/rc.eselect
rm -f ${D}/usr/share/man/man1/*-config.1.bz2
rm -f ${D}/usr/share/man/man5/kernel.eselect.5.bz2
rm -f ${D}/usr/share/man/man5/rc.eselect.5.bz2
## end ####"""
    installMask = installMask.replace("\n", "\n\t")
    installMask += "\n"

    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        # insert to the end of src_install()
        pos = buf.find("src_install() {")
        if pos == -1:
            raise ValueError()
        pos = buf.find("\n}\n", pos)
        if pos == -1:
            raise ValueError()
        pos += 1
        buf = buf[:pos] + installMask + buf[pos:]

        # save and generate manifest
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
