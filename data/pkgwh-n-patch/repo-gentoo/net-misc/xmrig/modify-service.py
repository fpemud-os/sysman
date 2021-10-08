#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import pathlib

fn = "files/xmrig.service"
try:
    buf = pathlib.Path(fn).read_text()

    # check
    if re.search("^DynamicUser=true$", buf, re.M) is None:
        raise ValueError()
    if re.search("^CapabilityBoundingSet=$", buf, re.M) is None:
        raise ValueError()
    if re.search("^ProtectKernelModules=true$", buf, re.M) is None:
        raise ValueError()
    if re.search("^PrivateUsers=true$", buf, re.M) is None:
        raise ValueError()

    # modify, so that the following function can take effect:
    # 1. /usr/bin/randomx_boost.sh
    # 2. built-in msr operation
    buf = buf.replace("DynamicUser=true", "#DynamicUser=true")
    buf = buf.replace("CapabilityBoundingSet=", "#CapabilityBoundingSet=")
    buf = buf.replace("ProtectKernelModules=true", "#ProtectKernelModules=true")
    buf = buf.replace("PrivateUsers=true", "#PrivateUsers=true")

    with open(fn, "w") as f:
        f.write(buf)
except ValueError:
    print("outdated")
