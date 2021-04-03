#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import glob
import shutil
import pathlib

try:
    selfDir = os.path.dirname(os.path.realpath(__file__))
    if os.path.exists("files/kodi.service"):
        raise ValueError()
    if not os.path.exists("files"):
        os.mkdir("files")
    shutil.copyfile(os.path.join(selfDir, "files", "kodi.service"), os.path.join("files", "kodi.service"))

    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
systemd_dounit "${FILESDIR}"/kodi.service
## end ####"""
    buf2 = buf2.replace("\n", "\n\t")
    buf2 += "\n"

    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        buf = buf.replace("inherit ", "inherit systemd ")

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
