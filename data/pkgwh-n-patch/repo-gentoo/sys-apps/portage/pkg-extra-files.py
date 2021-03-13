#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/portage/**"

        echo "/etc/profile.env"
        echo "/etc/csh.env"
        echo "/etc/environment.d"                               # this two files are portage generated systemd
        echo "/etc/environment.d/10-gentoo-env.conf"            # user service environment variables setting

        echo "/var/cache/edb/***"

        echo "/var/db/pkg/***"

        echo "/var/log/emerge-fetch.log"
        echo "/var/log/emerge.log"
        echo "/var/log/portage/***"
}
""")
