#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/passwd"
        echo "/etc/group"
        echo "/etc/shadow"
        echo "/etc/gshadow"
        echo "/etc/subuid"
        echo "/etc/subgid"

        echo "/etc/passwd-"
        echo "/etc/group-"
        echo "/etc/shadow-"
        echo "/etc/gshadow-"
        echo "/etc/subuid-"
        echo "/etc/subgid-"

        # FIXME: I think this file should be deleted when the operation completes
        echo "/etc/.pwd.lock"

        echo "/var/log/lastlog"
}
""")
