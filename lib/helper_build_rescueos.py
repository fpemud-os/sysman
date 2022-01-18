#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import gstage4
import gstage4.scripts
import gstage4.seed_stages
import gstage4.repositories
import gstage4.target_features
import robust_layer.git
import robust_layer.simple_fops
from fm_util import FmUtil
from fm_util import CloudCacheGentoo
from fm_util import PrintLoadAvgThread
from fm_util import CcacheLocalService
from fm_param import FmConst


class RescueOsBuilder:

    def __init__(self, tmpDir, hwInfo):
        self._arch = "amd64"
        self._subarch = "amd64"
        self._tmpRootDir = os.path.join(tmpDir, "rescueos-rootfs")

        self._cp = gstage4.ComputingPower.new(hwInfo.hwDict["cpu"]["cores"],
                                              hwInfo.hwDict["memory"]["size"] * 1024 * 1024 * 1024,
                                              10 if "fan" in hwInfo.hwDict else 1)
        self._stage3FilesDict = dict()
        self._snapshotFile = None

    def downloadFiles(self):
        cache = CloudCacheGentoo(FmConst.gentooCacheDir)

        # sync
        cache.sync()

        # prefer local stage3 file
        try:
            self._stage3FilesDict[self._arch] = cache.get_latest_stage3(self._arch, self._subarch, self._subarch, cached_only=True)
        except FileNotFoundError:
            self._stage3FilesDict[self._arch] = cache.get_latest_stage3(self._arch, self._subarch, self._subarch)

        # always use newest snapshot
        self._snapshotFile = cache.get_latest_snapshot()

    def buildRescueOs(self):
        c = CcacheLocalService()

        ftPortage = gstage4.target_features.UsePortage()
        ftGenkernel = gstage4.target_features.UseGenkernel()
        ftOpenrc = gstage4.target_features.UseOpenrc()
        ftNoDeprecate = gstage4.target_features.DoNotUseDeprecatedPackagesAndFunctions()
        ftPerferGnu = gstage4.target_features.PreferGnuAndGpl()
        ftSetRootPassword = gstage4.target_features.SetPasswordForUserRoot("123456")

        # step
        print("        - Initializing...")
        wdir = gstage4.WorkDir(self._tmpRootDir)
        wdir.initialize()

        s = gstage4.Settings()
        s.program_name = FmConst.programName
        s.verbose_level = 0
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts.arch = self._arch
        ftPortage.update_target_settings(ts)
        ftGenkernel.update_target_settings(ts)
        ftOpenrc.update_target_settings(ts)
        ftNoDeprecate.update_target_settings(ts)
        ftPerferGnu.update_target_settings(ts)

        if c.is_enabled():
            s.host_ccache_dir = c.get_ccache_dir()
            ts.build_opts.ccache = True

        builder = gstage4.Builder(s, ts, wdir)

        # step
        print("        - Extracting seed stage...")
        with gstage4.seed_stages.GentooStage3Archive(*self._stage3FilesDict[self._arch]) as ss:
            builder.action_unpack(ss)

        # step
        print("        - Installing repositories...")
        repos = [
            gstage4.repositories.GentooSnapshot(self._snapshotFile),
        ]
        builder.action_init_repositories(repos)

        # step
        print("        - Generating configurations...")
        builder.action_init_confdir()

        # step
        with PrintLoadAvgThread("        - Updating world..."):
            installList = []
            if c.is_enabled():
                installList.append("dev-util/ccache")
            worldSet = {
                "app-admin/eselect",
                "app-arch/cpio",
                "app-arch/gzip",
                "app-arch/p7zip",
                "app-arch/rar",
                "app-arch/unzip",
                "app-arch/zip",
                "app-eselect/eselect-timezone",
                "app-editors/nano",
                "app-misc/mc",
                "app-misc/tmux",
                "dev-lang/python",
                "dev-util/strace",
                "dev-vcs/git",
                "dev-vcs/subversion",
                "net-misc/rsync",
                "sys-apps/dmidecode",
                "sys-apps/gptfdisk",
                "sys-apps/lshw",
                "sys-apps/smartmontools",
                "sys-apps/file",
                "sys-apps/hdparm",
                "sys-apps/nvme-cli",
                "sys-apps/sdparm",
                "sys-block/ms-sys",
                "sys-block/parted",
                "sys-devel/bc",
                "sys-fs/bcache-tools",
                "sys-fs/btrfs-progs",
                "sys-fs/dosfstools",
                "sys-fs/e2fsprogs",
                "sys-fs/exfat-utils",
                # "sys-fs/f2fs-tools",
                "sys-fs/lsscsi",
                "sys-fs/mtools",
                # "sys-fs/ntfs3g",          # requires FUSE2 which is deprecated
                "sys-fs/xfsdump",
                "sys-fs/xfsprogs",
                "sys-process/bpytop",
                "sys-process/lsof",
            }
            ftPortage.update_world_set(worldSet)
            ftGenkernel.update_world_set(worldSet)
            ftOpenrc.update_world_set(worldSet)
            builder.action_update_world(install_list=installList, world_set=worldSet)

        # step
        with PrintLoadAvgThread("        - Building kernel..."):
            scriptList = []
            builder.action_install_kernel(preprocess_script_list=scriptList)

        # hidden step
        builder.action_enable_services(service_list=[])

        # step
        print("        - Customizing...")
        scriptList = []
        # ftGettyAutoLogin.update_custom_script_list(scriptList)
        ftSetRootPassword.update_custom_script_list(scriptList)
        if True:
            buf = ""
            buf += "#!/bin/bash\n"
            buf += "rm -rf /usr/src/*"
            scriptList.append(gstage4.scripts.ScriptFromBuffer("Delete /usr/src content", buf))
        builder.action_customize_system(custom_script_list=scriptList)

        # step
        print("        - Cleaning up...")
        builder.action_cleanup()

    def installRescueOs(self, bbkiRescueOsSpec):
        sp = gstage4.WorkDir(self._tmpRootDir).get_old_chroot_dir_paths()[-1]

        robust_layer.simple_fops.mkdir(bbkiRescueOsSpec.root_dir)
        shutil.move(os.path.join(sp, "boot", "vmlinuz"), bbkiRescueOsSpec.kernel_filepath)
        shutil.move(os.path.join(sp, "boot", "initramfs.img"), bbkiRescueOsSpec.initrd_filepath)
        FmUtil.makeSquashedRootfsFiles(sp, bbkiRescueOsSpec.root_dir)

        # create rescue-os
        # FIXME: it sucks that genkernel's initrd requires this file
        with open(os.path.join(bbkiRescueOsSpec.root_dir, "rescue-os"), "w") as f:
            f.write("")
