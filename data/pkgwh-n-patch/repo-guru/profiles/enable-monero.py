#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import pathlib

buf = pathlib.Path("./package.mask").read_text()
if "\nnet-p2p/monero" in buf:
    with open("./package.mask", "w") as f:
        f.write(buf.replace("\nnet-p2p/monero", "\n#net-p2p/monero\n"))
else:
    print("outdated")
