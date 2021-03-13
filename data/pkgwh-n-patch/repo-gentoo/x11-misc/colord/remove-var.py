#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
echo "d /var/lib/color" >> "${D}/usr/lib/tmpfiles.d/colord.conf"
echo "d /var/lib/color/icc" >> "${D}/usr/lib/tmpfiles.d/colord.conf"
echo "d /var/lib/colord 755 colord colord" >> "${D}/usr/lib/tmpfiles.d/colord.conf"
echo "d /var/lib/colord/icc 755 colord colord" >> "${D}/usr/lib/tmpfiles.d/colord.conf"

rm -rf ${D}/var/lib/color/icc
[ -z "$(ls -A ${D}/var/lib/color)" ] && rmdir ${D}/var/lib/color

rm -rf ${D}/var/lib/colord/icc
[ -z "$(ls -A ${D}/var/lib/colord)" ] && rmdir ${D}/var/lib/colord

[ -z "$(ls -A ${D}/var/lib)" ] && rmdir ${D}/var/lib
[ -z "$(ls -A ${D}/var)" ] && rmdir ${D}/var
## end ####"""
    buf2 = buf2.replace("\n", "\n\t")
    buf2 += "\n"

    for fn in glob.glob("*.ebuild"):
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
except ValueError:
    print("outdated")
