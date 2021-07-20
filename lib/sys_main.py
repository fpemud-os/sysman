#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import pyudev
import strict_pgs
import strict_hdds
from fm_util import FmUtil
from fm_param import FmConst
from helper_boot import FkmBootDir
from helper_boot import FkmBootLoader
from helper_boot import FkmMountBootDirRw
from helper_dyncfg import DynCfgModifier
from helper_boot_rescueos import RescueOs
from helper_boot_rescueos import RescueDiskBuilder
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

        helperBootDir = FkmBootDir()
        helperRescueOs = RescueOs()
        helperBootLoader = FkmBootLoader()
        repoman = EbuildRepositories()
        layman = EbuildOverlays()

        if self.param.runMode != "normal":
            print("WARNING: Running in \"%s\" mode!!!" % (self.param.runMode))
            print("")

        s = "System status: "
        if helperBootLoader.isStable():
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
        if FmUtil.isEfi():
            print("    UEFI")
        else:
            print("    BIOS")

        print("Main OS:")
        mainOsInfo = helperBootDir.getMainOsStatus()
        if mainOsInfo is None:
            mainOsInfo = "None?!"
        print("    %s" % (mainOsInfo))

        print("Rescue OS:")
        if helperRescueOs.isInstalled():
            print("    Installed")
        else:
            print("    Not installed")

        if self.param.runMode in ["normal", "setup"]:
            auxOsInfo = helperBootLoader.getAuxOsInfo()
            if len(auxOsInfo) > 0:
                print("Auxillary OSes:")
                for osDesc, osPart, osbPart, chain in auxOsInfo:
                    sys.stdout.write("    %s:" % (osDesc))
                    for i in range(0, 20 - len(osDesc)):
                        sys.stdout.write(" ")
                    if osPart == osbPart:
                        print(osPart)
                    else:
                        print(osPart + " (Boot Partition: " + osbPart + ")")

        print("")

        layout = None
        if self.param.runMode in ["normal", "setup"]:
            layout = strict_hdds.parse_storage_layout()

        print("Storage layout:")
        if True:
            def partSize(devpath):
                sz = FmUtil.getBlkDevSize(devpath)
                return FmUtil.formatSize(sz)

            def totalSize(hddDevList, partiNum):
                sz = sum(FmUtil.getBlkDevSize(x + partiNum) for x in hddDevList)
                return FmUtil.formatSize(sz)

            if layout is None:
                print("    State: unusable")
            else:
                print("    Name: %s" % (layout.name))
                print("    State: ready")
                if layout.name == "bios-simple":
                    print("    Boot disk: %s" % (layout.get_boot_disk()))
                    print("    Root partititon: %s (%s)" % (layout.dev_rootfs, partSize(layout.dev_rootfs)))
                elif layout.name == "bios-lvm":
                    print("    Boot disk: %s" % (layout.get_boot_disk()))
                    print("    LVM PVs: %s (total: %s)" % (" ".join(layout.get_disk_list()), totalSize(layout.get_disk_list(), "1")))
                elif layout.name == "efi-simple":
                    print("    Boot disk: %s" % (layout.get_boot_disk()))
                    print("    Root partititon: %s (%s)" % (layout.dev_rootfs, partSize(layout.dev_rootfs)))
                elif layout.name == "efi-lvm":
                    print("    Boot disk: %s" % (layout.get_boot_disk()))
                    print("    LVM PVs: %s (total: %s)" % (" ".join(layout.get_disk_list()), totalSize(layout.get_disk_list(), "2")))
                elif layout.name == "efi-bcache-lvm":
                    if layout.get_ssd() is not None:
                        print("    SSD: %s (boot disk)" % (layout.get_ssd()))
                        if layout.get_ssd_swap_partition() is not None:
                            print("    Swap partition: %s (%s)" % (layout.get_ssd_swap_partition(), partSize(layout.get_ssd_swap_partition())))
                        else:
                            print("    Swap partition: None")
                        print("    Cache partition: %s (%s)" % (layout.get_ssd_cache_partition(), partSize(layout.get_ssd_cache_partition())))
                    else:
                        print("    SSD: None")
                        print("    Boot disk: %s" % (layout.get_boot_disk()))
                    totalSize = 0
                    pvStrList = []
                    for hddDev, bcacheDev in layout.hddDict.items():
                        pvStrList.append("%s,%s" % (hddDev, bcacheDev.replace("/dev/", "")))
                        totalSize += FmUtil.getBlkDevSize(bcacheDev)
                    print("    LVM PVs: %s (total: %s)" % (" ".join(pvStrList), FmUtil.formatSize(totalSize)))
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
            elif layout.dev_swap is None or not FmUtil.systemdIsServiceEnabled(FmUtil.path2SwapServiceName(layout.dev_swap)):
                print("    Disabled")
            else:
                print("    Enabled (%s)" % (FmUtil.formatSize(os.path.getsize(layout.dev_swap))))
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
            maxLen = 0
            for repoName in repoList:
                if len(repoName) > maxLen:
                    maxLen = len(repoName)

            for repoName in repoList:
                s1 = FmUtil.pad(repoName, maxLen)
                if repoman.isRepoExist(repoName):
                    print("    %s [Good     ] (Last Update: %s)" % (s1, FmUtil.getDirLastUpdateTime(repoman.getRepoDir(repoName))))
                else:
                    print("    %s [Not Exist]" % (s1))
        else:
            print("    None")

        print("")

        print("Overlays:")
        overlayList = layman.getOverlayList()
        if len(overlayList) > 0:
            maxLen = 0
            for lname in overlayList:
                if len(lname) > maxLen:
                    maxLen = len(lname)

            for lname in overlayList:
                if layman.getOverlayType(lname) == "static":
                    ltype = "[Static    ]"
                    lurl = None
                else:
                    ltype, lurl = layman.getOverlayVcsTypeAndUrl(lname)
                    if ltype == "git":
                        ltype = "[Git       ]"
                    elif ltype == "svn":
                        ltype = "[Subversion]"
                    else:
                        assert False
                s1 = FmUtil.pad(lname, maxLen)
                s2 = lurl if lurl is not None else ""
                print("    %s %s %s" % (s1, ltype, s2))
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

        layout = strict_hdds.parse_storage_layout()
        if layout is None:
            raise Exception("no valid storage layout")

        if layout.name in ["bios-simple", "efi-simple"]:
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))
        elif layout.name in ["bios-lvm", "efi-lvm", "efi-bcache-lvm"]:
            self.infoPrinter.printInfo(">> Adding harddisk...")
            layout.add_disk(devpath)
            print("")
        else:
            assert False

        self.param.sysUpdater.updateAfterHddAddOrRemove(self.param.machineInfoGetter.hwInfo(), layout)

        return 0

    def doHddRemove(self, devpath):
        if self.param.runMode == "prepare":
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1

        layout = strict_hdds.parse_storage_layout()
        if layout is None:
            raise Exception("no valid storage layout")

        if layout.name in ["bios-simple", "efi-simple"]:
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))
        elif layout.name in ["bios-lvm", "efi-lvm", "efi-bcache-lvm"]:
            self.infoPrinter.printInfo(">> Move data in %s to other place..." % (devpath))
            layout.release_disk(devpath)
            print("")
            self.infoPrinter.printInfo(">> Removing harddisk...")
            layout.remove_disk(devpath)
            print("")
        else:
            assert False

        self.param.sysUpdater.updateAfterHddAddOrRemove(self.param.machineInfoGetter.hwInfo(), layout)

        return 0

    def doEnableSwap(self):
        if self.param.runMode == "prepare":
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1

        layout = strict_hdds.parse_storage_layout()
        if layout is None:
            raise Exception("no valid storage layout")

        if layout.name in ["bios-simple", "efi-simple"]:
            if layout.dev_swap is None:
                layout.create_swap_file()
            serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
            if not layout.check_swap_size():
                self.param.swapManager.disableSwapService(layout.dev_swap, serviceName)
                layout.remove_swap_file()
                layout.create_swap_file()
            self.param.swapManager.createSwapService(layout.dev_swap, serviceName)
            self.param.swapManager.enableSwapService(layout.dev_swap, serviceName)

            swapSizeStr = FmUtil.formatSize(os.path.getsize(layout.dev_swap))
            print("Swap File: %s (size:%s)" % (layout.dev_swap, swapSizeStr))
            return 0

        if layout.name in ["bios-lvm", "efi-lvm"]:
            if layout.dev_swap is None:
                layout.create_swap_lv()
            serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
            if not layout.check_swap_size():
                self.param.swapManager.disableSwapService(layout.dev_swap, serviceName)
                layout.remove_swap_lv()
                layout.create_swap_lv()
            self.param.swapManager.createSwapService(layout.dev_swap, serviceName)
            self.param.swapManager.enableSwapService(layout.dev_swap, serviceName)

            uuid = pyudev.Device.from_device_file(pyudev.Context(), layout.dev_swap).get("ID_FS_UUID")
            swapSizeStr = FmUtil.formatSize(FmUtil.getBlkDevSize(layout.dev_swap))
            print("Swap Partition: %s (UUID:%s, size:%s)" % (layout.dev_swap, uuid, swapSizeStr))
            return 0

        if layout.name == "efi-bcache-lvm":
            if layout.dev_swap is None:
                raise Exception("no swap partition")
            if not layout.check_swap_size():
                raise Exception("swap partition is too small")
            serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
            self.param.swapManager.createSwapService(layout.dev_swap, serviceName)
            self.param.swapManager.enableSwapService(layout.dev_swap, serviceName)

            uuid = pyudev.Device.from_device_file(pyudev.Context(), layout.dev_swap).get("ID_FS_UUID")
            swapSizeStr = FmUtil.formatSize(FmUtil.getBlkDevSize(layout.dev_swap))
            print("Swap Partition: %s (UUID:%s, size:%s)" % (layout.dev_swap, uuid, swapSizeStr))
            return 0

        assert False

    def doDisableSwap(self):
        if self.param.runMode == "prepare":
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1

        layout = strict_hdds.parse_storage_layout()
        if layout is None:
            raise Exception("no valid storage layout")

        if layout.dev_swap is not None:
            serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
            self.param.swapManager.disableSwapService(layout.dev_swap, serviceName)
            self.param.swapManager.removeSwapService(layout.dev_swap, serviceName)

            if layout.name in ["bios-simple", "efi-simple"]:
                layout.remove_swap_file()
            elif layout.name in ["bios-lvm", "efi-lvm"]:
                layout.remove_swap_lv()
            elif layout.name == "efi-bcache-lvm":
                pass
            else:
                assert False

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
        self.infoPrinter.printInfo(">> Refreshing system configuration...")
        if True:
            dcm = DynCfgModifier()
            dcm.updateMirrors()
            dcm.updateDownloadCommand()
            dcm.updateParallelism(self.param.machineInfoGetter.hwInfo())
        print("")

        layout = strict_hdds.parse_storage_layout()
        with FkmMountBootDirRw(layout):
            self.infoPrinter.printInfo(">> Installing Rescue OS into /boot...")
            mgr = RescueOs()
            mgr.installOrUpdate(self.param.tmpDirOnHdd)
            print("")

            self.infoPrinter.printInfo(">> Updating boot-loader...")
            bootloader = FkmBootLoader()
            bootloader.updateBootloader(self.param.machineInfoGetter.hwInfo(), layout, FmConst.kernelInitCmd)
            print("")

        return 0

    def uninstallRescueOs(self):
        if self.param.runMode in ["prepare", "setup"]:
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1

        self.param.sysChecker.baiscCheckStorage()

        mgr = RescueOs()
        if not mgr.isInstalled():
            print("Rescue OS is not installed.", file=sys.stderr)
            return 1

        layout = strict_hdds.parse_storage_layout()
        with FkmMountBootDirRw(layout):
            self.infoPrinter.printInfo(">> Uninstalling Rescue OS...")
            mgr.uninstall()
            print("")

            self.infoPrinter.printInfo(">> Updating boot-loader...")
            bootloader = FkmBootLoader()
            bootloader.updateBootloader(self.param.machineInfoGetter.hwInfo(), layout, FmConst.kernelInitCmd)
            print("")

        return 0

    def buildRescueDisk(self, devPath):
        if self.param.runMode in ["prepare", "setup"]:
            print("Operation is not supported in \"%s\" mode." % (self.param.runMode), file=sys.stderr)
            return 1
        self.param.sysChecker.basicCheckWithOverlayContent()

        builder = RescueDiskBuilder()

        self.infoPrinter.printInfo(">> Checking...")
        builder.checkUsbDevice(devPath)
        print("")

        self.infoPrinter.printInfo(">> Build rescue disk image...")
        builder.build(self.param.tmpDirOnHdd)
        print("")

        # make target
        self.infoPrinter.printInfo(">> Installing into USB stick...")
        builder.installIntoUsbDevice(devPath)
        print("")

        return 0

    def logToMemory(self):
        assert False

    def logToDisk(self, bRealtime):
        assert False
