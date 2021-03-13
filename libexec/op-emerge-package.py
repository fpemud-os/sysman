#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from helper_pkg_merger import PkgMerger


pkgName = sys.argv[1]
tmpOp = sys.argv[2]                 # "0" or "1"

if not tmpOp and FmUtil.portageIsPkgInstalled(pkgName):
    print("The specified package is already installed.")
else:
    PkgMerger().emergePkg("%s %s" % ("-1" if tmpOp == "1" else "", pkgName))
