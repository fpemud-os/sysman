#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import glob
import pathlib

pattern = r'\S+sys-fs/vhba-[0-9]+'
try:
    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        if re.search(pattern, buf) is None:
            raise ValueError()
        buf = re.sub(pattern, "", buf)

        # do insert
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
