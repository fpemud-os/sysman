#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import gstage4
import gstage4.seed_stages
import gstage4.repositories
import gstage4.target_features
from fm_util import FmUtil
from fm_util import CloudCacheGentoo
from fm_param import FmConst


class RescueDiskBuilder:

    def __init__(self, arch, subarch, devPath, tmpDir, hwInfo):
        self._diskName = "SystemRescueDisk"
        self._diskLabel = "SYSREC"

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
        cache = CloudCacheGentoo(FmConst.gentooCacheDir)

        # sync
        cache.sync()
        if self._arch not in cache.get_arch_list():
            raise Exception("arch \"%s\" is not supported" % (self._arch))
        if self._subarch not in cache.get_subarch_list(self._arch):
            raise Exception("subarch \"%s\" is not supported" % (self._subarch))

        # prefer local stage3 file
        self._stage3Files = cache.get_latest_stage3(self._arch, self._subarch, self._stage3Variant, cached_only=True)
        if self._stage3Files is None:
            self._stage3Files = cache.get_latest_stage3(self._arch, self._subarch, self._stage3Variant)

        # always use newest snapshot
        self._snapshotFile = cache.get_latest_snapshot()

    def buildTargetSystem(self):
        ftPortage = gstage4.target_features.Portage()
        # ftGenkernel = gstage4.target_features.Genkernel()
        # ftSystemd = gstage4.target_features.Systemd()
        ftNoDeprecate = gstage4.target_features.DoNotUseDeprecatedPackagesAndFunctions()
        ftSshServer = gstage4.target_features.SshServer()
        ftChronyDaemon = gstage4.target_features.ChronyDaemon()
        ftNetworkManager = gstage4.target_features.NetworkManager()
        ftGettyAutoLogin = gstage4.target_features.GettyAutoLogin()

        self._tmpRootfsDir.initialize()

        s = gstage4.Settings()
        s.program_name = "fpemud-os-sysman"
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts.arch = "amd64"
        ftPortage.update_target_settings(ts)
        # ftGenkernel.update_target_settings(ts)
        # ftSystemd.update_target_settings(ts)
        ftNoDeprecate.update_target_settings(ts)

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
            # "app-admin/eselec",
            # "app-eselect/eselect-timezone",
            "app-editors/nano",
            # "sys-kernel/gentoo-sources",
        }
        ftPortage.update_world_set(worldSet)
        # ftGenkernel.update_world_set(worldSet)
        # ftSystemd.update_world_set(worldSet)
        # ftSshServer.update_world_set(worldSet)
        # ftChronyDaemon.update_world_set(worldSet)
        # ftNetworkManager.update_world_set(worldSet)
        builder.action_update_world(world_set=worldSet)

        print("Build kernel")
        builder.action_install_kernel()

        p = self._tmpRootfsDir.get_old_chroot_dir_path(self._tmpRootfsDir.get_old_chroot_dir_names()[-1])
        p = os.path.join(p, "boot")
        with open(os.path.join(p, "vmlinuz"), "w") as f:
            f.write("")
        with open(os.path.join(p, "initramfs.img"), "w") as f:
            f.write("")

        # serviceList = []
        # ftSshServer.update_service_list(serviceList)
        # ftChronyDaemon.update_service_list(serviceList)
        # ftNetworkManager.update_service_list(serviceList)
        # builder.action_enable_services(service_list=serviceList)

        # scriptList = []
        # ftGettyAutoLogin.update_custom_script_list(scriptList)
        # builder.action_customize_system(custom_script_list=scriptList)

        builder.action_cleanup()

    def buildWorkerSystem(self):
        ftPortage = gstage4.target_features.Portage()
        ftNoDeprecate = gstage4.target_features.DoNotUseDeprecatedPackagesAndFunctions()
        if self._devType == "iso":
            ftCreateLiveCd = gstage4.target_features.CreateLiveCdAsIsoFile("amd64", self._diskName, self._diskLabel)
        elif self._devType == "usb":
            ftCreateLiveCd = gstage4.target_features.CreateLiveCdOnRemovableMedia(self._diskName, self._diskLabel)
        elif self._devType == "cdrom":
            ftCreateLiveCd = gstage4.target_features.CreateLiveCdOnCdrom("amd64", self._diskName, self._diskLabel)
        else:
            assert False

        self._tmpStageDir.initialize()

        s = gstage4.Settings()
        s.program_name = "fpemud-os-sysman"
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts.arch = "amd64"
        ftPortage.update_target_settings(ts)
        ftNoDeprecate.update_target_settings(ts)

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

        worldSet = set()
        ftPortage.update_world_set(worldSet)
        ftCreateLiveCd.update_world_set(worldSet)
        builder.action_update_world(world_set=worldSet)

    def installIntoDevice(self):
        if self._devType == "iso":
            ftCreateLiveCd = gstage4.target_features.CreateLiveCdAsIsoFile("amd64", self._diskName, self._diskLabel)
        elif self._devType == "usb":
            ftCreateLiveCd = gstage4.target_features.CreateLiveCdOnRemovableMedia(self._diskName, self._diskLabel)
        elif self._devType == "cdrom":
            ftCreateLiveCd = gstage4.target_features.CreateLiveCdOnCdrom("amd64", self._diskName, self._diskLabel)
        else:
            assert False

        p = self._tmpRootfsDir.get_old_chroot_dir_path(self._tmpRootfsDir.get_old_chroot_dir_names()[-1])
        workerScript = ftCreateLiveCd.get_worker_script(p, self._devPath)

        p = self._tmpStageDir.get_old_chroot_dir_path(self._tmpStageDir.get_old_chroot_dir_names()[-1])
        with gstage4.Chrooter(p) as wc:
            wc.script_exec(workerScript)


devMinSizeInGb = 1                        # 1Gib

devMinSize = 1 * 1024 * 1024 * 1024       # 1GiB
