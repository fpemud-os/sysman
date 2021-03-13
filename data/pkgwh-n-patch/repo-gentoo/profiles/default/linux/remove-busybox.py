#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import pathlib

buf = pathlib.Path("./packages").read_text()
if "*sys-apps/busybox\n" in buf:
    with open("./packages", "w") as f:
        f.write(buf.replace("*sys-apps/busybox\n", ""))
else:
    print("outdated")
