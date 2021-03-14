#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

# package installs many files into /var/lib/i2pd
# so we can't have a remove-var.py

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/var/lib/i2pd/***"
}
""")
