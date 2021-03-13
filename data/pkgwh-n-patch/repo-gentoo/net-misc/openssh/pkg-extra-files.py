#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/ssh/ssh_host_key"
        echo "/etc/ssh/ssh_host_key.pub"

        echo "/etc/ssh/ssh_host_dsa_key"
        echo "/etc/ssh/ssh_host_dsa_key.pub"

        echo "/etc/ssh/ssh_host_ecdsa_key"
        echo "/etc/ssh/ssh_host_ecdsa_key.pub"

        echo "/etc/ssh/ssh_host_ed25519_key"
        echo "/etc/ssh/ssh_host_ed25519_key.pub"

        echo "/etc/ssh/ssh_host_rsa_key"
        echo "/etc/ssh/ssh_host_rsa_key.pub"

        echo "~/.ssh"
        echo "~/.ssh/id_rsa"
        echo "~/.ssh/id_rsa.pub"
        echo "~/.ssh/authorized_keys"
        echo "~/.ssh/known_hosts"
}
""")
