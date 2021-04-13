#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import pathlib


fn = "drivers/bluetooth/btrtl.c"
try:
    # read
    buf = pathlib.Path(fn).read_text()

    # check
    if 'MODULE_FIRMWARE("rtl_bt/rtl8761b_fw.bin");' in buf:
        raise ValueError()
    if 'MODULE_FIRMWARE("rtl_bt/rtl8761b_config.bin");' in buf:
        raise ValueError()

    # modify
    buf += '\n'
    buf += 'MODULE_FIRMWARE("rtl_bt/rtl8761b_fw.bin");\n'
    buf += 'MODULE_FIRMWARE("rtl_bt/rtl8761b_config.bin");\n'
    with open(fn, "w") as f:
        f.write(buf)

except ValueError:
    print("outdated")
