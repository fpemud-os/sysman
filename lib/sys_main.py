#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import shutil
import pyudev
import tarfile
import strict_pgs
import strict_fsh
import strict_hdds
import bbki.util
import robust_layer.simple_fops
from datetime import datetime
from fm_util import FmUtil
from fm_util import BootDirWriter
from fm_util import TmpMount
from fm_param import FmConst
from helper_dyncfg import DynCfgModifier
from helper_rescue import RescueCdBuilder
from helper_installcd import InstallCdBuilder
from helper_bbki import BbkiWrapper
from helper_pkg_warehouse import EbuildRepositories
from helper_pkg_warehouse import EbuildOverlays
from helper_pkg_warehouse import CloudOverlayDb
from sys_machine_info import HwInfoPcBranded
from sys_machine_info import HwInfoPcAssembled
from sys_machine_info import DevHwInfoDb


class FmMain:

    def __init__(self, param):
        self.param = param
        self.infoPrinter = self.param.infoPrinter

    def doShow(self):
        '''
        >>> Example:

        System status: unstable

        Hardware:
            Unknown hardware
        Boot mode:
            UEFI
        Main OS:
            Linux (kernel-x86_64-4.4.6)
        Rescue OS:
            Installed
        Auxillary OSes:
            None

        Storage layout:
            Name: efi-bcache-lvm
            ESP partition: /dev/sdc1
            Swap partition: /dev/sdc2 (16.0GiB)
            Cache partition: /dev/sdc3 (102.7GiB)
            LVM PVs: /dev/sda,bcache0 /dev/sdb,bcache16 (total: 8.2TiB)
        Swap:
            Disabled
        Logging:
            To harddisk (/var/log)

        Backend graphics devices:
            /dev/dri/card1 /dev/dri/card2 (total: 16GiB 14.3TFLOPs)

        System users:       root, nobody
        System groups:      root, nobody, nogroup, wheel, users

        Repositories:
            fpemud-overlay    [Dirty]       (Last Update: 2016-01-01 00:00:00)
            local             [Not Exist]

        Overlays:
            wrobel    [Subversion] (https://overlays.gentoo.org/svn/dev/wrobel     )

        Selected packages:
            app-admin/ansible               (repo-gentoo)
            app-misc/sway                   (overlay-uly55e5)
        '''

        self.param.sysChecker.basicCheckWithOverlayContent()

        bbkiObj = BbkiWrapper()
        repoman = EbuildRepositories()
        layman = EbuildOverlays()

        if self.param.runMode != "normal":
            print("WARNING: Running in \"%s\" mode!!!" % (self.param.runMode))
            print("")

        if self.param.runMode in ["normal", "setup"]:
            s = "System status: "
            if bbkiObj.isStable():
                s += "stable"
            else:
                s += "unstable"
            print(s)
            print("")

        print("Hardware:")
        hwInfo = self.param.machineInfoGetter.hwInfo()
        if isinstance(hwInfo, HwInfoPcBranded):
            print("    %s %s" % (hwInfo.vendor, hwInfo.model))
        elif isinstance(hwInfo, HwInfoPcAssembled):
            print("    DIY PC")
        else:
            assert False

        print("Boot mode:")
        if bbki.util.get_boot_mode() == bbki.BootMode.EFI:
            print("    UEFI")
        elif bbki.util.get_boot_mode() == bbki.BootMode.BIOS:
            print("    BIOS")
        else:
            assert False

        print("Main OS:")
        be = bbkiObj.get_pending_boot_entry()
        if be is None:
            be = "None"
        else:
            be = "Linux (%s)" % (be.postfix)
        print("    %s" % (be))

        print("Rescue OS:")
        if bbkiObj.isRescueOsInstalled():
            print("    Installed")
        else:
            print("    Not installed")

        if self.param.runMode in ["normal", "setup"]:
            auxOsInfo = bbkiObj.getAuxOsInfo()
            if len(auxOsInfo) > 0:
                print("Auxillary OSes:")
                for item in auxOsInfo:
                    sys.stdout.write("    %s:" % (item.name))
                    for i in range(0, 20 - len(item.name)):
                        sys.stdout.write(" ")
                    print(item.partition_path)

        print("")

        layout = None
        if self.param.runMode in ["normal", "setup"]:
            layout = strict_hdds.get_current_storage_layout()

        print("Storage layout:")
        if True:
            def partSize(devpath):
                sz = FmUtil.getBlkDevSize(devpath)
                return FmUtil.formatSize(sz)

            if layout is None:
                print("    State: unusable")
            else:
                print("    Name: %s" % (layout.name))
                print("    State: ready")
                if layout.name == "bios-ext4":
                    print("    Boot disk: %s" % (layout.boot_disk))
                    print("    Root partititon: %s (%s)" % (layout.dev_rootfs, partSize(layout.dev_rootfs)))
                elif layout.name == "efi-ext4":
                    print("    Boot disk: %s" % (layout.boot_disk))
                    print("    Root partititon: %s (%s)" % (layout.dev_rootfs, partSize(layout.dev_rootfs)))
                elif layout.name in ["efi-btrfs"]:
                    print("    Boot disk: %s" % (layout.boot_disk))
                    totalSize = 0
                    pvStrList = []
                    for hddDevPath in layout.get_hdd_list():
                        parti = layout.get_hdd_data_partition(hddDevPath)
                        pvStrList.append("%s" % (parti))
                        totalSize += FmUtil.getBlkDevSize(parti)
                    print("    HDDs: %s (total: %s)" % (" ".join(pvStrList), FmUtil.formatSize(totalSize)))
                elif layout.name == "efi-bcache-btrfs":
                    if layout.get_ssd() is not None:
                        print("    SSD: %s (boot disk)" % (layout.get_ssd()))
                        if layout.get_ssd_swap_partition() is not None:
                            print("    Swap partition: %s (%s)" % (layout.get_ssd_swap_partition(), partSize(layout.get_ssd_swap_partition())))
                        else:
                            print("    Swap partition: None")
                        print("    Cache partition: %s (%s, hit-ratio: %.2f%%)" % (layout.get_ssd_cache_partition(), partSize(layout.get_ssd_cache_partition()), layout.get_bcache_stats("cache_hit_ratio_day") * 100))
                    else:
                        print("    SSD: None")
                        print("    Boot disk: %s" % (layout.boot_disk))
                    totalSize = 0
                    pvStrList = []
                    for hddDevPath in layout.get_hdd_list():
                        bcacheDevPath = layout.get_hdd_bcache_dev(hddDevPath)
                        pvStrList.append("%s,%s" % (hddDevPath, bcacheDevPath.replace("/dev/", "")))
                        totalSize += FmUtil.getBlkDevSize(bcacheDevPath)
                    print("    HDDs: %s (total: %s)" % (" ".join(pvStrList), FmUtil.formatSize(totalSize)))
                elif layout.name == "efi-bcachefs":
                    if layout.get_ssd() is not None:
                        print("    SSD: %s (boot disk)" % (layout.get_ssd()))
                        if layout.get_ssd_swap_partition() is not None:
                            print("    Swap partition: %s (%s)" % (layout.get_ssd_swap_partition(), partSize(layout.get_ssd_swap_partition())))
                        else:
                            print("    Swap partition: None")
                        print("    Cache partition: %s (%s)" % (layout.get_ssd_cache_partition(), partSize(layout.get_ssd_cache_partition())))
                    else:
                        print("    SSD: None")
                        print("    Boot disk: %s" % (layout.boot_disk))
                    totalSize = 0
                    pvStrList = []
                    for hddDevPath in layout.get_hdd_list():
                        parti = layout.get_hdd_data_partition(hddDevPath)
                        pvStrList.append("%s" % (parti))
                        totalSize += FmUtil.getBlkDevSize(parti)
                    print("    HDDs: %s (total: %s)" % (" ".join(pvStrList), FmUtil.formatSize(totalSize)))
                else:
                    assert False

        print("Swap:")
        if self.param.runMode == "prepare":
            print("    Unknown")
        elif self.param.runMode == "setup":
            if layout is None:
                print("    Unknown")
            else:
                print("    Disabled")
        elif self.param.runMode == "normal":
            if layout is None:
                print("    Unknown")
            else:
                if layout.dev_swap is None:
                    print("    Disabled")
                else:
                    serviceName = FmUtil.systemdFindSwapServiceInDirectory("/etc/systemd/system", layout.dev_swap)
                    if serviceName is None or not FmUtil.systemdIsServiceEnabled(serviceName):
                        print("    Disabled")
                    else:
                        print("    Enabled (%s)" % (FmUtil.formatSize(layout.get_swap_size())))
        else:
            assert False

        # FIXME
        print("Logging:")
        if True:
            print("    To harddisk (/var/log)")

        print("")

        if True:
            ret = FmUtil.findBackendGraphicsDevices()
            if len(ret) > 0:
                totalMem = 0
                totalFlopsForFp32 = 0
                for path in ret:
                    rc = FmUtil.getVendorIdAndDeviceIdByDevNode(path)
                    if rc is None:
                        totalMem = None
                        break
                    info = DevHwInfoDb.getDevHwInfo(rc[0], rc[1])
                    if info is None:
                        totalMem = None
                        break
                    if "mem" not in info or not isinstance(info["mem"], int):
                        totalMem = None
                        break
                    if "fp32" not in info or not isinstance(info["fp32"], int):
                        totalMem = None
                        break
                    totalMem += info["mem"]
                    totalFlopsForFp32 += info["fp32"]

                totalStr = "unknown"
                if totalMem is not None:
                    totalStr = "%s %s" % (FmUtil.formatSize(totalMem), FmUtil.formatFlops(totalFlopsForFp32))

                print("Backend graphics devices:")
                print("    %s (total: %s)" % (" ".join(ret), totalStr))
                print("")

        with strict_pgs.PasswdGroupShadow() as pgs:
            print("System users:       %s" % (", ".join(pgs.getSystemUserList())))
            print("System groups:      %s" % (", ".join(pgs.getSystemGroupList())))
            print("")

        print("Repositories:")
        repoList = repoman.getRepositoryList()
        if len(repoList) > 0:
            maxLen = FmUtil.strListMaxLen(repoList)
            for repoName in repoList:
                s1 = FmUtil.pad(repoName, maxLen)
                if repoman.isRepoExist(repoName):
                    print("    %s [Good     ] Last Update: %s" % (s1, FmUtil.getDirLastUpdateTime(repoman.getRepoDir(repoName))))
                else:
                    print("    %s [Not Exist]" % (s1))
        else:
            print("    None")

        print("")

        print("Overlays:")
        overlayList = layman.getOverlayList()
        if len(overlayList) > 0:
            tlist2 = []
            tlist3 = []
            for lname in overlayList:
                if layman.getOverlayType(lname) == "static":
                    ltype = "Static"
                    lurl = ""
                else:
                    ltype, lurl = layman.getOverlayVcsTypeAndUrl(lname)
                    if ltype == "git":
                        ltype = "Git"
                    elif ltype == "svn":
                        ltype = "Subversion"
                    else:
                        assert False
                tlist2.append(ltype)
                tlist3.append(lurl)
            maxLen1 = FmUtil.strListMaxLen(overlayList)
            maxLen2 = FmUtil.strListMaxLen(tlist2)
            maxLen3 = FmUtil.strListMaxLen(tlist3)
            for i in range(0, len(overlayList)):
                s1 = FmUtil.pad(overlayList[i], maxLen1)
                s2 = FmUtil.pad(tlist2[i], maxLen2)
                s3 = FmUtil.pad(tlist3[i], maxLen3)
                print("    %s [%s %s] Last Update: %s" % (s1, s2, s3, FmUtil.getDirLastUpdateTime(layman.getOverlayDir(overlayList[i]))))
        else:
            print("    None")

        print("")

        print("Selected packages:")
        if True:
            pkgList = FmUtil.portageReadWorldFile(FmConst.worldFile)
            maxLen = max([len(x) for x in pkgList])

            for repoName in repoman.getRepositoryList():
                tempList = []
                for pkg in pkgList:
                    if os.path.exists(os.path.join(repoman.getRepoDir(repoName), pkg)):
                        print("    %s (repo-%s)" % (FmUtil.pad(pkg, maxLen), repoName))
                    else:
                        tempList.append(pkg)
                pkgList = tempList

            for overlayName in layman.getOverlayList():
                tempList = []
                for pkg in pkgList:
                    if os.path.exists(os.path.join(layman.getOverlayDir(overlayName), pkg)):
                        print("    %s (overlay-%s)" % (FmUtil.pad(pkg, maxLen), overlayName))
                    else:
                        tempList.append(pkg)
                pkgList = tempList

            for pkg in pkgList:
                print("    %s" % (pkg))

        return 0

    def doUpdate(self, bSync):
        self.param.sysChecker.basicCheck()

        self.param.sysUpdater.update(bSync, True)
        return 0

    def doClean(self, bPretend):
        self.param.sysChecker.basicCheckWithOverlayContent()

        self.param.sysCleaner.clean(bPretend)
        return 0

    def doStablize(self):
        self.param.sysChecker.basicCheckWithOverlayContent()

        self.param.sysUpdater.stablize()
        return 0

    def doHddAdd(self, devpath, bMainBoot, bWithBadBlock):
        if self.param.runMode == "prepare":
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1

        layout = strict_hdds.get_current_storage_layout()
        if layout is None:
            print("Invalid storage layout.", file=sys.stderr)
            return 1

        if layout.name in ["bios-ext4", "efi-ext4"]:
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))
        elif layout.name in ["efi-btrfs", "efi-bcache-btrfs", "efi-bcachefs"]:
            self.infoPrinter.printInfo(">> Adding harddisk...")
            layout.add_disk(devpath)
            print("")
        else:
            assert False

        self.param.sysUpdater.updateAfterHddAddOrRemove(self.param.machineInfoGetter.hwInfo(), layout, BbkiWrapper())

        return 0

    def doHddRemove(self, devpath):
        if self.param.runMode == "prepare":
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1

        layout = strict_hdds.get_current_storage_layout()
        if layout is None:
            print("Invalid storage layout.", file=sys.stderr)
            return 1

        if layout.name in ["bios-ext4", "efi-ext4"]:
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))
        elif layout.name in ["efi-btrfs", "efi-bcache-btrfs", "efi-bcachefs"]:
            self.infoPrinter.printInfo(">> Removing harddisk...")
            layout.remove_disk(devpath)
            print("")
        else:
            assert False

        self.param.sysUpdater.updateAfterHddAddOrRemove(self.param.machineInfoGetter.hwInfo(), layout, BbkiWrapper())

        return 0

    def doEnableSwap(self):
        if self.param.runMode == "prepare":
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1

        layout = strict_hdds.get_current_storage_layout()
        if layout is None:
            print("Invalid storage layout.", file=sys.stderr)
            return 1

        self.param.swapManager.enableSwap(layout)

        if layout.name in ["bios-ext4", "efi-ext4"]:
            swapSizeStr = FmUtil.formatSize(os.path.getsize(layout.dev_swap))
            print("Swap File: %s (size:%s)" % (layout.dev_swap, swapSizeStr))
        elif layout.name in ["efi-bcache-btrfs", "efi-bcachefs"]:
            uuid = pyudev.Device.from_device_file(pyudev.Context(), layout.dev_swap).get("ID_FS_UUID")
            swapSizeStr = FmUtil.formatSize(FmUtil.getBlkDevSize(layout.dev_swap))
            print("Swap Partition: %s (UUID:%s, size:%s)" % (layout.dev_swap, uuid, swapSizeStr))
        else:
            assert False

        return 0

    def doDisableSwap(self):
        if self.param.runMode == "prepare":
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1

        layout = strict_hdds.get_current_storage_layout()
        if layout is None:
            print("Invalid storage layout.", file=sys.stderr)
            return 1

        if layout.dev_swap is None:
            return 0

        self.param.swapManager.disableSwap(layout)
        return 0

    def doAddUser(self, username):
        self.param.userManager.addUser(username)
        return 0

    def doRemoveUser(self, username):
        self.param.userManager.removeUser(username)
        return 0

    def doResetUserPassword(self, username):
        self.param.userManager.resetUserPassword(username)
        return 0

    def doModifyUser(self, username):
        assert False

    def doFlushUser(self, username):
        self.param.userManager.flushUser(username)
        return 0

    def doAddOverlay(self, overlayName, vcsType, url):
        self.param.sysChecker.basicCheckWithOverlayContent()

        layman = EbuildOverlays()

        if layman.isOverlayExist(overlayName):
            print("The specified overlay has already been installed.", file=sys.stderr)
            return 1

        # update overlay database
        self.infoPrinter.printInfo(">> Updating overlay database...")
        cloudDb = CloudOverlayDb()
        cloudDb.update()
        print("")

        # install overlay
        if vcsType is None or url is None:
            if not cloudDb.hasOverlay(overlayName):
                print("Overlay \"%s\" is not in overlay database, --vcs-type and --url must be specified." % (overlayName), file=sys.stderr)
                return 1
            vcsType, url = cloudDb.getOverlayVcsTypeAndUrl(overlayName)
            self.infoPrinter.printInfo(">> Installing %s overlay \"%s\" from \"%s\"..." % (vcsType, overlayName, url))
        else:
            self.infoPrinter.printInfo(">> Installing overlay...")
        layman.addTransientOverlay(overlayName, vcsType, url)
        print("")

        return 0

    def doRemoveOverlay(self, overlayName):
        layman = EbuildOverlays()

        if not layman.isOverlayExist(overlayName):
            print("Overlay \"%s\" is not installed." % (overlayName), file=sys.stderr)
            return 1

        overlayType = None
        try:
            overlayType = layman.getOverlayType(overlayName)
        except BaseException:
            # allow removing corrupted overlay
            overlayType = "trusted"
        if overlayType == "static":
            print("Overlay \"%s\" is a static overlay." % (overlayName), file=sys.stderr)
            return 1

        layman.removeOverlay(overlayName)
        return 0

    def doEnableOverlayPkg(self, overlayName, pkgName):
        self.param.sysChecker.basicCheckWithOverlayContent()

        layman = EbuildOverlays()

        if not layman.isOverlayExist(overlayName):
            print("Overlay \"%s\" is not installed." % (overlayName), file=sys.stderr)
            return 1
        if layman.getOverlayType(overlayName) != "transient":
            print("Overlay \"%s\" is not a transient overlay." % (overlayName), file=sys.stderr)
            return 1

        layman.enableOverlayPackage(overlayName, pkgName)
        return 0

    def doDisableOverlayPkg(self, overlayName, pkgName):
        self.param.sysChecker.basicCheckWithOverlayContent()

        layman = EbuildOverlays()

        if not layman.isOverlayExist(overlayName):
            print("Overlay \"%s\" is not installed." % (overlayName), file=sys.stderr)
            return 1
        if layman.getOverlayType(overlayName) != "transient":
            print("Overlay \"%s\" is not a transient overlay." % (overlayName), file=sys.stderr)
            return 1

        layman.disableOverlayPackage(overlayName, pkgName)
        return 0

    def installPackage(self, packageName, bTest):
        self.param.sysChecker.basicCheckWithOverlayContent()

        self.param.pkgManager.installPackage(packageName, bTest)
        return 0

    def uninstallPackage(self, packageName):
        self.param.sysChecker.basicCheckWithOverlayContent()

        self.param.pkgManager.uninstallPackage(packageName)
        return 0

    def installRescueOs(self):
        if self.param.runMode in ["prepare", "setup"]:
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1
        self.param.sysChecker.basicCheckWithOverlayContent()

        # modify dynamic config
        self.infoPrinter.printInfo(">> Preparing...")
        if True:
            dcm = DynCfgModifier()
            dcm.updateMirrors()
            dcm.updateDownloadCommand()
            dcm.updateParallelism(self.param.machineInfoGetter.hwInfo())
            dcm.updateCcache()
        print("")

        # build
        bbkiObj = BbkiWrapper()
        builder = RescueCdBuilder(RescueCdBuilder.DEV_TYPE_RESCUE_OS,
                                  self.param.tmpDirOnHdd, self.param.machineInfoGetter.hwInfo(),
                                  rescue_os_spec=bbkiObj.rescue_os_spec)

        self.infoPrinter.printInfo(">> Downloading files...")
        builder.downloadFiles()
        print("")

        self.infoPrinter.printInfo(">> Building Rescue OS...")
        builder.buildTargetSystem("amd64")
        print("")

        # install
        layout = strict_hdds.get_current_storage_layout()
        with BootDirWriter(layout):
            try:
                self.infoPrinter.printInfo(">> Installing Rescue OS into /boot...")
                builder.exportTargetSystem()
                print("")

                self.infoPrinter.printInfo(">> Updating boot-loader...")
                bbkiObj.updateBootloaderAfterRescueOsChange()
                print("")
            except Exception:
                shutil.rmtree(bbkiObj.rescue_os_spec.root_dir)
                raise

        return 0

    def uninstallRescueOs(self):
        if self.param.runMode in ["prepare", "setup"]:
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1
        self.param.sysChecker.basicCheckWithOverlayContent()

        layout = strict_hdds.get_current_storage_layout()
        bbkiObj = BbkiWrapper()

        if not bbkiObj.isRescueOsInstalled():
            print("Rescue OS is not installed.", file=sys.stderr)
            return 1

        with BootDirWriter(layout):
            self.infoPrinter.printInfo(">> Uninstalling Rescue OS...")
            robust_layer.simple_fops.rm(bbkiObj.rescue_os_spec.root_dir)
            print("")

            self.infoPrinter.printInfo(">> Updating boot-loader...")
            bbkiObj.updateBootloaderAfterRescueOsChange()
            print("")

        return 0

    def buildRescueDisk(self, devPath):
        if self.param.runMode in ["prepare", "setup"]:
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1
        self.param.sysChecker.basicCheckWithOverlayContent()

        # modify dynamic config
        self.infoPrinter.printInfo(">> Preparing...")
        if True:
            dcm = DynCfgModifier()
            dcm.updateMirrors()
            dcm.updateDownloadCommand()
            dcm.updateParallelism(self.param.machineInfoGetter.hwInfo())
            dcm.updateCcache()
        print("")

        # build
        if devPath.endswith(".iso"):
            builder = RescueCdBuilder(RescueCdBuilder.DEV_TYPE_ISO,
                                      self.param.tmpDirOnHdd, self.param.machineInfoGetter.hwInfo(),
                                      file_path=devPath, disk_name=FmConst.rescueDiskName, disk_label=FmConst.rescueDiskLabel)
        elif re.fullmatch("/dev/sd.*", devPath) is not None:
            builder = RescueCdBuilder(RescueCdBuilder.DEV_TYPE_USB_STICK,
                                      self.param.tmpDirOnHdd, self.param.machineInfoGetter.hwInfo(),
                                      dev_path=devPath, disk_name=FmConst.rescueDiskName, disk_label=FmConst.rescueDiskLabel)
        elif re.fullmatch("/dev/sr.*", devPath) is not None:
            builder = RescueCdBuilder(RescueCdBuilder.DEV_TYPE_CDROM,
                                      self.param.tmpDirOnHdd, self.param.machineInfoGetter.hwInfo(),
                                      dev_path=devPath, disk_name=FmConst.rescueDiskName, disk_label=FmConst.rescueDiskLabel)
        else:
            raise Exception("target is not supported")

        self.infoPrinter.printInfo(">> Downloading files...")
        builder.downloadFiles()
        print("")

        self.infoPrinter.printInfo(">> Building %s (%s)..." % (FmConst.rescueDiskName, builder.getArchName("amd64")))
        builder.buildTargetSystem("amd64")
        print("")

        self.infoPrinter.printInfo(">> Building %s (%s)..." % (FmConst.rescueDiskName, builder.getArchName("arm64")))
        # builder.buildTargetSystem("arm64")
        print("")

        if builder.getDevType() == RescueCdBuilder.DEV_TYPE_ISO:
            self.infoPrinter.printInfo(">> Creating %s..." % (devPath))
        elif builder.getDevType() == RescueCdBuilder.DEV_TYPE_USB_STICK:
            self.infoPrinter.printInfo(">> Installing into USB stick %s..." % (devPath))
        elif builder.getDevType() == RescueCdBuilder.DEV_TYPE_CDROM:
            self.infoPrinter.printInfo(">> Burning CD in %s..." % (devPath))
        else:
            assert False
        builder.exportTargetSystem()
        print("")

        return 0

    def buildInstallDisk(self, devPath):
        if self.param.runMode in ["prepare", "setup"]:
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1
        self.param.sysChecker.basicCheckWithOverlayContent()

        # modify dynamic config
        self.infoPrinter.printInfo(">> Preparing...")
        if True:
            dcm = DynCfgModifier()
            dcm.updateMirrors()
            dcm.updateDownloadCommand()
            dcm.updateParallelism(self.param.machineInfoGetter.hwInfo())
            dcm.updateCcache()
        print("")

        # build
        if devPath.endswith(".iso"):
            builder = InstallCdBuilder(InstallCdBuilder.DEV_TYPE_ISO,
                                       self.param.tmpDirOnHdd, self.param.machineInfoGetter.hwInfo(),
                                       file_path=devPath, disk_name=FmConst.installDiskName, disk_label=FmConst.installDiskLabel)
        elif re.fullmatch("/dev/sd.*", devPath) is not None:
            builder = InstallCdBuilder(InstallCdBuilder.DEV_TYPE_USB_STICK,
                                       self.param.tmpDirOnHdd, self.param.machineInfoGetter.hwInfo(),
                                       dev_path=devPath, disk_name=FmConst.installDiskName, disk_label=FmConst.installDiskLabel)
        elif re.fullmatch("/dev/sr.*", devPath) is not None:
            builder = InstallCdBuilder(InstallCdBuilder.DEV_TYPE_CDROM,
                                       self.param.tmpDirOnHdd, self.param.machineInfoGetter.hwInfo(),
                                       dev_path=devPath, disk_name=FmConst.installDiskName, disk_label=FmConst.installDiskLabel)
        else:
            raise Exception("target is not supported")

        self.infoPrinter.printInfo(">> Downloading files...")
        builder.downloadFiles()
        print("")

        self.infoPrinter.printInfo(">> Building stage4 (%s)..." % (builder.getArchName("amd64")))
        builder.buildStage4("amd64")
        print("")

        self.infoPrinter.printInfo(">> Building %s (%s)..." % (FmConst.installDiskName, builder.getArchName("amd64")))
        builder.buildTargetSystem("amd64")
        print("")

        self.infoPrinter.printInfo(">> Building stage4 (%s)..." % (builder.getArchName("arm64")))
        # builder.buildStage4("arm64")
        print("")

        self.infoPrinter.printInfo(">> Building %s (%s)..." % (FmConst.installDiskName, builder.getArchName("arm64")))
        # builder.buildTargetSystem("arm64")
        print("")

        if builder.getDevType() == RescueCdBuilder.DEV_TYPE_ISO:
            self.infoPrinter.printInfo(">> Creating %s..." % (devPath))
        elif builder.getDevType() == RescueCdBuilder.DEV_TYPE_USB_STICK:
            self.infoPrinter.printInfo(">> Installing into USB stick %s..." % (devPath))
        elif builder.getDevType() == RescueCdBuilder.DEV_TYPE_CDROM:
            self.infoPrinter.printInfo(">> Burning CD in %s..." % (devPath))
        else:
            assert False
        builder.exportTargetSystem()
        print("")

        return 0

    def backup(self, devPath):
        # FIXME: a very simple backup process

        if re.fullmatch("/dev/[a-z]+", devPath) is None:
            raise Exception("invalid backup device %s" % (devPath))

        parti = devPath + "1"
        if not os.path.exists(parti):
            raise Exception("backup partition %s does not exist" % (devPath))
        if FmUtil.isMountPoint(parti):
            raise Exception("%s is already mounted" % (devPath))

        obj = strict_fsh.RootFs()

        wildcards = []
        wildcards = strict_fsh.merge_wildcards(wildcards, obj.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_SYSTEM_CFG))
        wildcards = strict_fsh.merge_wildcards(wildcards, obj.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_SYSTEM_DATA))
        wildcards = strict_fsh.merge_wildcards(wildcards, obj.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_USER))
        wildcards = strict_fsh.deduct_wildcards(wildcards, obj.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_USER_CACHE))
        wildcards = strict_fsh.deduct_wildcards(wildcards, obj.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_USER_TRASH))

        fileList = obj.wildcards_glob(wildcards)

        with TmpMount(parti) as mp:
            tarfilepath = os.path.join(mp.mountpoint, "backup-%s.tar.gz" % (datetime.now().strftime("%Y%m%d%H%M%S")))
            with tarfile.open(tarfilepath, mode="x") as tf:
                for fullfn in fileList:
                    print(fullfn)
                    tf.add(fullfn, recursive=False)

    def logToMemory(self):
        assert False

    def logToDisk(self, bRealtime):
        assert False
