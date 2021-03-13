#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/env.d/rust/last-set"

        echo "/usr/bin/cargo"
        echo "/usr/bin/rustc"
        echo "/usr/bin/rustdoc"
        echo "/usr/bin/rust-gdb"
        echo "/usr/bin/rust-gdbgui"
        echo "/usr/bin/rust-lldb"

        echo "/usr/lib/rustlib"
        echo "/usr/lib/rust/lib"
        echo "/usr/lib/rust/man"

        echo "/usr/share/doc/rust"
}
""")
