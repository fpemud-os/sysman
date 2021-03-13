#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from fm_param import FmConst
from helper_boot import FkmBootEntry
from helper_boot_kernel import FkmKCacheUpdater


kcacheUpdater = FkmKCacheUpdater()

print("        - Analyzing...")

# get kernel file list to be removed in cache directory
kernelFileList = []
ret = FkmBootEntry.findCurrent()
if ret is not None:
    kernelFileList = kcacheUpdater.getOldKernelFileList(ret)

# show information
print("            Kernel files to be removed in \"%s\":" % (FmConst.kcacheDir))
if kernelFileList == []:
    print("              None")
else:
    for f in kernelFileList:
        print("              %s" % (f))

# get kernel firmware file list to be removed in cache directory
firmwareFileList = kcacheUpdater.getOldFirmwareFileList()

# show information
print("            Firmware files to be removed in \"%s\":" % (FmConst.kcacheDir))
if firmwareFileList == []:
    print("              None")
else:
    for f in firmwareFileList:
        print("              %s" % (f))

# get wireless-reg-db file list to be removed in cache directory
wirelessRegDbFileList = kcacheUpdater.getOldWirelessRegDbFileList()

# show information
print("            Wireless regulatory database files to be removed in \"%s\":" % (FmConst.kcacheDir))
if wirelessRegDbFileList == []:
    print("              None")
else:
    for f in wirelessRegDbFileList:
        print("              %s" % (f))

# remove files
if len(kernelFileList) > 0 or len(firmwareFileList) > 0 or len(wirelessRegDbFileList) > 0:
    print("        - Deleting...")
    for f in kernelFileList:
        FmUtil.forceDelete(os.path.join(FmConst.kcacheDir, f))
    for f in firmwareFileList:
        FmUtil.forceDelete(os.path.join(FmConst.kcacheDir, f))
    for f in wirelessRegDbFileList:
        FmUtil.forceDelete(os.path.join(FmConst.kcacheDir, f))
