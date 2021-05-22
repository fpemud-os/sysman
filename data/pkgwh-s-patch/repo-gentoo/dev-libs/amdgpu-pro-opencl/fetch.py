#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import glob
import pathlib

try:
    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        m = re.search(r'^SRC_URI="(.*)"', buf, flags=re.M)
        if m is None:
            raise ValueError()
        if m.group(1).startswith("https://"):
            raise ValueError()
        buf = re.sub(r'^SRC_URI="', r'SRC_URI="https://drivers.amd.com/drivers/linux/', buf, flags=re.M)

        # write back to the original file
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
