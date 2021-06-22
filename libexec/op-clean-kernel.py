#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import glob
import robust_layer.simple_fops
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from helper_boot import FkmBootDir
from helper_boot import FkmBootEntry


bootDir = "/boot"
kernelModuleDir = "/lib/modules"
firmwareDir = "/lib/firmware"
resultFile = sys.argv[1]


print("        - Analyzing...")

# get file list to be removed in boot directory
bootFileList = sorted(FkmBootDir().getHistoryFileList())

# get file list to be removed in kernel module directory
moduleFileList = []
if True:
    moduleFileList = os.listdir(kernelModuleDir)
    ret = FkmBootEntry.findCurrent()
    if ret is not None:
        moduleFileList.remove(ret.buildTarget.verstr)
    moduleFileList = sorted([os.path.join(kernelModuleDir, f) for f in moduleFileList])

# get file list to be removed in firmware directory
firmwareFileList = []
if os.path.exists(firmwareDir):
    validList = []
    for ver in os.listdir(kernelModuleDir):
        if ver in moduleFileList:
            continue
        verDir = os.path.join(kernelModuleDir, ver)
        for fullfn in glob.glob(os.path.join(verDir, "**", "*.ko"), recursive=True):
            # python-kmod bug: can only recognize the last firmware in modinfo
            # so use the command output of modinfo directly
            for line in FmUtil.cmdCall("/bin/modinfo", fullfn).split("\n"):
                m = re.fullmatch("firmware: +(\\S.*)", line)
                if m is None:
                    continue
                firmwareName = m.group(1)
                if not os.path.exists(os.path.join(firmwareDir, firmwareName)):
                    continue
                validList.append(firmwareName)

    standardFiles = [
        ".ctime",
        "regulatory.db",
        "regulatory.db.p7s",
    ]
    for root, dirs, files in os.walk(firmwareDir):
        for filepath in files:
            firmwareName = os.path.join(re.sub("^/lib/firmware/?", "", root), filepath)
            if firmwareName in standardFiles:
                continue
            if firmwareName in validList:
                continue
            firmwareFileList.append(firmwareName)

# show file list to be removed in boot directory
print("            Items to be removed in \"/boot\":")
if len(bootFileList) == 0:
    print("              None")
else:
    for f in bootFileList:
        print("              %s" % (f))

# show file list to be removed in kernel module directory
print("            Items to be removed in \"%s\":" % (kernelModuleDir))
if len(moduleFileList) == 0:
    print("              None")
else:
    for f in moduleFileList:
        assert os.path.isdir(os.path.join(kernelModuleDir, f))
        print("              %s/" % (f))

# show file list to be removed in firmware directory
print("            Items to be removed in \"%s\":" % (firmwareDir))
if len(firmwareFileList) == 0:
    print("              None")
else:
    for f in firmwareFileList:
        print("              %s" % (f))

# remove files
if len(bootFileList) > 0 or len(moduleFileList) > 0 or len(firmwareFileList) > 0:
    ret = 1
    print("        - Deleting...")
    for f in bootFileList:
        robust_layer.simple_fops.rm(os.path.join(bootDir, f))
    for f in moduleFileList:
        robust_layer.simple_fops.rm(os.path.join(kernelModuleDir, f))
    for f in firmwareFileList:
        fullfn = os.path.join(firmwareDir, f)
        robust_layer.simple_fops.rm(os.path.join(firmwareDir, f))
        d = os.path.dirname(fullfn)
        if len(os.listdir(d)) == 0:
            os.rmdir(d)
else:
    ret = 0

# write result file
os.makedirs(os.path.dirname(resultFile), exist_ok=True)
with open(resultFile, "w", encoding="iso8859-1") as f:
    f.write("%d\n" % (ret))
