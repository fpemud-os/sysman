#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import bbki
import glob
import shutil
import strict_hdds
import robust_layer.simple_fops
from fm_param import FmConst
from fm_util import FmUtil
from fm_util import ArchLinuxBasedOsBuilder


class BbkiWrapper:

    def __init__(self):
        self._bbkiObj = bbki.Bbki(bbki.EtcDirConfig(FmConst.portageCfgDir))

        self.filesDir = os.path.join(FmConst.dataDir, "rescue", "rescueos")
        self.pkgListFile = os.path.join(self.filesDir, "packages")
        self.pkgDir = os.path.join(FmConst.dataDir, "rescue", "pkg")
        self.mirrorList = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "ARCHLINUX_MIRRORS").split()

    @property
    def repositories(self):
        return self._bbkiObj.repositories

    @property
    def boot_dir_writer(self):
        return self._bbkiObj.boot_dir_writer

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
        self._bbkiObj.install_initramfs(self._bbkiObj.get_initramfs_atom(), self._bbkiStorageInfo(layout), beList[0])

    def updateBootloader(self, layout):
        beList = self._bbkiObj.get_boot_entries()
        if len(beList) == 0:
            raise Exception("no boot entry")
        if len(beList) > 1:
            raise Exception("multiple boot entries")
        self._bbkiObj.install_bootloader(self._bbkiBootMode(layout), self._bbkiStorageInfo(layout), beList[0], self.getAuxOsInfo(), "")

    def isRescueOsInstalled(self):
        return os.path.exists(self._bbkiObj.rescue_os_spec.root_dir)

    def installOrUpdateRescueOs(self, tmpDir):
        robust_layer.simple_fops.mkdir(self._bbkiObj.rescue_os_spec.root_dir)
        builder = ArchLinuxBasedOsBuilder(self.mirrorList, FmConst.archLinuxCacheDir, tmpDir)
        try:
            if builder.bootstrapPrepare():
                builder.bootstrapDownload()

            builder.bootstrapExtract()

            localPkgFileList = glob.glob(os.path.join(self.pkgDir, "*.pkg.tar.xz"))

            fileList = []
            for x in glob.glob(os.path.join(FmConst.libexecDir, "rescue-*")):
                fileList.append((x, 0o755, "/root"))
            fileList.append((os.path.join(self.filesDir, "getty-autologin.conf"), 0o644, "/etc/systemd/system/getty@.service.d"))

            builder.createRootfs(initcpioHooksDir=os.path.join(self.filesDir, "initcpio"),
                                 pkgList=FmUtil.readListFile(self.pkgListFile),
                                 localPkgFileList=localPkgFileList, fileList=fileList)

            rootfsFn = os.path.join(self._bbkiObj.rescue_os_spec.root_dir, "airootfs.sfs")
            rootfsMd5Fn = os.path.join(self._bbkiObj.rescue_os_spec.root_dir, "airootfs.sha512")
            builder.squashRootfs(rootfsFn, rootfsMd5Fn, self._bbkiObj.rescue_os_spec.kernel_filepath, self._bbkiObj.rescue_os_spec.initrd_filepath)
        except Exception:
            shutil.rmtree(self._bbkiObj.rescue_os_spec.root_dir)
            raise

    def uninstallRescueOs(self):
        robust_layer.simple_fops.rm(self._bbkiObj.rescue_os_spec.root_dir)

    def updateBootloaderAfterRescueOsChange(self):
        self._bbkiObj.update_bootloader()

    def updateBootloaderAfterCleaning(self):
        self._bbkiObj.update_bootloader()

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

    def getAuxOsInfo(self):
        ret = []
        for line in FmUtil.cmdCall("/usr/bin/os-prober").split("\n"):
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

    def _bbkiStorageInfo(self, layout):
        mpList = []
        mpList.append(bbki.HostMountPoint(bbki.HostMountPoint.NAME_ROOT, "/", layout.dev_rootfs))
        if layout.name in ["bios-simple", "bios-lvm"]:
            bootDisk = layout.get_boot_disk()
        elif layout.name in ["efi-simple", "efi-lvm", "efi-bcache-lvm"]:
            mpList.append(bbki.HostMountPoint(bbki.HostMountPoint.NAME_ESP, "/boot", layout.get_esp()))
            bootDisk = None
        return bbki.HostStorage(self._bbkiBootMode(layout), mpList, bootDisk)
