#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
mkdir -p "${D}/usr/lib/tmpfiles.d"
echo "d /var/log/cups" >> "${D}/usr/lib/tmpfiles.d/cups.conf"
echo "d /var/spool/cups 0710 root lp" >> "${D}/usr/lib/tmpfiles.d/cups.conf"
echo "d /var/spool/cups/tmp 0755 root lp" >> "${D}/usr/lib/tmpfiles.d/cups.conf"

rm -rf ${D}/var/log/cups
[ -z "$(ls -A ${D}/var/log)" ] && rmdir ${D}/var/log

rm -rf ${D}/var/spool/cups/tmp
[ -z "$(ls -A ${D}/var/spool/cups)" ] && rmdir ${D}/var/spool/cups
[ -z "$(ls -A ${D}/var/spool)" ] && rmdir ${D}/var/spool

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
