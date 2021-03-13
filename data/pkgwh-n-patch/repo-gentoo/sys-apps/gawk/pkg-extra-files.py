#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/bin/awk"             # FIXME: should consider split-usr USE flag
        echo "/usr/bin/awk"
        echo "/usr/share/man/man1/awk.1.bz2"
}
""")
