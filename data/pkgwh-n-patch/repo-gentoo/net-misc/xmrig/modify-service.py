#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import pathlib

fn = "files/xmrig.service"
try:
    buf = pathlib.Path(fn).read_text()

    # check
    if re.search("^PrivateDevices=true$", buf, re.M) is None:
        raise ValueError()
    if re.search("^ProtectClock=true$", buf, re.M) is None:
        raise ValueError()

    # modify, so that /usr/bin/randomx_boost.sh can take effect
    buf = buf.replace("PrivateDevices=true", "#PrivateDevices=true")
    buf = buf.replace("ProtectClock=true", "#ProtectClock=true")
    with open(fn, "w") as f:
        f.write(buf)
except ValueError:
    print("outdated")
