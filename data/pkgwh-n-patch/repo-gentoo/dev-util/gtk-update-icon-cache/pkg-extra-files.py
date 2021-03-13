#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        if [[ -d /usr/share/icons ]] ; then
                for fn in /usr/share/icons/* ; do
                        if [[ -f ${fn}/index.theme ]] ; then
                                echo "${fn}/icon-theme.cache"
                        fi
                done
        fi
}
""")
