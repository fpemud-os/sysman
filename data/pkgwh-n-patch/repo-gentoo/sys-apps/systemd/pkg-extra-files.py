#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/machine-id"
        echo "/etc/machine-info"

        echo "/etc/udev/hwdb.bin"
        echo "/etc/udev/rules.d/**"             # rules added by system admin

        echo "/etc/systemd/system/**"           # unit symlinks and override files created by system admin

        echo "/var/lib/systemd/***"

        echo "/var/log/journal/***"

        echo "/var/cache/private"
        echo "/var/lib/private"
        echo "/var/log/private"

        echo "~/.config/systemd/***"
        echo "~/.local/share/systemd/***"
}
""")
