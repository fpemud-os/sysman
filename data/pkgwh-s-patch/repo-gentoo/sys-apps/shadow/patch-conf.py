#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
find "${D}" -name "*sg*" | xargs rm -f
find "${D}" -name "*chgpasswd*" | xargs rm -f
find "${D}" -name "*gpasswd*" | xargs rm -f
find "${D}" -name "*newgrp*" | xargs rm -f

# change SUB_UID_COUNT / SUB_GID_COUNT from 65536 to 100000
# the orginal configuration leads to unaligned range in /etc/subuid
sed -i 's/\(^SUB_UID_COUNT\s*\)  [0-9].*$/\\1 100000/g' "${D}/etc/login.defs"      # why we can't use "[0-9]+", sed bug? we remove one space.
sed -i 's/\(^SUB_GID_COUNT\s*\)  [0-9].*$/\\1 100000/g' "${D}/etc/login.defs"      # same as above
## end ####"""
    buf2 = buf2.replace("\n", "\n\t")
    buf2 += "\n"

    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        # insert to the end of src_install()
        pos = buf.find("src_install() {")
        if pos == -1:
            raise ValueError()
        pos = buf.find("\n}\n", pos)
        if pos == -1:
            raise ValueError()
        pos += 1

        # do insert
        buf = buf[:pos] + buf2 + buf[pos:]
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
