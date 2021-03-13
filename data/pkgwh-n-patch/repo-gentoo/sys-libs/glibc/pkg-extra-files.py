#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        # for ldconfig
        echo "/etc/ld.so.conf"
        echo "/etc/ld.so.conf.d"        # directory
        echo "/etc/ld.so.cache"
        echo "/var/cache/ldconfig/***"

        # for locales
        echo "/usr/lib/locale/**"

        # for gconv
        echo "/usr/lib64/gconv/gconv-modules.cache"             # why there's no cache file in /usr/lib?

        # for standard log files
        echo "/var/log/btmp"
        echo "/var/log/wtmp"
}
""")
