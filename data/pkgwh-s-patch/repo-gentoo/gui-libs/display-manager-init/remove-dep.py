#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import glob
import pathlib

try:
    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        if re.search(r'\S+sys-apps/sysvinit.*$', buf, re.M) is None:
            raise ValueError()
        buf = re.sub(r'\S+sys-apps/sysvinit.*$', "", buf, re.M)

        # do insert
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
