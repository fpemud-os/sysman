#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
# it seems that /etc/fstab is installed in pkg_postinst so INSTALL_MASK has no effect.
rm -f "${D}/etc/fstab"

# INSTALL_MASK has no effect, so we do this, strange.
rm -f "${D}/etc/sysctl.conf"

# move /etc/modprobe.d to /usr/lib/modprobe.d
mv "${D}/etc/modprobe.d" "${D}/usr/lib"
mkdir "${D}/etc/modprobe.d"
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
