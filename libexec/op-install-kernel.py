#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import bbki
import json
import pathlib
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from fm_util import PrintLoadAvgThread
from fm_param import FmConst


kernelCfgRules = json.loads(sys.argv[1])
resultFile = sys.argv[2]

bbki = bbki.Bbki(bbki.EtcDirConfig(FmConst.portageCfgDir))
kernelBuilder = bbki.get_kernel_installer(bbki.get_kernel_atom(), bbki.get_kernel_addon_atoms())
bootEntry = bbki.get_pending_boot_entry()
targetBootEntry = kernelBuilder.get_target_boot_entry()

print("        - Extracting...")
kernelBuilder.unpack()

print("        - Patching...")
kernelBuilder.patch_kernel()

print("        - Generating .config file...")
kernelBuilder.generate_kernel_dotcfg()

kernelBuildNeeded = False
if not kernelBuildNeeded:
    if bootEntry is None:
        kernelBuildNeeded = True
if not kernelBuildNeeded:
    if not bootEntry.has_kernel_files():
        kernelBuildNeeded = True
if not kernelBuildNeeded:
    if bootEntry != kernelBuilder.get_progress().target_boot_entry:
        kernelBuildNeeded = True
if not kernelBuildNeeded:
    if not FmUtil.dotCfgFileCompare(bootEntry.kernel_config_filepath, kernelBuilder.get_progress().kernel_config_filepath):
        kernelBuildNeeded = True

with PrintLoadAvgThread("        - Building..."):
    if kernelBuildNeeded:
        kernelBuilder.build()

with PrintLoadAvgThread("        - Installing..."):
    if kernelBuildNeeded:
        kernelBuilder.install()

# FIXME: should move out from here
print("        - Installing firmware and wireless-regdb...")
kernelBuilder.buildStepInstallFirmware()

if kernelBuildNeeded:
    kernelBuilder.buildStepClean()

os.makedirs(os.path.dirname(resultFile), exist_ok=True)
with open(resultFile, "w", encoding="iso8859-1") as f:
    f.write("%d\n" % (kernelBuildNeeded))
    f.write("%s\n" % (kernelBuilder.dstTarget.postfix))
