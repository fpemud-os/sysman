#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import pyudev
import strict_pgs
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
from sys_hw_info import HwInfoPcBranded
from sys_hw_info import HwInfoPcAssembled
from sys_hw_info import DevHwInfoDb
from sys_storage_manager import FmStorageLayoutBiosSimple
from sys_storage_manager import FmStorageLayoutBiosLvm
from sys_storage_manager import FmStorageLayoutEfiSimple
from sys_storage_manager import FmStorageLayoutEfiLvm
from sys_storage_manager import FmStorageLayoutEfiBcacheLvm
from sys_storage_manager import FmStorageLayoutNonStandard
from sys_storage_manager import FmStorageLayoutEmpty


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
        if isinstance(self.param.hwInfoGetter.current(), HwInfoPcBranded):
            print("    %s" % (self.param.hwInfoGetter.current().name))
        elif isinstance(self.param.hwInfoGetter.current(), HwInfoPcAssembled):
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

        print("Storage layout:")
        if True:
            def partSize(devpath):
                sz = FmUtil.getBlkDevSize(devpath)
                return FmUtil.formatSize(sz)

            def totalSize(hddDevList, partiNum):
                sz = sum(FmUtil.getBlkDevSize(x + partiNum) for x in hddDevList)
                return FmUtil.formatSize(sz)

            layout = self.param.storageManager.getStorageLayout()
            print("    Name: %s" % (layout.name))
            if isinstance(layout, FmStorageLayoutBiosSimple):
                print("    State: ready")
                if layout.hddRootParti is not None:
                    print("    Root partititon: %s (%s)" % (layout.hddRootParti, partSize(layout.hddRootParti)))
                else:
                    print("    Root partititon: None")
            elif isinstance(layout, FmStorageLayoutBiosLvm):
                print("    State: ready")
                if layout.bootHdd is not None:
                    print("    Boot disk: %s" % (layout.bootHdd))
                else:
                    print("    Boot disk: None")
                if layout.lvmPvHddList != []:
                    print("    LVM PVs: %s (total: %s)" % (" ".join(layout.lvmPvHddList), totalSize(layout.lvmPvHddList, "1")))
                else:
                    print("    LVM PVs: None")
            elif isinstance(layout, FmStorageLayoutEfiSimple):
                print("    State: ready")
                if layout.hddRootParti is not None:
                    print("    Root partititon: %s (%s)" % (layout.hddRootParti, partSize(layout.hddRootParti)))
                else:
                    print("    Root partititon: None")
            elif isinstance(layout, FmStorageLayoutEfiLvm):
                print("    State: ready")
                if layout.bootHdd is not None:
                    print("    Boot disk: %s" % (layout.bootHdd))
                else:
                    print("    Boot disk: None")
                if layout.lvmPvHddList != []:
                    print("    LVM PVs: %s (total: %s)" % (" ".join(layout.lvmPvHddList), totalSize(layout.lvmPvHddList, "2")))
                else:
                    print("    LVM PVs: None")
            elif isinstance(layout, FmStorageLayoutEfiBcacheLvm):
                print("    State: ready")
                if layout.ssd is not None:
                    print("    SSD: %s" % (layout.ssd))
                    if layout.ssdSwapParti is not None:
                        print("    Swap partition: %s (%s)" % (layout.ssdSwapParti, partSize(layout.ssdSwapParti)))
                    else:
                        print("    Swap partition: None")
                    print("    Cache partition: %s (%s)" % (layout.ssdCacheParti, partSize(layout.ssdCacheParti)))
                else:
                    print("    SSD: None")
                    print("    Boot disk: %s" % (layout.bootHdd))
                totalSize = 0
                pvStrList = []
                for hddDev, bcacheDev in layout.lvmPvHddDict.items():
                    pvStrList.append("%s,%s" % (hddDev, bcacheDev.replace("/dev/", "")))
                    totalSize += FmUtil.getBlkDevSize(bcacheDev)
                if pvStrList != []:
                    print("    LVM PVs: %s (total: %s)" % (" ".join(pvStrList), FmUtil.formatSize(totalSize)))
                else:
                    print("    LVM PVs: None")
            elif isinstance(layout, FmStorageLayoutNonStandard):
                print("    State: %s" % ("ready" if layout.isReady() else "unusable"))
                print("    similar to %s, but %s." % (layout.closestLayoutName, layout.message))
            elif isinstance(layout, FmStorageLayoutEmpty):
                print("    State: unusable")
            else:
                assert False

        print("Swap:")
        if True:
            layout = self.param.storageManager.getStorageLayout()
            found = None
            swapDevOrFile = None
            swapSize = None
            if isinstance(layout, FmStorageLayoutBiosSimple):
                found = True
                if layout.swapFile is not None:
                    swapDevOrFile = layout.swapFile
                    swapSize = os.path.getsize(swapDevOrFile)
            elif isinstance(layout, FmStorageLayoutBiosLvm):
                found = True
                if layout.lvmSwapLv is not None:
                    swapDevOrFile = layout.lvmSwapLv
                    swapSize = FmUtil.getBlkDevSize(swapDevOrFile)
            elif isinstance(layout, FmStorageLayoutEfiSimple):
                found = True
                if layout.swapFile is not None:
                    swapDevOrFile = layout.swapFile
                    swapSize = os.path.getsize(swapDevOrFile)
            elif isinstance(layout, FmStorageLayoutEfiLvm):
                found = True
                if layout.lvmSwapLv is not None:
                    swapDevOrFile = layout.lvmSwapLv
                    swapSize = FmUtil.getBlkDevSize(swapDevOrFile)
            elif isinstance(layout, FmStorageLayoutEfiBcacheLvm):
                found = True
                if layout.ssdSwapParti is not None:
                    swapDevOrFile = layout.ssdSwapParti
                    swapSize = FmUtil.getBlkDevSize(swapDevOrFile)
            elif isinstance(layout, FmStorageLayoutNonStandard):
                found = False
            elif isinstance(layout, FmStorageLayoutEmpty):
                found = False
            else:
                assert False

            if not found:
                print("    Unknown")
            elif swapDevOrFile is None:
                print("    Disabled")
            else:
                if self.param.runMode == "prepare":
                    assert False        # always get FmStorageLayoutEmpty in prepare mode
                elif self.param.runMode == "setup":
                    print("    Disabled")
                elif self.param.runMode == "normal":
                    serviceName = FmUtil.path2SwapServiceName(swapDevOrFile)
                    if not FmUtil.systemdIsServiceEnabled(serviceName):
                        print("    Disabled")
                    else:
                        print("    Enabled (%s)" % (FmUtil.formatSize(swapSize)))
                else:
                    assert False

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
                    print("    %s %s (Last Update: )" % (s1, FmUtil.pad("[Good]", 15)))
                else:
                    print("    %s %s" % (s1, FmUtil.pad("[Not Exist]", 15)))
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
                    ltype = "Static"
                    lurl = None
                else:
                    ltype, lurl = layman.getOverlayVcsTypeAndUrl(lname)
                    if ltype == "git":
                        ltype = "Git"
                    elif ltype == "svn":
                        ltype == "Subversion"
                    else:
                        assert False
                s1 = FmUtil.pad(lname, maxLen)
                s2 = "[" + FmUtil.pad(ltype, 10) + "]"
                s3 = "(" + FmUtil.pad(lurl, FmUtil.terminal_width() - maxLen - 22) + ")" if lurl is not None else ""
                print("    %s %s %s" % (s1, s2, s3))
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

    def doHddAdd(self, devpath, bMainBoot, bWithBadBlock):
        layout = self.param.storageManager.getStorageLayout()

        self.infoPrinter.printInfo(">> Adding harddisk...")
        self.param.storageManager.addHdd(layout, devpath, bMainBoot, bWithBadBlock)
        print("")

        self.param.sysUpdater.updateAfterHddAddOrRemove(self.param.hwInfoGetter.current(), layout)

    def doHddRemove(self, devpath):
        layout = self.param.storageManager.getStorageLayout()

        self.infoPrinter.printInfo(">> Move data in %s to other place..." % (devpath))
        self.param.storageManager.releaseHdd(layout, devpath)
        print("")

        self.infoPrinter.printInfo(">> Removing harddisk...")
        self.param.storageManager.removeHdd(layout, devpath)
        print("")

        self.param.sysUpdater.updateAfterHddAddOrRemove(self.param.hwInfoGetter.current(), layout)

    def doAddOverlay(self, overlayName, overlayUrl):
        if overlayUrl is None:
            cloudDb = CloudOverlayDb()
            cloudDb.updateCache()
            if not cloudDb.hasOverlay(overlayName):
                raise Exception("overlay \"%s\" is not in cloud database, overlay URL must be specified" % (overlayName))
            vcsType, overlayUrl = cloudDb.getOverlayVcsTypeAndUrl(overlayName)

        EbuildOverlays().addTransientOverlay(overlayName, overlayUrl)

    def doRemoveOverlay(self, overlayName):
        EbuildOverlays().removeOverlay(overlayName)

    def doEnableOverlayPkg(self, overlayName, pkgName):
        EbuildOverlays().enableOverlayPackage(overlayName, pkgName)

    def doDisableOverlayPkg(self, overlayName, pkgName):
        EbuildOverlays().disableOverlayPackage(overlayName, pkgName)

    def doEnableSwap(self):
        layout = self.param.storageManager.getStorageLayout()

        # do work
        self.param.storageManager.enableSwap(layout)

        # show result
        if isinstance(layout, (FmStorageLayoutBiosSimple, FmStorageLayoutEfiSimple)):
            if layout.swapFile is not None:
                swapSizeStr = FmUtil.formatSize(os.path.getsize(layout.swapFile))
                print("Swap File: %s (size:%s)" % (layout.swapFile, swapSizeStr))
        elif isinstance(layout, (FmStorageLayoutBiosLvm, FmStorageLayoutEfiLvm)):
            if layout.lvmSwapLv is not None:
                uuid = pyudev.Device.from_device_file(pyudev.Context(), layout.lvmSwapLv).get("ID_FS_UUID")
                swapSizeStr = FmUtil.formatSize(FmUtil.getBlkDevSize(layout.lvmSwapLv))
                print("Swap Partition: %s (UUID:%s, size:%s)" % (layout.lvmSwapLv, uuid, swapSizeStr))
        elif isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            if layout.ssdSwapParti is not None:
                uuid = pyudev.Device.from_device_file(pyudev.Context(), layout.ssdSwapParti).get("ID_FS_UUID")
                swapSizeStr = FmUtil.formatSize(FmUtil.getBlkDevSize(layout.ssdSwapParti))
                print("Swap Partition: %s (UUID:%s, size:%s)" % (layout.ssdSwapParti, uuid, swapSizeStr))

    def doDisableSwap(self):
        layout = self.param.storageManager.getStorageLayout()
        self.param.storageManager.disableSwap(layout)

    def modifyUser(self, username):
        assert False

    def enableUser(self, username):
        assert False

    def disableUser(self, username):
        assert False

    def addGroup(self):
        assert False

    def removeGroup(self):
        assert False

    def modifyGroup(self):
        assert False

    def installRescueOs(self):
        layout = self.param.storageManager.getStorageLayout()

        # modify dynamic config
        self.infoPrinter.printInfo(">> Refreshing system configuration...")
        if True:
            dcm = DynCfgModifier()
            dcm.updateMirrors()
            dcm.updateDownloadCommand()
            dcm.updateParallelism(self.param.hwInfoGetter.current())
        print("")

        with FkmMountBootDirRw(layout):
            self.infoPrinter.printInfo(">> Installing Rescue OS into /boot...")
            mgr = RescueOs()
            mgr.installOrUpdate(self.param.tmpDirOnHdd)
            print("")

            self.infoPrinter.printInfo(">> Updating boot-loader...")
            bootloader = FkmBootLoader()
            bootloader.updateBootloader(self.param.hwInfoGetter.current(), layout, FmConst.kernelInitCmd)
            print("")

    def uninstallRescueOs(self):
        mgr = RescueOs()
        if not mgr.isInstalled():
            raise Exception("rescue os is not installed")

        layout = self.param.storageManager.getStorageLayout()
        with FkmMountBootDirRw(layout):
            self.infoPrinter.printInfo(">> Uninstalling Rescue OS...")
            mgr.uninstall()
            print("")

            self.infoPrinter.printInfo(">> Updating boot-loader...")
            bootloader = FkmBootLoader()
            bootloader.updateBootloader(self.param.hwInfoGetter.current(), layout, FmConst.kernelInitCmd)
            print("")

    def buildRescueDisk(self, devPath):
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

    def logToMemory(self):
        assert False

    def logToDisk(self, bRealtime):
        assert False
