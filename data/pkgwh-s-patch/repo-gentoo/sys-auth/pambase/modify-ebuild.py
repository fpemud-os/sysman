#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import glob
import shutil
import pathlib

selfDir = os.path.dirname(os.path.realpath(__file__))
if not os.path.exists("files"):
    os.mkdir("files")
shutil.copyfile(os.path.join(selfDir, "files", "login"), os.path.join("files", "login"))
shutil.copyfile(os.path.join(selfDir, "files", "passwd"), os.path.join("files", "passwd"))
shutil.copyfile(os.path.join(selfDir, "files", "system-auth"), os.path.join("files", "system-auth"))
try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
cp -f ${FILES}/{login,passwd,system-auth} ${D}/etc/pam.d
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
