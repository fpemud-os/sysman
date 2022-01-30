#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import gstage4
from fm_util import FmUtil
from fm_util import CloudCacheGentoo
from fm_util import CcacheLocalService
from fm_param import FmConst


class InstallCdBuilder:

    DEV_TYPE_ISO = "iso"
    DEV_TYPE_CDROM = "cdrom"
    DEV_TYPE_USB_STICK = "usb-stick"

    def __init__(self, devType, tmpDir, hwInfo, **kwargs):
        self._archDirDict = {
            "amd64": "x86_64",
            "arm64": "arm64",
        }
        self._stage4ArchInfoDict = {
            "amd64": ["amd64", "systemd", "default/linux/amd64/17.1", os.path.join(tmpDir, "stage4-amd64"), False],   # [subarch, variant, profile, rootfs-dir, complete-flag]
            # "arm64": ["arm64", None],
        }
        self._archInfoDict = {
            "amd64": ["amd64", "openrc", "default/linux/amd64/17.1/no-multilib", os.path.join(tmpDir, "instcd-rootfs-amd64"), False],   # [subarch, variant, profile, rootfs-dir, complete-flag]
            # "arm64": ["arm64", None],
        }

        self._devType = devType
        if self._devType == self.DEV_TYPE_ISO:
            assert len(kwargs) == 3 and "file_path" in kwargs and "disk_name" in kwargs and "disk_label" in kwargs
            self._filePath = kwargs["file_path"]
            self._diskName = kwargs["disk_name"]
            self._diskLabel = kwargs["disk_label"]
            # FIXME: check
        elif self._devType == self.DEV_TYPE_CDROM:
            assert len(kwargs) == 3 and "dev_path" in kwargs and "disk_name" in kwargs and "disk_label" in kwargs
            self._devPath = kwargs["dev_path"]
            self._diskName = kwargs["disk_name"]
            self._diskLabel = kwargs["disk_label"]
            # FIXME: check
        elif self._devType == self.DEV_TYPE_USB_STICK:
            assert len(kwargs) == 3 and "dev_path" in kwargs and "disk_name" in kwargs and "disk_label" in kwargs
            self._devPath = kwargs["dev_path"]
            self._diskName = kwargs["disk_name"]
            self._diskLabel = kwargs["disk_label"]
            if not FmUtil.isBlkDevUsbStick(self._devPath):
                raise Exception("device %s does not seem to be an usb-stick." % (self._devPath))
            if FmUtil.getBlkDevSize(self._devPath) < DEV_MIN_SIZE:
                raise Exception("device %s needs to be at least %d GB." % (self._devPath, DEV_MIN_SIZE_IN_GB))
            if FmUtil.isMountPoint(self._devPath):
                raise Exception("device %s or any of its partitions is already mounted, umount it first." % (self._devPath))
        elif self._devType == self.DEV_TYPE_RESCUE_OS:
            assert len(kwargs) == 1 and "rescue_os_spec" in kwargs
            self._rescueOsSpec = kwargs["rescue_os_spec"]
        else:
            assert False

        self._cp = gstage4.ComputingPower.new(hwInfo.hwDict["cpu"]["cores"],
                                              hwInfo.hwDict["memory"]["size"] * 1024 * 1024 * 1024,
                                              10 if "fan" in hwInfo.hwDict else 1)

        self._stage3FilesDict = dict()
        self._snapshotFile = None

    def getDevType(self):
        return self._devType

    def getArchName(self, arch):
        return self._archDirDict[arch]

    def downloadFiles(self):
        cache = CloudCacheGentoo(FmConst.gentooCacheDir)

    def buildStage4(self, arch):
        tmpRootfsDir = self._stage4ArchInfoDict[arch][3]

        c = CcacheLocalService()

        ftPortage = gstage4.target_features.UsePortage()
        ftSystemd = gstage4.target_features.UseSystemd()
        ftNoDeprecate = gstage4.target_features.DoNotUseDeprecatedPackagesAndFunctions()
        ftUsrMerge = gstage4.target_features.UsrMerge()
        ftPerferGnu = gstage4.target_features.PreferGnuAndGpl()
        ftSshServer = gstage4.target_features.SshServer()
        ftChronyDaemon = gstage4.target_features.ChronyDaemon()
        ftNetworkManager = gstage4.target_features.NetworkManager()

        # step
        print("        - Initializing...")
        wdir = gstage4.WorkDir(tmpRootfsDir)
        wdir.initialize()

        s = gstage4.Settings()
        s.program_name = FmConst.programName
        s.verbose_level = 0
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts.arch = arch
        ts.profile = self._archInfoDict[arch][2]
        ftUsrMerge.update_target_settings(ts)
        ftPortage.update_target_settings(ts)
        ftSystemd.update_target_settings(ts)
        ftNoDeprecate.update_target_settings(ts)
        ftPerferGnu.update_target_settings(ts)

        if c.is_enabled():
            s.host_ccache_dir = c.get_ccache_dir()
            ts.build_opts.ccache = True

        builder = gstage4.Builder(s, ts, wdir)

        # step
        print("        - Extracting seed stage...")
        with gstage4.seed_stages.GentooStage3Archive(*self._stage3FilesDict[arch]) as ss:
            builder.action_unpack(ss)

        # step
        print("        - Installing gentoo repository...")
        gentooRepo = gstage4.repositories.GentooSnapshot(self._snapshotFile)
        builder.action_create_gentoo_repository(gentooRepo)

        # step
        print("        - Generating configurations...")
        builder.action_init_confdir()

        # step
        print("        - Installing overlays...")
        builder.action_create_overlays(overlay_list=[
            Stage4Overlay("mirrorshq-overlay", "https://github.com/mirrorshq/gentoo-overlay"),
            Stage4Overlay("fpemud-os-overlay", "https://github.com/fpemud-os/gentoo-overlay"),
        ])

        # step
        with PrintLoadAvgThread("        - Updating world..."):
            scriptList = [
                Stage4ScriptUseRobustLayer(gentooRepo.get_datadir_path())
            ]
            ftUsrMerge.update_preprocess_script_list_for_update_world(scriptList)

            installList = []
            if c.is_enabled():
                installList.append("dev-util/ccache")

            worldSet = {
                "app-admin/fpemud-os-sysman",
            }
            ftPortage.update_world_set(worldSet)
            ftSystemd.update_world_set(worldSet)
            ftSshServer.update_world_set(worldSet)
            ftChronyDaemon.update_world_set(worldSet)
            ftNetworkManager.update_world_set(worldSet)

            builder.action_update_world(preprocess_script_list=scriptList, install_list=installList, world_set=worldSet)

        # step
        print("        - Enabling services...")
        serviceList = []
        ftSshServer.update_service_list(serviceList)
        ftChronyDaemon.update_service_list(serviceList)
        ftNetworkManager.update_service_list(serviceList)
        builder.action_enable_services(service_list=serviceList)

        # step
        print("        - Customizing...")
        scriptList = []
        gstage4.target_features.SetPasswordForUserRoot("123456").update_custom_script_list(scriptList)
        scriptList.append(gstage4.scripts.OneLinerScript("Update system", "sysman update"))
        builder.action_customize_system(custom_script_list=scriptList)

        # step
        print("        - Cleaning up...")
        builder.action_cleanup()

        self._stage4ArchInfoDict[arch][-1] = True

    def buildTargetSystem(self, arch):
        tmpRootfsDir = self._archInfoDict[arch][3]

        c = CcacheLocalService()

        ftPortage = gstage4.target_features.UsePortage()
        ftGenkernel = gstage4.target_features.UseGenkernel()
        ftOpenrc = gstage4.target_features.UseOpenrc()
        ftNoDeprecate = gstage4.target_features.DoNotUseDeprecatedPackagesAndFunctions()
        ftUsrMerge = gstage4.target_features.UsrMerge()
        ftPerferGnu = gstage4.target_features.PreferGnuAndGpl()
        ftSshServer = gstage4.target_features.SshServer()
        ftChronyDaemon = gstage4.target_features.ChronyDaemon()
        ftNetworkManager = gstage4.target_features.NetworkManager()
        # ftGettyAutoLogin = gstage4.target_features.GettyAutoLogin()

        # step
        print("        - Initializing...")
        wdir = gstage4.WorkDir(tmpRootfsDir)
        wdir.initialize()

        s = gstage4.Settings()
        s.program_name = FmConst.programName
        s.verbose_level = 0
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts.arch = arch
        ts.profile = self._archInfoDict[arch][2]
        ftUsrMerge.update_target_settings(ts)
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
        with gstage4.seed_stages.GentooStage3Archive(*self._stage3FilesDict[arch]) as ss:
            builder.action_unpack(ss)

        # step
        print("        - Installing gentoo repository...")
        gentooRepo = gstage4.repositories.GentooSnapshot(self._snapshotFile)
        builder.action_create_gentoo_repository(gentooRepo)

        # step
        print("        - Generating configurations...")
        builder.action_init_confdir()

        # step
        print("        - Installing overlays...")
        builder.action_create_overlays(overlay_list=[
            Stage4Overlay("mirrorshq-overlay", "https://github.com/mirrorshq/gentoo-overlay"),
            Stage4Overlay("fpemud-os-overlay", "https://github.com/fpemud-os/gentoo-overlay"),
        ])

        # step
        with PrintLoadAvgThread("        - Updating world..."):
            scriptList = [
                Stage4ScriptUseRobustLayer(gentooRepo.get_datadir_path())
            ]
            ftUsrMerge.update_preprocess_script_list_for_update_world(scriptList)

            installList = []
            if c.is_enabled():
                installList.append("dev-util/ccache")

            worldSet = {
                "app-admin/eselect",
                "app-admin/fpemud-os-installcd-meta",
                "app-arch/cpio",
                "app-arch/gzip",
                "app-arch/p7zip",
                "app-arch/unzip",
                "app-arch/zip",
                "app-eselect/eselect-timezone",
                "app-editors/nano",
                "app-misc/mc",
                "app-misc/tmux",
                "dev-lang/python",
                "dev-vcs/git",
                "net-misc/rsync",
                "net-misc/wget",
                "sys-apps/dmidecode",
                "sys-apps/lshw",
                "sys-apps/smartmontools",
                "sys-boot/grub",            # also required by boot-chain in USB stick
                "sys-apps/file",
                "sys-apps/hdparm",
                "sys-apps/memtest86+",      # also required by boot-chain in USB stick
                "sys-apps/nvme-cli",
                "sys-apps/sdparm",
                "sys-block/parted",
                "sys-devel/bc",
                "sys-fs/bcache-tools",
                "sys-fs/btrfs-progs",
                "sys-fs/dosfstools",
                "sys-fs/e2fsprogs",
                "sys-fs/exfat-utils",
                # "sys-fs/f2fs-tools",      # FIXME: /sbin/sg_write_buffer from sys-fs/f2fs-tools collides with /usr/sbin/sg_write_buffer from sys-apps/sg3_utils under usr-merge
                "sys-fs/lsscsi",
                "sys-fs/mtools",
                # "sys-fs/ntfs3g",          # FIXME: requires FUSE2 which is deprecated
                "sys-kernel/gentoo-sources",
            }
            ftPortage.update_world_set(worldSet)
            ftGenkernel.update_world_set(worldSet)
            ftOpenrc.update_world_set(worldSet)
            ftSshServer.update_world_set(worldSet)
            ftChronyDaemon.update_world_set(worldSet)
            ftNetworkManager.update_world_set(worldSet)

            builder.action_update_world(preprocess_script_list=scriptList, install_list=installList, world_set=worldSet)

        # step
        with PrintLoadAvgThread("        - Building kernel..."):
            scriptList = []
            if True:
                s = gstage4.scripts.PlacingFilesScript("Install bcachefs kernel config file")
                s.append_dir("/usr")
                s.append_dir("/usr/src")
                s.append_file("/usr/src/dot-config", TMP_DOT_CONFIG)
                scriptList.append(s)
            builder.action_install_kernel(preprocess_script_list=scriptList)

        # step
        print("        - Enabling services...")
        serviceList = []
        ftSshServer.update_service_list(serviceList)
        ftChronyDaemon.update_service_list(serviceList)
        ftNetworkManager.update_service_list(serviceList)
        builder.action_enable_services(service_list=serviceList)

        # step
        print("        - Customizing...")
        scriptList = []
        # ftGettyAutoLogin.update_custom_script_list(scriptList)
        gstage4.target_features.SetPasswordForUserRoot("123456").update_custom_script_list(scriptList)  # FIXME
        scriptList.append(gstage4.scripts.OneLinerScript("Delete /usr/src content", "rm -rf /usr/src/*"))
        builder.action_customize_system(custom_script_list=scriptList)

        # step
        print("        - Cleaning up...")
        builder.action_cleanup()

        self._archInfoDict[arch][-1] = True

    def exportTargetSystem(self):
        assert all([x[-1] for x in self._archInfoDict.values()])

        if self._devType == self.DEV_TYPE_ISO:
            assert False
        elif self._devType == self.DEV_TYPE_CDROM:
            assert False
        elif self._devType == self.DEV_TYPE_USB_STICK:
            self._exportToUsbStick()
        elif self._devType == self.DEV_TYPE_RESCUE_OS:
            self._exportToRescueOsDir()
        else:
            assert False


DEV_MIN_SIZE_IN_GB = 10                     # 10Gib

DEV_MIN_SIZE = 10 * 1024 * 1024 * 1024      # 10GiB
