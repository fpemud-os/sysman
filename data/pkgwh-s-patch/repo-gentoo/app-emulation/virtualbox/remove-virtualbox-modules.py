#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import glob
import pathlib

try:
    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()
        m = re.search(".*app-emulation/virtualbox-modules-.*", buf, re.M)
        if m is None:
            raise ValueError()
        buf = buf.replace(m.group(0), "")
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
