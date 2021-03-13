#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        # sys-libs/db fix its so files in pkg_postinst()
        # if it can be in src_install() then the following code is not neccessary

        echo "/usr/include/db.h"
        echo "/usr/include/db_185.h"
        # echo "/usr/include/db_cxx.h"                  # why this file has no symlink?

        echo "/usr/lib/libdb.so"
        echo "/usr/lib/libdb_cxx.so"
        echo "/usr/lib/libdb_stl.so"

        echo "/usr/lib64/libdb.so"
        echo "/usr/lib64/libdb_cxx.so"
        echo "/usr/lib64/libdb_stl.so"
}
""")
