#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import glob
import pathlib

try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
rm -rf ${D}/var
## end ####"""
    buf2 = buf2.replace("\n", "\n\t")
    buf2 += "\n"

    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()
        if "/var/lib/dbus" not in buf:
            raise ValueError()

        # step 1: remove /var/lib/dbus
        buf = re.sub(".*/var/lib/dbus.*", "", buf, re.M)

        # step 2: insert to the end of multilib_src_install_all()
        pos = buf.find("multilib_src_install_all() {")
        if pos == -1:
            raise ValueError()
        pos = buf.find("\n}\n", pos)
        if pos == -1:
            raise ValueError()
        pos += 1
        buf = buf[:pos] + buf2 + buf[pos:]

        # step 3: merge pkg-extra-files.py here, to avoid conflict with step 1
        buf += """
pkg_extra_files() {
        echo "/var/lib/dbus"
        echo "/var/lib/dbus/machine-id"
}
"""

        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
