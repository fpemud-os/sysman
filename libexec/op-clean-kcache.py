#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
import strict_hdds
sys.path.append('/usr/lib64/fpemud-os-sysman')
from helper_bbki import BbkiWrapper

runMode = sys.argv[1]
bPretend = (sys.argv[2] != "0")
pretendPrefix = "to be " if bPretend else ""

print("        - Processing...")
if runMode in ["normal", "setup"]:
    layout = strict_hdds.get_storage_layout()
else:
    layout = None
bbkiObj = BbkiWrapper(layout)
fileList = bbkiObj.clean_distfiles(pretend=bPretend)

# show file list to be removed in BBKI distfiles directory
print("            Files %sremoved in \"%s\":" % (pretendPrefix, bbkiObj.config.cache_distfiles_dir))
if fileList == []:
    print("              None")
else:
    for f in fileList:
        print("              %s" % (f))
