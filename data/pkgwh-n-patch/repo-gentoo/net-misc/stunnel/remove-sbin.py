#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    for fn in glob.glob("*.ebuild"):
        lineList = pathlib.Path(fn).read_text().split("\n")
        lineList = [x for x in lineList if "dosym" not in x]
        with open(fn, "w") as f:
            f.write("\n".join(lineList))
except ValueError:
    print("outdated")
