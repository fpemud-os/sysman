#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    for fn in glob.glob("*.ebuild"):
        newBuf = ""
        for line in pathlib.Path(fn).read_text().split("\n"):
            if "/var/lib/bitcoin" not in line:
                newBuf += line + "\n"
        with open(fn, "w") as f:
            f.write(newBuf)
except ValueError:
    print("outdated")
