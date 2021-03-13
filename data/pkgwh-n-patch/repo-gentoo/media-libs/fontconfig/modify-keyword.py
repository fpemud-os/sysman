#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import glob
import pathlib

# only <=fontconfig-2.13.90 has keyword ~* in the orginal ebuild
# make the keyword available in every version
tstr = r'\[\[ \$\(ver_cut 3\) -ge [0-9]+ \]\]'
try:
    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()
        m = re.search(tstr, buf)
        if m is None:
            raise ValueError()
        buf = buf.replace(m.group(0), "false")
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
