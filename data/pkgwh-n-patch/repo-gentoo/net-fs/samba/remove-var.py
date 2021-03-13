#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
rm -rf ${D}/run             # upstream sucks, these directories are tmpfs nowadays
rm -rf ${D}/var/lock
rm -rf ${D}/var/run

echo "d /var/lib/ctdb" >> "${D}/usr/lib/tmpfiles.d/samba.conf"
echo "d /var/lib/samba" >> "${D}/usr/lib/tmpfiles.d/samba.conf"
echo "d /var/lib/samba/bind-dns" >> "${D}/usr/lib/tmpfiles.d/samba.conf"
echo "d /var/lib/samba/private" >> "${D}/usr/lib/tmpfiles.d/samba.conf"
echo "d /var/lib/samba/usershare 755 root users" >> "${D}/usr/lib/tmpfiles.d/samba.conf"
echo "d /var/cache/samba" >> "${D}/usr/lib/tmpfiles.d/samba.conf"
echo "d /var/log/samba" >> "${D}/usr/lib/tmpfiles.d/samba.conf"

rm -rf ${D}/var/log/samba
[ -z "$(ls -A ${D}/var/log)" ] && rmdir ${D}/var/log

rm -rf ${D}/var/cache/samba
[ -z "$(ls -A ${D}/var/cache)" ] && rmdir ${D}/var/cache

rm -rf ${D}/var/lib/samba/{bind-dns,private,usershare}
[ -z "$(ls -A ${D}/var/lib/samba)" ] && rmdir ${D}/var/lib/samba

rm -rf ${D}/var/lib/ctdb
[ -z "$(ls -A ${D}/var/lib)" ] && rmdir ${D}/var/lib

[ -z "$(ls -A ${D}/var)" ] && rmdir ${D}/var
## end ####"""
    buf2 = buf2.replace("\n", "\n\t")
    buf2 += "\n"

    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        # insert to the end of src_install()
        pos = buf.find("multilib_src_install() {")
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
