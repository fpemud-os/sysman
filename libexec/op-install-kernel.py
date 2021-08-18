#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import bbki
import base64
import pickle
import pathlib
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from fm_util import PrintLoadAvgThread
from fm_param import FmConst
from helper_boot_kernel import FkmBootEntry
from helper_boot_kernel import FkmKernelBuilder
from helper_boot_kernel import FkmKCache


kernelCfgRules = pickle.loads(base64.b64decode(sys.argv[1].encode("ascii")))
resultFile = sys.argv[2]

bbki = bbki.Bbki(bbki.EtcDirConfig(FmConst.portageCfgDir))
kernelBuilder = bbki.get_kernel_installer(bbki.HostInfo(arch="native"), bbki.get_kernel_atom(), bbki.get_kernel_addon_atoms())
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
    if bootEntry != targetBootEntry:
        kernelBuildNeeded = True
if not kernelBuildNeeded:
    if not FmUtil.dotCfgFileCompare(bootEntry.kernel_config_filepath, kernelBuilder.dotCfgFile):
        kernelBuildNeeded = True

with PrintLoadAvgThread("        - Building..."):
    if kernelBuildNeeded:
        kernelBuilder.buildStepMakeInstall()
        for name in kcache.getExtraDriverList():
            kernelBuilder.buildStepBuildAndInstallExtraDriver(name)

# FIXME: should move out from here
print("        - Installing firmware and wireless-regdb...")
kernelBuilder.buildStepInstallFirmware()

if kernelBuildNeeded:
    kernelBuilder.buildStepClean()

os.makedirs(os.path.dirname(resultFile), exist_ok=True)
with open(resultFile, "w", encoding="iso8859-1") as f:
    f.write("%d\n" % (kernelBuildNeeded))
    f.write("%s\n" % (kernelBuilder.dstTarget.postfix))
