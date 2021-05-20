#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import curses
import base64
import pickle
import pathlib
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from fm_util import PrintLoadAvgThread
from helper_boot_kernel import FkmBootEntry
from helper_boot_kernel import FkmKernelBuilder
from helper_boot_kernel import FkmKCache
from helper_boot_initramfs import FkmInitramfsKcfgChecker


kernelCfgRules = pickle.loads(base64.b64decode(sys.argv[1].encode("ascii")))
resultFile = sys.argv[2]

curses.setupterm()

bootEntry = FkmBootEntry.findCurrent(strict=False)
kcache = FkmKCache()
kernelBuilder = FkmKernelBuilder(kcache, kernelCfgRules)

print("        - Extracting...")
kernelBuilder.buildStepExtract()

print("        - Generating .config file...")
kernelBuilder.buildStepGenerateDotCfg()

print("        - Checking .config file...")
c = FkmInitramfsKcfgChecker()
c.check(kernelBuilder.realSrcDir, kernelBuilder.dotCfgFile)

kernelBuildNeeded = False
if not kernelBuildNeeded:
    if bootEntry is None:
        kernelBuildNeeded = True
if not kernelBuildNeeded:
    if not bootEntry.kernelFilesExists():
        kernelBuildNeeded = True
if not kernelBuildNeeded:
    if bootEntry.buildTarget.ver != kernelBuilder.kernelVer:
        kernelBuildNeeded = True
if not kernelBuildNeeded:
    if kernelBuilder.srcSignature != pathlib.Path(bootEntry.kernelSrcSignatureFile).read_text():
        kernelBuildNeeded = True
if not kernelBuildNeeded:
    if not FmUtil.dotCfgFileCompare(os.path.join("/boot", bootEntry.kernelCfgFile), kernelBuilder.dotCfgFile):
        kernelBuildNeeded = True

print("        - Building...")
if kernelBuildNeeded:
    if True:
        with PrintLoadAvgThread("                - Installing kernel and modules..."):
            kernelBuilder.buildStepMakeInstall()
    if True:
        print("                - Installing firmware and wireless-regdb...")
        kernelBuilder.buildStepInstallFirmware()
    for name in kcache.getExtraDriverList():
        with PrintLoadAvgThread("                - Installing kernel driver \"%s\"..." % (name)):
            kernelBuilder.buildStepBuildAndInstallExtraDriver(name)
    if True:
        print("                - Cleaning...")
        kernelBuilder.buildStepClean()
else:
    print("No operation needed.")

os.makedirs(os.path.dirname(resultFile), exist_ok=True)
with open(resultFile, "w", encoding="iso8859-1") as f:
    f.write("%d\n" % (kernelBuildNeeded))
    f.write("%s\n" % (kernelBuilder.dstTarget.postfix))
