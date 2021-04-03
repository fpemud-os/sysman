#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import pathlib

fn = "./git-r3.eclass"
try:
	buf = pathlib.Path(fn).read_text()
	buf2 = buf.replace("git fetch", "/usr/libexec/robust_layer/git fetch")
	if buf2 == buf:
		raise ValueError()
	with open(fn, "w") as f:
		f.write(buf2)
except Exception:
    print("outdated")
