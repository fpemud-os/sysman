#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import glob
import shutil
import pathlib
import gstage4
import gstage4.seed_stages
import gstage4.repositories
import gstage4.target_features
from fm_util import FmUtil
from fm_util import TmpMount
from fm_util import TempChdir
from fm_util import CloudCacheGentoo
from fm_param import FmConst


class RescueDiskBuilder:

    def __init__(self, arch, subarch, devPath, tmpDir, hwInfo):
        self._filesDir = os.path.join(FmConst.dataDir, "rescue", "rescuedisk")
        self._pkgListFile = os.path.join(self._filesDir, "packages.x86_64")
        self._grubCfgSrcFile = os.path.join(self._filesDir, "grub.cfg.in")
        self._pkgDir = os.path.join(FmConst.dataDir, "rescue", "pkg")

        self._mirrorList = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "ARCHLINUX_MIRRORS").split()

        self._arch = arch
        self._subarch = subarch
        if self._arch == "alpha":
            assert False
        elif self._arch == "amd64":
            self._stage3Variant = "systemd"
        elif self._arch == "arm":
            assert False
        elif self._arch == "arm64":
            assert False
        elif self._arch == "hppa":
            assert False
        elif self._arch == "ia64":
            assert False
        elif self._arch == "m68k":
            assert False
        elif self._arch == "ppc":
            assert False
        elif self._arch == "riscv":
            assert False
        elif self._arch == "s390":
            assert False
        elif self._arch == "sh":
            assert False
        elif self._arch == "sparc":
            assert False
        elif self._arch == "x86":
            assert False
        else:
            assert False

        self._devPath = devPath
        if self._devPath.endswith(".iso"):
            self._devType = "iso"
        elif re.fullmatch("/dev/sd.*", self._devPath) is not None:
            self._devType = "usb"
        elif re.fullmatch("/dev/sr.*", self._devPath) is not None:
            self._devType = "cdrom"
        else:
            raise Exception("device not supported")

        self._cp = gstage4.ComputingPower.new(hwInfo.hwDict["cpu"]["cores"],
                                              hwInfo.hwDict["memory"]["size"] * 1024 * 1024 * 1024,
                                              10 if "fan" in hwInfo.hwDict else 1)

        self._stage3Files = None
        self._snapshotFile = None

        self._tmpRootfsDir = gstage4.WorkDir(os.path.join(tmpDir, "rootfs"))
        self._tmpStageDir = gstage4.WorkDir(os.path.join(tmpDir, "tmpstage"))

        self._ftNoDeprecate = gstage4.target_features.DoNotUseDeprecatedPackagesAndFunctions()
        self._ftSshServer = gstage4.target_features.SshServer()
        self._ftChronyDaemon = gstage4.target_features.ChronyDaemon()
        self._ftNetworkManager = gstage4.target_features.NetworkManager()
        self._ftGettyAutoLogin = gstage4.target_features.GettyAutoLogin()

    def checkDevice(self):
        if self._devType == "iso":
            # FIXME
            pass
        elif self._devType == "usb":
            if not FmUtil.isBlkDevUsbStick(self._devPath):
                raise Exception("device %s does not seem to be an usb-stick." % (self._devPath))
            if FmUtil.getBlkDevSize(self._devPath) < devMinSize:
                raise Exception("device %s needs to be at least %d GB." % (self._devPath, devMinSizeInGb))
            if FmUtil.isMountPoint(self._devPath):
                raise Exception("device %s or any of its partitions is already mounted, umount it first." % (self._devPath))
        elif self._devType == "cdrom":
            assert False
        else:
            assert False

    def downloadFiles(self):
        cache = CloudCacheGentoo(FmConst.gentooCacheDir, True)
        cache.sync()
        if self._arch not in cache.get_arch_list():
            raise Exception("arch \"%s\" is not supported" % (self._arch))
        if self._subarch not in cache.get_subarch_list(self._arch):
            raise Exception("subarch \"%s\" is not supported" % (self._subarch))
        self._stage3Files = cache.get_latest_stage3(self._arch, self._subarch, self._stage3Variant)
        self._snapshotFile = cache.get_latest_snapshot()

    def buildTargetSystem(self):
        self._tmpRootfsDir.initialize()

        s = gstage4.Settings()
        s.program_name = "fpemud-os-sysman"
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        self._ftNoDeprecate.update_target_settings(ts)

        builder = gstage4.Builder(s, ts, self._tmpRootfsDir)

        print("Extract seed stage")
        with gstage4.seed_stages.GentooStage3Archive(*self._stage3Files) as ss:
            builder.action_unpack(ss)
        print("")

        repos = [
            gstage4.repositories.GentooSquashedSnapshot(self._snapshotFile),
        ]
        builder.action_init_repositories(repos)

        builder.action_init_confdir()

        worldSet = {
            "app-admin/eselec",
            "app-eselect/eselect-timezone",
            "app-editors/nano",
            "sys-kernel/gentoo-sources",
            "sys-kernel/genkernel",
            "sys-apps/portage",
            "sys-apps/systemd",
        }
        self._ftSshServer.update_world_set(worldSet)
        self._ftChronyDaemon.update_world_set(worldSet)
        self._ftNetworkManager.update_world_set(worldSet)
        builder.action_update_world(world_set=worldSet)

        print("Build kernel")
        builder.action_install_kernel()

        serviceList = []
        self._ftSshServer.update_service_list(serviceList)
        self._ftChronyDaemon.update_service_list(serviceList)
        self._ftNetworkManager.update_service_list(serviceList)
        builder.action_enable_services(serviceList)

        scriptList = []
        self._ftGettyAutoLogin.update_custom_script_list(scriptList)
        builder.action_customize_system(scriptList)

        builder.action_cleanup()

    def buildWorkerSystem(self):
        self._tmpRootfsDir.initialize()

        s = gstage4.Settings()
        s.program_name = "fpemud-os-sysman"
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()





        ts.pkg_use = {
            "*/*": "-deprecated",
            "*/*": "-fallback",
            "net-misc/networkmanager": "iwd",
        }
        ts.pkg_license = {
            "*/*": "*",
        }

        builder = gstage4.Builder(s, ts, self._tmpStageDir)

        print("Extract seed stage")
        with gstage4.seed_stages.GentooStage3Archive(*self._stage3Files) as ss:
            builder.action_unpack(ss)
        print("")

        repos = [
            gstage4.repositories.GentooSquashedSnapshot(self._snapshotFile),
        ]
        builder.action_init_repositories(repos)

        builder.action_init_confdir()

        worldSet = {
            "sys-apps/portage",
            "sys-apps/systemd",
        }
        builder.action_update_world(world_set=worldSet)

    def installIntoDevice(self):
        if self._devType == "iso":
            # FIXME
            assert False
        elif self._devType == "usb":
            self._installIntoUsbStick()
        elif self._devType == "cdrom":
            # FIXME
            assert False
        else:
            assert False

    def _installIntoUsbStick(self):
        # create partitions
        FmUtil.initializeDisk(self._devPath, "mbr", [
            ("*", "vfat"),
        ])
        partDevPath = self._devPath + "1"

        # format the new partition and get its UUID
        FmUtil.cmdCall("/usr/sbin/mkfs.vfat", "-F", "32", "-n", "SYSRESC", partDevPath)
        uuid = FmUtil.getBlkDevUuid(partDevPath)
        if uuid == "":
            raise Exception("can not get FS-UUID for %s" % (partDevPath))

        with TmpMount(partDevPath) as mp:
            # we need a fresh partition
            assert len(os.listdir(mp.mountpoint)) == 0

            os.makedirs(os.path.join(mp.mountpoint, "rescuedisk", "x86_64"))

            srcDir = self._tmpRootfsDir.get_old_chroot_dir_names()[-1]
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
            FmUtil.cmdCall("/usr/sbin/grub-install", "--removable", "--target=i386-pc", "--boot-directory=%s" % (os.path.join(mp.mountpoint, "boot")), self._devPath)
            with open(os.path.join(mp.mountpoint, "boot", "grub", "grub.cfg"), "w") as f:
                buf = pathlib.Path(self._grubCfgSrcFile).read_text()
                buf = buf.replace("%UUID%", uuid)
                buf = buf.replace("%BASEDIR%", "/rescuedisk")
                buf = buf.replace("%PREFIX%", "/rescuedisk/x86_64")
                f.write(buf)


devMinSizeInGb = 1                        # 1Gib

devMinSize = 1 * 1024 * 1024 * 1024       # 1GiB
