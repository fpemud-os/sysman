#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    buf2 = """
## patched by fpemud-refsystem ####
mkdir -p "${D}/usr/lib/tmpfiles.d"
echo "d /var/lib/gentoo" >> "${D}/usr/lib/tmpfiles.d/eselect.conf"
echo "d /var/lib/gentoo/news 0775" >> "${D}/usr/lib/tmpfiles.d/eselect.conf"

rm -rf ${D}/var/lib/gentoo/news
[ -z "$(ls -A ${D}/var/lib/gentoo)" ] && rmdir ${D}/var/lib/gentoo
[ -z "$(ls -A ${D}/var/lib)" ] && rmdir ${D}/var/lib
[ -z "$(ls -A ${D}/var)" ] && rmdir ${D}/var
## end ####"""
    buf2 = buf2.replace("\n", "\n\t")
    buf2 += "\n"

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
        buf = buf[:pos] + buf2 + buf[pos:]

        # save
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
