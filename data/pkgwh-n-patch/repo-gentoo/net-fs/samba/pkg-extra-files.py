#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/samba/***"
        echo "/var/cache/samba/***"
        echo "/var/lib/ctdb/***"
        echo "/var/lib/samba/***"
        echo "/var/log/samba/***"
}
""")
