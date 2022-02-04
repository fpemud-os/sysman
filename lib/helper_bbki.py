#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import bbki
import bbki.etcdir_cfg
import strict_hdds
from fm_param import FmConst
from fm_util import FmUtil


class BbkiWrapper:

    def __init__(self):
        if "FPEMUD_OS_PREPARE" in os.environ:
            bSelfBoot = False
        elif "FPEMUD_OS_SETUP" in os.environ:
            bSelfBoot = False
        else:
            bSelfBoot = True
        self._bbkiObj = bbki.Bbki(bbki.etcdir_cfg.Config(FmConst.portageCfgDir), bSelfBoot)

    @property
    def repositories(self):
        return self._bbkiObj.repositories

    @property
    def rescue_os_spec(self):
        return self._bbkiObj.rescue_os_spec

    def isStable(self):
        return self._bbkiObj.get_stable_flag()

    def setStable(self, value):
        self._bbkiObj.set_stable_flag(value)

    def get_current_boot_entry(self):
        return self._bbkiObj.get_current_boot_entry()

    def get_pending_boot_entry(self):
        return self._bbkiObj.get_pending_boot_entry()

    def installInitramfs(self, layout):
        beList = self._bbkiObj.get_boot_entries()
        if len(beList) == 0:
            raise Exception("no boot entry")
        if len(beList) > 1:
            raise Exception("multiple boot entries")
        hostStorage = bbki.HostStorage(self._bbkiBootMode(layout), [bbki.HostMountPoint(x.mnt_point, x.target, mnt_opt=x.mnt_opts) for x in layout.mount_entries], layout.boot_disk)
        self._bbkiObj.install_initramfs(self._bbkiObj.get_initramfs_atom(), hostStorage, beList[0])

    def updateBootloader(self, layout):
        beList = self._bbkiObj.get_boot_entries()
        if len(beList) == 0:
            raise Exception("no boot entry")
        if len(beList) > 1:
            raise Exception("multiple boot entries")
        hostStorage = bbki.HostStorage(self._bbkiBootMode(layout), [bbki.HostMountPoint(x.mnt_point, x.target, mnt_opt=x.mnt_opts) for x in layout.mount_entries], layout.boot_disk)
        self._bbkiObj.install_bootloader(self._bbkiBootMode(layout), hostStorage, beList[0], self.getAuxOsInfo(), "")

    def isRescueOsInstalled(self):
        return os.path.exists(self._bbkiObj.rescue_os_spec.root_dir)

    def updateBootloaderAfterRescueOsChange(self):
        self._bbkiObj.update_bootloader()

    def updateBootloaderAfterCleaning(self):
        self._bbkiObj.update_bootloader()

    def check_config(self, autofix=False, error_callback=None):
        return self._bbkiObj.check_config(autofix, error_callback)

    def check_repositories(self, autofix=False, error_callback=None):
        return self._bbkiObj.check_repositories(autofix, error_callback)

    def check_boot_entry_files(self, autofix=False, error_callback=None):
        return self._bbkiObj.check_boot_entry_files(autofix, error_callback)

    def get_kernel_atom(self):
        return self._bbkiObj.get_kernel_atom()

    def get_kernel_addon_atoms(self):
        return self._bbkiObj.get_kernel_addon_atoms()

    def get_initramfs_atom(self):
        return self._bbkiObj.get_initramfs_atom()

    def fetch(self, atom):
        return self._bbkiObj.fetch(atom)

    def get_kernel_installer(self, kernel_atom, kernel_addon_atom_list, initramfs_atom=None):
        return self._bbkiObj.get_kernel_installer(kernel_atom, kernel_addon_atom_list, initramfs_atom)

    def getAuxOsInfo(self):
        if not FmConst.supportOsProber:
            return []

        ret = []
        for line in FmUtil.cmdCall("os-prober").split("\n"):
            itemList = line.split(":")
            if len(itemList) != 4:
                continue
            if itemList[3] == "linux":
                continue

            if itemList[1].endswith("(loader)"):               # for Microsoft Windows quirks
                m = re.fullmatch("(.*?)([0-9]+)", itemList[0])
                osDesc = itemList[1].replace("(loader)", "").strip()
                osPart = "%s%d" % (m.group(1), int(m.group(2)) + 1)
                chain = 4
                ret.append(bbki.HostAuxOs(osDesc, osPart, chain))
                continue
            if True:
                ret.append(bbki.HostAuxOs(itemList[1], itemList[0], 1))
                continue
        return ret

    def _bbkiBootMode(self, layout):
        if layout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_EFI:
            return bbki.BootMode.EFI
        elif layout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_BIOS:
            return bbki.BootMode.BIOS
        else:
            assert False
