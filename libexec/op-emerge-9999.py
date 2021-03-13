#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import sys
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from fm_param import FmConst
from helper_pkg_merger import PkgMerger


# get all installed packages with version "-9999"
pkgList = []
for pkgAtom in FmUtil.portageGetInstalledPkgAtomList(FmConst.portageDbDir):
    m = re.fullmatch(r'(.*/.*)-9999+', pkgAtom)       # 9999 or more
    if m is not None:
        pkgList.append(m.group(1))

# emerge package
PkgMerger().emergePkg("-1 --keep-going %s" % (" ".join(pkgList)))
