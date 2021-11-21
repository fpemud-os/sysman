#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import glob
import time
import ntplib
import struct
import pathlib
import filecmp
import strict_pgs
import strict_fsh
import strict_hdds
import configparser
import robust_layer.simple_fops
from fm_util import FmUtil
from fm_util import TmpMount
from fm_util import BootDirWriter
from fm_param import FmConst
from helper_bbki import BbkiWrapper
from helper_pkg_warehouse import PkgWarehouse
from helper_pkg_warehouse import RepositoryCheckError
from helper_pkg_warehouse import OverlayCheckError
from helper_pkg_warehouse import CloudOverlayDb
from helper_pkg_merger import PkgMerger


# TODO:
# *. no 512 disk check
# 1. partition 4k align check
# 2. disk 2048 reserve check
# 3. ssd io scheduler check
# 7. systemd unit files reference not-exist service or target file
# 8. check mount option for boot device
# 9. should not have uid/gid without name
# *. remove "default" routing table from /etc/iproute2/rt_tables, remove "32767:  from all lookup default" rule (is it set by kernel?)
# *. hardware check: monitor config by ddcci
# *. install and uninstall all in_focus packages
# *. don't enable non-critical INTEL and AMD cpu kernel option (it's a general TODO item, not related to sysman-check)
# *. /var should have at least 100MiB freespace, especially for mounted_var
# *. check dmesg for "end_request: I/O error, dev 03:06 (sda), sector"
# *. should mount noatime
# *. verify cups setup is fresh and easy
#    if printer is exported:
#       non-network printer exist and only non-network printer can be exported
#    if printer is not exported:
#       do nothing
# *. no virtual-printer is allowed. virtual-printer is a mis-use of print framework, they should be implemented as other form
# *. no abstract unix domain socket should exist (https://utcc.utoronto.ca/~cks/space/blog/linux/SocketAbstractNamespace?showcomments, comment's from Lennart)
# *. no direcotry is mounted more than once
#
# exception rules:
# 1. use "printError" than "raise exception" if possible
# 2. no "printError" in basicCheck()


