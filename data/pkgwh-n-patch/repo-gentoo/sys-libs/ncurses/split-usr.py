#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import glob
import pathlib


tstr = """
multilib_src_install_all() {
	if use minimal ; then
		# Only keeps the basic terminfo files
		local terms=(
			# Dumb/simple values that show up when using the in-kernel VT.
			ansi console dumb linux
			vt{52,100,102,200,220}
			# [u]rxvt users used to be pretty common.  Probably should drop this
			# since upstream is dead and people are moving away from it.
			rxvt{,-unicode}{,-256color}
			# xterm users are common, as is terminals re-using/spoofing it.
			xterm xterm-{,256}color
			# screen is common (and reused by tmux).
			screen{,-256color}
			screen.xterm-256color
		)
		local x
		for x in $(find "${ED}"/usr/share/terminfo/ -type f 2>/dev/null); do
			if [[ " ${terms[*]} " != *" $(basename ${x}) "* ]]; then
				rm "${x}" || die
			fi
		done
	fi

	cd "${S}" || die
	dodoc ANNOUNCE MANIFEST NEWS README* TO-DO doc/*.doc
	if use doc ; then
		docinto html
		dodoc -r doc/html/
	fi
}
"""

bBad = False
for fn in glob.glob("*.ebuild"):
    lineList = pathlib.Path(fn).read_text().split("\n")

    # remove --with-terminfo-dirs= line and all the comments above
    idx = None
    for i in range(0, len(lineList)):
        if re.fullmatch(r'\s*--with-terminfo-dirs=.*', lineList[i]):
            idx = i
            break
    if idx is None:
        bBad = True
        break
    while idx >= 0:
        lineList.pop(idx)
        idx -= 1
        if not re.fullmatch(r'\s*#.*', lineList[idx]):
            break

    # replace multilib_src_install_all()
    idx = None
    for i in range(0, len(lineList)):
        if lineList[i].rstrip() == "multilib_src_install_all() {":
            idx = i
            break
    if idx is None:
        bBad = True
        break
    i = idx
    while i < len(lineList):
        lineList.pop(i)
        if lineList[i].rstrip() == "}":
            lineList.pop(i)
            break
    if i == len(lineList):
        bBad = True
        break
    lineList = lineList[:idx] + tstr.split("\n") + lineList[idx:]

    # berkdb USE flag
    if False:
        # re-add berkdb USE flag
        idx = None
        for i in range(0, len(lineList)):
            if re.fullmatch(r'IUSE=.*', lineList[i]):
                idx = i
                break
        if idx is None:
            bBad = True
            break
        if "berkdb" in lineList[idx]:
            bBad = True
            break
        lineList[idx] = lineList[idx].replace("IUSE=\"", "IUSE=\"berkdb ")

        # re-add berkdb dependency
        idx = None
        for i in range(0, len(lineList)):
            if re.fullmatch(r'#\s*berkdb\?', lineList[i]):
                idx = i
                break
        if idx is None:
            bBad = True
            break
        lineList[idx] = lineList[idx].replace("#", " ")

        # re-add berkdb configuration, remove all the comments above
        idx = None
        for i in range(0, len(lineList)):
            if lineList[i].strip() == "#$(use_with berkdb hashed-db)":
                idx = i
                break
        if idx is None:
            bBad = True
            break
        lineList[idx] = lineList[idx].replace("#", "")
        while idx >= 0:
            idx -= 1
            if not re.fullmatch(r'\s*#.*', lineList[idx]):
                break
            lineList.pop(idx)

    with open(fn, "w") as f:
        f.write("\n".join(lineList))

if bBad:
    print("outdated")
