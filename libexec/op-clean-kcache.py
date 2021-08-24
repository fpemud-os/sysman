#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
import bbki
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_param import FmConst


bPretend = (sys.argv[1] != "0")
pretendPrefix = "to be " if bPretend else ""

print("        - Processing...")
bbki = bbki.Bbki(bbki.EtcDirConfig(FmConst.portageCfgDir))
fileList = bbki.clean_distfiles(prtend=bPretend)

# show file list to be removed in BBKI distfiles directory
print("            Files %sremoved in \"%s\":" % (pretendPrefix, bbki.config.cache_distfiles_dir))
if fileList == []:
    print("              None")
else:
    for f in fileList:
        print("              %s" % (f))
