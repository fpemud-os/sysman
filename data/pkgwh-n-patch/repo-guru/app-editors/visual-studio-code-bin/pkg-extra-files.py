#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        # it's strange that ~/.vscode and ~/.config/XXX is used simutanously
        echo "~/.vscode"
        echo "~/.vscode/***"
        echo "~/.config/Code"
        echo "~/.config/Code/***"
}
""")
