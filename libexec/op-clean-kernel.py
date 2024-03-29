#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import strict_hdds

sys.path.append('/usr/lib64/fpemud-os-sysman')
from helper_bbki import BbkiWrapper
from helper_bbki import BootDirWriter


runMode = sys.argv[1]
bPretend = (sys.argv[2] != "0")
pretendPrefix = "to be " if bPretend else ""
resultFile = sys.argv[3]


# do clean
print("        - Processing...")
if runMode in ["normal", "setup"]:
    layout = strict_hdds.get_storage_layout()
else:
    layout = None
bbkiObj = BbkiWrapper(layout)
bootFileList, moduleFileList, firmwareFileList = [], [], []
if not bPretend:
    with BootDirWriter(layout):
        bootFileList, moduleFileList, firmwareFileList = bbkiObj.clean_boot_entry_files(pretend=bPretend)
else:
    bootFileList, moduleFileList, firmwareFileList = bbkiObj.clean_boot_entry_files(pretend=bPretend)

# show file list to be removed in boot directory
print("            Items %sremoved in \"/boot\":" % (pretendPrefix))
if len(bootFileList) == 0:
    print("              None")
else:
    for f in bootFileList:
        print("              %s" % (f))

# show file list to be removed in kernel module directory
print("            Items %sremoved in \"/lib/modules\":" % (pretendPrefix))
if len(moduleFileList) == 0:
    print("              None")
else:
    for f in moduleFileList:
        print("              %s" % (f))

# show file list to be removed in firmware directory
print("            Items %sremoved in \"/lib/firmware\":" % (pretendPrefix))
if len(firmwareFileList) == 0:
    print("              None")
else:
    for f in firmwareFileList:
        print("              %s" % (f))

# files removed?
if not bPretend and (len(bootFileList) > 0 or len(moduleFileList) > 0 or len(firmwareFileList) > 0):
    ret = 1
else:
    ret = 0

# write result file
os.makedirs(os.path.dirname(resultFile), exist_ok=True)
with open(resultFile, "w", encoding="iso8859-1") as f:
    f.write("%d\n" % (ret))
