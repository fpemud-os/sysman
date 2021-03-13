#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import glob
import pathlib

found = False
for fn in glob.glob("*.ebuild"):
    buf = pathlib.Path(fn).read_text()
    if re.search("IUSE=.*split-usr.*", buf, re.M) is not None:
        continue

    buf2 = buf.replace("IUSE=\"", "IUSE=\"+split-usr ")
    assert buf != buf2
    buf = buf2

    buf2 = buf.replace("if ! [[ -e ${EROOT}/bin/awk ]] ; then", "if ! [[ -e ${EROOT}/bin/awk ]] && use split-usr ; then")
    buf3 = buf.replace("[[ ! -e ${EROOT}/bin/awk ]] && ", "[[ ! -e ${EROOT}/bin/awk ]] && use split-usr && ")
    if buf2 != buf and buf3 == buf:
        buf = buf2
    elif buf3 != buf and buf2 == buf:
        buf = buf3
    else:
        assert False

    with open(fn, "w") as f:
        f.write(buf)
    found = True

if not found:
    print("outdated")
