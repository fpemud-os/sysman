#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/usr/include/cblas.h"
        echo "/usr/include/cblas_f77.h"
        echo "/usr/include/cblas_mangling.h"
        echo "/usr/include/cblas_test.h"
        echo "/usr/lib64/libcblas.a"
        echo "/usr/lib64/libcblas.so"
        echo "/usr/lib64/libcblas.so.3"
        echo "/usr/lib64/pkgconfig/cblas.pc"
}
""")
