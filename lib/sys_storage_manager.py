#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
from fm_util import FmUtil
from fm_param import FmConst


class FmStorageLayoutEmpty:

    name = "empty"

    def getType(self):
        return None

    def isReady(self):
        return False

    def getBootHdd(self):
        assert False

    def getBootDev(self):
        assert False

    def getRootDev(self):
        assert False


class FmStorageLayoutBiosSimple:
    """Layout:
           /dev/sda          MBR, BIOS-GRUB
               /dev/sda1     root device, EXT4
       Description:
           1. partition number of /dev/sda1 and /dev/sda2 is irrelevant
           2. use optional swap file /var/swap.dat
           3. extra partition is allowed to exist
    """

    name = "bios-simple"

    def __init__(self):
        self.hdd = None
        self.hddRootParti = None
        self.swapFile = None

    def getType(self):
        return "bios"

    def isReady(self):
        assert self.hdd is not None
        assert self.hddRootParti is not None
        assert self.swapFile is None or self.swapFile == _swapFilename
        return True

    def getBootHdd(self):
        assert self.isReady()
        return self.hdd

    def getBootDev(self):
        assert self.isReady()
        return None                     # bios use boot-hdd not boot-dev

    def getRootDev(self):
        assert self.isReady()
        return self.hddRootParti


class FmStorageLayoutBiosLvm:
    """Layout:
           /dev/sda                 MBR, BIOS-GRUB
               /dev/sda1            LVM-PV for VG hdd
           /dev/mapper/hdd.root     root device, EXT4
           /dev/mapper/hdd.swap     swap device
       Description:
           1. only one partition is allowed in LVM-PV device
           2. swap device is optional
           3. extra LVM-LV is allowed to exist
           4. extra harddisk is allowed to exist
    """

    name = "bios-lvm"

    def __init__(self):
        self.lvmVg = None
        self.lvmPvHddList = []
        self.lvmRootLv = None
        self.lvmSwapLv = None
        self.bootHdd = None

    def getType(self):
        return "bios"

    def isReady(self):
        assert self.lvmVg == "hdd"
        assert len(self.lvmPvHddList) > 0
        assert self.lvmRootLv == "root"
        assert self.lvmSwapLv is None or self.lvmSwapLv == "swap"
        assert self.bootHdd is not None and self.bootHdd in self.lvmPvHddList
        return True

    def getBootHdd(self):
        assert self.isReady()
        return self.bootHdd

    def getBootDev(self):
        assert self.isReady()
        return None                     # bios use boot-hdd not boot-dev

    def getRootDev(self):
        assert self.isReady()
        # return "/dev/mapper/%s.%s" % (self.lvmVg, self.lvmRootLv)
        ret = "/dev/mapper/%s.%s" % (self.lvmVg, self.lvmRootLv)
        if os.path.exists(ret):
            return ret
        else:
            ret = "/dev/mapper/%s-%s" % (self.lvmVg, self.lvmRootLv)    # compatible with old lvm version
            if os.path.exists(ret):
                return ret
        assert False


class FmStorageLayoutEfiSimple:
    """Layout:
           /dev/sda          GPT, EFI-GRUB
               /dev/sda1     ESP partition
               /dev/sda2     root device, EXT4
       Description:
           1. the 3 partition in /dev/sda is order-insensitive
           2. use optional swap file /var/swap.dat
           3. extra partition is allowed to exist
    """

    name = "efi-simple"

    def __init__(self):
        self.hdd = None
        self.hddEspParti = None
        self.hddRootParti = None
        self.swapFile = None

    def getType(self):
        return "efi"

    def isReady(self):
        assert self.hdd is not None
        assert self.hddEspParti == FmUtil.devPathDiskToPartition(self.hdd, 1)
        assert self.hddRootParti == FmUtil.devPathDiskToPartition(self.hdd, 2)
        assert self.swapFile is None or self.swapFile == _swapFilename
        return True

    def getBootHdd(self):
        assert self.isReady()
        return None                     # efi use boot-dev not boot-hdd

    def getBootDev(self):
        assert self.isReady()
        return self.hddEspParti

    def getRootDev(self):
        assert self.isReady()
        return self.hddRootParti


class FmStorageLayoutEfiLvm:
    """Layout:
           /dev/sda                 GPT, EFI-GRUB
               /dev/sda1            ESP partition
               /dev/sda2            LVM-PV for VG hdd
           /dev/sdb                 Non-SSD, GPT
               /dev/sdb1            reserved ESP partition
               /dev/sdb2            LVM-PV for VG hdd
           /dev/mapper/hdd.root     root device, EXT4
           /dev/mapper/hdd.swap     swap device
       Description:
           1. /dev/sda1 and /dev/sdb1 must has the same size
           2. /dev/sda1 and /dev/sda2 is order-sensitive, no extra partition is allowed
           3. /dev/sdb1 and /dev/sdb2 is order-sensitive, no extra partition is allowed
           4. swap device is optional
           5. extra LVM-LV is allowed to exist
           6. extra harddisk is allowed to exist
    """

    name = "efi-lvm"

    def __init__(self):
        self.lvmVg = None
        self.lvmPvHddList = []
        self.lvmRootLv = None
        self.lvmSwapLv = None
        self.bootHdd = None

    def getType(self):
        return "efi"

    def isReady(self):
        assert self.lvmVg == "hdd"
        assert len(self.lvmPvHddList) > 0
        assert self.lvmRootLv == "root"
        assert self.lvmSwapLv is None or self.lvmSwapLv == "swap"
        assert self.bootHdd is not None and self.bootHdd in self.lvmPvHddList
        return True

    def getBootHdd(self):
        assert self.isReady()
        return None                     # efi use boot-dev not boot-hdd

    def getBootDev(self):
        assert self.isReady()
        return FmUtil.devPathDiskToPartition(self.bootHdd, 1)

    def getRootDev(self):
        assert self.isReady()
        # return "/dev/mapper/%s.%s" % (self.lvmVg, self.lvmRootLv)
        ret = "/dev/mapper/%s.%s" % (self.lvmVg, self.lvmRootLv)
        if os.path.exists(ret):
            return ret
        else:
            ret = "/dev/mapper/%s-%s" % (self.lvmVg, self.lvmRootLv)    # compatible with old lvm version
            if os.path.exists(ret):
                return ret
        assert False


