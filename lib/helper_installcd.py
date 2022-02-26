#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import bz2
import shutil
import tarfile
import windown
import gstage4
import wstage4
from fm_util import FmUtil
from fm_util import CloudCacheGentoo
from fm_util import CcacheLocalService
from fm_util import Stage4Overlay
from fm_util import Stage4ScriptUseRobustLayer
from fm_util import PrintLoadAvgThread
from fm_util import TmpMount
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

        self._stage4Info = {
            "gentoo-linux": {
                "amd64": {
                    "subarch": "amd64",
                    "variant": "systemd",
                    "profile": "default/linux/amd64/17.1",
                    "stage3-file": None,
                    "work-dir": gstage4.WorkDir(os.path.join(tmpDir, "stage4-gentoo-amd64")),
                    "completed": False
                },
                # "arm64": {
                #   "arch": "arm64",
                #   "completed": False
                # },
            },
            "windows-xp": {
                "amd64": {
                    "arch": wstage4.Arch.X86_64,
                    "version": wstage4.Version.WINDOWS_XP,
                    "edition": wstage4.Edition.WINDOWS_XP_PROFESSIONAL,
                    "lang": wstage4.Lang.en_US,
                    "product-id": "windows-xp-professional.x86_64.en-US",
                    "work-dir": wstage4.WorkDir(os.path.join(tmpDir, "stage4-winxp-amd64")),
                    "completed": False,
                },
            },
            "windows-7": {
                "amd64": {
                    "arch": wstage4.Arch.X86_64,
                    "version": wstage4.Version.WINDOWS_7,
                    "edition": wstage4.Edition.WINDOWS_7_ULTIMATE,
                    "lang": wstage4.Lang.en_US,
                    "product-id": "windows-7-ultimate.x86_64.en-US",
                    "work-dir": wstage4.WorkDir(os.path.join(tmpDir, "stage4-win7-amd64")),
                    "completed": False,
                },
            },
        }

        self._targetSystemInfo = {
            "amd64": {
                "subarch": "amd64",
                "variant": "openrc",
                "profile": "default/linux/amd64/17.1/no-multilib",
                "stage3-file": None,
                "work-dir": gstage4.WorkDir(os.path.join(tmpDir, "instcd-rootfs-amd64")),
                "completed": False
            },
            # "arm64": {
            #   "arch": "arm64",
            #   "completed": False
            # },
        }

        self._snapshotFile = None

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
        else:
            assert False

        self._cp = gstage4.ComputingPower.new(hwInfo.hwDict["cpu"]["cores"],
                                              hwInfo.hwDict["memory"]["size"] * 1024 * 1024 * 1024,
                                              10 if "fan" in hwInfo.hwDict else 1)

        self._winCache = windown.WindowsDownloader(WindownCfg())

    def getDevType(self):
        return self._devType

    def getArchName(self, arch):
        return self._archDirDict[arch]

    def downloadFiles(self):
        # get gentoo source files
        cache = CloudCacheGentoo(FmConst.gentooLinuxCacheDir)
        cache.sync()
        for arch, v in list(self._stage4Info["gentoo-linux"].items()) + list(self._targetSystemInfo.items()):
            assert arch in cache.get_arch_list()
            assert v["subarch"] in cache.get_subarch_list(arch)
        for arch, v in list(self._stage4Info["gentoo-linux"].items()) + list(self._targetSystemInfo.items()):
            try:
                v["stage3-file"] = cache.get_latest_stage3(arch, v["subarch"], v["variant"], cached_only=True)   # prefer local stage3 file
            except FileNotFoundError:
                v["stage3-file"] = cache.get_latest_stage3(arch, v["subarch"], v["variant"])
        self._snapshotFile = cache.get_latest_snapshot()                                                         # always use newest snapshot

        # get windows source files
        os.makedirs(FmConst.mswinCacheDir, exist_ok=True)
        for key in ["windows-xp", "windows-7"]:
            for arch, v in self._stage4Info[key].items():
                self._winCache.download(v["product-id"], FmConst.mswinCacheDir, create_product_subdir=True)

    def buildGentooLinuxStage4(self, arch):
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
        wdir = self._stage4Info["gentoo-linux"][arch]["work-dir"]
        wdir.initialize()

        s = gstage4.Settings()
        s.program_name = FmConst.programName
        s.verbose_level = 0
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts.arch = arch
        ts.profile = self._stage4Info["gentoo-linux"][arch]["profile"]
        ftUsrMerge.update_target_settings(ts)
        ftPortage.update_target_settings(ts)
        ftSystemd.update_target_settings(ts)
        ftNoDeprecate.update_target_settings(ts)
        ftPerferGnu.update_target_settings(ts)

        c = CcacheLocalService()
        if c.is_enabled():
            s.host_ccache_dir = c.get_ccache_dir()
            ts.build_opts.ccache = True

        builder = gstage4.Builder(s, ts, wdir)

        # step
        print("        - Extracting seed stage...")
        with gstage4.seed_stages.GentooStage3Archive(*self._stage4Info["gentoo-linux"][arch]["stage3-file"]) as ss:
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
            Stage4Overlay("guru", "https://github.com/gentoo/guru"),
            Stage4Overlay("mirrorshq-overlay", "https://github.com/mirrorshq/gentoo-overlay"),
            Stage4Overlay("fpemud-os-overlay", "https://github.com/fpemud-os/gentoo-overlay"),
            Stage4Overlay("junkdrawer", "https://github.com/doctaweeks/junkdrawer-overlay"),        # dev-python/pycdlib
        ])

        # step
        with PrintLoadAvgThread("        - Updating world..."):
            scriptList = [
                Stage4ScriptUseRobustLayer(gentooRepo.get_datadir_path()),
                PrepareInstallingFpemudOsSysman(gentooRepo.get_datadir_path()),
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

        self._stage4Info["gentoo-linux"][arch]["completed"] = True

    def buildWindowsXpStage4(self, arch):
        # step
        print("        - Initializing...")
        wdir = self._stage4Info["windows-xp"][arch]["work-dir"]
        wdir.initialize()

        s = wstage4.Settings()
        s.program_name = FmConst.programName
        s.verbose_level = 0

        ts = wstage4.TargetSettings()
        ts.arch = self._stage4Info["windows-xp"][arch]["arch"]
        ts.version = self._stage4Info["windows-xp"][arch]["version"]
        ts.edition = self._stage4Info["windows-xp"][arch]["edition"]
        ts.lang = self._stage4Info["windows-xp"][arch]["lang"]

        installIsoFile = self._winCache.get_install_iso_filepath(self._stage4Info["windows-xp"][arch]["product-id"])
        installIsoFile = wstage4.CustomWindowsInstallIsoFile(ts.arch, ts.version, ts.edition, ts.lang, installIsoFile)

        builder = wstage4.Builder(s, ts, wdir)
        builder.action_prepare_custom_install_media(installIsoFile)

        # step
        print("        - Installing windows...")
        builder.action_install_windows()

        # step
        print("        - Installing core applications...")
        builder.action_install_core_applications()

        # step
        print("        - Installing extra applications...")
        builder.action_install_extra_applications()

        # step
        print("        - Customizing...")
        builder.action_customize_system()

        # step
        print("        - Cleaning up...")
        builder.action_cleanup()

        self._stage4Info["windows-xp"][arch]["completed"] = True

    def buildWindows7Stage4(self, arch):
        # step
        print("        - Initializing...")
        wdir = self._stage4Info["windows-7"][arch]["work-dir"]
        wdir.initialize()

        s = wstage4.Settings()
        s.program_name = FmConst.programName
        s.verbose_level = 0

        ts = wstage4.TargetSettings()
        ts.arch = self._stage4Info["windows-7"][arch]["arch"]
        ts.version = self._stage4Info["windows-7"][arch]["version"]
        ts.edition = self._stage4Info["windows-7"][arch]["edition"]
        ts.lang = self._stage4Info["windows-7"][arch]["lang"]

        installIsoFile = self._winCache.get_install_iso_filepath(self._stage4Info["windows-7"][arch]["product-id"])
        installIsoFile = wstage4.CustomWindowsInstallIsoFile(ts.arch, ts.version, ts.edition, ts.lang, installIsoFile)

        builder = wstage4.Builder(s, ts, wdir)
        builder.action_prepare_custom_install_media(installIsoFile)

        # step
        print("        - Installing windows...")
        builder.action_install_windows()

        # step
        print("        - Installing core applications...")
        builder.action_install_core_applications()

        # step
        print("        - Installing extra applications...")
        builder.action_install_extra_applications()

        # step
        print("        - Customizing...")
        builder.action_customize_system()

        # step
        print("        - Cleaning up...")
        builder.action_cleanup()

        self._stage4Info["windows-7"][arch]["completed"] = True

    def buildTargetSystem(self, arch):
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
        wdir = self._targetSystemInfo[arch]["work-dir"]
        wdir.initialize()

        s = gstage4.Settings()
        s.program_name = FmConst.programName
        s.verbose_level = 0
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts.arch = arch
        ts.profile = self._targetSystemInfo[arch]["profile"]
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
        with gstage4.seed_stages.GentooStage3Archive(*self._targetSystemInfo[arch]["stage3-file"]) as ss:
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
                from helper_rescue import TMP_DOT_CONFIG                    # FIXME
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

        self._targetSystemInfo[arch]["completed"] = True

    def exportTargetSystem(self):
        assert all([x["completed"] for x in self._targetSystemInfo.values()])

        if self._devType == self.DEV_TYPE_ISO:
            assert False
        elif self._devType == self.DEV_TYPE_CDROM:
            assert False
        elif self._devType == self.DEV_TYPE_USB_STICK:
            self._exportToUsbStick()
        else:
            assert False

    def _exportToUsbStick(self):
        # format USB stick and get its UUID
        partDevPath = FmUtil.formatDisk(self._devPath, partitionType="vfat", partitionLabel=self._diskLabel)
        uuid = FmUtil.getBlkDevUuid(partDevPath)
        if uuid == "":
            raise Exception("can not get FS-UUID for %s" % (partDevPath))

        with TmpMount(partDevPath) as mp:
            osDir = os.path.join(mp.mountpoint, "os")
            os.mkdir(osDir)
            dataDir = os.path.join(mp.mountpoint, "data")
            os.mkdir(dataDir)

            # install Gentoo Linux files
            if self._stage4Info["gentoo-linux"]["amd64"]["completed"]:
                srcDir = self._stage4Info["gentoo-linux"]["amd64"]["work-dir"].get_old_chroot_dir_paths()[-1]
                dstFile = os.path.join(dataDir, "gentoo-linux-amd64.tar.bz2")
                with tarfile.open(dstFile, mode="x:bz2") as tf:
                    tf.add(srcDir, arcname="/")

            # install Windows XP files
            if self._stage4Info["windows-xp"]["amd64"]["completed"]:
                srcFile = self._stage4Info["windows-xp"]["amd64"]["work-dir"].image_filepath
                dstFile = os.path.join(dataDir, "microsoft-windows-xp-amd64.image.bz2")
                with bz2.open(dstFile, "wb") as f:
                    with open(srcFile, "rb") as f2:
                        buf = f2.read(4096)
                        while len(buf) > 0:
                            f.write(buf)
                            buf = f2.read(4096)

            # install Windows 7 files
            if self._stage4Info["windows-7"]["amd64"]["completed"]:
                srcFile = self._stage4Info["windows-7"]["amd64"]["work-dir"].image_filepath
                dstFile = os.path.join(dataDir, "microsoft-windows-7-amd64.image.bz2")
                with bz2.open(dstFile, "wb") as f:
                    with open(srcFile, "rb") as f2:
                        buf = f2.read(4096)
                        while len(buf) > 0:
                            f.write(buf)
                            buf = f2.read(4096)

            # install target system files into usb stick
            bFound = False
            for arch, v in self._targetSystemInfo.items():
                if not v["completed"]:
                    continue

                bFound = True
                sp = v["work-dir"].get_old_chroot_dir_paths()[-1]
                dstOsDir = os.path.join(osDir, self._archDirDict[arch])

                os.mkdir(dstOsDir)
                shutil.move(os.path.join(sp, "boot", "vmlinuz"), dstOsDir)
                shutil.move(os.path.join(sp, "boot", "initramfs.img"), dstOsDir)
                shutil.copy(os.path.join(sp, "usr", "share", "memtest86+", "memtest.bin"), dstOsDir)
                FmUtil.makeSquashedRootfsFiles(sp, dstOsDir)

                # install grub
                if arch == "amd64":
                    FmUtil.shellCall("grub-install --removable --target=x86_64-efi --boot-directory=%s --efi-directory=%s --no-nvram" % (mp.mountpoint, mp.mountpoint))
                    FmUtil.shellCall("grub-install --removable --target=i386-pc --boot-directory=%s %s" % (mp.mountpoint, self._devPath))
                    # src = grub_install.Source(base_dir=sp)
                    # dst = grub_install.Target(boot_dir=mp.mountpoint, hdd_dev=self._devPath)
                    # grub_install.install(src, dst, ["i386-pc", "x86_64_efi"])
                elif arch == "arm64":
                    # src = grub_install.Source(base_dir=sp)
                    # dst = grub_install.Target(boot_dir=mp.mountpoint, hdd_dev=self._devPath)
                    # grub_install.install(src, dst, ["arm64_efi"])
                    assert False
                else:
                    assert False

            assert bFound

            # create grub.cfg
            osArchDir = os.path.join("/os", self._archDirDict["amd64"])      # FIXME
            with open(os.path.join(mp.mountpoint, "grub", "grub.cfg"), "w") as f:
                f.write("set default=0\n")
                f.write("set timeout=90\n")
                f.write("set gfxmode=auto\n")
                f.write("\n")

                f.write("insmod efi_gop\n")
                f.write("insmod efi_uga\n")
                f.write("insmod gfxterm\n")
                f.write("insmod all_video\n")
                f.write("insmod videotest\n")
                f.write("insmod videoinfo\n")
                f.write("terminal_output gfxterm\n")
                f.write("\n")

                f.write("menuentry \"Boot %s\" --class gnu-linux --class os {\n" % (self._diskName))
                f.write("    linux %s/vmlinuz root=/dev/ram0 init=/linuxrc dev_uuid=%s looptype=squashfs loop=%s/rootfs.sqfs cdroot dokeymap docache gk.hw.use-modules_load=1\n" % (osArchDir, uuid, osArchDir))            # without gk.hw.use-modules_load=1, squashfs module won't load, sucks
                f.write("    initrd %s/initramfs.img\n" % (osArchDir))
                f.write("}\n")
                f.write("\n")

                f.write("menuentry \"Boot existing OS\" --class os {\n")
                f.write("    set root=(hd0)\n")
                f.write("    chainloader +1\n")
                f.write("}\n")
                f.write("\n")

                # FIXME: memtest86+ does not work under UEFI?
                f.write("menuentry \"Run Memtest86+\" {\n")
                f.write("    linux %s/memtest.bin\n" % (osArchDir))
                f.write("}\n")
                f.write("\n")

                # menuentry "Hardware Information (HDT)" {
                #     linux /os/%ARCH%/hdt
                # }

                # Menu
                f.write("menuentry \"Restart\" {\n")
                f.write("    reboot\n")
                f.write("}\n")
                f.write("\n")

                # Menu
                f.write("menuentry \"Power Off\" {\n")
                f.write("    halt\n")
                f.write("}\n")

            # create livecd
            # FIXME: it sucks that genkernel's initrd requires this file
            with open(os.path.join(mp.mountpoint, "livecd"), "w") as f:
                f.write("")


class WindownCfg(windown.ConfigBase):

    def __init__(self):
        self.check()

    @property
    def quiet(self):
        return False

    @property
    def fetch_command(self):
        return self._wgetCmd(False, False)

    @property
    def resume_command(self):
        return self._wgetCmd(False, True)

    @property
    def fetch_command_quiet(self):
        return self._wgetCmd(True, True)

    @property
    def resume_command_quiet(self):
        return self._wgetCmd(True, True)

    @property
    def checksum_failure_max_tries(self):
        return 1

    def _wgetCmd(self, bQuiet, bContinue):
        ret = r'/usr/libexec/robust_layer/wget '
        if bQuiet:
            ret += r' -q'
        if bContinue:
            ret += r' -c'
        ret += r' -O \"\${FILE}\" \"\${URI}\"'


class PrepareInstallingFpemudOsSysman(gstage4.ScriptInChroot):

    def __init__(self, gentoo_repo_dirpath):
        self._gentooRepoDir = gentoo_repo_dirpath

    def fill_script_dir(self, script_dir_hostpath):
        fullfn = os.path.join(script_dir_hostpath, "main.sh")
        with open(fullfn, "w") as f:
            f.write("#!/bin/sh\n")
            f.write("\n")
            f.write("cd %s\n" % (self._gentooRepoDir))
            f.write("sed -i '/dosym/d' net-misc/stunnel/*.ebuild\n")
            f.write("ebuild $(ls net-misc/stunnel/*.ebuild | head -n1) manifest\n")
            f.write("\n")
        os.chmod(fullfn, 0o755)

    def get_description(self):
        return "Prepare installing fpemud-os-sysman"

    def get_script(self):
        return "main.sh"


DEV_MIN_SIZE_IN_GB = 10                     # 10Gib

DEV_MIN_SIZE = 10 * 1024 * 1024 * 1024      # 10GiB
