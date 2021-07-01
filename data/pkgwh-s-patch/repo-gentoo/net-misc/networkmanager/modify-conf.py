#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import glob
import pathlib

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

    for fn in glob.glob("*.ebuild"):
        m = re.fullmatch(".*?-([0-9-r\\.]+)\\.ebuild", fn)
        if m is None:
            raise ValueError()

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