class FmSysChecker:

    def __init__(self, param):
        self.param = param
        self.pkgwh = PkgWarehouse()
        self.infoPrinter = None
        self.bAutoFix = False

    def basicCheck(self):
        self._checkPortageCfg(bFullCheck=False)
        self._checkRepositories(bFullCheck=False)
        self._checkOverlays(False, bFullCheck=False)

    def basicCheckWithOverlayContent(self):
        self._checkPortageCfg(bFullCheck=False)
        self._checkRepositories(bFullCheck=False)
        self._checkOverlays(True, bFullCheck=False)

    def fullCheck(self, bAutoFix, deepHardwareCheck, deepFileSystemCheck):
        self.bAutoFix = bAutoFix
        self.infoPrinter = self.param.infoPrinter
        try:
            with self.infoPrinter.printInfoAndIndent(">> Preparing..."):
                self.basicCheck()

            with self.infoPrinter.printInfoAndIndent(">> Checking hardware..."):
                self._checkHarddisks(deepHardwareCheck)
                self._checkCooling()

            with self.infoPrinter.printInfoAndIndent(">> Checking storage layout..."):
                self._checkStorageLayout()

            with self.infoPrinter.printInfoAndIndent(">> Checking file system layout..."):
                with self.infoPrinter.printInfoAndIndent("- Check rootfs..."):
                    self._checkRootfsLayout(deepFileSystemCheck)
                with self.infoPrinter.printInfoAndIndent("- Check premount rootfs..."):
                    self._checkPreMountRootfsLayout()

            with self.infoPrinter.printInfoAndIndent(">> Checking BIOS, bootloader, initramfs and kernel..."):
                bbkiObj = BbkiWrapper()
                with self.infoPrinter.printInfoAndIndent("- Check config..."):
                    bbkiObj.check_config(self.bAutoFix, self.infoPrinter.printError)
                with self.infoPrinter.printInfoAndIndent("- Check repositories..."):
                    bbkiObj.check_repositories(self.bAutoFix, self.infoPrinter.printError)
                with self.infoPrinter.printInfoAndIndent("- Check boot entries..."):
                    if self.bAutoFix:
                        with BootDirWriter(strict_hdds.get_current_storage_layout()):
                            bbkiObj.check_boot_entry_files(self.bAutoFix, self.infoPrinter.printError)
                    else:
                        bbkiObj.check_boot_entry_files(self.bAutoFix, self.infoPrinter.printError)

            with self.infoPrinter.printInfoAndIndent(">> Checking operating system..."):
                with self.infoPrinter.printInfoAndIndent("- Check system configuration..."):
                    self._checkCpuFreqDriver()              # config in /sys
                    # self._checkMachineInfo()
                    self._checkHostsFile()                  # config in /etc
                    self._checkNsswitchFile()               # config in /etc
                    self._checkSystemLocale()               # config in /etc
                    # self._checkPamCfgFiles()
                    self._checkEtcOnlyUserCreatedFiles()
                    self._checkEtcLmSensorsCfgFiles()
                    self._checkEtcUdevRuleFiles()
                    self._checkServiceFiles()
                    self._checkPortageCfg()
                    self._checkSystemServices()
                    self._checkSystemTime()                 # dynamic system status
                with self.infoPrinter.printInfoAndIndent("- Check package repositories & overlays..."):
                    self._checkPortagePkgwhCfg()
                    self._checkRepositories()
                    self._checkOverlays(True)
                    self._checkNews()
                    self._checkImportantPackage()
                    self._checkWorldFile()
                    self._checkRedundantRepositoryAndOverlay()
                with self.infoPrinter.printInfoAndIndent("- Check users and groups..."):
                    self._checkUsersAndGroups()

            with self.infoPrinter.printInfoAndIndent(">> Checking software packages..."):
                for pkgNameVer in sorted(FmUtil.portageGetInstalledPkgAtomList(FmConst.portageDbDir)):
                    with self.infoPrinter.printInfoAndIndent("- Package %s:" % (pkgNameVer), bRecallable=True):
                        self._checkPackageContentFile(pkgNameVer)
                        self._checkPackageFileScope(pkgNameVer)
                        self._checkPackageMd5(pkgNameVer)
                        self._checkPkgByScript(pkgNameVer)

            with self.infoPrinter.printInfoAndIndent(">> Checking cruft files..."):
                self._checkSystemCruft()
        finally:
            self.infoPrinter = None
            self.bAutoFix = False

    def _checkHarddisks(self, deepCheck):
        tlist = FmUtil.getDevPathListForFixedHdd()
        if len(tlist) == 0:
            self.infoPrinter.printError("No hard disk?!")
            return

        # hardware check
        if not deepCheck:
            for hdd in tlist:
                with self.infoPrinter.printInfoAndIndent("- Doing basic hardware check for %s(%s)" % (hdd, FmUtil.getBlkDevModel(hdd))):
                    rc, out = FmUtil.cmdCallWithRetCode("/usr/sbin/smartctl", "-H", hdd)
                    if re.search("failure", out, re.I) is not None:
                        self.infoPrinter.printError("HDD health check failed! Run \"smartctl -H %s\" to do future inspection!" % (hdd))
        else:
            with self.infoPrinter.printInfoAndIndent("- Starting extensive hardware test for %s(%s)" % (hdd, FmUtil.getBlkDevModel(hdd))):
                tlist2 = list(tlist)
                for hdd in tlist:
                    try:
                        rc, out = FmUtil.cmdCallWithRetCode("/usr/sbin/smartctl", "-t", "long", hdd)
                        if rc == 0:
                            m = re.search("Please wait ([0-9]+) minutes for test to complete\\.", out, re.M)
                            if m is None:
                                raise Exception("")
                            self.infoPrinter.printInfo("Test on %s(%s) started, %s minutes needed." % (hdd, FmUtil.getBlkDevModel(hdd), m.group(1)))
                        elif rc == 4:
                            self.infoPrinter.printInfo("Test on %s(%s) started. Why it is already in progress?" % (hdd, FmUtil.getBlkDevModel(hdd)))
                        else:
                            raise Exception("")
                    except:
                        self.infoPrinter.printError("Failed to start test on %s(%s)!" % (hdd, FmUtil.getBlkDevModel(hdd)))
                        FmUtil.cmdCallIgnoreResult("/usr/sbin/smartctl", "-X", hdd)
                        tlist2.remove(hdd)

            with self.infoPrinter.printInfoAndIndent("- Waiting..."):
                try:
                    last_progress = 0
                    while tlist2 != []:
                        time.sleep(60 * 5)
                        min_progress = None
                        for hdd in list(tlist2):
                            out = FmUtil.cmdCall("/usr/sbin/smartctl", "-l", "selftest", hdd)
                            if re.search("# 1\\s+Extended offline\\s+Completed without error\\s+.*", out, re.M) is not None:
                                self.infoPrinter.printInfo("Test on %s finished." % (hdd))
                                tlist2.remove(hdd)
                                continue
                            m = re.search("# 1\\s+Extended offline\\s+Self-test routine in progress\\s+([0-9]+)%.*", out, re.M)
                            if m is None:
                                self.infoPrinter.printInfo("Test on %s failed. Run \"smartctl -l selftest %s\" to do future inspection." % (hdd, hdd))
                                tlist2.remove(hdd)
                                continue
                            if min_progress is None:
                                min_progress = 100
                            min_progress = min(min_progress, 100 - int(m.group(1)))
                        if min_progress is not None and min_progress > last_progress:
                            self.infoPrinter.printInfo("Test progress: %d%%" % (min_progress))
                            last_progress = min_progress
                finally:
                    for hdd in tlist2:
                        FmUtil.cmdCallIgnoreResult("/usr/sbin/smartctl", "-X", hdd)

    def _checkCooling(self):
        # FIXME: check temperature event, too high, cpu throttle, gpu throttle... (_checkCooling)

        with self.infoPrinter.printInfoAndIndent("- Checking cooling system..."):
            # check cpu thermal throttle history
            for fullfn in glob.glob("/sys/devices/system/cpu/cpu*/thermal_throttle/*_throttle_count"):
                count = int(pathlib.Path(fullfn).read_text().rstrip("\n"))
                if count != 0:
                    self.infoPrinter.printError("\"%s\" is not 0." % (fullfn))

    def _checkStorageLayout(self):
        tlist = FmUtil.getDevPathListForFixedHdd()
        if len(tlist) == 0:
            self.infoPrinter.printError("No hard disk?!")
            return

        layout = strict_hdds.get_current_storage_layout()
        if layout is None:
            self.infoPrinter.printError("No valid storage layout.")
            return

        obj = _DiskPartitionTableChecker()
        for hdd in tlist:
            with self.infoPrinter.printInfoAndIndent("- Checking partition table for %s(%s)" % (hdd, FmUtil.getBlkDevModel(hdd))):
                try:
                    obj.checkDisk(hdd)
                except _DiskPartitionTableCheckerFailure as e:
                    self.infoPrinter.printError(e.message)
                if len(glob.glob(hdd + "*")) == 1:
                    self.infoPrinter.printError("Harddisk %s has no partition." % (hdd))

        with self.infoPrinter.printInfoAndIndent("- Checking storage layout"):
            if layout.name == "bios-ext4":
                pass
            elif layout.name == "efi-ext4":
                pass
            elif layout.name == "efi-lvm-ext4":
                pass
            elif layout.name == "efi-bcache-lvm-ext4":
                if layout.get_ssd() is None:
                    self.infoPrinter.printError("Storage layout \"%s\" should have a cache device." % (layout.name))
                for fn in glob.glob("/sys/block/bcache*"):
                    devPath = os.path.join("/dev", os.path.basename(fn))
                    if FmUtil.bcacheDeviceGetMode(devPath) != "writeback":
                        self.infoPrinter.printError("BCACHE device %s should be configured as writeback mode." % (devPath))
            else:
                assert False

        with self.infoPrinter.printInfoAndIndent("- Checking ESP partition"):
            if layout.name == "bios-ext4":
                pass
            elif layout.name in ["efi-ext4", "efi-lvm-ext4", "efi-bcache-lvm-ext4"]:
                if layout.get_esp() is None:
                    self.infoPrinter.printError("Storage layout \"%s\" has no ESP partition?!" % (layout.name))
                if FmUtil.getBlkDevSize(layout.get_esp()) != layout.get_suggestted_esp_size():
                    self.infoPrinter.printError("ESP partition \"%s\" has invalid size." % (layout.get_esp()))
            else:
                assert False

        with self.infoPrinter.printInfoAndIndent("- Checking file systems"):
            # if True:
            #     # what we can check is very limited:
            #     # 1. no way to fsck ext4 root partition when it's on-line
            #     # 2. fscking vfat partition when it's on-line always finds dirty-bit
            #     if self.bAutoFix:
            #         fatFsckCmd = "/usr/sbin/fsck.vfat -a"
            #     else:
            #         fatFsckCmd = "/usr/sbin/fsck.vfat -n"

            #     if isinstance(layout, FmStorageLayoutBiosSimple):
            #         pass
            #     elif isinstance(layout, FmStorageLayoutEfiSimple):
            #         FmUtil.shellExec("%s %s" % (fatFsckCmd, layout.hddEspParti))
            #     elif isinstance(layout, FmStorageLayoutEfiLvm):
            #         for hdd in layout.lvmPvHddList:
            #             FmUtil.shellExec("%s %s" % (fatFsckCmd, FmUtil.devPathDiskToPartition(hdd, 1)))
            #     elif isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            #         if layout.ssd is not None:
            #             FmUtil.shellExec("%s %s" % (fatFsckCmd, layout.ssdEspParti))
            #         for hdd in layout.lvmPvHddDict:
            #             FmUtil.shellExec("%s %s" % (fatFsckCmd, FmUtil.devPathDiskToPartition(hdd, 1)))
            #     else:
            #         assert False
            pass

        with self.infoPrinter.printInfoAndIndent("- Checking swap"):
            dirname = "/etc/systemd/system"
            bEnabled = None                     # assigned by __checkAndGetSwapEnablement()

            def __checkRedundantSwapService():
                # only standard swap service should exist
                for sname in FmUtil.systemdFindAllSwapServicesInDirectory(dirname):
                    if layout.dev_swap is not None and sname == FmUtil.path2SwapServiceName(layout.dev_swap):
                        continue
                    self.infoPrinter.printError("Swap service \"%s\" should not exist." % (os.path.join(dirname, sname)))

            def __checkAndGetSwapEnablement():
                # swap should be enabled
                if layout.dev_swap is None:
                    self.infoPrinter.printError("Swap is not enabled.")
                    bEnabled = False
                    return
                serviceName = FmUtil.systemdFindSwapServiceInDirectory(dirname, layout.dev_swap)
                if serviceName is None:
                    self.infoPrinter.printError("Swap is not enabled.")
                    bEnabled = False
                    return
                if self.param.runMode == "normal":
                    if not FmUtil.systemdIsServiceEnabled(serviceName):
                        self.infoPrinter.printError("Swap is not enabled.")
                        bEnabled = False
                        return
                bEnabled = True
                return

            def __checkSwapFileSize():
                assert bEnabled is not None
                if layout.dev_swap is not None and FmUtil.getBlkDevSize(layout.dev_swap) < layout.get_suggestted_swap_size():
                    if self.bAutoFix:
                        if bEnabled:
                            self.param.swapManager.disableSwap(layout)
                            self.param.swapManager.enableSwap(layout)
                        else:
                            layout.remove_swap_file()
                            layout.create_swap_file()
                    else:
                        self.infoPrinter.printError("Swap file has invalid size.")

            def __checkSwapLvSize():
                assert bEnabled is not None
                if layout.dev_swap is not None and FmUtil.getBlkDevSize(layout.dev_swap) < layout.get_suggestted_swap_size():
                    if self.bAutoFix:
                        if bEnabled:
                            self.param.swapManager.disableSwap(layout)
                            self.param.swapManager.enableSwap(layout)
                        else:
                            layout.remove_swap_lv()
                            layout.create_swap_lv()
                    else:
                        self.infoPrinter.printError("Swap LV has invalid size.")

            def __checkSwapPartiSize():
                assert bEnabled is not None
                if layout.dev_swap is not None and FmUtil.getBlkDevSize(layout.dev_swap) < layout.get_suggestted_swap_size():
                    # no way to auto-fix
                    self.infoPrinter.printError("Swap partition has invalid size.")

            # swap service should only exist in /etc
            for td in ["/usr/lib/systemd/system", "/lib/systemd/system"]:
                if os.path.exists(td):
                    for sname in FmUtil.systemdFindAllSwapServicesInDirectory(td):
                        self.infoPrinter.printError("Swap service \"%s\" should not exist." % (os.path.join(td, sname)))

            # check by layout
            if layout.name == "bios-ext4":
                __checkRedundantSwapService()
                __checkAndGetSwapEnablement()
                __checkSwapFileSize()
            elif layout.name == "efi-ext4":
                __checkRedundantSwapService()
                __checkAndGetSwapEnablement()
                __checkSwapFileSize()
            elif layout.name == "efi-lvm-ext4":
                __checkRedundantSwapService()
                __checkAndGetSwapEnablement()
                __checkSwapLvSize()
            elif layout.name == "efi-bcache-lvm-ext4":
                __checkRedundantSwapService()
                __checkAndGetSwapEnablement()
                __checkSwapPartiSize()
            else:
                assert False

    def _checkRootfsLayout(self, deepCheck):
        # general check
        obj = strict_fsh.RootFs()
        obj.check(deep_check=deepCheck, auto_fix=self.bAutoFix, error_callback=self.infoPrinter.printError)

        # addtional check: /usr/local should not exist
        if os.path.exists("/usr/local"):
            self.infoPrinter.printError("/usr/local should not exist.")

    def _checkPreMountRootfsLayout(self):
        layout = strict_hdds.get_current_storage_layout()
        with TmpMount(layout.dev_rootfs) as mp:
            obj = strict_fsh.PreMountRootFs(mp.mountpoint,
                                            mounted_boot=(layout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_EFI),
                                            mounted_home=False,
                                            mounted_cache=False,
                                            mounted_var=False)
            obj.check(auto_fix=self.bAutoFix, error_callback=self.infoPrinter.printError)

    def _checkMachineInfo(self):
        """Check /etc/machine-info"""

        ret = FmUtil.getMachineInfoWithCache("CHASSIS")

        # check CHASSIS
        if ret is not None:
            if ret in ["computer", "laptop", "tablet", "handset", "headless"]:
                pass
            else:
                raise FmCheckException("invalid CHASSIS in \"/etc/machine-info\"")

    def _checkCpuFreqDriver(self):
        # hwInfo = self.param.machineInfoGetter.hwInfo()

        # drv = None
        # if hwInfo.hwDict["cpu"]["vendor"] == "Intel":
        #     drv = "intel_p_state"
        # elif hwInfo.hwDict["cpu"]["vendor"] == "AMD":
        #     drv = "acpi_freq"
        # else:
        #     self.infoPrinter.printError("CPU vendor is %s, can not check cpu-freq driver.")
        #     return

        # flist = FmUtil.shellCall("/usr/bin/find /sys/devices/system/cpu/cpufreq -name scaling_driver").split("\n")
        # flist = [x for x in flist if x != ""]
        # if len(flist) != hwInfo.hwDict["cpu"]["cores"]:
        #     self.infoPrinter.printError("Incorrent number of scaling_driver files (%d/%d) found in sysfs." % (hwInfo.hwDict["cpu"]["cores"], len(flist)))

        # for fullfn in flist:
        #     if pathlib.Path(fullfn).read_text() != drv + "\n":
        #         self.infoPrinter.printError("Invalid content in file \"%s\"." % (fullfn))

        pass

    def _checkHostsFile(self):
        """Check /etc/hosts"""

        content = ""
        content += "127.0.0.1 localhost\n"
        content += "::1 localhost\n"                    # selenium fails when "::1 localhost" exist in /etc/hosts ?
        if pathlib.Path("/etc/hosts").read_text() != content:
            if self.bAutoFix:
                with open("/etc/hosts", "w") as f:
                    f.write(content)
            else:
                self.infoPrinter.printError("File /etc/hosts has invalid content.")

    def _checkNsswitchFile(self):
        """Check /etc/nsswitch.conf"""
        pass

    def _checkPamCfgFiles(self):
        # FIXME: change to INSTALL_MASK?
        modBlackList = [
            "pam_group.so",         # so that uid/gid relationship is always clear
        ]

        # PAM-free system?
        if not os.path.exists("/etc/pam.d"):
            return

        for fn in os.listdir("/etc/pam.d"):
            fullfn = os.path.join("/etc/pam.d", fn)
            cfgDict = FmUtil.pamParseCfgFile(fullfn)

            # check module
            for modIntf, items in cfgDict.items():
                for ctrlFlag, modArgs in items:
                    if ctrlFlag == "include":
                        continue
                    mod = modArgs.split(" ")[0]
                    if not os.path.exists("/lib64/security/" + mod):
                        self.infoPrinter.printError("Non-exist module \"%s\" in PAM config file \"%s\"." % (mod, fullfn))
                    if mod in modBlackList:
                        self.infoPrinter.printError("Prohibited module \"%s\" in PAM config file \"%s\"." % (mod, fullfn))
                    if modIntf.replace("-", "") not in FmUtil.pamGetModuleTypesProvided(mod):
                        self.infoPrinter.printError("Module \"%s\" is not suitable for %s in PAM config file \"%s\"." % (mod, modIntf, fullfn))

            # check order
            # FIXME
            for items in cfgDict.values():
                ctrlFlagCur = None
                for ctrlFlag, modArgs in items:
                    if ctrlFlag == "include":
                        if not (ctrlFlagCur is None or ctrlFlagCur == "include"):
                            self.infoPrinter.printError("Inappropriate \"include\" control flag order in PAM config file \"%s\"." % (fullfn))
                    if ctrlFlag != "optional" and ctrlFlagCur == "optional":
                        self.infoPrinter.printError("Inappropriate \"optional\" control flag order in PAM config file \"%s\"." % (fullfn))
                    ctrlFlagCur = ctrlFlag

    def _checkEtcOnlyUserCreatedFiles(self):
        # the following directories have /usr/lib/* counterpart, so only user created files are allowed in them
        dirList = [
            "/etc/binfmt.d",
            "/etc/environment.d",
            "/etc/modprobe.d",
            "/etc/modules-load.d",
            "/etc/systemd/system",
            "/etc/systemd/user",
            "/etc/tmpfiles.d",
            "/etc/udev/hwdb.d",
            "/etc/udev/rules.d",
        ]

        fileSet = None
        for dn in dirList:
            if not os.path.exists(dn):
                continue
            for fullfn in glob.glob(os.path.join(dn, "*")):
                if fileSet is None:
                    fileSet = FmUtil.portageGetInstalledFileSet()
                if fullfn in fileSet:
                    self.infoPrinter.printError("\"%s\" should contain only user created files, but \"%s\" is not." % (dn, fullfn))

    def _checkEtcLmSensorsCfgFiles(self):
        fn = "/etc/modules-load.d/lm_sensors.conf"
        if not os.path.exists(fn):
            self.infoPrinter.printError("You should use \"sensors-detect\" command from package \"sys-apps/lm-sensors\" to generate \"%s\"." % (fn))

    def _checkEtcUdevRuleFiles(self):
        fileSet = None

        # check /etc/udev/hwdb.d
        hwdbDir = "/etc/udev/hwdb.d"
        if os.path.exists(hwdbDir):
            for fn, fullfn in FmUtil.listDirWithoutKeepFiles(hwdbDir):
                self.infoPrinter.printError("\"%s\" should be empty, so \"%s\" should not exist." % (hwdbDir, fullfn))

        # check /etc/udev/rules.d
        rulesDir = "/etc/udev/rules.d"
        if os.path.exists(rulesDir):
            for fn, fullfn in FmUtil.listDirWithoutKeepFiles(rulesDir):
                if fileSet is None:
                    fileSet = FmUtil.portageGetInstalledFileSet()
                if fullfn in fileSet:
                    self.infoPrinter.printError("\"%s\" should contain only user created files, but \"%s\" is not." % (rulesDir, fullfn))
                if not FmUtil.udevIsPureUaccessRuleFile(fullfn):
                    self.infoPrinter.printError("\"%s\" is not a pure uaccess udev rule file." % (fullfn))

    def _checkServiceFiles(self):
        mustEnableServiceList = [
            "bluetooth.service",            # userspace daemon for bluetooth hardware
            "cups.service",                 # multiplex daemon for printer
            "iio-sensor-proxy.service",     # multiplex daemon for iio-sensor
            "iwd.service",                  # userspace daemon for WiFi/802.1X
        ]

        for s in mustEnableServiceList:
            libFn = os.path.join("/lib/systemd/system", s)
            if not os.path.exists(libFn):
                continue
            if not FmUtil.systemdIsServiceEnabled(s):
                self.infoPrinter.printError("\"%s\" is not enabled." % (s))

    def _checkPortageCfg(self, bFullCheck=True):
        commonDir = os.path.join(FmConst.dataDir, "etc-common")

        # check /var/lib/portage
        if not os.path.isdir(FmConst.portageDataDir):
            if self.bAutoFix:
                os.mkdir(FmConst.portageDataDir)
            else:
                raise FmCheckException("\"%s\" is not a directory" % (FmConst.portageDataDir))

        # check /var/cache/portage
        if not os.path.isdir(FmConst.portageCacheDir):
            if self.bAutoFix:
                os.makedirs(FmConst.portageCacheDir, exist_ok=True)
            else:
                raise FmCheckException("\"%s\" is not a directory" % (FmConst.portageCacheDir))

        # check /var/cache/portage/overlay-db
        if not os.path.isdir(FmConst.cloudOverlayDbDir):
            if self.bAutoFix:
                os.makedirs(FmConst.cloudOverlayDbDir, exist_ok=True)
            else:
                raise FmCheckException("\"%s\" is not a directory" % (FmConst.cloudOverlayDbDir))

        # check /var/cache/portage/laymanfiles
        if not os.path.isdir(FmConst.laymanfilesDir):
            if self.bAutoFix:
                os.makedirs(FmConst.laymanfilesDir, exist_ok=True)
            else:
                raise FmCheckException("\"%s\" is not a directory" % (FmConst.laymanfilesDir))

        # check /var/cache/portage/kcache
        if not os.path.isdir(FmConst.kcacheDir):
            if self.bAutoFix:
                os.makedirs(FmConst.kcacheDir, exist_ok=True)
            else:
                raise FmCheckException("\"%s\" is not a directory" % (FmConst.kcacheDir))

        # check /var/cache/portage/distfiles
        if not os.path.isdir(FmConst.distDir):
            if self.bAutoFix:
                os.makedirs(FmConst.distDir, exist_ok=True)
            else:
                raise FmCheckException("\"%s\" is not a directory" % (FmConst.distDir))

        # check /etc/portage/make.profile
        if not os.path.exists(FmConst.portageCfgMakeProfile):
            raise FmCheckException("%s must exist" % (FmConst.portageCfgMakeProfile))
        else:
            tlist = FmUtil.realPathSplit(os.path.realpath(FmConst.portageCfgMakeProfile))
            if not re.fullmatch("[0-9\\.]+", tlist[-1]):
                raise FmCheckException("%s must points to a vanilla profile (eg. default/linux/amd64/17.0)" % (FmConst.portageCfgMakeProfile))

        # check /etc/portage/make.conf
        if True:
            # check CHOST variable
            if FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "CHOST") != "":
                raise FmCheckException("variable CHOST should not exist in %s" % (FmConst.portageCfgMakeConf))

            # check/fix ACCEPT_LICENSE variable
            if FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "ACCEPT_LICENSE") != "*":
                if self.bAutoFix:
                    FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "ACCEPT_LICENSE", "*")
                else:
                    raise FmCheckException("invalid value of variable ACCEPT_LICENSE in %s" % (FmConst.portageCfgMakeConf))

            # check/fix DISTDIR variable
            if FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "DISTDIR") != FmConst.distDir:
                if self.bAutoFix:
                    FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "DISTDIR", FmConst.distDir)
                else:
                    raise FmCheckException("invalid value of variable DISTDIR in %s" % (FmConst.portageCfgMakeConf))

            # check/fix ACCEPT_KEYWORDS variable
            keywordList = ["~%s" % (x) for x in self.pkgwh.getKeywordList()]
            tlist = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "ACCEPT_KEYWORDS").split(" ")
            if set(tlist) != set(keywordList):
                if self.bAutoFix:
                    FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "ACCEPT_KEYWORDS", " ".join(keywordList))
                else:
                    raise FmCheckException("invalid value of variable ACCEPT_KEYWORDS in %s" % (FmConst.portageCfgMakeConf))

            # check/fix EMERGE_DEFAULT_OPTS variable
            value = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS")
            if re.search("--quiet-build\\b", value) is None:
                if self.bAutoFix:
                    value += " --quiet-build"
                    FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS", value.lstrip())
                else:
                    raise FmCheckException("variable EMERGE_DEFAULT_OPTS in %s should contain --quiet-build argument" % (FmConst.portageCfgMakeConf))
            value = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS")
            if True:
                m = re.search("--backtrack(=([0-9]+))?\\b", value)
                if m is None:
                    if self.bAutoFix:
                        value += " --backtrack=%d" % (30)
                        FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS", value.lstrip())
                    else:
                        raise FmCheckException("variable EMERGE_DEFAULT_OPTS in %s should contain --backtrack argument" % (FmConst.portageCfgMakeConf))
                elif m.group(2) is None or int(m.group(2)) < 30:
                    if self.bAutoFix:
                        value = value.replace(m.group(0), "--backtrack=%d" % (30))
                        FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS", value)
                    else:
                        raise FmCheckException("variable EMERGE_DEFAULT_OPTS in %s has an inappropriate --backtrack argument" % (FmConst.portageCfgMakeConf))

            # check/fix GENTOO_DEFAULT_MIRROR variable
            if FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "GENTOO_DEFAULT_MIRROR") != FmConst.defaultGentooMirror:
                if self.bAutoFix:
                    FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "GENTOO_DEFAULT_MIRROR", FmConst.defaultGentooMirror)
                else:
                    raise FmCheckException("variable GENTOO_DEFAULT_MIRROR in %s does not exist or has invalid value" % (FmConst.portageCfgMakeConf))

            # check/fix RSYNC_DEFAULT_MIRROR variable
            if FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "RSYNC_DEFAULT_MIRROR") != FmConst.defaultRsyncMirror:
                if self.bAutoFix:
                    FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "RSYNC_DEFAULT_MIRROR", FmConst.defaultRsyncMirror)
                else:
                    raise FmCheckException("variable RSYNC_DEFAULT_MIRROR in %s does not exist or has invalid value" % (FmConst.portageCfgMakeConf))

            # check/fix KERNEL_DEFAULT_MIRROR variable
            if FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "KERNEL_DEFAULT_MIRROR") != FmConst.defaultKernelMirror:
                if self.bAutoFix:
                    FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "KERNEL_DEFAULT_MIRROR", FmConst.defaultKernelMirror)
                else:
                    raise FmCheckException("variable KERNEL_DEFAULT_MIRROR in %s does not exist or has invalid value" % (FmConst.portageCfgMakeConf))

        # check /etc/portage/repos.conf directory
        self.__checkAndFixEtcDir(FmConst.portageCfgReposDir)

        # check /etc/portage/package.mask directory
        self.__checkAndFixEtcDir(FmConst.portageCfgMaskDir)
        if True:
            self.__initCheckAndFixEtcDirContent(FmConst.portageCfgMaskDir)

            # standard files
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgMaskDir, "?-base",               # /etc/portage/package.mask/01-base
                                                   commonDir, "package.mask.base")
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgMaskDir, "?-base_deprecated",    # /etc/portage/package.mask/02-base_deprecated
                                                   commonDir, "package.mask.base_deprecated")
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgMaskDir, "?-base_bugfix",        # /etc/portage/package.mask/02-base_bugfix
                                                   commonDir, "package.mask.base_bugfix")

            # /etc/portage/package.mask/bugfix
            self.__checkAndFixEtcDirContentEmptyFile(FmConst.portageCfgMaskDir, "bugfix")

            # remove redundant files
            self.__endCheckAndFixEtcDirContent(FmConst.portageCfgMaskDir)

            # check package atom validity
            if bFullCheck:
                pass
                # porttree = portage.db[portage.root]["porttree"]
                # cpvAll = porttree.dbapi.cpv_all()
                # for fn in os.listdir(FmConst.portageCfgMaskDir):
                #     fullfn = os.path.join(FmConst.portageCfgMaskDir, fn)
                #     for pkgAtom in FmUtil.portageReadCfgMaskFile(fullfn):
                #         if len(porttree.dbapi.match(pkgAtom)) == 0:
                #             raise FmCheckException("invalid package atom \"%s\" in %s" % (pkgAtom, fullfn))

        # check /etc/portage/package.unmask directory
        self.__checkAndFixEtcDir(FmConst.portageCfgUnmaskDir)
        if True:
            self.__initCheckAndFixEtcDirContent(FmConst.portageCfgUnmaskDir)

            # standard files
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgUnmaskDir, "?-base",
                                                   commonDir, "package.unmask.base")

            # remove redundant files
            self.__endCheckAndFixEtcDirContent(FmConst.portageCfgUnmaskDir)

        # check /etc/portage/package.use directory
        self.__checkAndFixEtcDir(FmConst.portageCfgUseDir)
        if True:
            self.__initCheckAndFixEtcDirContent(FmConst.portageCfgUseDir)

            # standard files
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgUseDir, "?-base",
                                                   commonDir, "package.use.base")
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgUseDir, "?-base_bugfix",
                                                   commonDir, "package.use.base_bugfix")

            # /etc/portage/package.use/98-autouse-manual
            self.__checkAndFixEtcDirContentEmptyFile(FmConst.portageCfgUseDir, "98-autouse-manual")

            # /etc/portage/package.use/99-autouse
            self.__checkAndFixEtcDirContentEmptyFile(FmConst.portageCfgUseDir, "99-autouse")
            fn = os.path.join(FmConst.portageCfgUseDir, "99-autouse")
            for pkgAtom, useList in FmUtil.portageParseCfgUseFile(pathlib.Path(fn).read_text()):
                pkgName = FmUtil.portageGetPkgNameFromPkgAtom(pkgAtom)
                if pkgName != pkgAtom:
                    raise FmCheckException("invalid package name \"%s\" in %s" % (pkgAtom, fn))
                for uf in useList:
                    if uf.startswith("-"):
                        raise FmCheckException("invalid USE flag \"%s\" for package \"%s\" in %s" % (uf, pkgAtom, fn))

            # remove redundant files
            self.__endCheckAndFixEtcDirContent(FmConst.portageCfgUseDir)

            # check use flag existence
            if bFullCheck:
                pass
                # porttree = portage.db[portage.root]["porttree"]
                # cpvAll = porttree.dbapi.cpv_all()
                # for fn in os.listdir(FmConst.portageCfgUseDir):
                #     fullfn = os.path.join(FmConst.portageCfgUseDir, fn)
                #     for pkgAtom, useList in FmUtil.portageReadCfgUseFile(fullfn):
                #         if useList[0].endswith(":"):
                #             # convert EXPAND_USE to normal use flags
                #             useList = [useList[0][:-1].lower() + "_" + x.lstrip("-") for x in useList[1:] if x != "-*"]
                #         else:
                #             useList = [x.lstrip("-") for x in useList]

                #         if pkgAtom == "*/*":
                #             for u in useList:
                #                 bFound = False
                #                 for cpv in cpvAll:
                #                     iuseList = porttree.dbapi.aux_get(cpv, ["IUSE"])[0].split()
                #                     iuseList = [x.lstrip("+") for x in iuseList]
                #                     if u in iuseList:
                #                         bFound = True
                #                         break
                #                 if bFound:
                #                     break
                #             if not bFound:
                #                 raise FmCheckException("invalid USE flag \"%s\" for \"%s\" in %s" % (u, pkgAtom, fullfn))
                #         else:
                #             cpvList = porttree.dbapi.match(pkgAtom)
                #             if len(cpvList) == 0:
                #                 raise FmCheckException("invalid package atom \"%s\" in %s" % (pkgAtom, fullfn))
                #             if FmUtil.portageIsSimplePkgAtom(pkgAtom):
                #                 cpvList = cpvList[-1:]                     # checks only the latest version for simple package atom (eg: media-video/smplayer)
                #             for cpv in cpvList:
                #                 iuseList = porttree.dbapi.aux_get(cpv, ["IUSE"])[0].split()
                #                 iuseList = [x.lstrip("+") for x in iuseList]
                #                 for u in useList:
                #                     if u not in iuseList:
                #                         print(iuseList)
                #                         raise FmCheckException("invalid USE flag \"%s\" for package atom \"%s\" in %s" % (u, pkgAtom, fullfn))

            # check use flag conflict
            if bFullCheck:
                pass

        # check /etc/portage/package.accept_keywords directory
        self.__checkAndFixEtcDir(FmConst.portageCfgAcceptKeywordsDir)
        if True:
            self.__initCheckAndFixEtcDirContent(FmConst.portageCfgAcceptKeywordsDir)

            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgAcceptKeywordsDir, "?-base",
                                                   commonDir, "package.accept_keywords")

            # /etc/portage/package.accept_keywords/99-autokeyword
            self.__checkAndFixEtcDirContentEmptyFile(FmConst.portageCfgAcceptKeywordsDir, "99-autokeyword")

            # remove redundant files
            self.__endCheckAndFixEtcDirContent(FmConst.portageCfgAcceptKeywordsDir)

        # check /etc/portage/package.in_focus directory
        self.__checkAndFixEtcDir(FmConst.portageCfgInFocusDir)
        if True:
            self.__initCheckAndFixEtcDirContent(FmConst.portageCfgInFocusDir)

            # standard files
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgInFocusDir, "?-base",            # /etc/portage/package.in_focus/01-base
                                                   commonDir, "package.in_focus")

            # remove redundant files
            self.__endCheckAndFixEtcDirContent(FmConst.portageCfgInFocusDir)

        # check /etc/portage/package.license directory
        self.__checkAndFixEtcDir(FmConst.portageCfgLicDir)
        if True:
            self.__initCheckAndFixEtcDirContent(FmConst.portageCfgLicDir)

            # standard files
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgLicDir, "?-base",                # /etc/portage/package.license/01-base
                                                   commonDir, "package.license")

            # remove redundant files
            self.__endCheckAndFixEtcDirContent(FmConst.portageCfgLicDir)

        # check /etc/portage/package.env and /etc/portage/env directory
        self.__checkAndFixEtcDir(FmConst.portageCfgEnvDir)
        self.__checkAndFixEtcDir(FmConst.portageCfgEnvDataDir)
        if True:
            self.__initCheckAndFixEtcDirContent(FmConst.portageCfgEnvDir)
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgEnvDir, "01-base", commonDir, "package.env")   # /etc/portage/package.env/01-base
            self.__endCheckAndFixEtcDirContent(FmConst.portageCfgEnvDir)

            self.__initCheckAndFixEtcDirContent(FmConst.portageCfgEnvDataDir)
            self.__checkAndFixEtcDirContentSymlink(FmConst.portageCfgEnvDataDir, "01-base", commonDir, "env.base")  # /etc/portage/env/01-base (directory symlink)
            self.__endCheckAndFixEtcDirContent(FmConst.portageCfgEnvDataDir)

            # /etc/portage/package.env/01-base and /etc/portage/env/01-base should be consistent
            with open(os.path.join(FmConst.portageCfgEnvDir, "01-base"), "r") as f:
                lineList = f.read().split("\n")
                lineList = [x.strip() for x in lineList]
                lineList = [x for x in lineList if x != "" and not x.startswith("#")]
                lineList = [x.split(" ")[0] for x in lineList]
                lineList.remove("*/*")
                dirList = FmUtil.getFileList(os.path.join(FmConst.portageCfgEnvDataDir, "01-base"), 2, "d")
                if set(lineList) != set(dirList):
                    raise FmCheckException("invalid content in %s" % (os.path.join(FmConst.portageCfgEnvDir, "01-base")))

        # check /etc/portage/bbki.kernel
        self.__checkAndFixEtcSymlink(FmConst.bbkiKernelFile, os.path.join(commonDir, "bbki.kernel"))

        # check /etc/portage/bbki.kernel_addon directory
        self.__checkAndFixEtcDir(FmConst.bbkiKernelAddonDir)
        if True:
            self.__initCheckAndFixEtcDirContent(FmConst.bbkiKernelAddonDir)

            # standard files
            self.__checkAndFixEtcDirContentSymlink(FmConst.bbkiKernelAddonDir, "?-base",            # /etc/portage/bbki.kernel_addon/01-base
                                                   commonDir, "bbki.kernel_addon.base")

            # remove redundant files
            self.__endCheckAndFixEtcDirContent(FmConst.bbkiKernelAddonDir)

        # check /etc/portage/bbki.mask directory
        self.__checkAndFixEtcDir(FmConst.bbkiMaskDir)
        if True:
            self.__initCheckAndFixEtcDirContent(FmConst.bbkiMaskDir)

            # standard files
            self.__checkAndFixEtcDirContentSymlink(FmConst.bbkiMaskDir, "?-not_adapted",            # /etc/portage/bbki.mask/01-not_adapted
                                                   commonDir, "bbki.mask.not_adapted")

            # remove redundant files
            self.__endCheckAndFixEtcDirContent(FmConst.bbkiMaskDir)

        # check /etc/portage/bbki.options
        pass

        # check dispatch-conf.conf
        if True:
            buf = ""
            with open(FmConst.cfgDispatchConf, "r") as f:
                buf = f.read()

            # check the existence of variable "archive-dir"
            m = re.search("^archive-dir=(.*)$", buf, re.M)
            if m is None:
                raise FmCheckException("no config item archive-dir in %s" % (FmConst.cfgDispatchConf))

            # check/fix value for variable "archive-dir"
            if m.group(1) != os.path.join("${EPREFIX}", FmConst.configArchiveDir):
                if self.bAutoFix:
                    newLine = "archive-dir=%s" % (os.path.join("${EPREFIX}", FmConst.configArchiveDir))
                    buf = buf.replace(m.group(0), newLine)
                    with open(FmConst.cfgDispatchConf, 'w') as f:
                        f.write(buf)
                else:
                    raise FmCheckException("invalid value of config item archive-dir in %s" % (FmConst.cfgDispatchConf))

        # check /etc/portage/cert.pem & /etc/porage/privkey.pem
        if not os.path.exists(FmConst.myCertFile) or not os.path.exists(FmConst.myPrivKeyFile):
            if self.bAutoFix:
                cert, key = FmUtil.genSelfSignedCertAndKey("-", 1024)
                FmUtil.dumpCertAndKey(cert, key, FmConst.myCertFile, FmConst.myPrivKeyFile)
            else:
                raise FmCheckException("\"%s\" or \"%s\" does not exist" % (FmConst.myCertFile, FmConst.myPrivKeyFile))

        # check /etc/portage/*-
        if bFullCheck:
            flist = glob.glob(os.path.join(FmConst.portageCfgDir, "*-"))
            if len(flist) > 0:
                if self.bAutoFix:
                    for fn in flist:
                        robust_layer.simple_fops.rm(fn)
                else:
                    for fn in flist:
                        self.infoPrinter.printError("Redundant file \"%s\" exist." % (fn))

    def _checkRepositories(self, bFullCheck=True):
        """Check repositories"""

        # all repositories should exist
        for repoName in self.pkgwh.repoman.getRepositoryList():
            if not self.pkgwh.repoman.isRepoExist(repoName):
                if self.bAutoFix:
                    self.pkgwh.repoman.createRepository(repoName)
                else:
                    raise FmCheckException("repository \"%s\" does not exist" % (repoName))

        # check all repositories
        for repoName in self.pkgwh.repoman.getRepositoryList():
            # FIXME: this function throws exception directly, there should be a way to auto fix it
            try:
                self.pkgwh.repoman.checkRepository(repoName, self.bAutoFix)
            except RepositoryCheckError as e:
                raise FmCheckException(e.message)

        # there should be no same ebuild directory between repositories
        if bFullCheck:
            infoDict = dict()
            for repoName in self.pkgwh.repoman.getRepositoryList():
                repoDir = self.pkgwh.repoman.getRepoDir(repoName)
                infoDict[repoName] = set(FmUtil.repoGetEbuildDirList(repoDir))

            tlist = list(infoDict.items())
            for i in range(0, len(tlist)):
                for j in range(i + 1, len(tlist)):
                    k, v = tlist[i]
                    k2, v2 = tlist[j]
                    for vi in list(v & v2):
                        self.infoPrinter.printError("Repository \"%s\" and \"%s\" has same package \"%s\"" % (k, k2, vi))

    def _checkOverlays(self, bCheckContent, bFullCheck=True):
        """Check overlays"""

        # check all overlays
        for overlayName in self.pkgwh.layman.getOverlayList():
            try:
                self.pkgwh.layman.checkOverlay(overlayName, bCheckContent, self.bAutoFix)
            except OverlayCheckError as e:
                raise FmCheckException(e.message)

        # basic check stops here
        if not bFullCheck:
            return

        overlayDb = CloudOverlayDb()
        if not overlayDb.isUpdateComplete():
            if self.bAutoFix:
                overlayDb.update()
            else:
                raise FmCheckException("overlay database is not updated")

        for overlayName in self.pkgwh.layman.getOverlayList():
            oDir = self.pkgwh.layman.getOverlayDir(overlayName)

            # 1. compare overlay vcs-type and name with cloud database, use cache only
            if overlayDb.hasOverlay(overlayName):
                ret = overlayDb.getOverlayVcsTypeAndUrl(overlayName)
                if ret != self.pkgwh.layman.getOverlayVcsTypeAndUrl(overlayName):
                    if self.bAutoFix:
                        self.pkgwh.layman.modifyOverlayVcsTypeAndUrl(overlayName, ret[0], ret[1])
                    else:
                        self.infoPrinter.printError("Overlay \"%s\" should have VCS type \"%s\" and URL \"%s\", same with the cloud overlay database." % (overlayName, ret[0], ret[1]))

            # 2. there should be no same ebuild directory between repository and overlay
            if True:
                infoDict = dict()
                for repoName in self.pkgwh.repoman.getRepositoryList():
                    repoDir = self.pkgwh.repoman.getRepoDir(repoName)
                    infoDict[repoName] = set(FmUtil.repoGetEbuildDirList(repoDir))

                oDirInfo = set(FmUtil.repoGetEbuildDirList(oDir))
                for k, v in infoDict.items():
                    for vi in list(v & oDirInfo):
                        if self.bAutoFix and self.pkgwh.layman.getOverlayType(overlayName) in ["trusted", "transient"]:
                            FmUtil.repoRemovePackageAndCategory(oDir, vi)
                        else:
                            self.infoPrinter.printError("Repository \"%s\" and overlay \"%s\" has same package \"%s\"." % (k, overlayName, vi))

            # 3. transient overlay must has at least one enabled package
            #    this should be after check 2 since check 2 may auto remove package from overlay
            if self.pkgwh.layman.getOverlayType(overlayName) == "transient":
                if len(FmUtil.repoGetEbuildDirList(oDir)) == 0:
                    if self.bAutoFix:
                        self.pkgwh.layman.removeOverlay(overlayName)
                        continue
                    else:
                        self.infoPrinter.printError("Overlay \"%s\" has no enabled package." % (overlayName))

            # 4. overlays should not have same repo_name
            if True:
                overlayRepoName = self.pkgwh.layman.getOverlayMetadata(overlayName, "repo-name")
                for repoName in self.pkgwh.repoman.getRepositoryList():
                    if self.pkgwh.repoman.getRepoMetadata(repoName, "repo-name") == overlayRepoName:
                        self.infoPrinter.printError("Repository \"%s\" and overlay \"%s\" has same repo_name." % (repoName, overlayName))
                for oname2 in self.pkgwh.layman.getOverlayList():
                    if overlayName == oname2:
                        continue
                    if self.pkgwh.layman.getOverlayMetadata(oname2, "repo-name") == overlayRepoName:
                        self.infoPrinter.printError("Overlay \"%s\" and \"%s\" has same repo_name." % (oname2, overlayName))

