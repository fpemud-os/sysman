#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import pathlib

buf = pathlib.Path("./use.force").read_text()
if "\nsplit-usr\n" in buf:
    with open("./use.force", "w") as f:
        f.write(buf.replace("\nsplit-usr\n", "\n#split-usr\n"))
else:
    print("outdated")
