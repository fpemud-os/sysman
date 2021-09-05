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


class FmBbkiWrapper:

    def __init__(self, param):
        self.param = param
        self._bbki = bbki.Bbki(bbki.EtcDirConfig(FmConst.portageCfgDir))

        self.filesDir = os.path.join(FmConst.dataDir, "rescue", "rescueos")
        self.pkgListFile = os.path.join(self.filesDir, "packages")
        self.pkgDir = os.path.join(FmConst.dataDir, "rescue", "pkg")
        self.mirrorList = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "ARCHLINUX_MIRRORS").split()

    def obj(self):
        return self._bbki

    def installInitramfs(self, layout):
        self._bbki.install_initramfs(self._bbki.get_initramfs_atom(), self._bbkiStorageInfo(layout))

    def installBootloader(self, layout):
        self._bbki.install_bootloader(self._bbkiBootMode(layout), self._bbkiStorageInfo(layout), self.getAuxOsInfo(), "")

    def isRescurOsInstalled(self):
        return os.path.exists(self._bbki.rescue_os_spec.root_dir)

    def installOrUpdateRescueOs(self, tmpDir):
        robust_layer.simple_fops.mkdir(self._bbki.rescue_os_spec.root_dir)
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

            rootfsFn = os.path.join(self._bbki.rescue_os_spec.root_dir, "airootfs.sfs")
            rootfsMd5Fn = os.path.join(self._bbki.rescue_os_spec.root_dir, "airootfs.sha512")
            builder.squashRootfs(rootfsFn, rootfsMd5Fn, self._bbki.rescue_os_spec.kernel_filepath, self._bbki.rescue_os_spec.initrd_filepath)
        except Exception:
            shutil.rmtree(self._bbki.rescue_os_spec.root_dir)
            raise

    def uninstallRescueOs(self):
        robust_layer.simple_fops.rm(self._bbki.rescue_os_spec.root_dir)

    def updateBootloaderAfterRescueOsChange(self):
        self._bbki.update_bootloader(self.getAuxOsInfo(), "")

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
                ret.append(bbki.HostAuxOs(osDesc, osPart, FmUtil.getBlkDevUuid(osPart), chain))
                continue
            if True:
                ret.append(bbki.HostAuxOs(itemList[1], itemList[0], FmUtil.getBlkDevUuid(itemList[0]), 1))
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
