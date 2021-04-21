#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from helper_pkg_merger import PkgMerger


PkgMerger().emergePkg("-uDN --with-bdeps=y @world")
PkgMerger().emergePkg("@preserved-rebuild")

# sometimes emerge leaves /var/tmp/portage behind
FmUtil.forceDelete("/var/tmp/portage")

print("")
