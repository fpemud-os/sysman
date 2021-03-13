#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/usr/sbin/iptables"
        echo "/usr/sbin/iptables-save"
        echo "/usr/sbin/iptables-restore"
        echo "/usr/sbin/iptables-xml"

        echo "/usr/sbin/ip6tables"
        echo "/usr/sbin/ip6tables-save"
        echo "/usr/sbin/ip6tables-restore"
}
""")
