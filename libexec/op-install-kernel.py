#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import base64
import pickle
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import FmUtil
from helper_boot_kernel import FkmBootEntry
from helper_boot_kernel import FkmKernelBuilder
from helper_boot_kernel import FkmKCache
from helper_boot_initramfs import FkmInitramfsKcfgChecker


kernelCfgRules = pickle.loads(base64.b64decode(sys.argv[1].encode("ascii")))
resultFile = sys.argv[2]

bootEntry = FkmBootEntry.findCurrent(strict=False)
kcache = FkmKCache()
kernelBuilder = FkmKernelBuilder(kcache, kernelCfgRules)

print("        - Extracting...")
kernelBuilder.buildStepExtract()

print("        - Patching...")
kernelBuilder.buildStepPatch()

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
    if "tbs" in kcache.getKernelUseFlags():
        kernelBuildNeeded = True
        fn = "/boot/signature.tbs-%s" % (kernelBuilder.dstTarget.postfix)
        if os.path.exists(fn):
            with open(fn, "r") as f:
                if f.read() == kcache.getTbsDriverSourceSignature():
                    kernelBuildNeeded = False
if not kernelBuildNeeded:
    if "vbox" in kcache.getKernelUseFlags():
        kernelBuildNeeded = True
        fn = "/boot/signature.vbox-%s" % (kernelBuilder.dstTarget.postfix)
        if os.path.exists(fn):
            with open(fn, "r") as f:
                if f.read() == kcache.getVboxDriverSourceSignature():
                    kernelBuildNeeded = False
if not kernelBuildNeeded:
    kernelBuildNeeded = True
    fn = "/boot/signature.vhba-%s" % (kernelBuilder.dstTarget.postfix)
    if os.path.exists(fn):
        with open(fn, "r") as f:
            if f.read() == kcache.getVhbaModuleSourceSignature():
                kernelBuildNeeded = False
if not kernelBuildNeeded:
    if not FmUtil.dotCfgFileCompare(os.path.join("/boot", bootEntry.kernelCfgFile), kernelBuilder.dotCfgFile):
        kernelBuildNeeded = True
    print("        - Building...")
if kernelBuildNeeded:
    if True:
        print("                - Installing kernel image...")
        kernelBuilder.buildStepMakeInstall()
    if True:
        print("                - Installing modules...")
        kernelBuilder.buildStepMakeModulesInstall()
    if True:
        print("                - Installing firmware...")
        kernelBuilder.buildStepInstallFirmware()
    if "tbs" in kcache.getKernelUseFlags():
        print("                - Installing TBS driver...")
        kernelBuilder.buildStepBuildAndInstallTbsDriver()
    if "vbox" in kcache.getKernelUseFlags():
        print("                - Installing VirtualBox driver...")
        kernelBuilder.buildStepBuildAndInstallVboxDriver()
    if True:
        print("                - Installing VHBA module...")
        kernelBuilder.buildStepBuildAndInstallVhbaModule()
    if True:
        print("                - Cleaning...")
        kernelBuilder.buildStepClean()
else:
    print("No operation needed.")

FmUtil.ensureDir(os.path.dirname(resultFile))
with open(resultFile, "w", encoding="iso8859-1") as f:
    f.write("%d\n" % (kernelBuildNeeded))
    f.write("%s\n" % (kernelBuilder.dstTarget.postfix))
