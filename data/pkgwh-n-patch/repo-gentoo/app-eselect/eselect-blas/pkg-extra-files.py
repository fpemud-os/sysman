#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/usr/lib64/libblas.a"
        echo "/usr/lib64/libblas.so"
        echo "/usr/lib64/libblas.so.3"
        echo "/usr/lib64/pkgconfig/blas.pc"
}
""")
