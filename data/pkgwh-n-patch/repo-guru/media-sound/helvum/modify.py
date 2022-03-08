#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        if "gui-libs/gtk" in buf:
            raise ValueError()

        buf += "\n"
        buf += 'DEPEND="${DEPEND} gui-libs/gtk\n'
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
