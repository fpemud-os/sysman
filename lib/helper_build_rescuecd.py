#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import shutil
import gstage4
import gstage4.scripts
import gstage4.seed_stages
import gstage4.repositories
import gstage4.target_features
import robust_layer.simple_fops
from fm_util import FmUtil
from fm_util import TmpMount
from fm_util import CloudCacheGentoo
from fm_util import PrintLoadAvgThread
from fm_util import CcacheLocalService
from fm_util import Stage4Overlay
from fm_param import FmConst


class RescueDiskBuilder:

    DEV_TYPE_ISO = "iso"
    DEV_TYPE_CDROM = "cdrom"
    DEV_TYPE_USB_STICK = "usb-stick"

    def __init__(self, devType, devPath, tmpDir, hwInfo, diskName, diskLabel):
        self._archInfoDict = {
            "amd64": ["amd64", "openrc", os.path.join(tmpDir, "rescd-rootfs-amd64"), os.path.join(tmpDir, "rescd-tmp-amd64"), False],   # [subarch, variant, rootfs-dir, tmp-stage-dir, complete-flag]
            # "arm64": ["arm64", None],
        }
        self._archDirDict = {
            "amd64": "x86_64",
            "arm64": "arm64",
        }

        assert devType in [self.DEV_TYPE_ISO, self.DEV_TYPE_CDROM, self.DEV_TYPE_USB_STICK]
        self._devType = devType
        self._devPath = devPath

        self._cp = gstage4.ComputingPower.new(hwInfo.hwDict["cpu"]["cores"],
                                              hwInfo.hwDict["memory"]["size"] * 1024 * 1024 * 1024,
                                              10 if "fan" in hwInfo.hwDict else 1)

        self._diskName = diskName
        self._diskLabel = diskLabel

        self._stage3FilesDict = dict()
        self._snapshotFile = None

    def getArchName(self, arch):
        return self._archDirDict[arch]

    def check(self):
        if self._devType == self.DEV_TYPE_ISO:
            raise NotImplementedError()
        elif self._devType == self.DEV_TYPE_CDROM:
            raise NotImplementedError()
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
        for arch, v in self._archInfoDict.items():
            assert arch in cache.get_arch_list()
            assert v[0] in cache.get_subarch_list(arch)

        # prefer local stage3 file
        for arch, v in self._archInfoDict.items():
            try:
                self._stage3FilesDict[arch] = cache.get_latest_stage3(arch, v[0], v[1], cached_only=True)
            except FileNotFoundError:
                self._stage3FilesDict[arch] = cache.get_latest_stage3(arch, v[0], v[1])

        # always use newest snapshot
        self._snapshotFile = cache.get_latest_snapshot()

    def buildTargetSystem(self, arch):
        tmpRootfsDir = self._archInfoDict[arch][2]
        tmpStageDir = self._archInfoDict[arch][3]

        c = CcacheLocalService()

        ftPortage = gstage4.target_features.UsePortage()
        ftGenkernel = gstage4.target_features.UseGenkernel()
        ftOpenrc = gstage4.target_features.UseOpenrc()
        ftNoDeprecate = gstage4.target_features.DoNotUseDeprecatedPackagesAndFunctions()
        ftPerferGnu = gstage4.target_features.PreferGnuAndGpl()
        ftSshServer = gstage4.target_features.SshServer()
        ftChronyDaemon = gstage4.target_features.ChronyDaemon()
        ftNetworkManager = gstage4.target_features.NetworkManager()
        # ftGettyAutoLogin = gstage4.target_features.GettyAutoLogin()

        # step
        print("        - Initializing...")
        wdir = gstage4.WorkDir(tmpRootfsDir)
        wdir.initialize()

        robust_layer.simple_fops.mkdir(tmpStageDir)

        s = gstage4.Settings()
        s.program_name = FmConst.programName
        s.verbose_level = 0
        s.host_computing_power = self._cp
        s.host_distfiles_dir = FmConst.distDir

        ts = gstage4.TargetSettings()
        ts.arch = arch
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
            installList = []
            if c.is_enabled():
                installList.append("dev-util/ccache")

            worldSet = {
                "app-admin/eselect",
                "app-admin/fpemud-os-rescuecd-meta",
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
                "net-analyzer/nmap",
                "net-analyzer/tcpdump",
                "net-analyzer/traceroute",
                "net-fs/cifs-utils",
                "net-fs/nfs-utils",
                "net-misc/rsync",
                "net-misc/wget",
                "sys-apps/dmidecode",
                "sys-apps/gptfdisk",
                "sys-apps/lshw",
                "sys-apps/smartmontools",
                "sys-boot/grub",            # also required by boot-chain in USB stick
                "sys-apps/file",
                "sys-apps/hdparm",
                "sys-apps/memtest86+",      # also required by boot-chain in USB stick
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
            ftSshServer.update_world_set(worldSet)
            ftChronyDaemon.update_world_set(worldSet)
            ftNetworkManager.update_world_set(worldSet)

            scriptList = []
            if True:
                targetFile = os.path.join(gentooRepo.get_datadir_path(), "eclass", "git-r3.eclass")
                cmd = "sed -i 's#git fetch#/usr/libexec/robust_layer/git fetch#' %s" % (targetFile)
                scriptList.append(gstage4.scripts.OneLinerScript("Modify git-r3.eclass", cmd))

            builder.action_update_world(preprocess_script_list=scriptList, install_list=installList, world_set=worldSet)

        # step
        with PrintLoadAvgThread("        - Building kernel..."):
            scriptList = []
            if True:
                hostp = "/var/cache/bbki/distfiles/git-src/git/bcachefs.git"
                if not os.path.isdir(hostp):
                    raise Exception("directory \"%s\" does not exist in host system" % (hostp))
                s = gstage4.scripts.PlacingFilesScript("Install bcachefs kernel")
                s.append_dir("/usr/src/linux-%s-bcachefs" % (FmUtil.getKernelVerStr(hostp)), 0, 0, dmode=0o755, fmode=0o755, hostpath=hostp, recursive=True)    # script files in kernel source needs to be executable, simply make all files rwxrwxrwx
                scriptList.append(s)
            if True:
                buf = ""
                buf += "#!/bin/bash\n"
                buf += "echo 'CONFIG_BCACHEFS_FS=y' >> /usr/share/genkernel/arch/x86_64/generated-config\n"
                buf += "echo 'CONFIG_BCACHEFS_QUOTA=y' >> /usr/share/genkernel/arch/x86_64/generated-config\n"
                buf += "echo 'CONFIG_BCACHEFS_POSIX_ACL=y' >> /usr/share/genkernel/arch/x86_64/generated-config\n"
                scriptList.append(gstage4.scripts.ScriptFromBuffer("Add bcachfs kernel config", buf))
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

            # install files into usb stick
            for arch, v in self._archInfoDict.items():
                tmpRootfsDir = v[2]
                sp = gstage4.WorkDir(tmpRootfsDir).get_old_chroot_dir_paths()[-1]
                dstOsDir = os.path.join(osDir, self._archDirDict[arch])

                os.mkdir(dstOsDir)
                shutil.move(os.path.join(sp, "boot", "vmlinuz"), dstOsDir)
                shutil.move(os.path.join(sp, "boot", "initramfs.img"), dstOsDir)
                shutil.copy(os.path.join(sp, "usr", "share", "memtest86+", "memtest.bin"), dstOsDir)
                FmUtil.makeSquashedRootfsFiles(sp, dstOsDir)

                # install grub
                if arch == "amd64":
                    FmUtil.shellCall("/usr/sbin/grub-install --removable --target=x86_64-efi --boot-directory=%s --efi-directory=%s --no-nvram" % (mp.mountpoint, mp.mountpoint))
                    FmUtil.shellCall("/usr/sbin/grub-install --removable --target=i386-pc --boot-directory=%s %s" % (mp.mountpoint, self._devPath))
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

            # create README.txt
            with open(os.path.join(mp.mountpoint, README_FILENAME), "w") as f:
                buf = README_CONTENT.strip("\n") + "\n"
                buf = buf.replace("%DISK_NAME%", self._diskName)
                f.write(buf)

            # create livecd
            # FIXME: it sucks that genkernel's initrd requires this file
            with open(os.path.join(mp.mountpoint, "livecd"), "w") as f:
                f.write("")


DEV_MIN_SIZE_IN_GB = 1                      # 1Gib

DEV_MIN_SIZE = 1 * 1024 * 1024 * 1024       # 1GiB

README_FILENAME = "README.txt"

README_CONTENT = """
This lists the possible command line options that can be used to tweak the boot
process of this %DISK_NAME%.  This list contains a few options that are built-in
to the kernel, but that have been proven very useful. Also, all options that
start with "do" have a "no" inverse, that does the opposite.  For example, "doscsi"
enables SCSI support in the initial ramdisk boot, while "noscsi" disables it.


Hardware options:
acpi=on         This loads support for ACPI and also causes the acpid daemon to
                be started by the CD on boot.  This is only needed if your
                system requires ACPI to function properly.  This is not
                required for Hyperthreading support.
acpi=off        Completely disables ACPI.  This is useful on some older systems
                and is also a requirement for using APM.  This will disable any
                Hyperthreading support of your processor.
console=X       This sets up serial console access for the CD.  The first
                option is the device, usually ttyS0 on x86, followed by any
                connection options, which are comma separated.  The default
                options are 9600,8,n,1.
dmraid=X        This allows for passing options to the device-mapper RAID
                subsystem.  Options should be encapsulated in quotes.
doapm           This loads APM driver support.  This requires you to also use
                acpi=off.
dopcmcia        This loads support for PCMCIA and Cardbus hardware and also
                causes the pcmcia cardmgr to be started by the CD on boot.
                This is only required when booting from PCMCIA/Cardbus devices.
doscsi          This loads support for most SCSI controllers.  This is also a
                requirement for booting most USB devices, as they use the SCSI
                subsystem of the kernel.
hda=stroke      This allows you to partition the whole hard disk even when your
                BIOS is unable to handle large disks.  This option is only used
                on machines with an older BIOS.  Replace hda with the device
                that is requiring this option.
ide=nodma       This forces the disabling of DMA in the kernel and is required
                by some IDE chipsets and also by some CDROM drives.  If your
                system is having trouble reading from your IDE CDROM, try this
                option.  This also disables the default hdparm settings from
                being executed.
noapic          This disables the Advanced Programmable Interrupt Controller
                that is present on newer motherboards.  It has been known to
                cause some problems on older hardware.
nodetect        This disables all of the autodetection done by the CD,
                including device autodetection and DHCP probing.  This is
                useful for doing debugging of a failing CD or driver.
nodhcp          This disables DHCP probing on detected network cards.  This is
                useful on networks with only static addresses.
nodmraid        Disables support for device-mapper RAID, such as that used for
                on-board IDE/SATA RAID controllers.
nofirewire      This disables the loading of Firewire modules.  This should
                only be necessary if your Firewire hardware is causing
                a problem with booting the CD.
nogpm           This diables gpm console mouse support.
nohotplug       This disables the loading of the hotplug and coldplug init
                scripts at boot.  This is useful for doing debugging of a
                failing CD or driver.
nokeymap        This disables the keymap selection used to select non-US
                keyboard layouts.
nolapic         This disables the local APIC on Uniprocessor kernels.
nosata          This disables the loading of Serial ATA modules.  This is used
                if your system is having problems with the SATA subsystem.
nosmp           This disables SMP, or Symmetric Multiprocessing, on SMP-enabled
                kernels.  This is useful for debugging SMP-related issues with
                certain drivers and motherboards.
nosound         This disables sound support and volume setting.  This is useful
                for systems where sound support causes problems.
nousb           This disables the autoloading of USB modules.  This is useful
                for debugging USB issues.
slowusb         This adds some extra pauses into the boot process for slow
                USB CDROMs, like in the IBM BladeCenter.

Volume/Device Management:
doevms          This enables support for IBM's pluggable EVMS, or Enterprise
                Volume Management System.  This is not safe to use with lvm2.
dolvm           This enables support for Linux's Logical Volume Management.
                This is not safe to use with evms2.

Screen reader access:
speakup.synth=synth  starts speakup using a given synthesizer.
                     supported synths are acntpc, acntsa, apollo, audptr, bns,
                     decext, dectlk, dtlk, keypc, ltlk, spkout and txprt.
                     Also, soft is supported for software speech and dummy is
                     supported for testing.
speakup.quiet=1      sets the synthesizer not to speak until a key is pressed.
speakup_SYNTH.port=n sets the port for internal synthesizers.
speakup_SYNTH.ser=n  sets the serial port for external synthesizers.

Other options:
debug           Enables debugging code.  This might get messy, as it displays
                a lot of data to the screen.
docache         This caches the entire runtime portion of the CD into RAM,
                which allows you to umount /mnt/cdrom and mount another CDROM.
                This option requires that you have at least twice as much
                available RAM as the size of the CD.
doload=X        This causes the initial ramdisk to load any module listed, as
                well as dependencies.  Replace X with the module name.
                Multiple modules can be specified by a comma-separated list.
dosshd          Starts sshd on boot, which is useful for unattended installs.
passwd=foo      Sets whatever follows the equals as the root password, which
                is required for dosshd since we scramble the root password.
noload=X        This causes the initial ramdisk to skip the loading of a
                specific module that may be causing a problem.  Syntax matches
                that of doload.
nonfs           Disables the starting of portmap/nfsmount on boot.
nox             This causes an X-enabled LiveCD to not automatically start X,
                but rather, to drop to the command line instead.
scandelay       This causes the CD to pause for 10 seconds during certain
                portions the boot process to allow for devices that are slow to
                initialize to be ready for use.
scandelay=X     This allows you to specify a given delay, in seconds, to be
                added to certain portions of the boot process to allow for
                devices that are slow to initialize to be ready for use.
                Replace X with the number of seconds to pause.
"""