#            # there should be no same set files between overlays
#            if True:
#                infoDict = dict()
#                for oname2 in self.pkgwh.layman.getOverlayList():
#                    oSetDir = os.path.join(self.pkgwh.layman.getOverlayFilesDir(oname2), "set")
#                    infoDict[oname2] = set(os.listdir(oSetDir)) if os.path.exists(oSetDir) else set()
#                for oname2 in self.pkgwh.layman.getOverlayList():
#                    if overlayName == oname2:
#                        continue
#                    vi = list(infoDict[overlayName] & infoDict[oname2])
#                    if len(vi) == 0:
#                        continue
#                    for f in vi:
#                        self.infoPrinter.printError("Overlay \"%s\" and \"%s\" has same set file \"%s\"" % (overlayName, oname2, f))
#                    for f in vi:
#                        fname1 = os.path.join(self.pkgwh.layman.getOverlayFilesDir(k), "set", f)
#                        fname2 = os.path.join(self.pkgwh.layman.getOverlayFilesDir(k2), "set", f)
#                        if not FmUtil.fileHasSameContent(fname1, fname2):
#                            raise FmCheckException("overlay \"%s\" and \"%s\" has same set file \"%s\"" % (k, k2, f))

    def _checkRedundantRepositoryAndOverlay(self):
        tlist = []
        tlist += glob.glob(os.path.join(FmConst.portageDataDir, "repo-*"))
        tlist += glob.glob(os.path.join(FmConst.portageDataDir, "overlay-*"))

        # check /etc/portage/repos.conf directory
        fileList = []
        for repoName in self.pkgwh.repoman.getRepositoryList():
            fileList.append(self.pkgwh.repoman.getRepoCfgReposFile(repoName))
        for overlayName in self.pkgwh.layman.getOverlayList():
            fileList.append(self.pkgwh.layman.getOverlayCfgReposFile(overlayName))
        for fn in os.listdir(FmConst.portageCfgReposDir):
            fullfn = os.path.join(FmConst.portageCfgReposDir, fn)
            if fullfn not in fileList:
                if self.bAutoFix:
                    os.remove(fullfn)
                else:
                    self.infoPrinter.printError("Redundant repository configuration file \"%s\" exist." % (fullfn))

        # find un-referenced directory in /var/lib/portage/repo-* & /var/lib/portage/overlay-*
        redundantList = []
        for fullfn in tlist:
            fn = os.path.basename(fullfn)
            if not os.path.exists(os.path.join(FmConst.portageCfgReposDir, "%s.conf" % (fn))):
                if self.bAutoFix:
                    robust_layer.simple_fops.rm(fullfn)
                else:
                    redundantList.append(fullfn)
                    self.infoPrinter.printError("Redundant directory \"%s\" found." % (fullfn))

        # find un-referenced directory in /var/cache/portage/laymanfiles/*
        for fn in os.listdir(FmConst.laymanfilesDir):
            fullfn = os.path.join(FmConst.laymanfilesDir, fn)
            libFullfn = os.path.join(FmConst.portageDataDir, "overlay-%s" % (fn))
            if not os.path.exists(libFullfn) or libFullfn in redundantList:
                if self.bAutoFix:
                    robust_layer.simple_fops.rm(fullfn)
                else:
                    self.infoPrinter.printError("Redundant directory \"%s\" found." % (fullfn))

    def _checkNews(self):
        # check unread news
        if FmUtil.cmdCall("/usr/bin/eselect", "news", "count") != "0":
            if self.bAutoFix:
                FmUtil.cmdCallIgnoreResult("/usr/bin/eselect", "news", "read", "all")
            else:
                self.infoPrinter.printError("There are unread portage news items, please use \"eselect news read all\".")

    def _checkPortagePkgwhCfg(self):
        # /etc/portage/package.use/30-hardware
        # /etc/portage/package.use/90-python-targets
        # /etc/portage/package.use/91-ruby-targets
        if self.bAutoFix:
            self.pkgwh.refreshHardwareUseFlags(self.param.machineInfoGetter.hwInfo())
            self.pkgwh.refreshTargetUseFlags()
        else:
            self.pkgwh.checkHardwareUseFlags(self.param.machineInfoGetter.hwInfo())
            self.pkgwh.checkTargetUseFlags()

        # /etc/portage/package.use/97-linguas
        # FIXME: support syncupd
        if self.bAutoFix:
            self.pkgwh.refreshLinguasUseFlags()
        else:
            self.pkgwh.checkLinguasUseFlags()

    def _checkImportantPackage(self):
        # get important package list
        importantPkgList = []
        for fn in os.listdir(FmConst.portageCfgInFocusDir):
            with open(os.path.join(FmConst.portageCfgInFocusDir, fn), "r") as f:
                for line in f.read().split("\n"):
                    line = line.strip()
                    if line == "" or line.startswith("#"):
                        continue
                    line = re.sub(r'\s*#.*', "", line)
                    importantPkgList.append(line)

        # get all package list:
        allPkgList = []
        for repoName in self.pkgwh.repoman.getRepositoryList():
            allPkgList += FmUtil.repoGetEbuildDirList(self.pkgwh.repoman.getRepoDir(repoName))
        for oName in self.pkgwh.layman.getOverlayList():
            allPkgList += FmUtil.repoGetEbuildDirList(self.pkgwh.layman.getOverlayDir(oName))

        # check existence
        for pkg in importantPkgList:
            if pkg not in allPkgList:
                self.infoPrinter.printError("Important package \"%s\" does not exist in any repository or overlay." % (pkg))

    def _checkWorldFile(self):
        worldFile = os.path.join(FmConst.portageDataDir, "world")
        for line in pathlib.Path(worldFile).read_text().split("\n"):
            line = line.strip()
            if line == "":
                continue
            if not FmUtil.portageIsPkgInstallable(line):
                self.infoPrinter.printError("Uninstallable package \"%s\" in \"%s\"." % (line, worldFile))

    def _checkUsersAndGroups(self):
        # make sure passwd/group/shadow are tidy
        if self.bAutoFix:
            with strict_pgs.PasswdGroupShadow(readOnly=False, msrc="fpemud-os") as pgs:
                pass

        # do checks
        with strict_pgs.PasswdGroupShadow() as pgs:
            pgs.verify()
            if len(pgs.getStandAloneGroupList()) > 0:
                raise FmCheckException("there should be no stand alone groups")

    def _checkSystemLocale(self):
        """Check system locale configuration"""

        fn = "/etc/locale.conf"
        content = "LANG=\"C.utf8\""     # we don't accept LANGUAGE and LC_* variables

        # check if /etc/locale.conf exists
        if not os.path.exists(fn):
            if not self.bAutoFix:
                self.infoPrinter.printError("Locale is not configured.")
            else:
                with open(fn, "w") as f:
                    f.write(content + "\n")
            return

        # check if content of /etc/locale.conf is correct
        lines = FmUtil.readListFile(fn)
        if len(lines) != 1 or lines[0] != content:
            if not self.bAutoFix:
                self.infoPrinter.printError("System locale should be configured as \"C.utf8\".")
            else:
                with open(fn, "w") as f:
                    f.write(content + "\n")
            return

    def _checkSystemServices(self):
        # all enabled services should be runnning
        # FIXME: not that simple
        if False:
            for s in FmUtil.systemdGetAllServicesEnabled():
                print(s)
                if not FmUtil.systemdIsUnitRunning(s):
                    self.infoPrinter.printError("Service \"%s\" is enabled but not running.")

        # default LimitNOFILE is 1024:524288 (for soft and hard limit)
        # ideally it should be infinity:infinity
        # we make it 524288:524288 currently
        cfg = configparser.ConfigParser()
        cfg.read("/etc/systemd/system.conf")
        if not cfg.has_option("Manager", "DefaultLimitNOFILE") or cfg.get("Manager", "DefaultLimitNOFILE") != "524288:524288":
            self.infoPrinter.printError("DefaultLimitNOFILE in /etc/systemd/system.conf should be set to 524288.")

        # check limit in-effect for all system services
        pass

    def _checkSystemTime(self):
        # check timezone configuration
        while True:
            if not os.path.exists("/etc/timezone") or not os.path.exists("/etc/localtime"):
                self.infoPrinter.printError("Timezone is not properly configured.")
                break
            tz = None
            with open("/etc/timezone", "r") as f:
                tz = os.path.join("/usr/share/zoneinfo", f.read().rstrip("\n"))
            if not os.path.exists(tz):
                self.infoPrinter.printError("Timezone is not properly configured.")
                break
            if not filecmp.cmp("/etc/localtime", tz):
                self.infoPrinter.printError("Timezone is not properly configured.")
                break
            break

        # check system time
        try:
            for i in range(0, 4):
                try:
                    nc = ntplib.NTPClient()
                    ret = nc.request("%d.pool.ntp.org" % (i))
                    if abs(ret.offset) > 1.0:
                        # we tolerant an offset of 1 seconds
                        self.infoPrinter.printError("System time is incorrect. Maybe you need network time synchronization?")
                    break
                except:
                    if i == 3:
                        raise
        except Exception as e:
            self.infoPrinter.printError("Error occured when checking system time, %s." % (str(e)))

    def _checkPackageContentFile(self, pkgNameVer):
        contf = os.path.join(FmConst.portageDbDir, pkgNameVer, "CONTENTS_2")
        if not os.path.exists(contf):
            if self.bAutoFix:
                PkgMerger().reInstallPkg(pkgNameVer)
                if not os.path.exists(contf):
                    self.infoPrinter.printError("Content file %s is missing, auto-fix failed." % (contf))
            else:
                self.infoPrinter.printError("Content file %s is missing." % (contf))

    def _checkPackageFileScope(self, pkgNameVer):
        # There're some directories and files I think should not belong to any package, but others don't think so...
        wildcards = []
        if True:
            obj = strict_fsh.RootFs()
            wildcards = strict_fsh.merge_wildcards(wildcards, obj.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_SYSTEM_DATA))
            wildcards = strict_fsh.merge_wildcards(wildcards, obj.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_USER_DATA))
            wilecards = strict_fsh.merge_wildcards(wildcards, obj.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_BOOT))
            wildcards = strict_fsh.merge_wildcards(wildcards, obj.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_RUNTIME))

        # get file list for this package
        cmdStr = r"/bin/cat /var/db/pkg/%s/CONTENTS " % (pkgNameVer)
        cmdStr += r'| /bin/sed -e "s:^obj \(.*\) [[:xdigit:]]\+ [[:digit:]]\+$:\1:" '
        cmdStr += r'| /bin/sed -e "s:^sym \(.*\) -> .* .*$:\1:" '
        cmdStr += r'| /bin/sed -e "s:^dir \(.*\)$:\1:" '
        ret = FmUtil.shellCall(cmdStr).split("\n")

        # check
        for fn in strict_fsh.wildcards_filter(ret, wilecards):
            self.infoPrinter.printError("\"%s\" should not be installed by package manager. (add to \"/usr/lib/tmpfiles.d/*.conf\"?)" % (fn))

    def _checkPackageMd5(self, pkgNameVer):
        itemList = []

        # get item list from CONTENTS_2 file
        if True:
            contf = os.path.join(FmConst.portageDbDir, pkgNameVer, "CONTENTS_2")
            if not os.path.exists(contf):
                # FIXME
                self.infoPrinter.printError("CONTENTS_2 file for %s is missing." % (pkgNameVer))
                return
            itemList = FmUtil.portageParseVarDbPkgContentFile(contf)

        # filter extra files
        if True:
            wildcards = FmUtil.repoGetPkgExtraFilesWildcards(FmConst.portageDbDir, pkgNameVer)
            wildcards = strict_fsh.merge_wildcards(wildcards, ["+ /etc/***"])
            itemList = [x for x in itemList if not strict_fsh.wildcards_match(x[1], wildcards)]

        # check md5
        for item in itemList:
            if item[0] == "dir":
                if not os.path.exists(item[1]):
                    self.infoPrinter.printError("Directory %s is missing." % (item[1]))
                else:
                    s = os.stat(item[1])
                    if s.st_uid != item[3]:
                        self.infoPrinter.printError("Directory %s failes for uid verification." % (item[1]))
                    if s.st_gid != item[4]:
                        self.infoPrinter.printError("Directory %s failes for gid verification." % (item[1]))
            elif item[0] == "obj":
                if not os.path.exists(item[1]):
                    self.infoPrinter.printError("File %s is missing" % (item[1]))
                else:
                    if not FmUtil.verifyFileMd5(item[1], item[2]):
                        self.infoPrinter.printError("File %s fails for MD5 verification." % (item[1]))
                    s = os.stat(item[1])
                    if s.st_mode != item[3]:
                        self.infoPrinter.printError("File %s failes for permission verification." % (item[1]))
                    if s.st_uid != item[4]:
                        self.infoPrinter.printError("File %s failes for uid verification." % (item[1]))
                    if s.st_gid != item[5]:
                        self.infoPrinter.printError("File %s failes for gid verification." % (item[1]))
            elif item[0] == "sym":
                if not os.path.islink(item[1]):
                    self.infoPrinter.printError("Symlink %s is missing." % (item[1]))
                else:
                    if os.readlink(item[1]) != item[2]:
                        self.infoPrinter.printError("Symlink %s fails for target verification." % (item[1]))
                    if not os.path.exists(item[1]):
                        self.infoPrinter.printError("Symlink %s is broken." % (item[1]))
                    else:
                        s = os.stat(item[1])
                        if s.st_uid != item[3]:
                            self.infoPrinter.printError("Symlink %s failes for uid verification." % (item[1]))
                        if s.st_gid != item[4]:
                            self.infoPrinter.printError("Symlink %s failes for gid verification." % (item[1]))
            else:
                assert False

    def _checkPkgByScript(self, pkgNameVer):
        pass
        # e2dir = Ebuild2Dir()
        # fbasename = FmUtil.portageGetPkgNameFromPkgAtom(pkgNameVer)
        # if e2dir.hasPkgCheckScript(fbasename):
        #     try:
        #         e2dir.execPkgCheckScript(fbasename)
        #     except Ebuild2CheckError as e:
        #         self.infoPrinter.printError(e.message)

    def _checkSystemCruft(self):
        rootFs = strict_fsh.RootFs()

        # get wildcards
        wildcards = rootFs.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_SYSTEM)
        wildcards = strict_fsh.merge_wildcards(wildcards, rootFs.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_SYSTEM_DATA))

        # filter wildcards: filter layout files
        wildcards = strict_fsh.deduct_wildcards(wildcards, rootFs.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_LAYOUT))

        # filter wildcards: filter trash files
        wildcards = strict_fsh.deduct_wildcards(wildcards, rootFs.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_USER_TRASH))

        # filter wildcards: filter boot files, which we manage by ourself
        wildcards = strict_fsh.deduct_wildcards(wildcards, rootFs.get_wildcards(wildcards_flag=strict_fsh.WILDCARDS_BOOT))

        # filter wildcards: filter all package extra files
        for pkgAtom in FmUtil.portageGetInstalledPkgAtomList(FmConst.portageDbDir):
            wildcards2 = FmUtil.repoGetPkgExtraFilesWildcards(FmConst.portageDbDir, pkgAtom)
            wildcards = strict_fsh.deduct_wildcards(wildcards, wildcards2)

        # get files
        fileSet = set(rootFs.wildcards_glob(wildcards))

        # filter files: filter installed files
        if True:
            fileSet -= FmUtil.portageGetInstalledFileSet(expanded=True)

        # show or delete
        for cf in sorted(list(fileSet)):
            if self.bAutoFix:
                # auto remove cruft file: broken symlink
                if os.path.islink(cf) and not os.path.exists(cf):
                    os.unlink(cf)
                    continue
            # show cruft file
            self.infoPrinter.printError("Cruft file found: %s" % (cf))

    def __checkAndFixEtcDir(self, etcDir):
        if not os.path.exists(etcDir):
            if self.bAutoFix:
                os.mkdir(etcDir)
            else:
                raise FmCheckException("\"%s\" is not a directory" % (etcDir))
        elif not os.path.isdir(etcDir):
            if self.bAutoFix:
                etcDir2 = etcDir + ".2"
                os.mkdir(etcDir2)
                os.rename(etcDir, os.path.join(etcDir2, self.__portageGetUnknownFilename(etcDir2)))
                os.rename(etcDir2, etcDir)
            else:
                raise FmCheckException("\"%s\" is not a directory" % (etcDir))

    def __checkAndFixEtcFile(self, filename, content):
        if os.path.exists(filename):
            with open(filename, "r") as f:
                if f.read() == content:
                    return
                else:
                    if not self.bAutoFix:
                        raise FmCheckException("\"%s\" has invalid content" % (filename))
        else:
            if not self.bAutoFix:
                raise FmCheckException("\"%s\" does not exist" % (filename))

        with open(filename, "w") as f:
            f.write(content)

    def __checkAndFixEtcSymlink(self, filename, target):
        if os.path.islink(filename) and os.readlink(filename) == target:
            return

        if not self.bAutoFix:
            raise FmCheckException("\"%s\" is an invalid symlink" % (filename))
        else:
            robust_layer.simple_fops.ln(target, filename)

    def __initCheckAndFixEtcDirContent(self, etcDir):
        self._etcDir = etcDir
        self._etcDirContentIndex = 1
        self._etcSymLinkList = []

    def __checkAndFixEtcDirContentSymlink(self, etcDir, linkName, libDir, targetName):
        assert etcDir == self._etcDir
        assert os.path.exists(os.path.join(libDir, targetName))

        if "?" in linkName:
            linkName = linkName.replace("?", "%02d" % (self._etcDirContentIndex))
            self._etcDirContentIndex += 1

        linkFile = os.path.join(self._etcDir, linkName)
        targetFile = os.path.join(libDir, targetName)

        # <linkFile> does not exist, fix: create the symlink
        if not os.path.lexists(linkFile):
            if self.bAutoFix:
                os.symlink(targetFile, linkFile)
            else:
                raise FmCheckException("\"%s\" must be a symlink to \"%s\"" % (linkFile, targetFile))

        # <linkFile> is not a symlink, fix: keep the original file, create the symlink
        if not os.path.islink(linkFile):
            if self.bAutoFix:
                os.rename(linkFile, os.path.join(self._etcDir, self.__portageGetUnknownFilename(self._etcDir)))
                os.symlink(targetFile, linkFile)
            else:
                raise FmCheckException("\"%s\" must be a symlink to \"%s\"" % (linkFile, targetFile))

        # <linkFile> is wrong, fix: re-create the symlink
        if os.readlink(linkFile) != targetFile:
            if self.bAutoFix:
                robust_layer.simple_fops.ln(targetFile, linkFile)
            else:
                raise FmCheckException("\"%s\" must be a symlink to \"%s\"" % (linkFile, targetFile))

        self._etcSymLinkList.append(linkFile)

    def __checkAndFixEtcDirContentEmptyFile(self, etcDir, fileName):
        assert etcDir == self._etcDir

        if "?" in fileName:
            fileName = fileName.replace("?", "%02d" % (self._etcDirContentIndex))
            self._etcDirContentIndex += 1

        fn = os.path.join(self._etcDir, fileName)
        if not os.path.exists(fn):
            if self.bAutoFix:
                FmUtil.touchFile(fn)
            else:
                raise FmCheckException("\"%s\" does not exist" % (fn))

    def __endCheckAndFixEtcDirContent(self, etcDir):
        assert etcDir == self._etcDir

        if self.bAutoFix:
            for fn in os.listdir(self._etcDir):
                fullfn = os.path.join(self._etcDir, fn)
                if os.path.islink(fullfn) and fullfn not in self._etcSymLinkList:
                    os.unlink(fullfn)

        del self._etcSymLinkList
        del self._etcDirContentIndex
        del self._etcDir

    def __portageGetUnknownFilename(self, dirpath):
        if not os.path.exists(os.path.join(dirpath, "90-unknown")):
            return "90-unknown"
        i = 2
        while True:
            if not os.path.exists(os.path.join(dirpath, "90-unknown-%d" % (i))):
                return "90-unknown-%d" % (i)
            i += 1


