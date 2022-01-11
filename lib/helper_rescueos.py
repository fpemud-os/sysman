#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import gstage4
import gstage4.seed_stages
import gstage4.repositories
import gstage4.target_features
#import grub_install
from fm_util import FmUtil
from fm_util import TmpMount
from fm_util import CloudCacheGentoo
from fm_param import FmConst


class RescueDiskBuilder:

    DEV_TYPE_ISO = "iso"
    DEV_TYPE_CDROM = "cdrom"
    DEV_TYPE_USB_STICK = "usb-stick"

    def __init__(self, arch, subarch, devType, devPath, tmpDir, hwInfo):
        self._filesDir = os.path.join(FmConst.dataDir, "rescue", "rescuedisk")
        self._pkgListFile = os.path.join(self._filesDir, "packages.x86_64")
        self._grubCfgSrcFile = os.path.join(self._filesDir, "grub.cfg.in")
        self._pkgDir = os.path.join(FmConst.dataDir, "rescue", "pkg")
        self._tmpRootfsDir = os.path.join(tmpDir, "rootfs")
        self._tmpStageDir = os.path.join(tmpDir, "tmpstage")

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

        assert devType in [self.DEV_TYPE_ISO, self.DEV_TYPE_CDROM, self.DEV_TYPE_USB_STICK]
        self._devType = devType
        self._devPath = devPath

        self._cp = gstage4.ComputingPower.new(hwInfo.hwDict["cpu"]["cores"],
                                              hwInfo.hwDict["memory"]["size"] * 1024 * 1024 * 1024,
                                              10 if "fan" in hwInfo.hwDict else 1)

        self._stage3Files = None
        self._snapshotFile = None

    def check(self):
        if self._devType == self.DEV_TYPE_ISO:
            # FIXME
            pass
        elif self._devType == self.DEV_TYPE_CDROM:
            assert False
        elif self._devType == self.DEV_TYPE_USB_STICK:
            if not FmUtil.isBlkDevUsbStick(self._devPath):
                raise Exception("device %s does not seem to be an usb-stick." % (self._devPath))
            if FmUtil.getBlkDevSize(self._devPath) < DEV_MIN_SIZE:
                raise Exception("device %s needs to be at least %d GB." % (self._devPath, DEV_MIN_SIZE_IN_GB))
            if FmUtil.isMountPoint(self._devPath):
                raise Exception("device %s or any of its partitions is already mounted, umount it first." % (self._devPath))
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
        ftGenkernel = gstage4.target_features.Genkernel()
        ftSystemd = gstage4.target_features.Systemd()
        ftNoDeprecate = gstage4.target_features.DoNotUseDeprecatedPackagesAndFunctions()
        ftSshServer = gstage4.target_features.SshServer()
        ftChronyDaemon = gstage4.target_features.ChronyDaemon()
        ftNetworkManager = gstage4.target_features.NetworkManager()
        ftGettyAutoLogin = gstage4.target_features.GettyAutoLogin()

        # step
        print("        - Initializing...")
        wdir = gstage4.WorkDir(self._tmpRootfsDir)
        wdir.initialize()

        s = gstage4.Settings()
        s.program_name = "fpemud-os-sysman"
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts.arch = "amd64"
        ftPortage.update_target_settings(ts)
        ftGenkernel.update_target_settings(ts)
        ftSystemd.update_target_settings(ts)
        ftNoDeprecate.update_target_settings(ts)

        builder = gstage4.Builder(s, ts, wdir)

        # step
        print("        - Extracting seed stage...")
        with gstage4.seed_stages.GentooStage3Archive(*self._stage3Files) as ss:
            builder.action_unpack(ss)

        # step
        print("        - Installing repositories...")
        repos = [
            gstage4.repositories.GentooSquashedSnapshot(self._snapshotFile),
        ]
        builder.action_init_repositories(repos)

        # step
        print("        - Generating configurations...")
        builder.action_init_confdir()

        # step
        print("        - Updating world...")
        installList = [
            "sys-boot/grub",
            "sys-apps/memtest86+",
        ]
        worldSet = {
            "app-admin/eselec",
            "app-eselect/eselect-timezone",
            "app-editors/nano",
            "sys-kernel/gentoo-sources",
        }
        ftPortage.update_world_set(worldSet)
        ftGenkernel.update_world_set(worldSet)
        ftSystemd.update_world_set(worldSet)
        ftSshServer.update_world_set(worldSet)
        ftChronyDaemon.update_world_set(worldSet)
        ftNetworkManager.update_world_set(worldSet)
        builder.action_update_world(install_list=installList, world_set=worldSet)

        # step
        print("        - Building kernel...")
        builder.action_install_kernel()

        # hidden step: pick out boot related files
        if True:
            sp = wdir.get_old_chroot_dir_paths()[-1]
            for p in ["boot", "usr/lib/grub", "usr/share/grub", "usr/share/locale"]:
                os.makedirs(os.path.dirname(os.path.join(self._tmpStageDir, p)))
                shutil.copytree(os.path.join(sp, p), os.path.join(self._tmpStageDir, p), symlinks=True, dirs_exist_ok=True)

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
        ftGettyAutoLogin.update_custom_script_list(scriptList)
        builder.action_customize_system(custom_script_list=scriptList)

        # step
        print("        - Cleaning up...")
        builder.action_cleanup()

    def exportTargetSystem(self):
        sp = gstage4.WorkDir(self._tmpRootfsDir).get_old_chroot_dir_paths()[-1]

        if self._devType == self.DEV_TYPE_ISO:
            print("        - Creating %s..." % (self._devPath))
            assert False
        elif self._devType == self.DEV_TYPE_CDROM:
            print("        - Burning CD in %s..." % (self._devPath))
            assert False
        elif self._devType == self.DEV_TYPE_USB_STICK:
            print("        - Installing into USB stick %s..." % (self._devPath))
            self._exportToUsbStick(sp)
        else:
            assert False

    def _exportToUsbStick(self, rootfsDir):
        FmUtil.cmdCall("parted", "--script", self._devPath, "mklabel", "msdos", "mkpart", "primary", "fat32", r"0%", r"100%")
        FmUtil.cmdCall("mkfs.vfat", "-F", "32", "-n", DISK_LABEL, self._devPath + "1")

        with TmpMount(self._devPath + "1") as mp:
            # create rootfs.sqfs and rootfs.sqfs.sha512
            sqfsFile = os.path.join(mp.mountpoint, "rootfs.sqfs")
            sqfsSumFile = os.path.join(mp.mountpoint, "rootfs.sqfs.sha512")
            FmUtil.shellCall("/bin/cp %s %s" % (os.path.join(rootfsDir, "boot", "*"), mp.mountpoint))
            FmUtil.shellCall("/usr/bin/mksquashfs %s %s -no-progress -noappend -quiet -e boot/*" % (rootfsDir, sqfsFile))
            FmUtil.shellCall("/usr/bin/sha512sum %s > %s" % (sqfsFile, sqfsSumFile))
            FmUtil.cmdCall("/bin/sed", "-i", "s#%s/\?##" % (mp.mountpoint), sqfsSumFile)   # remove directory prefix in rootfs.sqfs.sha512, sha512sum sucks

            # install grub
            FmUtil.shellCall("/usr/sbin/grub-install --removable --target=x86_64-efi --boot-directory=%s --efi-directory=%s --no-nvram" % (mp.mountpoint, os.path.join(mp.mountpoint, "EFI")))
            FmUtil.shellCall("/usr/sbin/grub-install --removable --target=i386-pc --boot-directory=%s %s" % (mp.mountpoint, self._devPath))
            # src = grub_install.Source(base_dir=self._tmpStageDir)
            # dst = grub_install.Target(boot_dir=mp.mountpoint, hdd_dev=self._devPath)
            # grub_install.install(src, dst, ["i386-pc", "x86_64_efi"])

            # create grub.cfg
            uuid = FmUtil.cmdCall("blkid", "-s", "UUID", "-o", "value", self._devPath).rstrip("\n")
            with open(os.path.join(mp.mountpoint, "grub", "grub.cfg"), "w") as f:
                f.write("set default=0\n")
                f.write("set timeout=90\n")

                f.write("set gfxmode=auto\n")
                f.write("insmod efi_gop\n")
                f.write("insmod efi_uga\n")
                f.write("insmod gfxterm\n")
                f.write("insmod all_video\n")
                f.write("insmod videotest\n")
                f.write("insmod videoinfo\n")
                f.write("terminal_output gfxterm\n")

                f.write("menuentry \"Boot %s\" {\n" % (DISK_NAME))
                f.write("    search --no-floppy --fs-uuid --set %s\n" % (uuid))
                f.write("    linux /data/%s/vmlinuz dev_uuid=%s basedir=/data\n" % ("x86_64", uuid))
                f.write("    initrd /data/%s/initramfs.img\n" % ("x86_64"))
                f.write("}\n")

                f.write("menuentry \"Boot existing OS\" {\n")
                f.write("    set root=(hd0)\n")
                f.write("    chainloader +1\n")
                f.write("}\n")

                f.write("menuentry \"Run Memtest86+ (RAM test)\" {\n")
                f.write("    linux /data/%s/memtest\n" % ("x86_64"))
                f.write("}\n")

                # menuentry "Hardware Information (HDT)" {
                #     linux /data/%ARCH%/hdt
                # }

                # Menu
                f.write("menuentry \"Restart\" {\n")
                f.write("    reboot\n")
                f.write("}\n")

                # Menu
                f.write("menuentry \"Power Off\" {\n")
                f.write("    halt\n")
                f.write("}\n")


DISK_NAME = "SystemRescueDisk"

DISK_LABEL = "SYSREC"

DEV_MIN_SIZE_IN_GB = 1                      # 1Gib

DEV_MIN_SIZE = 1 * 1024 * 1024 * 1024       # 1GiB
