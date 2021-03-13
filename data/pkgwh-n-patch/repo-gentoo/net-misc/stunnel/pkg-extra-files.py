#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/stunnel/stunnel.crt"
        echo "/etc/stunnel/stunnel.csr"
        echo "/etc/stunnel/stunnel.key"
        echo "/etc/stunnel/stunnel.pem"
}
""")
