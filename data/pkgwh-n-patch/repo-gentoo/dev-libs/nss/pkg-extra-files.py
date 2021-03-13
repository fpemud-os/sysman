#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/usr/lib/libfreebl3.chk"
        echo "/usr/lib/libnssdbm3.chk"
        echo "/usr/lib/libsoftokn3.chk"

        echo "/usr/lib64/libfreebl3.chk"
        echo "/usr/lib64/libnssdbm3.chk"
        echo "/usr/lib64/libsoftokn3.chk"
}
""")
