#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

tstr = "!sysv-utils? ( sys-apps/sysvinit )"
try:
    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        if tstr not in buf:
            raise ValueError()
        buf = buf.replace(tstr, "")

        # do insert
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
