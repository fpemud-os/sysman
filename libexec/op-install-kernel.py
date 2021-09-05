#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import json
import bbki
import bbki.util
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_util import PrintLoadAvgThread
from fm_param import FmConst


kernelCfgRules = json.loads(sys.argv[1])
resultFile = sys.argv[2]

obj = bbki.Bbki(bbki.EtcDirConfig(FmConst.portageCfgDir))

print("        - Fetching...")
kernelAtom = obj.get_kernel_atom()
kernelAddonAtoms = obj.get_kernel_addon_atoms()
initramfsAtom = obj.get_initramfs_atom()
for atom in [kernelAtom] + kernelAddonAtoms + [initramfsAtom]:
    obj.fetch(atom)

print("        - Extracting...")
kernelBuilder = obj.get_kernel_installer(kernelAtom, kernelAddonAtoms, initramfsAtom)
kernelBuilder.unpack()

print("        - Patching...")
kernelBuilder.patch_kernel()

print("        - Generating .config file...")
kernelBuilder.generate_kernel_config_file()

bootEntry = obj.get_pending_boot_entry()
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
    if not bbki.util.compare_kernel_config_files(bootEntry.kernel_config_filepath, kernelBuilder.get_progress().kernel_config_filepath):
        kernelBuildNeeded = True

with PrintLoadAvgThread("        - Building..."):
    if kernelBuildNeeded:
        kernelBuilder.build()

with PrintLoadAvgThread("        - Installing..."):
    if kernelBuildNeeded:
        kernelBuilder.install()

if kernelBuildNeeded:
    kernelBuilder.dispose()

os.makedirs(os.path.dirname(resultFile), exist_ok=True)
with open(resultFile, "w", encoding="iso8859-1") as f:
    f.write("%d\n" % (kernelBuildNeeded))
    f.write("%s\n" % (kernelBuilder.get_progress().target_boot_entry.postfix))
