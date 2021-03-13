#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
rm -rf ${D}/var/run

echo "d /var/lib/dav 750 apache apache" >> "${D}/usr/lib/tmpfiles.d/apache.conf"
echo "d /var/cache/apache2 750 apache apache" >> "${D}/usr/lib/tmpfiles.d/apache.conf"
echo "d /var/log/apache2 750 apache apache" >> "${D}/usr/lib/tmpfiles.d/apache.conf"
echo "d /var/www 755 root root" >> "${D}/usr/lib/tmpfiles.d/apache.conf"

rm -rf ${D}/var/www

rm -rf ${D}/var/log/apache2
[ -z "$(ls -A ${D}/var/log)" ] && rmdir ${D}/var/log

rm -rf ${D}/var/cache/apache2
[ -z "$(ls -A ${D}/var/cache)" ] && rmdir ${D}/var/cache

rm -rf ${D}/var/lib/dav
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

        # do insert
        buf = buf[:pos] + buf2 + buf[pos:]
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
