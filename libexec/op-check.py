#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
sys.path.append('/usr/lib64/fpemud-os-sysman')
from helper_boot_kernel import FkmKCacheUpdater
from helper_pkg_merger import PkgMerger


item = sys.argv[1]
bAutoFix = (sys.argv[2] != "0")

if item == "linguas-use-flags":
    assert False
    sys.exit(0)

if item == "repository":
    assert False
    sys.exit(0)

if item == "overlay":
    assert False
    sys.exit(0)

if item == "per-package-check":
    assert False
    sys.exit(0)

if item == "find-cruft":
    assert False
    sys.exit(0)

assert False
