#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/usr/lib/gio/modules/giomodule.cache"                     # for md5 check
        echo "/usr/share/glib-2.0/schemas/gschemas.compiled"            # for md5 check
}
""")