class FmCheckException(Exception):

    def __init__(self, message):
        super(FmCheckException, self).__init__(message)


class _DiskPartitionTableChecker:

    def __init__(self):
        # struct mbr_partition_record {
        #     uint8_t  boot_indicator;
        #     uint8_t  start_head;
        #     uint8_t  start_sector;
        #     uint8_t  start_track;
        #     uint8_t  os_type;
        #     uint8_t  end_head;
        #     uint8_t  end_sector;
        #     uint8_t  end_track;
        #     uint32_t starting_lba;
        #     uint32_t size_in_lba;
        # };
        self.mbrPartitionRecordFmt = "8BII"
        assert struct.calcsize(self.mbrPartitionRecordFmt) == 16

        # struct mbr_header {
        #     uint8_t                     boot_code[440];
        #     uint32_t                    unique_mbr_signature;
        #     uint16_t                    unknown;
        #     struct mbr_partition_record partition_record[4];
        #     uint16_t                    signature;
        # };
        self.mbrHeaderFmt = "440sIH%dsH" % (struct.calcsize(self.mbrPartitionRecordFmt) * 4)
        assert struct.calcsize(self.mbrHeaderFmt) == 512

    def checkDisk(self, devPath):
        pttype = FmUtil.getBlkDevPartitionTableType(devPath)
        if pttype == "gpt":
            self._checkGptDisk(devPath)
        elif pttype == "dos":
            self._checkMbrDisk(devPath)
        else:
            raise _DiskPartitionTableCheckerFailure("Unknown disk partition table type")

    def _checkGptDisk(self, devPath):
        # get Protective MBR header
        mbrHeader = None
        with open(devPath, "rb") as f:
            buf = f.read(struct.calcsize(self.mbrHeaderFmt))
            mbrHeader = struct.unpack(self.mbrHeaderFmt, buf)

        # check Protective MBR header
        if not FmUtil.isBufferAllZero(mbrHeader[0]):
            raise _DiskPartitionTableCheckerFailure("Protective MBR Boot Code should be empty")
        if mbrHeader[1] != 0:
            raise _DiskPartitionTableCheckerFailure("Protective MBR Disk Signature should be zero")
        if mbrHeader[2] != 0:
            raise _DiskPartitionTableCheckerFailure("reserved area in Protective MBR should be zero")

        # check Protective MBR Partition Record
        if True:
            pRec = struct.unpack_from(self.mbrPartitionRecordFmt, mbrHeader[3], 0)
            if pRec[4] != 0xEE:
                raise _DiskPartitionTableCheckerFailure("the first Partition Record should be Protective MBR Partition Record (OS Type == 0xEE)")
            if pRec[0] != 0:
                raise _DiskPartitionTableCheckerFailure("Boot Indicator in Protective MBR Partition Record should be zero")

        # other Partition Record should be filled with zero
        if not FmUtil.isBufferAllZero(mbrHeader[struct.calcsize(self.mbrPartitionRecordFmt):]):
            raise _DiskPartitionTableCheckerFailure("all the Partition Record should be filled with zero")

        # ghnt and check primary and backup GPT header
        pass

    def _checkMbrDisk(self, devPath):
        pass


class _DiskPartitionTableCheckerFailure(Exception):

    def __init__(self, message):
        self.message = message
