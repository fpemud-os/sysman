#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/eselect/wine/**"

        echo "/usr/include/wine"
        echo "/usr/include/wine-vanilla"
        echo "/usr/include/wine-staging"

        echo "/usr/share/applications/wine.desktop"
        echo "/usr/share/applications/wine-vanilla.desktop"
        echo "/usr/share/applications/wine-staging.desktop"
}
""")
