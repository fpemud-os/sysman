#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
import robust_layer.simple_fops
sys.path.append('/usr/lib64/fpemud-os-sysman')
from helper_pkg_merger import PkgMerger


PkgMerger().emergePkg("-uDN --with-bdeps=y @world")
PkgMerger().emergePkg("@preserved-rebuild")

# sometimes emerge leaves /var/tmp/portage behind
robust_layer.simple_fops.rm("/var/tmp/portage")

print("")