class FmStorageLayoutEfiBcacheLvm:
    """Layout:
           /dev/sda                 SSD, GPT, EFI-GRUB (cache-disk)
               /dev/sda1            ESP partition
               /dev/sda2            swap device
               /dev/sda3            bcache cache device
           /dev/sdb                 Non-SSD, GPT
               /dev/sdb1            reserved ESP partition
               /dev/sdb2            bcache backing device
           /dev/sdc                 Non-SSD, GPT
               /dev/sdc1            reserved ESP partition
               /dev/sdc2            bcache backing device
           /dev/bcache0             corresponds to /dev/sdb2, LVM-PV for VG hdd
           /dev/bcache1             corresponds to /dev/sdc2, LVM-PV for VG hdd
           /dev/mapper/hdd.root     root device, EXT4
       Description:
           1. /dev/sda1 and /dev/sd{b,c}1 must has the same size
           2. /dev/sda1, /dev/sda2 and /dev/sda3 is order-sensitive, no extra partition is allowed
           3. /dev/sd{b,c}1 and /dev/sd{b,c}2 is order-sensitive, no extra partition is allowed
           4. cache-disk is optional, and only one cache-disk is allowed at most
           5. cache-disk must have a swap partition
           6. extra LVM-LV is allowed to exist
           7. extra harddisk is allowed to exist
    """

    name = "efi-bcache-lvm"

    def __init__(self):
        self.ssd = None
        self.ssdEspParti = None
        self.ssdSwapParti = None
        self.ssdCacheParti = None
        self.lvmVg = None
        self.lvmPvHddDict = {}          # dict<hddDev,bcacheDev>
        self.lvmRootLv = None
        self.bootHdd = None

    def getType(self):
        return "efi"

    def isReady(self):
        assert self.lvmVg == "hdd"
        assert len(self.lvmPvHddDict) > 0
        assert self.lvmRootLv == "root"
        if self.ssd is not None:
            assert self.ssdEspParti == FmUtil.devPathDiskToPartition(self.ssd, 1)
            assert self.ssdSwapParti == FmUtil.devPathDiskToPartition(self.ssd, 2)
            assert self.ssdCacheParti == FmUtil.devPathDiskToPartition(self.ssd, 3)
            assert self.bootHdd is None
        else:
            assert self.bootHdd is not None and self.bootHdd in self.lvmPvHddDict
        return True

    def getBootHdd(self):
        assert self.isReady()
        return None                     # efi use boot-dev not boot-hdd

    def getBootDev(self):
        assert self.isReady()
        if self.ssd is not None:
            return self.ssdEspParti
        else:
            return FmUtil.devPathDiskToPartition(self.bootHdd, 1)

    def getRootDev(self):
        assert self.isReady()
        # return "/dev/mapper/%s.%s" % (self.lvmVg, self.lvmRootLv)
        ret = "/dev/mapper/%s.%s" % (self.lvmVg, self.lvmRootLv)
        if os.path.exists(ret):
            return ret
        else:
            ret = "/dev/mapper/%s-%s" % (self.lvmVg, self.lvmRootLv)    # compatible with old lvm version
            if os.path.exists(ret):
                return ret
        assert False


class FmStorageLayoutNonStandard:

    name = "non-standard"

    def __init__(self, bEfi, bootHdd, bootDev, rootDev, closestLayoutName, message):
        self.closestLayoutName = closestLayoutName
        self.message = message
        self._efi = bEfi
        self._bootHdd = bootHdd
        self._bootDev = bootDev
        self._rootDev = rootDev

    def getType(self):
        if self._efi:
            return "efi"
        else:
            return "bios"

    def isReady(self):
        if self._efi:
            assert self._bootHdd is None
            assert self._bootDev is not None
        else:
            assert self._bootHdd is not None
            assert self._bootDev is None
        assert self._rootDev is not None
        return True

    def getBootHdd(self):
        assert self.isReady()
        return self._bootHdd

    def getBootDev(self):
        assert self.isReady()
        return self._bootDev

    def getRootDev(self):
        assert self.isReady()
        return self._rootDev


