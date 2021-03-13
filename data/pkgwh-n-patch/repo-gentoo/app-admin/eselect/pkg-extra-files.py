#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        # eselect-locale
        echo "/etc/locale.conf"
        echo "/etc/env.d/02locale"              # symlink to /etc/locale.conf

        # eselect-editor
        echo "/etc/env.d/99editor"

        # eselect-news
        echo "/var/lib/gentoo"
        echo "/var/lib/gentoo/news/***"
}""")
