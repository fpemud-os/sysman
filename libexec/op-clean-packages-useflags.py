#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import pathlib
from gentoolkit.dependencies import Dependencies
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from fm_param import FmConst
from helper_pkg_merger import PkgMerger


bPretend = (sys.argv[1] != "0")
assert not bPretend

i = 1
while True:
    # remove unused packages
    pkgChanged = False
    print("        - Cycle %d: removing unused packages..." % (i))
    if not bPretend:
        list1 = FmUtil.getFileList(FmConst.portageDbDir, 2, "d")
        FmUtil.cmdCall("/usr/bin/emerge", "--depclean")
        list2 = FmUtil.getFileList(FmConst.portageDbDir, 2, "d")
        pkgChanged |= (list1 != list2)
    else:
        FmUtil.cmdExec("/usr/bin/emerge", "--depclean", "--pretend")
    print("")

    # clean python
    if os.path.exists("/usr/share/eselect/modules/python.eselect"):
        print("        - Cycle %d: cleaning python..." % (i))
        if not bPretend:
            FmUtil.cmdCall("/usr/bin/eselect", "python", "cleanup")
        else:
            FmUtil.cmdCall("/usr/bin/eselect", "python", "list")
        print("")

    # clean perl
    if os.path.exists("/usr/sbin/perl-cleaner"):
        print("        - Cycle %d: cleaning perl related packages..." % (i))
        if not bPretend:
            list1 = FmUtil.getFileList(FmConst.portageDbDir, 2, "d")
            FmUtil.cmdCall("/usr/sbin/perl-cleaner", "--all")
            list2 = FmUtil.getFileList(FmConst.portageDbDir, 2, "d")
            pkgChanged |= (list1 != list2)
        else:
            FmUtil.cmdExec("/usr/sbin/perl-cleaner", "--all", "-p")
        print("")

    # clean preserved libraries
    print("        - Cycle %d: cleaning preserved libraries..." % (i))
    if not bPretend:
        list1 = FmUtil.getFileList(FmConst.portageDbDir, 2, "d")
        FmUtil.cmdCall("/usr/bin/revdep-rebuild")
        list2 = FmUtil.getFileList(FmConst.portageDbDir, 2, "d")
        pkgChanged |= (list1 != list2)
    else:
        FmUtil.cmdExec("/usr/bin/revdep-rebuild", "-p")
    print("")

    # remove unused USE flags
    print("        - Cycle %d: removing unused USE flags..." % (i))
    if not bPretend:
        fn = os.path.join(FmConst.portageCfgUseDir, "99-autouse")
        buf = pathlib.Path(fn).read_text()

        useMap = dict()
        for pkgAtom, useList in FmUtil.portageParseCfgUseFile(buf):
            pkgName = FmUtil.portageGetPkgNameFromPkgAtom(pkgAtom)
            if pkgName in useMap:
                useMap[pkgName] |= set(useList)
            else:
                useMap[pkgName] = set(useList)

        # don't keep use flag for not-installed package
        for pkgName in list(useMap.keys()):
            if not FmUtil.portageIsPkgInstalled(pkgName):
                del useMap[pkgName]

        # FIXME
        # only keep use flag that depends by other packages (unneccessary circular-dependency?)
        # for pkgName, useList in useMap.items():
        #     depObj = Dependencies(pkgName)
        #     depObj.graph_reverse_depends()

        buf2 = FmUtil.portageGenerateCfgUseFileByUseMap(useMap)

        if buf != buf2:
            with open(fn, "w") as f:
                f.write(buf2)
            pkgChanged = True
    print("")

    # pretend mode, no further process
    if bPretend:
        print("Leaving all items untouched!")
        break

    # all finished
    if not pkgChanged:
        print("        - Cycle %d: no more changes, all finished..." % (i))
        break

    # rebuild pacakges
    print("        - Cycle %d: rebuilding..." % (i))
    PkgMerger().emergePkg("-uDN1 --with-bdeps=y @installed", autouse=False)
    i += 1
    print("")
