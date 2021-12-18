#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import glob
import shutil
import pathlib
import gstage4
import gstage4.seed_stages
import gstage4.repositories
from fm_util import FmUtil
from fm_util import TmpMount
from fm_util import TempChdir
from fm_param import FmConst


class RescueDiskBuilder:

    def __init__(self, devPath, tmpDir):
        self.usbStickMinSize = 1 * 1024 * 1024 * 1024       # 1GiB

        self.filesDir = os.path.join(FmConst.dataDir, "rescue", "rescuedisk")
        self.pkgListFile = os.path.join(self.filesDir, "packages.x86_64")
        self.grubCfgSrcFile = os.path.join(self.filesDir, "grub.cfg.in")
        self.pkgDir = os.path.join(FmConst.dataDir, "rescue", "pkg")

        self.mirrorList = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "ARCHLINUX_MIRRORS").split()

        self.devPath = devPath

        self.tmpDir = gstage4.WorkDir(os.path.join(tmpDir, "rootfs"))
        self.tmpDir2 = gstage4.WorkDir(os.path.join(tmpDir, "tmpstage"))

    def checkCdromDevice(self):
        assert False

    def checkUsbDevice(self):
        if not FmUtil.isBlkDevUsbStick(self.devPath):
            raise Exception("device %s does not seem to be an usb-stick." % (self.devPath))
        if FmUtil.getBlkDevSize(self.devPath) < self.usbStickMinSize:
            raise Exception("device %s needs to be at least %d GB." % (self.devPath, self.usbStickMinSize / 1024 / 1024 / 1024))
        if FmUtil.isMountPoint(self.devPath):
            raise Exception("device %s or any of its partitions is already mounted, umount it first." % (self.devPath))

    def build(self, hwInfo):
        s = gstage4.Settings()
        s.set_program_name("fpemud-os-sysman")
        s.set_host_computing_power(gstage4.ComputingPower.new(hwInfo.hwDict["cpu"]["cores"],
                                                              hwInfo.hwDict["memory"]["size"] * 1024 * 1024 * 1024,
                                                              10 if "fan" in hwInfo.hwDict else 1))
        s["host_distfiles_dir"] = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts["pkg_license"] = {
            "*/*": "*",
        }
        ts["world_set"] = [
            "app-admin/eselect",
            "app-eselect/eselect-timezone",
            "app-editors/nano",
            "sys-kernel/gentoo-sources",
            "sys-kernel/genkernel",
        ]

        self.tmpDir.initialize()
        b = gstage4.Builder(s, ts, self.tmpDir)

        c = gstage4.seed_stages.GentooStage3Archive("/stage3-amd64-systemd-20211212T170613Z.tar.xz")
        b.action_unpack(c)

        print("step2")
        repos = [
            # gentooRepo = gstage4.repositories.GentooRsync(),
            gstage4.repositories.GentooFromHost("/root/gentoo"),
        ]
        b.action_init_repositories(repos)

        print("step3")
        b.action_init_confdir()

        print("step6")
        b.action_update_world_set()

        print("step7")
        b.action_install_kernel()

        print("step8")
        fileList = []
        if True:
            for x in glob.glob(os.path.join(FmConst.libexecDir, "rescue-*")):
                fileList.append((x, 0o755, "/root"))
            fileList.append((os.path.join(self.filesDir, "getty-autologin.conf"), 0o644, "/etc/systemd/system/getty@.service.d"))
        cmdList = [
            "systemctl enable sshd",
            "systemctl enable NetworkManager",
            "systemctl enable chronyd",
        ]
        b.action_config_system(fileList, cmdList)

        print("step9")
        b.action_cleanup()

        print("finished")

    def installIntoCdromDevice(self):
        assert False

    def installIntoUsbDevice(self):
        # create partitions
        FmUtil.initializeDisk(self.devPath, "mbr", [
            ("*", "vfat"),
        ])
        partDevPath = self.devPath + "1"

        # format the new partition and get its UUID
        FmUtil.cmdCall("/usr/sbin/mkfs.vfat", "-F", "32", "-n", "SYSRESC", partDevPath)
        uuid = FmUtil.getBlkDevUuid(partDevPath)
        if uuid == "":
            raise Exception("can not get FS-UUID for %s" % (partDevPath))

        with TmpMount(partDevPath) as mp:
            # we need a fresh partition
            assert len(os.listdir(mp.mountpoint)) == 0

            os.makedirs(os.path.join(mp.mountpoint, "rescuedisk", "x86_64"))

            srcDir = self.tmpDir.get_old_chroot_dir_names()[-1]
            rootfsFn = os.path.join(mp.mountpoint, "rescuedisk", "x86_64", "airootfs.sfs")
            rootfsMd5Fn = os.path.join(mp.mountpoint, "rescuedisk", "x86_64", "airootfs.sha512")
            kernelFn = os.path.join(mp.mountpoint, "rescuedisk", "x86_64", "vmlinuz")
            initrdFn = os.path.join(mp.mountpoint, "rescuedisk", "x86_64", "initcpio.img")

            FmUtil.cmdCall("/bin/mv", glob.glob(os.path.join(srcDir, "boot", "vmlinuz-*"))[0], kernelFn)
            FmUtil.cmdCall("/bin/mv", glob.glob(os.path.join(srcDir, "boot", "initramfs-*"))[0], initrdFn)
            shutil.rmtree(os.path.join(srcDir, "boot"))

            FmUtil.cmdExec("/usr/bin/mksquashfs", srcDir, rootfsFn, "-no-progress", "-noappend", "-quiet")
            with TempChdir(os.path.dirname(rootfsFn)):
                FmUtil.shellExec("/usr/bin/sha512sum \"%s\" > \"%s\"" % (os.path.basename(rootfsFn), rootfsMd5Fn))

            # generate grub.cfg
            FmUtil.cmdCall("/usr/sbin/grub-install", "--removable", "--target=x86_64-efi", "--boot-directory=%s" % (os.path.join(mp.mountpoint, "boot")), "--efi-directory=%s" % (mp.mountpoint), "--no-nvram")
            FmUtil.cmdCall("/usr/sbin/grub-install", "--removable", "--target=i386-pc", "--boot-directory=%s" % (os.path.join(mp.mountpoint, "boot")), self.devPath)
            with open(os.path.join(mp.mountpoint, "boot", "grub", "grub.cfg"), "w") as f:
                buf = pathlib.Path(self.grubCfgSrcFile).read_text()
                buf = buf.replace("%UUID%", uuid)
                buf = buf.replace("%BASEDIR%", "/rescuedisk")
                buf = buf.replace("%PREFIX%", "/rescuedisk/x86_64")
                f.write(buf)
