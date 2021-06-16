#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
sys.path.append('/usr/lib64/fpemud-os-sysman')
from helper_boot_kernel import FkmKCache


item = sys.argv[1]

if item == "kernel":
    postfix = sys.argv[2]
    kcache = FkmKCache()
    kcache.updateKernelCache(postfix)
    sys.exit(0)

if item == "firmware":
    version = sys.argv[2]
    kcache = FkmKCache()
    kcache.updateFirmwareCache(version)
    sys.exit(0)

if item == "extra-driver-source":
    name = sys.argv[2]
    sourceName = sys.argv[3]
    bForce = (sys.argv[4] != "0")

    kcache = FkmKCache()
    sourceInfo = kcache.getExtraDriverSourceInfo(name)
    assert sourceName == sourceInfo["name"]
    kcache.updateExtraSourceCache(sourceInfo, bForce)
    sys.exit(0)

if item == "extra-firmware-source":
    name = sys.argv[2]
    sourceName = sys.argv[3]
    bForce = (sys.argv[4] != "0")

    kcache = FkmKCache()
    sourceInfo = kcache.getExtraFirmwareSourceInfo(name)
    assert sourceName == sourceInfo["name"]
    kcache.updateExtraSourceCache(sourceInfo, bForce)
    sys.exit(0)

if item == "wireless-regdb":
    ver = sys.argv[2]
    kcache = FkmKCache()
    kcache.updateWirelessRegDbCache(ver)
    sys.exit(0)

assert False
