#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import glob
import shutil
from fm_util import FmUtil
from fm_util import TmpMount
from fm_util import ArchLinuxBasedOsBuilder
from fm_param import FmConst


class RescueOs:

    def __init__(self):
        self.filesDir = os.path.join(FmConst.dataDir, "rescue", "rescueos")
        self.pkgListFile = os.path.join(self.filesDir, "packages")
        self.pkgDir = os.path.join(FmConst.dataDir, "rescue", "pkg")
        self.sysRescCdDir = os.path.join(_bootDir, "rescue")
        self.mirrorList = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "ARCHLINUX_MIRRORS").split()
        self.rootfsFn = os.path.join(self.sysRescCdDir, "x86_64", "airootfs.sfs")
        self.rootfsMd5Fn = os.path.join(self.sysRescCdDir, "x86_64", "airootfs.sha512")
        self.kernelFn = os.path.join(self.sysRescCdDir, "x86_64", "vmlinuz")
        self.initrdFn = os.path.join(self.sysRescCdDir, "x86_64", "initcpio.img")

    def isInstalled(self):
        return os.path.exists(self.sysRescCdDir)

    def installOrUpdate(self, tmpDir):
        FmUtil.ensureDir(os.path.join(self.sysRescCdDir, "x86_64"))
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

            builder.squashRootfs(self.rootfsFn, self.rootfsMd5Fn, self.kernelFn, self.initrdFn)
        except Exception:
            shutil.rmtree(self.sysRescCdDir)
            raise

    def uninstall(self):
        FmUtil.forceDelete(self.sysRescCdDir)


class RescueDiskBuilder:

    def __init__(self):
        self.usbStickMinSize = 1 * 1024 * 1024 * 1024       # 1GiB

        self.filesDir = os.path.join(FmConst.dataDir, "rescue", "rescuedisk")
        self.pkgListFile = os.path.join(self.filesDir, "packages.x86_64")
        self.grubCfgSrcFile = os.path.join(self.filesDir, "grub.cfg.in")
        self.pkgDir = os.path.join(FmConst.dataDir, "rescue", "pkg")

        self.mirrorList = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "ARCHLINUX_MIRRORS").split()
        self.builder = None

    def checkCdromDevice(self, devPath):
        assert False

    def checkUsbDevice(self, devPath):
        if not FmUtil.isBlkDevUsbStick(devPath):
            raise Exception("device %s does not seem to be an usb-stick." % (devPath))
        if FmUtil.getBlkDevSize(devPath) < self.usbStickMinSize:
            raise Exception("device %s needs to be at least %d GB." % (devPath, self.usbStickMinSize / 1024 / 1024 / 1024))
        if FmUtil.isMountPoint(devPath):
            raise Exception("device %s or any of its partitions is already mounted, umount it first." % (devPath))

    def build(self, tmpDir):
        self.builder = ArchLinuxBasedOsBuilder(self.mirrorList, FmConst.archLinuxCacheDir, tmpDir)

        if self.builder.bootstrapPrepare():
            self.builder.bootstrapDownload()

        self.builder.bootstrapExtract()

        localPkgFileList = glob.glob(os.path.join(self.pkgDir, "*.pkg.tar.xz"))

        fileList = []
        for x in glob.glob(os.path.join(FmConst.libexecDir, "rescue-*")):
            fileList.append((x, 0o755, "/root"))
        fileList.append((os.path.join(self.filesDir, "getty-autologin.conf"), 0o644, "/etc/systemd/system/getty@.service.d"))

        cmdList = [
            "/bin/systemctl enable sshd",
            "/bin/systemctl enable NetworkManager",
            "/bin/systemctl enable chronyd",
        ]

        self.builder.createRootfs(initcpioHooksDir=os.path.join(self.filesDir, "initcpio"),
                                  pkgList=FmUtil.readListFile(self.pkgListFile),
                                  localPkgFileList=localPkgFileList, fileList=fileList, cmdList=cmdList)

    def generateCdromImageFile(self, filePath):
        assert False

    def installIntoCdromDevice(self, devPath):
        assert False

    def generateUsbImageFile(self, filePath):
        assert False

    def installIntoUsbDevice(self, devPath):
        # create partitions
        FmUtil.initializeDisk(devPath, "mbr", [
            ("*", "vfat"),
        ])
        partDevPath = devPath + "1"

        # format the new partition and get its UUID
        FmUtil.cmdCall("/usr/sbin/mkfs.vfat", "-F", "32", "-n", "SYSRESC", partDevPath)
        uuid = FmUtil.getBlkDevUuid(partDevPath)
        if uuid == "":
            raise Exception("can not get FS-UUID for %s" % (partDevPath))

        with TmpMount(partDevPath) as mp:
            # we need a fresh partition
            assert len(os.listdir(mp.mountpoint)) == 0

            rootfsFn = os.path.join(mp.mountpoint, "rescuedisk", "x86_64", "airootfs.sfs")
            rootfsMd5Fn = os.path.join(mp.mountpoint, "rescuedisk", "x86_64", "airootfs.sha512")
            kernelFn = os.path.join(mp.mountpoint, "rescuedisk", "x86_64", "vmlinuz")
            initrdFn = os.path.join(mp.mountpoint, "rescuedisk", "x86_64", "initcpio.img")

            os.makedirs(os.path.join(mp.mountpoint, "rescuedisk", "x86_64"))
            self.builder.squashRootfs(rootfsFn, rootfsMd5Fn, kernelFn, initrdFn)

            # generate grub.cfg
            FmUtil.cmdCall("/usr/sbin/grub-install", "--removable", "--target=x86_64-efi", "--boot-directory=%s" % (os.path.join(mp.mountpoint, "boot")), "--efi-directory=%s" % (mp.mountpoint), "--no-nvram")
            FmUtil.cmdCall("/usr/sbin/grub-install", "--removable", "--target=i386-pc", "--boot-directory=%s" % (os.path.join(mp.mountpoint, "boot")), devPath)
            with open(os.path.join(mp.mountpoint, "boot", "grub", "grub.cfg"), "w") as f:
                buf = FmUtil.readFile(self.grubCfgSrcFile)
                buf = buf.replace("%UUID%", uuid)
                buf = buf.replace("%BASEDIR%", "/rescuedisk")
                buf = buf.replace("%PREFIX%", "/rescuedisk/x86_64")
                f.write(buf)


def _standardMountList(rootfsDir):
    mountList = []
    if True:
        tstr = os.path.join(rootfsDir, "proc")
        mountList.append((tstr, "-t proc -o nosuid,noexec,nodev proc %s" % (tstr)))
    if True:
        tstr = os.path.join(rootfsDir, "sys")
        mountList.append((tstr, "--rbind /sys %s" % (tstr), "--make-rslave %s" % (tstr)))
    if True:
        tstr = os.path.join(rootfsDir, "dev")
        mountList.append((tstr, "--rbind /dev %s" % (tstr), "--make-rslave %s" % (tstr)))
    if True:
        tstr = os.path.join(rootfsDir, "run")
        mountList.append((tstr, "--bind /run %s" % (tstr)))
    if True:
        tstr = os.path.join(rootfsDir, "tmp")
        mountList.append((tstr, "-t tmpfs -o mode=1777,strictatime,nodev,nosuid tmpfs %s" % (tstr)))
    return mountList


_bootDir = "/boot"