class FmStorageManager:

    def __init__(self, param):
        self.param = param

        self.espPartiSize = 512 * 1024 * 1024
        self.espPartiSizeStr = "512MiB"

        self.swapSizeInGb = FmUtil.getPhysicalMemorySize() * 2
        self.swapSize = self.swapSizeInGb * 1024 * 1024 * 1024
        self.swapPartiSizeStr = "%dGiB" % (self.swapSizeInGb)

    def getStorageLayout(self):
        if self.param.runMode == "prepare":
            return FmStorageLayoutEmpty()

        rootDev = FmUtil.getMountDeviceForPath("/")
        bootDev = FmUtil.getMountDeviceForPath("/boot")

        assert rootDev is not None
        if bootDev is not None:
            try:
                lvmInfo = FmUtil.getBlkDevLvmInfo(rootDev)
                if lvmInfo is not None:
                    tlist = FmUtil.lvmGetSlaveDevPathList(lvmInfo[0])
                    if any(re.fullmatch("/dev/bcache[0-9]+", x) is not None for x in tlist):
                        ret = self._getEfiBcacheLvmLayout(bootDev)
                    else:
                        ret = self._getEfiLvmLayout(bootDev)
                else:
                    ret = self._getEfiSimpleLayout(bootDev, rootDev)
            except _FmHddLayoutError as e:
                return FmStorageLayoutNonStandard(True, None, bootDev, rootDev, e.layoutName, e.message)
        else:
            try:
                if FmUtil.getBlkDevLvmInfo(rootDev) is not None:
                    ret = self._getBiosLvmLayout()
                else:
                    ret = self._getBiosSimpleLayout(rootDev)
            except _FmHddLayoutError as e:
                if e.layoutName == FmStorageLayoutBiosLvm.name:
                    # get harddisk for lvm volume group
                    diskSet = set()
                    lvmInfo = FmUtil.getBlkDevLvmInfo(rootDev)
                    for slaveDev in FmUtil.lvmGetSlaveDevPathList(lvmInfo[0]):
                        if FmUtil.devPathIsDiskOrPartition(slaveDev):
                            diskSet.add(slaveDev)
                        else:
                            diskSet.add(FmUtil.devPathPartitionToDisk(slaveDev))

                    # check which disk has Boot Code
                    # return the first disk if no disk has Boot Code
                    bootHdd = None
                    for d in sorted(list(diskSet)):
                        with open(d, "rb") as f:
                            if not FmUtil.isBufferAllZero(f.read(440)):
                                bootHdd = d
                                break
                    if bootHdd is None:
                        bootHdd = sorted(list(diskSet))[0]
                elif e.layoutName == FmStorageLayoutBiosSimple.name:
                    bootHdd = FmUtil.devPathPartitionToDisk(rootDev)
                else:
                    assert False
                return FmStorageLayoutNonStandard(False, bootHdd, None, rootDev, e.layoutName, e.message)

        assert ret.isReady()
        return ret

    def addHdd(self, layout, devpath, bMainBoot, bWithBadBlock):
        # Returns True if there's a new boot device, or False if boot device is not changed
        # "layout" parameter is updated after this function returns

        if isinstance(layout, FmStorageLayoutEmpty):
            raise Exception("empty storage layout does not support this operation")

        if isinstance(layout, FmStorageLayoutBiosSimple):
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))

        if isinstance(layout, FmStorageLayoutBiosLvm):
            if bMainBoot:
                raise Exception("storage layout \"%s\" does not support --mainboot parameter" % (layout.name))
            else:
                return self._addHddBiosLvm(layout, devpath)

        if isinstance(layout, FmStorageLayoutEfiSimple):
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))

        if isinstance(layout, FmStorageLayoutEfiLvm):
            if bMainBoot:
                raise Exception("storage layout \"%s\" does not support --mainboot parameter" % (layout.name))
            else:
                return self._addHddEfiLvm(layout, devpath)

        if isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            if bMainBoot:
                return self._addSsdEfiBcacheLvm(layout, devpath)
            else:
                return self._addHddEfiBcacheLvm(layout, devpath)

        if isinstance(layout, FmStorageLayoutNonStandard):
            raise Exception("non-standard storage layout does not support this operation")

        assert False

    def releaseHdd(self, layout, devpath):
        if isinstance(layout, FmStorageLayoutEmpty):
            raise Exception("empty storage layout does not support this operation")

        if isinstance(layout, FmStorageLayoutBiosSimple):
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))

        if isinstance(layout, FmStorageLayoutBiosLvm):
            if devpath not in layout.lvmPvHddList:
                raise Exception("the specified device is not managed")
            parti = FmUtil.devPathDiskToPartition(devpath, 1)
            rc, out = FmUtil.cmdCallWithRetCode("/sbin/lvm", "pvmove", parti)
            if rc != 5:
                raise Exception("failed")
            return

        if isinstance(layout, FmStorageLayoutEfiSimple):
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))

        if isinstance(layout, FmStorageLayoutEfiLvm):
            if devpath not in layout.lvmPvHddList:
                raise Exception("the specified device is not managed")
            parti = FmUtil.devPathDiskToPartition(devpath, 2)
            rc, out = FmUtil.cmdCallWithRetCode("/sbin/lvm", "pvmove", parti)
            if rc != 5:
                raise Exception("failed")
            return

        if isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            if layout.ssd is not None and layout.ssd == devpath:
                return
            if devpath not in layout.lvmPvHddDict:
                raise Exception("the specified device is not managed")
            parti = FmUtil.devPathDiskToPartition(devpath, 2)
            bcacheDev = FmUtil.bcacheFindByBackingDevice(parti)
            rc, out = FmUtil.cmdCallWithRetCode("/sbin/lvm", "pvmove", bcacheDev)
            if rc != 5:
                raise Exception("failed")
            return

        if isinstance(layout, FmStorageLayoutNonStandard):
            raise Exception("non-standard storage layout does not support this operation")

        assert False

    def removeHdd(self, layout, devpath):
        # Returns True if there's a new boot device, or False if boot device is not changed
        # "layout" parameter is updated after this function returns

        if isinstance(layout, FmStorageLayoutEmpty):
            raise Exception("empty storage layout does not support this operation")

        if isinstance(layout, FmStorageLayoutBiosSimple):
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))

        if isinstance(layout, FmStorageLayoutBiosLvm):
            return self._removeHddBiosLvm(layout, devpath)

        if isinstance(layout, FmStorageLayoutEfiSimple):
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))

        if isinstance(layout, FmStorageLayoutEfiLvm):
            return self._removeHddEfiLvm(layout, devpath)

        if isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            if devpath == layout.ssd:
                return self._removeSsdEfiBcacheLvm(layout)
            else:
                return self._removeHddEfiBcacheLvm(layout, devpath)

        if isinstance(layout, FmStorageLayoutNonStandard):
            raise Exception("non-standard storage layout does not support this operation")

        assert False

    def needSyncBootPartition(self, layout):
        if isinstance(layout, FmStorageLayoutEmpty):
            return False

        if isinstance(layout, FmStorageLayoutBiosSimple) or isinstance(layout, FmStorageLayoutBiosLvm) or isinstance(layout, FmStorageLayoutEfiSimple):
            return False

        if isinstance(layout, FmStorageLayoutEfiLvm):
            if len(layout.lvmPvHddList) > 1:
                return True
            return False

        if isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            if layout.ssd is not None:
                return True
            if len(layout.lvmPvHddDict) > 1:
                return True
            return False

        if isinstance(layout, FmStorageLayoutNonStandard):
            return False

        assert False

    def syncBootPartition(self, layout):
        if isinstance(layout, FmStorageLayoutEmpty):
            assert False

        if isinstance(layout, FmStorageLayoutBiosSimple) or isinstance(layout, FmStorageLayoutBiosLvm) or isinstance(layout, FmStorageLayoutEfiSimple):
            assert False

        if isinstance(layout, FmStorageLayoutEfiLvm):
            src = FmUtil.devPathDiskToPartition(layout.bootHdd, 1)
            for hdd in layout.lvmPvHddList:
                if hdd != layout.bootHdd:
                    dst = FmUtil.devPathDiskToPartition(hdd, 1)
                    print("        - %s to %s..." % (src, dst))
                    FmUtil.syncBlkDev(src, dst, mountPoint1=FmConst.bootDir)
            return

        if isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            if layout.ssd is not None:
                src = layout.ssdEspParti
            else:
                src = FmUtil.devPathDiskToPartition(layout.bootHdd, 1)
            for hdd in layout.lvmPvHddDict:
                if layout.bootHdd is None or hdd != layout.bootHdd:
                    dst = FmUtil.devPathDiskToPartition(hdd, 1)
                    print("        - %s to %s..." % (src, dst))
                    FmUtil.syncBlkDev(src, dst, mountPoint1=FmConst.bootDir)
            return

        if isinstance(layout, FmStorageLayoutNonStandard):
            assert False

        assert False

    def adjustStorage(self, layout):
        if isinstance(layout, FmStorageLayoutEmpty):
            raise Exception("empty storage layout does not support this operation")

        if isinstance(layout, FmStorageLayoutBiosSimple):
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))

        if isinstance(layout, FmStorageLayoutBiosLvm) or isinstance(layout, FmStorageLayoutEfiLvm) or isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            total, used = FmUtil.getBlkDevCapacity(layout.getRootDev())
            if used / total < 0.9:
                raise Exception("root device space usage is less than 90%, adjustment is not needed")
            added = int(used / 0.7) - total
            added = (added // 1024 + 1) * 1024      # change unit from MB to GB
            FmUtil.cmdCall("/sbin/lvm", "lvextend", "-L+%dG" % (added), layout.getRootDev())
            FmUtil.cmdExec("/sbin/resize2fs", layout.getRootDev())
            return

        if isinstance(layout, FmStorageLayoutEfiSimple):
            raise Exception("storage layout \"%s\" does not support this operation" % (layout.name))

        if isinstance(layout, FmStorageLayoutNonStandard):
            raise Exception("non-standard storage layout does not support this operation")

        assert False

    def enableSwap(self, layout):
        if isinstance(layout, FmStorageLayoutEmpty):
            raise Exception("empty storage layout does not support this operation")

        if isinstance(layout, (FmStorageLayoutBiosSimple, FmStorageLayoutEfiSimple)):
            if layout.swapFile is None:
                self._createSwapFile(_swapFilename)
                layout.swapFile = _swapFilename
            serviceName = FmUtil.path2SwapServiceName(layout.swapFile)
            if os.path.getsize(layout.swapFile) < self.swapSize:
                self._disableSwapService(layout.swapFile, serviceName)
                self._createSwapFile(layout.swapFile)
            self._createSwapService(layout.swapFile, serviceName)
            self._enableSwapService(layout.swapFile, serviceName)
            return

        if isinstance(layout, (FmStorageLayoutBiosLvm, FmStorageLayoutEfiLvm)):
            if layout.lvmSwapLv is None:
                FmUtil.cmdCall("/sbin/lvm", "lvcreate", "-L", self.swapPartiSizeStr, "-n", "swap", "hdd")
                layout.lvmSwapLv = "swap"
            serviceName = FmUtil.path2SwapServiceName(layout.lvmSwapLv)
            if FmUtil.getBlkDevSize("/dev/mapper/hdd.swap") < self.swapSize:
                self._disableSwapService(layout.lvmSwapLv, serviceName)
                FmUtil.cmdCall("/sbin/lvm", "lvremove", "/dev/mapper/hdd.swap")
                FmUtil.cmdCall("/sbin/lvm", "lvcreate", "-L", self.swapPartiSizeStr, "-n", "swap", "hdd")
            self._createSwapService(layout.lvmSwapLv, serviceName)
            self._enableSwapService(layout.lvmSwapLv, serviceName)
            return

        if isinstance(layout, (FmStorageLayoutEfiBcacheLvm)):
            if FmUtil.getBlkDevSize(layout.ssdSwapParti) < self.swapSize:
                raise Exception("swap partition is too smalls")
            serviceName = FmUtil.path2SwapServiceName(layout.ssdSwapParti)
            self._createSwapService(layout.ssdSwapParti, serviceName)
            self._enableSwapService(layout.ssdSwapParti, serviceName)
            return

        if isinstance(layout, FmStorageLayoutNonStandard):
            raise Exception("non-standard storage layout does not support this operation")

        assert False

    def disableSwap(self, layout):
        if isinstance(layout, FmStorageLayoutEmpty):
            raise Exception("empty storage layout does not support this operation")

        if isinstance(layout, (FmStorageLayoutBiosSimple, FmStorageLayoutEfiSimple)):
            if layout.swapFile is not None:
                serviceName = FmUtil.path2SwapServiceName(layout.swapFile)
                self._disableSwapService(layout.swapFile, serviceName)
                self._removeSwapService(layout.swapFile, serviceName)
                os.unlink(layout.swapFile)
                layout.swapFile = None
            return

        if isinstance(layout, (FmStorageLayoutBiosLvm, FmStorageLayoutEfiLvm)):
            if layout.lvmSwapLv is not None:
                serviceName = FmUtil.path2SwapServiceName(layout.lvmSwapLv)
                self._disableSwapService(layout.lvmSwapLv, serviceName)
                self._removeSwapService(layout.lvmSwapLv, serviceName)
                FmUtil.cmdCall("/sbin/lvm", "lvremove", "/dev/mapper/hdd.swap")
                layout.lvmSwapLv = None
            return

        if isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            serviceName = FmUtil.path2SwapServiceName(layout.ssdSwapParti)
            self._disableSwapService(layout.ssdSwapParti, serviceName)
            self._removeSwapService(layout.ssdSwapParti, serviceName)
            return

        if isinstance(layout, FmStorageLayoutNonStandard):
            raise Exception("non-standard storage layout does not support this operation")

        assert False

    def _getEfiSimpleLayout(self, bootDev, rootDev):
        if not FmUtil.gptIsEspPartition(bootDev):
            raise _FmHddLayoutError(FmStorageLayoutEfiSimple, "boot device is not ESP partitiion")

        ret = FmStorageLayoutEfiSimple()

        # ret.hdd
        ret.hdd = FmUtil.devPathPartitionToDisk(bootDev)
        if ret.hdd != FmUtil.devPathPartitionToDisk(rootDev):
            raise _FmHddLayoutError(FmStorageLayoutEfiSimple, "boot device and root device is not the same")

        # ret.hddEspParti
        ret.hddEspParti = bootDev

        # ret.hddRootParti
        ret.hddRootParti = rootDev
        if True:
            fs = FmUtil.getBlkDevFsType(ret.hddRootParti)
            if fs != "ext4":
                raise _FmHddLayoutError(FmStorageLayoutEfiSimple, "root partition file system is \"%s\", not \"ext4\"" % (fs))

        # ret.swapFile
        if os.path.exists(_swapFilename) and FmUtil.cmdCallTestSuccess("/sbin/swaplabel", _swapFilename):
            ret.swapFile = _swapFilename

        return ret

    def _getEfiLvmLayout(self, bootDev):
        if not FmUtil.gptIsEspPartition(bootDev):
            raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "boot device is not ESP partitiion")

        ret = FmStorageLayoutEfiLvm()

        # ret.bootHdd
        ret.bootHdd = FmUtil.devPathPartitionToDisk(bootDev)

        # ret.lvmVg
        if not FmUtil.cmdCallTestSuccess("/sbin/lvm", "vgdisplay", "hdd"):
            raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "volume group \"hdd\" does not exist")
        ret.lvmVg = "hdd"

        # ret.lvmPvHddList
        out = FmUtil.cmdCall("/sbin/lvm", "pvdisplay", "-c")
        for m in re.finditer("(/dev/\\S+):hdd:.*", out, re.M):
            hdd, partId = FmUtil.devPathPartitionToDiskAndPartitionId(m.group(1))
            if FmUtil.getBlkDevPartitionTableType(hdd) != "gpt":
                raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "partition type of %s is not \"gpt\"" % (hdd))
            if partId != 2:
                raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "physical volume partition of %s is not %s" % (hdd, FmUtil.devPathDiskToPartition(hdd, 2)))
            if FmUtil.getBlkDevSize(FmUtil.devPathDiskToPartition(hdd, 1)) != self.espPartiSize:
                raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "%s has an invalid size" % (FmUtil.devPathDiskToPartition(hdd, 1)))
            if os.path.exists(FmUtil.devPathDiskToPartition(hdd, 3)):
                raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "redundant partition exists on %s" % (hdd))
            ret.lvmPvHddList.append(hdd)

        out = FmUtil.cmdCall("/sbin/lvm", "lvdisplay", "-c")
        if True:
            # ret.lvmRootLv
            if re.search("/dev/hdd/root:hdd:.*", out, re.M) is not None:
                ret.lvmRootLv = "root"
                if os.path.exists("/dev/mapper/hdd.root"):
                    fs = FmUtil.getBlkDevFsType("/dev/mapper/hdd.root")
                elif os.path.exists("/dev/mapper/hdd-root"):                # compatible with old lvm version
                    fs = FmUtil.getBlkDevFsType("/dev/mapper/hdd-root")
                else:
                    assert False
                if fs != "ext4":
                    raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "root partition file system is \"%s\", not \"ext4\"" % (fs))
            else:
                raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "logical volume \"/dev/mapper/hdd.root\" does not exist")

            # ret.lvmSwapLv
            if re.search("/dev/hdd/swap:hdd:.*", out, re.M) is not None:
                ret.lvmSwapLv = "swap"
                if os.path.exists("/dev/mapper/hdd.swap"):
                    if FmUtil.getBlkDevFsType("/dev/mapper/hdd.swap") != "swap":
                        raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "/dev/mapper/hdd.swap has an invalid file system")
                elif os.path.exists("/dev/mapper/hdd-swap"):                    # compatible with old lvm version
                    if FmUtil.getBlkDevFsType("/dev/mapper/hdd-swap") != "swap":
                        raise _FmHddLayoutError(FmStorageLayoutEfiLvm, "/dev/mapper/hdd.swap has an invalid file system")
                else:
                    assert False
        return ret

    def _getEfiBcacheLvmLayout(self, bootDev):
        if not FmUtil.gptIsEspPartition(bootDev):
            raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "boot device is not ESP partitiion")

        ret = FmStorageLayoutEfiBcacheLvm()

        # ret.lvmVg
        if not FmUtil.cmdCallTestSuccess("/sbin/lvm", "vgdisplay", "hdd"):
            raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "volume group \"hdd\" does not exist")
        ret.lvmVg = "hdd"

        # ret.lvmPvHddDict
        out = FmUtil.cmdCall("/sbin/lvm", "pvdisplay", "-c")
        for m in re.finditer("(/dev/\\S+):hdd:.*", out, re.M):
            if re.fullmatch("/dev/bcache[0-9]+", m.group(1)) is None:
                raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "volume group \"hdd\" has non-bcache physical volume")
            bcacheDev = m.group(1)
            tlist = FmUtil.bcacheGetSlaveDevPathList(bcacheDev)
            hddDev, partId = FmUtil.devPathPartitionToDiskAndPartitionId(tlist[-1])
            if partId != 2:
                raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "physical volume partition of %s is not %s" % (hddDev, FmUtil.devPathDiskToPartition(hddDev, 2)))
            if os.path.exists(FmUtil.devPathDiskToPartition(hddDev, 3)):
                raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "redundant partition exists on %s" % (hddDev))
            ret.lvmPvHddDict[hddDev] = bcacheDev

        # ret.lvmRootLv
        out = FmUtil.cmdCall("/sbin/lvm", "lvdisplay", "-c")
        if re.search("/dev/hdd/root:hdd:.*", out, re.M) is not None:
            ret.lvmRootLv = "root"
            if os.path.exists("/dev/mapper/hdd.root"):
                fs = FmUtil.getBlkDevFsType("/dev/mapper/hdd.root")
            elif os.path.exists("/dev/mapper/hdd-root"):                    # compatible with old lvm version
                fs = FmUtil.getBlkDevFsType("/dev/mapper/hdd-root")
            else:
                assert False
            if fs != "ext4":
                raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "root partition file system is \"%s\", not \"ext4\"" % (fs))
        else:
            raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "logical volume \"/dev/mapper/hdd.root\" does not exist")

        # ret.ssd
        ret.ssd = FmUtil.devPathPartitionToDisk(bootDev)
        if ret.ssd not in ret.lvmPvHddDict:
            # ret.ssdEspParti
            ret.ssdEspParti = FmUtil.devPathDiskToPartition(ret.ssd, 1)
            if ret.ssdEspParti != bootDev:
                raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "SSD is not boot device")
            if FmUtil.getBlkDevSize(ret.ssdEspParti) != self.espPartiSize:
                raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "%s has an invalid size" % (ret.ssdEspParti))

            # ret.ssdSwapParti
            ret.ssdSwapParti = FmUtil.devPathDiskToPartition(ret.ssd, 2)
            if not os.path.exists(ret.ssdSwapParti):
                raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "SSD has no swap partition")
            if FmUtil.getBlkDevFsType(ret.ssdSwapParti) != "swap":
                raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "swap device %s has an invalid file system" % (ret.ssdSwapParti))

            # ret.ssdCacheParti
            ret.ssdCacheParti = FmUtil.devPathDiskToPartition(ret.ssd, 3)
            if not os.path.exists(ret.ssdCacheParti):
                raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "SSD has no cache partition")

            for pvHdd, bcacheDev in ret.lvmPvHddDict.items():
                tlist = FmUtil.bcacheGetSlaveDevPathList(bcacheDev)
                if len(tlist) < 2:
                    raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "%s(%s) has no cache device" % (pvHdd, bcacheDev))
                if len(tlist) > 2:
                    raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "%s(%s) has multiple cache devices" % (pvHdd, bcacheDev))
                if tlist[0] != ret.ssdCacheParti:
                    raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "%s(%s) has invalid cache device" % (pvHdd, bcacheDev))
            if True:
                partName, partId = FmUtil.devPathPartitionToDiskAndPartitionId(ret.ssdCacheParti)
                nextPartName = FmUtil.devPathDiskToPartition(partName, partId + 1)
                if os.path.exists(nextPartName):
                    raise _FmHddLayoutError(FmStorageLayoutEfiBcacheLvm, "redundant partition exists on %s" % (ret.ssd))
        else:
            ret.ssd = None

        # ret.bootHdd
        if ret.ssd is None:
            ret.bootHdd = FmUtil.devPathPartitionToDisk(bootDev)

        return ret

    def _getBiosSimpleLayout(self, rootDev):
        ret = FmStorageLayoutBiosSimple()

        # ret.hdd
        ret.hdd = FmUtil.devPathPartitionToDisk(rootDev)
        if FmUtil.getBlkDevPartitionTableType(ret.hdd) != "dos":
            raise _FmHddLayoutError(FmStorageLayoutBiosSimple, "partition type of %s is not \"dos\"" % (ret.hdd))

        # ret.hddRootParti
        ret.hddRootParti = rootDev
        fs = FmUtil.getBlkDevFsType(ret.hddRootParti)
        if fs != "ext4":
            raise _FmHddLayoutError(FmStorageLayoutBiosSimple, "root partition file system is \"%s\", not \"ext4\"" % (fs))

        # ret.swapFile
        if os.path.exists(_swapFilename) and FmUtil.cmdCallTestSuccess("/sbin/swaplabel", _swapFilename):
            ret.swapFile = _swapFilename

        return ret

    def _getBiosLvmLayout(self):
        ret = FmStorageLayoutBiosLvm()

        # ret.lvmVg
        if not FmUtil.cmdCallTestSuccess("/sbin/lvm", "vgdisplay", "hdd"):
            raise _FmHddLayoutError(FmStorageLayoutBiosLvm, "volume group \"hdd\" does not exist")
        ret.lvmVg = "hdd"

        # ret.lvmPvHddList
        out = FmUtil.cmdCall("/sbin/lvm", "pvdisplay", "-c")
        for m in re.finditer("(/dev/\\S+):hdd:.*", out, re.M):
            hdd = FmUtil.devPathPartitionToDisk(m.group(1))
            if FmUtil.getBlkDevPartitionTableType(hdd) != "dos":
                raise _FmHddLayoutError(FmStorageLayoutBiosLvm, "partition type of %s is not \"dos\"" % (hdd))
            if os.path.exists(FmUtil.devPathDiskToPartition(hdd, 2)):
                raise _FmHddLayoutError(FmStorageLayoutBiosLvm, "redundant partition exists on %s" % (hdd))
            ret.lvmPvHddList.append(hdd)

        out = FmUtil.cmdCall("/sbin/lvm", "lvdisplay", "-c")
        if True:
            # ret.lvmRootLv
            if re.search("/dev/hdd/root:hdd:.*", out, re.M) is not None:
                ret.lvmRootLv = "root"
                if os.path.exists("/dev/mapper/hdd.root"):
                    fs = FmUtil.getBlkDevFsType("/dev/mapper/hdd.root")
                elif os.path.exists("/dev/mapper/hdd-root"):                # compatible with old lvm version
                    fs = FmUtil.getBlkDevFsType("/dev/mapper/hdd-root")
                else:
                    assert False
                if fs != "ext4":
                    raise _FmHddLayoutError(FmStorageLayoutBiosLvm, "root partition file system is \"%s\", not \"ext4\"" % (fs))
            else:
                raise _FmHddLayoutError(FmStorageLayoutBiosLvm, "logical volume \"/dev/mapper/hdd.root\" does not exist")

            # ret.lvmSwapLv
            if re.search("/dev/hdd/swap:hdd:.*", out, re.M) is not None:
                ret.lvmSwapLv = "swap"
                if os.path.exists("/dev/mapper/hdd.swap"):
                    if FmUtil.getBlkDevFsType("/dev/mapper/hdd.swap") != "swap":
                        raise _FmHddLayoutError(FmStorageLayoutBiosLvm, "/dev/mapper/hdd.swap has an invalid file system")
                elif os.path.exists("/dev/mapper/hdd-swap"):                # compatible with old lvm version
                    if FmUtil.getBlkDevFsType("/dev/mapper/hdd-swap") != "swap":
                        raise _FmHddLayoutError(FmStorageLayoutBiosLvm, "/dev/mapper/hdd.swap has an invalid file system")
                else:
                    assert False

        # ret.bootHdd
        for hdd in ret.lvmPvHddList:
            with open(hdd, "rb") as f:
                if not FmUtil.isBufferAllZero(f.read(440)):
                    if ret.bootHdd is not None:
                        raise _FmHddLayoutError(FmStorageLayoutBiosLvm, "boot-code exists on multiple harddisks")
                    ret.bootHdd = hdd
        if ret.bootHdd is None:
            raise _FmHddLayoutError(FmStorageLayoutBiosLvm, "no harddisk has boot-code")

        return ret

    def _addHddBiosLvm(self, layout, devpath):
        if devpath in layout.lvmPvHddList:
            raise Exception("the specified device is already managed")
        if devpath not in FmUtil.getDevPathListForFixedHdd():
            raise Exception("the specified device is not a fixed harddisk")

        assert False

    def _removeHddBiosLvm(self, layout, devpath):
        assert devpath in layout.lvmPvHddList

        if len(layout.lvmPvHddList) <= 1:
            raise Exception("can not remove the last physical volume")

        # change boot device if needed
        ret = False
        if layout.bootHdd == devpath:
            layout.lvmPvHddList.remove(devpath)
            layout.bootHdd = layout.lvmPvHddList[0]
            # FIXME: add Boot Code for layout.bootHdd?
            ret = True

        # remove harddisk
        parti = FmUtil.devPathDiskToPartition(devpath, 1)
        FmUtil.cmdCall("/sbin/lvm", "vgreduce", layout.lvmVg, parti)
        FmUtil.wipeHarddisk(devpath)

        return ret

    def _addHddEfiLvm(self, layout, devpath):
        if devpath in layout.lvmPvHddList:
            raise Exception("the specified device is already managed")
        if devpath not in FmUtil.getDevPathListForFixedHdd():
            raise Exception("the specified device is not a fixed harddisk")

        # create partitions
        FmUtil.initializeDisk(devpath, "gpt", [
            (self.espPartiSizeStr, "vfat"),
            ("*", "lvm"),
        ])

        # fill partition1, mount boot device if needed
        parti = FmUtil.devPathDiskToPartition(devpath, 1)
        FmUtil.cmdCall("/usr/sbin/mkfs.vfat", parti)
        FmUtil.syncBlkDev(FmUtil.devPathDiskToPartition(layout.bootHdd, 1), parti, mountPoint1=FmConst.bootDir)

        # create lvm physical volume on partition2 and add it to volume group
        parti = FmUtil.devPathDiskToPartition(devpath, 2)
        FmUtil.cmdCall("/sbin/lvm", "pvcreate", parti)
        FmUtil.cmdCall("/sbin/lvm", "vgextend", layout.lvmVg, parti)
        layout.lvmPvHddList.append(devpath)

        return False

    def _removeHddEfiLvm(self, layout, devpath):
        assert devpath in layout.lvmPvHddList

        if len(layout.lvmPvHddList) <= 1:
            raise Exception("can not remove the last physical volume")

        # change boot device if needed
        ret = False
        if layout.bootHdd == devpath:
            FmUtil.cmdCall("/bin/umount", FmConst.bootDir)
            layout.lvmPvHddList.remove(devpath)
            layout.bootHdd = layout.lvmPvHddList[0]
            FmUtil.gptToggleEspPartition(FmUtil.devPathDiskToPartition(layout.bootHdd, 1), True)
            FmUtil.cmdCall("/bin/mount", FmUtil.devPathDiskToPartition(layout.bootHdd, 1), FmConst.bootDir, "-o", "ro")
            ret = True

        # remove harddisk
        parti = FmUtil.devPathDiskToPartition(devpath, 2)
        FmUtil.cmdCall("/sbin/lvm", "vgreduce", layout.lvmVg, parti)
        FmUtil.wipeHarddisk(devpath)

        return ret

    def _addSsdEfiBcacheLvm(self, layout, devpath):
        if layout.ssd is not None:
            raise Exception("mainboot device already exists")
        if devpath in layout.lvmPvHddDict:
            raise Exception("the specified device is already managed")
        if devpath not in FmUtil.getDevPathListForFixedHdd() or not FmUtil.isBlkDevSsdOrHdd(devpath):
            raise Exception("the specified device is not a fixed SSD harddisk")

        # create partitions
        FmUtil.initializeDisk(devpath, "gpt", [
            (self.espPartiSizeStr, "esp"),
            (self.swapPartiSizeStr, "swap"),
            ("*", "bcache"),
        ])
        layout.ssd = devpath

        # sync partition1 as boot partition
        parti = FmUtil.devPathDiskToPartition(devpath, 1)
        FmUtil.cmdCall("/usr/sbin/mkfs.vfat", parti)
        FmUtil.syncBlkDev(FmUtil.devPathDiskToPartition(layout.bootHdd, 1), parti, mountPoint1=FmConst.bootDir)
        layout.ssdEspParti = parti

        # make partition2 as swap partition
        parti = FmUtil.devPathDiskToPartition(devpath, 2)
        FmUtil.cmdCall("/sbin/mkswap", parti)
        layout.ssdSwapParti = parti

        # make partition3 as cache partition
        parti = FmUtil.devPathDiskToPartition(devpath, 3)
        FmUtil.bcacheMakeDevice(parti, False)
        layout.ssdCacheParti = parti

        # enable cache partition
        with open("/sys/fs/bcache/register", "w") as f:
            f.write(parti)
        setUuid = FmUtil.bcacheGetSetUuid(layout.ssdCacheParti)
        for bcacheDev in layout.lvmPvHddDict.values():
            with open("/sys/block/%s/bcache/attach" % (os.path.basename(bcacheDev)), "w") as f:
                f.write(str(setUuid))

        # change boot device
        FmUtil.cmdCall("/bin/umount", FmConst.bootDir)
        FmUtil.gptToggleEspPartition(FmUtil.devPathDiskToPartition(layout.bootHdd, 1), False)
        FmUtil.cmdCall("/bin/mount", layout.ssdEspParti, FmConst.bootDir, "-o", "ro")
        layout.bootHdd = None

        return True

    def _addHddEfiBcacheLvm(self, layout, devpath):
        if devpath == layout.ssd or devpath in layout.lvmPvHddDict:
            raise Exception("the specified device is already managed")
        if devpath not in FmUtil.getDevPathListForFixedHdd():
            raise Exception("the specified device is not a fixed harddisk")

        if FmUtil.isBlkDevSsdOrHdd(devpath):
            print("WARNING: \"%s\" is an SSD harddisk, perhaps you want to add it as mainboot device?" % (devpath))

        # create partitions
        FmUtil.initializeDisk(devpath, "gpt", [
            (self.espPartiSizeStr, "vfat"),
            ("*", "bcache"),
        ])

        # fill partition1
        parti = FmUtil.devPathDiskToPartition(devpath, 1)
        FmUtil.cmdCall("/usr/sbin/mkfs.vfat", parti)
        if layout.ssd is not None:
            FmUtil.syncBlkDev(layout.ssdEspParti, parti, mountPoint1=FmConst.bootDir)
        else:
            FmUtil.syncBlkDev(FmUtil.devPathDiskToPartition(layout.bootHdd, 1), parti, mountPoint1=FmConst.bootDir)

        # add partition2 to bcache
        parti = FmUtil.devPathDiskToPartition(devpath, 2)
        FmUtil.bcacheMakeDevice(parti, True)
        with open("/sys/fs/bcache/register", "w") as f:
            f.write(parti)
        bcacheDev = FmUtil.bcacheFindByBackingDevice(parti)
        if layout.ssd is not None:
            setUuid = FmUtil.bcacheGetSetUuid(layout.ssdCacheParti)
            with open("/sys/block/%s/bcache/attach" % os.path.basename(bcacheDev), "w") as f:
                f.write(str(setUuid))

        # create lvm physical volume on bcache device and add it to volume group
        FmUtil.cmdCall("/sbin/lvm", "pvcreate", bcacheDev)
        FmUtil.cmdCall("/sbin/lvm", "vgextend", layout.lvmVg, bcacheDev)
        layout.lvmPvHddDict[devpath] = bcacheDev

        return False

    def _removeSsdEfiBcacheLvm(self, layout):
        assert layout.ssd is not None
        assert len(layout.lvmPvHddDict) > 0

        # check
        if FmUtil.systemdFindSwapService(layout.ssdSwapParti) is not None:
            raise Exception("swap partition is in use, please use \"sysman disable-swap\" first")

        # remove cache partition
        setUuid = FmUtil.bcacheGetSetUuid(layout.ssdCacheParti)
        with open("/sys/fs/bcache/%s/unregister" % (setUuid), "w") as f:
            f.write(layout.ssdCacheParti)
        layout.ssdCacheParti = None

        # remove swap partition
        layout.ssdSwapParti = None

        # change boot device
        FmUtil.cmdCall("/bin/umount", FmConst.bootDir)
        layout.bootHdd = list(layout.lvmPvHddDict.keys())[0]
        FmUtil.gptToggleEspPartition(FmUtil.devPathDiskToPartition(layout.bootHdd, 1), True)
        FmUtil.cmdCall("/bin/mount", FmUtil.devPathDiskToPartition(layout.bootHdd, 1), FmConst.bootDir, "-o", "ro")
        layout.ssdEspParti = None

        # wipe disk
        FmUtil.wipeHarddisk(layout.ssd)
        layout.ssd = None

        return True

    def _removeHddEfiBcacheLvm(self, layout, devpath):
        assert devpath in layout.lvmPvHddDict

        if len(layout.lvmPvHddDict) <= 1:
            raise Exception("can not remove the last physical volume")

        # change boot device if needed
        ret = False
        if layout.bootHdd is not None and layout.bootHdd == devpath:
            FmUtil.cmdCall("/bin/umount", FmConst.bootDir)
            del layout.lvmPvHddDict[devpath]
            layout.bootHdd = list(layout.lvmPvHddDict.keys())[0]
            FmUtil.gptToggleEspPartition(FmUtil.devPathDiskToPartition(layout.bootHdd, 1), True)
            FmUtil.cmdCall("/bin/mount", FmUtil.devPathDiskToPartition(layout.bootHdd, 1), FmConst.bootDir, "-o", "ro")
            ret = True

        # remove harddisk
        bcacheDev = FmUtil.bcacheFindByBackingDevice(FmUtil.devPathDiskToPartition(devpath, 2))
        FmUtil.cmdCall("/sbin/lvm", "vgreduce", layout.lvmVg, bcacheDev)
        with open("/sys/block/%s/bcache/stop" % (os.path.basename(bcacheDev)), "w") as f:
            f.write("1")
        FmUtil.wipeHarddisk(devpath)

        return ret

    def _createSwapFile(self, path):
        FmUtil.cmdCall("/bin/dd", "if=/dev/zero", "of=%s" % (path), "bs=%d" % (1024 * 1024 * 1024), "count=%d" % (self.swapSizeInGb))
        FmUtil.cmdCall("/sbin/mkswap", "-f", path)
        FmUtil.cmdCall("/bin/chmod", "600", path)

    def _createSwapService(self, path, serviceName):
        fullf = os.path.join("/etc/systemd/system", serviceName)
        fileContent = self._genSwapServFile(path)

        if os.path.exists(fullf):
            with open(fullf, "r") as f:
                if f.read() == fileContent:
                    return

        with open(fullf, "w") as f:
            f.write(fileContent)

    def _removeSwapService(self, path, serviceName):
        os.unlink(os.path.join("/etc/systemd/system", serviceName))

    def _enableSwapService(self, path, serviceName):
        FmUtil.cmdCall("/bin/systemctl", "enable", serviceName)
        if self.param.runMode == "prepare":
            assert False
        elif self.param.runMode == "setup":
            FmUtil.cmdCall("/sbin/swapon", path)
        elif self.param.runMode == "normal":
            FmUtil.cmdCall("/bin/systemctl", "start", serviceName)
        else:
            assert False

    def _disableSwapService(self, path, serviceName):
        if self.param.runMode == "prepare":
            assert False
        elif self.param.runMode == "setup":
            FmUtil.cmdCall("/sbin/swapoff", path)
        elif self.param.runMode == "normal":
            FmUtil.cmdCall("/bin/systemctl", "stop", serviceName)
        else:
            assert False
        FmUtil.cmdCall("/bin/systemctl", "disable", serviceName)

    def _genSwapServFile(self, swapfile):
        buf = ""
        buf += "[Unit]\n"
        if swapfile.startswith("/dev"):
            buf += "Description=Swap Partition\n"
        else:
            buf += "Description=Swap File\n"
        buf += "\n"
        buf += "[Swap]\n"
        buf += "What=%s\n" % (swapfile)
        buf += "\n"
        buf += "[Install]\n"
        buf += "WantedBy=swap.target\n"
        return buf


class _FmHddLayoutError(Exception):

    def __init__(self, layoutClass, message):
        self.layoutName = layoutClass.name
        self.message = message


_swapFilename = "/var/swap.dat"
