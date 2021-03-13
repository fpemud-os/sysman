#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import time
import json
import stat
import uuid
import glob
import crcmod
import parted
import struct
import argparse
import subprocess


class Main:

    def main(self):
        if os.getuid() != 0:
            print("You must run this command as root!")
            sys.exit(1)

        args = self._getArgParser().parse_args()
        if args.op == "show":
            StorageManager().showLayout()
        elif args.op == "create":
            if args.layout_name == "bios-simple":
                StorageManager().createLayoutBiosSimple()
            elif args.layout_name == "bios-lvm":
                StorageManager().createLayoutBiosLvm()
            elif args.layout_name == "efi-simple":
                StorageManager().createLayoutEfiSimple()
            elif args.layout_name == "efi-lvm":
                StorageManager().createLayoutEfiLvm()
            elif args.layout_name == "efi-bache-lvm":
                StorageManager().createLayoutEfiBcacheLvm()
            else:
                print("Invalid storage layout!")
                sys.exit(1)
        elif args.op == "wipe":
            StorageManager().wipeHarddisk(args.harddisk)
        elif args.op == "wipe-all":
            StorageManager().wipeAllDisks()
        elif args.op == "to-json":
            StorageManager().showLayout(to_json=True)
        else:
            assert False

    def _getArgParser(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        parser2 = subparsers.add_parser("show", help="Show target storage information")
        parser2.set_defaults(op="show")

        parser2 = subparsers.add_parser("create-layout", help="Create new target storage layout")
        parser2.set_defaults(op="create")
        parser2.add_argument("layout_name", metavar="layout-name")

        parser2 = subparsers.add_parser("wipe-harddisk", help="Wipe the specified harddisk")
        parser2.set_defaults(op="wipe")
        parser2.add_argument("harddisk")

        parser2 = subparsers.add_parser("wipe-all-harddisks", help="Wipe all the harddisks of target storage")
        parser2.set_defaults(op="wipe-all")

        parser2 = subparsers.add_parser("_to_json", help="Hidden argument, output storage information as json string")
        parser2.set_defaults(op="to-json")

        return parser


# see corresponding class in project "fpemud-refsystem"
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


# see corresponding class in project "fpemud-refsystem"
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
        assert self.swapFile is None or self.swapFile == "/var/swap.dat"
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


# see corresponding class in project "fpemud-refsystem"
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


# see corresponding class in project "fpemud-refsystem"
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
        assert self.hddEspParti == _Util.devPathDiskToPartition(self.hdd, 1)
        assert self.hddRootParti == _Util.devPathDiskToPartition(self.hdd, 2)
        assert self.swapFile is None or self.swapFile == "/var/swap.dat"
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


# see corresponding class in project "fpemud-refsystem"
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
        return _Util.devPathDiskToPartition(self.bootHdd, 1)

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


# see corresponding class in project "fpemud-refsystem"
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
            assert self.ssdEspParti == _Util.devPathDiskToPartition(self.ssd, 1)
            assert self.ssdSwapParti == _Util.devPathDiskToPartition(self.ssd, 2)
            assert self.ssdCacheParti == _Util.devPathDiskToPartition(self.ssd, 3)
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
            return _Util.devPathDiskToPartition(self.bootHdd, 1)

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


class StorageManager:

    def __init__(self):
        self.espPartiSize = 512 * 1024 * 1024
        self.espPartiSizeStr = "512MiB"

        self.swapSizeInGb = _Util.getPhysicalMemorySize() * 2
        self.swapSize = self.swapSizeInGb * 1024 * 1024 * 1024
        self.swapPartiSizeStr = "%dGiB" % (self.swapSizeInGb)

    def showLayout(self, to_json=False):
        # self._getXxxLayout() return value specification:
        # 1. None:                                jump over and try the next layout
        # 2. object:                              yes we find a valid layout
        # 3. raise _GetLayoutError: we find a layout but it is invalid

        def _print_json(layout):
            print(layout.__class__.name)
            print(json.dumps(layout.__dict__))

        try:
            # empty
            layout = self._getEmptyLayout()
            if layout is not None:
                if not to_json:
                    print("Storage layout: empty")
                else:
                    _print_json(layout)
                return

            # efi-bcache-lvm
            layout = self._getEfiBcacheLvmLayout()
            if layout is not None:
                if layout.ssd is not None:
                    ssdStr = layout.ssd
                    if layout.ssdSwapParti is not None:
                        swapStr = "(with swap)"
                    else:
                        swapStr = ""
                    bootDiskStr = ""
                else:
                    ssdStr = "None"
                    swapStr = ""
                    bootDiskStr = " (boot disk: %s)" % (layout.bootHdd)
                if not to_json:
                    print("Storage layout: %s, SSD: %s%s, LVM PVs: %s%s" % (layout.name, ssdStr, swapStr, " ".join(layout.lvmPvHddDict.keys()), bootDiskStr))
                else:
                    _print_json(layout)
                return

            # efi-lvm
            layout = self._getEfiLvmLayout()
            if layout is not None:
                extraStr = " ("
                if layout.lvmSwapLv is not None:
                    extraStr += "has swap, "
                extraStr += "boot disk: %s" % (layout.bootHdd)
                extraStr += ")"
                if not to_json:
                    print("Storage layout: %s, LVM PVs: %s%s" % (layout.name, " ".join(layout.lvmPvHddList), extraStr))
                else:
                    _print_json(layout)
                return

            # efi-simple
            layout = self._getEfiSimpleLayout()
            if layout is not None:
                if layout.swapFile is not None:
                    swapStr = " (with swap)"
                else:
                    swapStr = ""
                if not to_json:
                    print("Storage layout: %s, HDD: %s%s" % (layout.name, layout.hdd, swapStr))
                else:
                    _print_json(layout)
                return

            # bios-lvm
            layout = self._getBiosLvmLayout()
            if layout is not None:
                extraStr = " ("
                if layout.lvmSwapLv is not None:
                    extraStr += "has swap, "
                extraStr += "boot disk: %s" % (layout.bootHdd)
                extraStr += ")"
                if not to_json:
                    print("Storage layout: %s, LVM PVs: %s%s" % (layout.name, " ".join(layout.lvmPvHddList), extraStr))
                else:
                    _print_json(layout)
                return

            # bios-simple
            layout = self._getBiosSimpleLayout()
            if layout is not None:
                if layout.swapFile is not None:
                    swapStr = " (with swap)"
                else:
                    swapStr = ""
                if not to_json:
                    print("Storage layout: %s, HDD: %s%s" % (layout.name, layout.hdd, swapStr))
                else:
                    _print_json(layout)
                return
        except _GetLayoutError:
            raise

    def wipeAllDisks(self):
        _Util.cmdCall("/sbin/lvm", "vgchange", "-an")
        for devpath in _Util.getDevPathListForFixedHdd():
            print("Wipe harddisk %s" % (devpath))
            _Util.wipeHarddisk(devpath)

    def createLayoutBiosSimple(self, hdd=None):
        if hdd is None:
            hddList = _Util.getDevPathListForFixedHdd()
            if len(hddList) == 0:
                raise Exception("no harddisks")
            if len(hddList) > 1:
                raise Exception("multiple harddisks")
            hdd = hddList[0]

        # create partitions
        _Util.initializeDisk(hdd, "mbr", [
            ("*", "ext4"),
        ])

        # show result
        print("Root device: %s" % (_Util.devPathDiskToPartition(hdd, 1)))
        print("Swap file: None")

    def createLayoutBiosLvm(self, hddList=None):
        if hddList is None:
            hddList = _Util.getDevPathListForFixedHdd()
            if len(hddList) == 0:
                raise Exception("no harddisks")
        else:
            assert len(hddList) > 0

        vgCreated = False

        for devpath in hddList:
            # create partitions
            _Util.initializeDisk(devpath, "mbr", [
                ("*", "lvm"),
            ])

            # create lvm physical volume on partition1 and add it to volume group
            parti = _Util.devPathDiskToPartition(devpath, 1)
            _Util.cmdCall("/sbin/lvm", "pvcreate", parti)
            if not vgCreated:
                _Util.cmdCall("/sbin/lvm", "vgcreate", "hdd", parti)
                vgCreated = True
            else:
                _Util.cmdCall("/sbin/lvm", "vgextend", "hdd", parti)

        # create root lv
        out = _Util.cmdCall("/sbin/lvm", "vgdisplay", "-c", "hdd")
        freePe = int(out.split(":")[15])
        _Util.cmdCall("/sbin/lvm", "lvcreate", "-l", "%d" % (freePe // 2), "-n", "root", "hdd")

        # show result
        print("Root device: /dev/mapper/hdd-root")
        print("Swap device: None")
        print("Boot disk: %s" % (hddList[0]))

    def createLayoutEfiSimple(self, hdd=None):
        if hdd is None:
            hddList = _Util.getDevPathListForFixedHdd()
            if len(hddList) == 0:
                raise Exception("no harddisks")
            if len(hddList) > 1:
                raise Exception("multiple harddisks")
            hdd = hddList[0]

        # create partitions
        _Util.initializeDisk(hdd, "gpt", [
            (self.espPartiSizeStr, "vfat"),
            ("*", "ext4"),
        ])

        # show result
        print("Root device: %s" % (_Util.devPathDiskToPartition(hdd, 2)))
        print("Swap file: None")

    def createLayoutEfiLvm(self, hddList=None):
        if hddList is None:
            hddList = _Util.getDevPathListForFixedHdd()
            if len(hddList) == 0:
                raise Exception("no harddisks")
        else:
            assert len(hddList) > 0

        vgCreated = False

        for devpath in hddList:
            # create partitions
            _Util.initializeDisk(devpath, "gpt", [
                (self.espPartiSizeStr, "vfat"),
                ("*", "lvm"),
            ])

            # fill partition1
            parti = _Util.devPathDiskToPartition(devpath, 1)
            _Util.cmdCall("/usr/sbin/mkfs.vfat", parti)

            # create lvm physical volume on partition2 and add it to volume group
            parti = _Util.devPathDiskToPartition(devpath, 2)
            _Util.cmdCall("/sbin/lvm", "pvcreate", parti)
            if not vgCreated:
                _Util.cmdCall("/sbin/lvm", "vgcreate", "hdd", parti)
                vgCreated = True
            else:
                _Util.cmdCall("/sbin/lvm", "vgextend", "hdd", parti)

        # create root lv
        out = _Util.cmdCall("/sbin/lvm", "vgdisplay", "-c", "hdd")
        freePe = int(out.split(":")[15])
        _Util.cmdCall("/sbin/lvm", "lvcreate", "-l", "%d" % (freePe // 2), "-n", "root", "hdd")

        # show result
        print("Root device: /dev/mapper/hdd-root")
        print("Swap device: None")
        print("Boot disk: %s" % (hddList[0]))

    def createLayoutEfiBcacheLvm(self, ssd=None, hddList=None):
        if ssd is None and hddList is None:
            ssdList = []
            for devpath in _Util.getDevPathListForFixedHdd():
                if _Util.isBlkDevSsdOrHdd(devpath):
                    ssdList.append(devpath)
                else:
                    hddList.append(devpath)
            if len(ssdList) == 0:
                pass
            elif len(ssdList) == 1:
                ssd = ssdList[0]
            else:
                raise Exception("multiple SSD harddisks")
            if len(hddList) == 0:
                raise Exception("no HDD harddisks")
        else:
            assert hddList is not None and len(hddList) > 0

        setUuid = None
        vgCreated = False

        if ssd is not None:
            # create partitions
            _Util.initializeDisk(ssd, "gpt", [
                (self.espPartiSizeStr, "esp"),
                (self.swapPartiSizeStr, "swap"),
                ("*", "bcache"),
            ])

            # sync partition1 as boot partition
            parti = _Util.devPathDiskToPartition(ssd, 1)
            _Util.cmdCall("/usr/sbin/mkfs.vfat", parti)

            # make partition2 as swap partition
            parti = _Util.devPathDiskToPartition(ssd, 2)
            _Util.cmdCall("/sbin/mkswap", parti)

            # make partition3 as cache partition
            parti = _Util.devPathDiskToPartition(ssd, 3)
            _Util.bcacheMakeDevice(parti, False)
            with open("/sys/fs/bcache/register", "w") as f:
                f.write(parti)
            setUuid = _Util.bcacheGetSetUuid(parti)

        for devpath in hddList:
            # create partitions
            _Util.initializeDisk(devpath, "gpt", [
                (self.espPartiSizeStr, "vfat"),
                ("*", "bcache"),
            ])

            # fill partition1
            parti = _Util.devPathDiskToPartition(devpath, 1)
            _Util.cmdCall("/usr/sbin/mkfs.vfat", parti)

            # add partition2 to bcache
            parti = _Util.devPathDiskToPartition(devpath, 2)
            _Util.bcacheMakeDevice(parti, True)
            with open("/sys/fs/bcache/register", "w") as f:
                f.write(parti)
            bcacheDev = _Util.bcacheFindByBackingDevice(parti)
            if ssd is not None:
                with open("/sys/block/%s/bcache/attach" % (os.path.basename(bcacheDev)), "w") as f:
                    f.write(str(setUuid))

            # create lvm physical volume on bcache device and add it to volume group
            _Util.cmdCall("/sbin/lvm", "pvcreate", bcacheDev)
            if not vgCreated:
                _Util.cmdCall("/sbin/lvm", "vgcreate", "hdd", bcacheDev)
                vgCreated = True
            else:
                _Util.cmdCall("/sbin/lvm", "vgextend", "hdd", bcacheDev)

        # create root lv
        out = _Util.cmdCall("/sbin/lvm", "vgdisplay", "-c", "hdd")
        freePe = int(out.split(":")[15])
        _Util.cmdCall("/sbin/lvm", "lvcreate", "-l", "%d" % (freePe // 2), "-n", "root", "hdd")

        # show result
        print("Root device: /dev/mapper/hdd-root")
        print("Swap device: %s" % (_Util.devPathDiskToPartition(ssd, 2) if ssd is not None else "None"))
        print("Boot disk: %s" % (ssd if ssd is not None else hddList[0]))

    def _getEmptyLayout(self):
        hddList = _Util.getDevPathListForFixedHdd()
        for hdd in hddList:
            if _Util.getBlkDevPartitionTableType(hdd) == "":
                hddList.remove(hdd)
        if hddList == []:
            return FmStorageLayoutEmpty()
        return None

    def _getEfiBcacheLvmLayout(self):
        # bcache kernel support
        if not os.path.exists("/sys/fs/bcache"):
            rc, out = _Util.cmdCallWithRetCode("/sbin/modprobe", "bcache")
            if rc != 0:
                return None
            assert os.path.exists("/sys/fs/bcache")

        # get HDD list
        hddList = []
        for devpath in _Util.getDevPathListForFixedHdd():
            if not _Util.isBlkDevSsdOrHdd(devpath):
                if os.path.exists(_Util.devPathDiskToPartition(devpath, 1)) and os.path.exists(_Util.devPathDiskToPartition(devpath, 2)):
                    if _Util.bcacheIsBackingDevice(_Util.devPathDiskToPartition(devpath, 2)):
                        hddList.append(devpath)
        if hddList == []:
            return None

        # check HDD list
        for hdd in hddList:
            if _Util.getBlkDevSize(_Util.devPathDiskToPartition(hdd, 1)) != self.espPartiSize:
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "%s has an invalid size" % (_Util.devPathDiskToPartition(hdd, 1)))
            if os.path.exists(_Util.devPathDiskToPartition(hdd, 3)):
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "redundant partition exists on %s" % (hdd))

        # get bootable HDD list
        bootableHddList = []
        for hdd in hddList:
            if _Util.gptIsEspPartition(_Util.devPathDiskToPartition(hdd, 1)):
                bootableHddList.append(hdd)

        # get SSD
        ssd = None
        if True:
            ssdList = []
            for devpath in _Util.getDevPathListForFixedHdd():
                if not _Util.isBlkDevSsdOrHdd(devpath):
                    continue
                if not os.path.exists(_Util.devPathDiskToPartition(devpath, 1)):
                    continue
                if not os.path.exists(_Util.devPathDiskToPartition(devpath, 2)):
                    continue
                if not os.path.exists(_Util.devPathDiskToPartition(devpath, 3)):
                    continue
                if not _Util.bcacheIsCacheDevice(_Util.devPathDiskToPartition(devpath, 3)):
                    continue
                ssdList.append(devpath)
            if len(ssdList) > 1:
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "multiple cache device")
            if len(ssdList) == 1:
                ssd = ssdList[0]

        # check SSD
        if ssd is not None:
            if not _Util.gptIsEspPartition(_Util.devPathDiskToPartition(ssd, 1)):
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "%s is not ESP partition" % (_Util.devPathDiskToPartition(ssd, 1)))
            if _Util.getBlkDevSize(_Util.devPathDiskToPartition(ssd, 1)) != self.espPartiSize:
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "%s has an invalid size" % (_Util.devPathDiskToPartition(ssd, 1)))
            if _Util.getBlkDevFsType(_Util.devPathDiskToPartition(ssd, 2)) != "swap":
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "%s is not swap partition" % (_Util.devPathDiskToPartition(ssd, 2)))
            if os.path.exists(_Util.devPathDiskToPartition(ssd, 4)):
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "redundant partition exists on %s" % (ssd))

        # check HDD additionally
        if ssd is not None:
            if len(bootableHddList) != 0:
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "redundant bootable HDD")
        else:
            if len(bootableHddList) == 0:
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "no bootable HDD")
            if len(bootableHddList) > 1:
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "redundant bootable HDD")

        # activate bcache devices
        bdict = dict()
        for hdd in hddList:
            with open("/sys/fs/bcache/register_quiet", "w") as f:       # use register_quiet to ignore re-activation
                f.write(_Util.devPathDiskToPartition(hdd, 2))
            bdict[hdd] = _Util.bcacheFindByBackingDevice(_Util.devPathDiskToPartition(hdd, 2))
        if ssd is not None:
            with open("/sys/fs/bcache/register_quiet", "w") as f:
                if os.path.exists(_Util.devPathDiskToPartition(ssd, 3)):
                    f.write(_Util.devPathDiskToPartition(ssd, 3))
                else:
                    f.write(_Util.devPathDiskToPartition(ssd, 2))
        time.sleep(5)                                                   # simply wait bcache device to appear

        # activate volume groups
        _Util.cmdCall("/sbin/lvm", "vgchange", "-ay")
        rc, out = _Util.cmdCallWithRetCode("/sbin/lvm", "vgdisplay", "-v", "hdd")
        if rc != 0:
            raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "volume group hdd does not exist")

        # check logical volumes
        slaveList = []
        for m in re.finditer(" *PV Name +(\\S+)", out):
            bcacheDev = m.group(1)

            if re.fullmatch("/dev/bcache[0-9]+", bcacheDev) is None:
                raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "PV %s is not bcache device" % (bcacheDev))

            tlist = _Util.bcacheGetSlaveDevPathList(bcacheDev)
            if ssd is not None:
                if len(tlist) < 2:
                    raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "%s has no cache device" % (bcacheDev))
                if len(tlist) > 2:
                    raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "%s has multiple cache devices" % (bcacheDev))
                if _Util.devPathPartitionToDisk(tlist[0]) != ssd:
                    raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "%s has invalid cache device" % (bcacheDev))
                slaveList.append(tlist[1])
            else:
                if len(tlist) != 1:
                    raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "%s should not have cache device" % (bcacheDev))
                slaveList.append(tlist[0])
        if set(slaveList) != set([_Util.devPathDiskToPartition(x, 2) for x in hddList]):
            raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "invalid HDD list")

        rc, out = _Util.cmdCallWithRetCode("/sbin/lvm", "lvdisplay", "/dev/mapper/hdd-root")
        if rc != 0:
            raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "logical volume \"/dev/mapper/hdd-root\" does not exist")

        fs = _Util.getBlkDevFsType("/dev/mapper/hdd-root")
        if fs != "ext4":
            raise _GetLayoutError(FmStorageLayoutEfiBcacheLvm, "root partition file system is \"%s\", not \"ext4\"" % (fs))

        ret = FmStorageLayoutEfiBcacheLvm()
        if ssd is not None:
            ret.ssd = ssd
            ret.ssdEspParti = _Util.devPathDiskToPartition(ssd, 1)
            ret.ssdSwapParti = _Util.devPathDiskToPartition(ssd, 2)
            ret.ssdCacheParti = _Util.devPathDiskToPartition(ssd, 3)
        ret.lvmVg = "hdd"
        ret.lvmPvHddDict = bdict
        ret.lvmRootLv = "root"
        if ssd is None:
            ret.bootHdd = bootableHddList[0]

        return ret

    def _getEfiLvmLayout(self):
        ret = FmStorageLayoutEfiLvm()

        _Util.cmdCall("/sbin/lvm", "vgchange", "-ay")

        rc, out = _Util.cmdCallWithRetCode("/sbin/lvm", "vgdisplay", "-v", "hdd")
        if rc != 0:
            return None

        pvList = [x.group(1) for x in re.finditer(" *PV Name +(\\S+)", out)]
        for pv in pvList:
            hdd = _Util.devPathPartitionToDisk(pv)
            if _Util.getBlkDevPartitionTableType(hdd) != "gpt":
                return None

        ret.lvmVg = "hdd"
        ret.lvmRootLv = "root"

        for pv in pvList:
            hdd = _Util.devPathPartitionToDisk(pv)
            if re.fullmatch(".*[a-z]2", pv) is None:
                raise _GetLayoutError(FmStorageLayoutEfiLvm, "physical volume partition of %s is not %s" % (hdd, _Util.devPathDiskToPartition(hdd, 2)))
            if _Util.getBlkDevSize(_Util.devPathDiskToPartition(hdd, 1)) != self.espPartiSize:
                raise _GetLayoutError(FmStorageLayoutEfiLvm, "%s has an invalid size" % (_Util.devPathDiskToPartition(hdd, 1)))
            if os.path.exists(_Util.devPathDiskToPartition(hdd, 3)):
                raise _GetLayoutError(FmStorageLayoutEfiLvm, "redundant partition exists on %s" % (hdd))
            ret.lvmPvHddList.append(hdd)

        bootableHddList = []
        for hdd in ret.lvmPvHddList:
            if _Util.gptIsEspPartition(_Util.devPathDiskToPartition(hdd, 1)):
                bootableHddList.append(hdd)
        if len(bootableHddList) == 0:
            raise _GetLayoutError(FmStorageLayoutEfiLvm, "no bootable HDD")
        if len(bootableHddList) > 1:
            raise _GetLayoutError(FmStorageLayoutEfiLvm, "redundant bootable HDD")
        ret.bootHdd = bootableHddList[0]

        rc, out = _Util.cmdCallWithRetCode("/sbin/lvm", "lvdisplay", "/dev/mapper/hdd-root")
        if rc != 0:
            raise _GetLayoutError(FmStorageLayoutEfiLvm, "logical volume \"/dev/mapper/hdd-root\" does not exist")

        fs = _Util.getBlkDevFsType("/dev/mapper/hdd-root")
        if fs != "ext4":
            raise _GetLayoutError(FmStorageLayoutEfiLvm, "root partition file system is \"%s\", not \"ext4\"" % (fs))

        rc, out = _Util.cmdCallWithRetCode("/sbin/lvm", "lvdisplay", "/dev/mapper/hdd-swap")
        if rc == 0:
            ret.lvmSwapLv = "swap"
            if _Util.getBlkDevFsType("/dev/mapper/hdd-swap") != "swap":
                raise _GetLayoutError(FmStorageLayoutEfiLvm, "/dev/mapper/hdd-swap has an invalid file system")

        return ret

    def _getEfiSimpleLayout(self):
        ret = FmStorageLayoutEfiSimple()

        hddList = _Util.getDevPathListForFixedHdd()
        for hdd in hddList:
            if _Util.getBlkDevPartitionTableType(hdd) != "gpt":
                continue
            if not (os.path.exists(_Util.devPathDiskToPartition(hdd, 1)) and os.path.exists(_Util.devPathDiskToPartition(hdd, 2))):
                continue
            if not _Util.gptIsEspPartition(_Util.devPathDiskToPartition(hdd, 1)):
                continue
            if ret.hdd is not None:
                raise _GetLayoutError(FmStorageLayoutEfiSimple, "multiple bootable harddisks %s and %s" % (ret.hdd, hdd))
            ret.hdd = hdd

        if ret.hdd is None:
            return None

        ret.hddEspParti = _Util.devPathDiskToPartition(ret.hdd, 1)
        ret.hddRootParti = _Util.devPathDiskToPartition(ret.hdd, 2)
        ret.swapFile = None

        return ret

    def _getBiosLvmLayout(self):
        ret = FmStorageLayoutBiosLvm()

        _Util.cmdCall("/sbin/lvm", "vgchange", "-ay")

        rc, out = _Util.cmdCallWithRetCode("/sbin/lvm", "vgdisplay", "-v", "hdd")
        if rc != 0:
            return None

        pvList = [x.group(1) for x in re.finditer(" *PV Name +(\\S+)", out)]
        for pv in pvList:
            hdd = _Util.devPathPartitionToDisk(pv)
            if _Util.getBlkDevPartitionTableType(hdd) != "dos":
                return None

        ret.lvmVg = "hdd"
        ret.lvmRootLv = "root"

        for pv in pvList:
            hdd = _Util.devPathPartitionToDisk(pv)
            if re.fullmatch(".*[a-z]1", pv) is None:
                raise _GetLayoutError(FmStorageLayoutBiosLvm, "physical volume partition of %s is not %s" % (hdd, _Util.devPathDiskToPartition(hdd, 1)))
            if os.path.exists(_Util.devPathDiskToPartition(hdd, 2)):
                raise _GetLayoutError(FmStorageLayoutBiosLvm, "redundant partition exists on %s" % (hdd))
            ret.lvmPvHddList.append(hdd)

        for hdd in ret.lvmPvHddList:
            with open(hdd, "rb") as f:
                if not _Util.isBufferAllZero(f.read(440)):
                    if ret.bootHdd is not None:
                        raise _GetLayoutError(FmStorageLayoutBiosLvm, "boot-code exists on multiple harddisks")
                    ret.bootHdd = hdd
        if ret.bootHdd is None:
            raise _GetLayoutError(FmStorageLayoutBiosLvm, "no harddisk has boot-code")

        rc, out = _Util.cmdCallWithRetCode("/sbin/lvm", "lvdisplay", "/dev/mapper/hdd-root")
        if rc != 0:
            raise _GetLayoutError(FmStorageLayoutBiosLvm, "logical volume \"/dev/mapper/hdd-root\" does not exist")

        fs = _Util.getBlkDevFsType("/dev/mapper/hdd-root")
        if fs != "ext4":
            raise _GetLayoutError(FmStorageLayoutBiosLvm, "root partition file system is \"%s\", not \"ext4\"" % (fs))

        rc, out = _Util.cmdCallWithRetCode("/sbin/lvm", "lvdisplay", "/dev/mapper/hdd-swap")
        if rc == 0:
            ret.lvmSwapLv = "swap"
            if _Util.getBlkDevFsType("/dev/mapper/hdd-swap") != "swap":
                raise _GetLayoutError(FmStorageLayoutBiosLvm, "/dev/mapper/hdd-swap has an invalid file system")

        return ret

    def _getBiosSimpleLayout(self):
        ret = FmStorageLayoutBiosSimple()

        hddDict = dict()            # <hdd, (rootPartiList, otherPartiList)>
        for hdd in _Util.getDevPathListForFixedHdd():
            if _Util.getBlkDevPartitionTableType(hdd) != "dos":
                continue
            with open(hdd, "rb") as f:
                if _Util.isBufferAllZero(f.read(440)):      # no boot-code
                    continue
            rootPartiList = []
            otherPartiList = []
            for i in range(1, 100):
                parti = "%s%d" % (hdd, i)
                if not os.path.exists(parti):
                    break
                if _Util.getBlkDevFsType(parti) == "ext4":
                    rootPartiList.append(parti)
                else:
                    otherPartiList.append(parti)
            hddDict[hdd] = (rootPartiList, otherPartiList)

        # use bootable hdd with one root partition only
        for hdd, value in hddDict.items():
            rootPartiList, otherPartiList = value
            if len(rootPartiList) != 1:
                continue
            if otherPartiList != []:
                continue
            if ret.hdd is not None:
                raise _GetLayoutError(FmStorageLayoutBiosSimple, "multiple bootable harddisks %s and %s" % (ret.hdd, hdd))
            ret.hdd = hdd
            ret.hddRootParti = rootPartiList[0]
        if ret.hdd is not None:
            return ret

        # use bootable hdd with one root partition and other partitions
        for hdd, value in hddDict.items():
            rootPartiList, otherPartiList = value
            if len(rootPartiList) != 1:
                continue
            if ret.hdd is not None:
                raise _GetLayoutError(FmStorageLayoutBiosSimple, "multiple bootable harddisks %s and %s" % (ret.hdd, hdd))
            ret.hdd = hdd
            ret.hddRootParti = rootPartiList[0]
        if ret.hdd is not None:
            return ret

        # no valid hdd found
        return None


class _GetLayoutError(Exception):

    def __init__(self, layoutClass, message):
        self.layoutName = layoutClass.name
        self.message = message


class _Util:

    @staticmethod
    def cmdCall(cmd, *kargs):
        # call command to execute backstage job
        #
        # scenario 1, process group receives SIGTERM, SIGINT and SIGHUP:
        #   * callee must auto-terminate, and cause no side-effect
        #   * caller must be terminated by signal, not by detecting child-process failure
        # scenario 2, caller receives SIGTERM, SIGINT, SIGHUP:
        #   * caller is terminated by signal, and NOT notify callee
        #   * callee must auto-terminate, and cause no side-effect, after caller is terminated
        # scenario 3, callee receives SIGTERM, SIGINT, SIGHUP:
        #   * caller detects child-process failure and do appopriate treatment

        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def cmdCallWithRetCode(cmd, *kargs):
        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        return (ret.returncode, ret.stdout.rstrip())

    @staticmethod
    def getPhysicalMemorySize():
        with open("/proc/meminfo", "r") as f:
            # We return memory size in GB.
            # Since the memory size shown in /proc/meminfo is always a
            # little less than the real size because various sort of
            # reservation, so we do a "+1"
            m = re.search("^MemTotal:\\s+(\\d+)", f.read())
            return int(m.group(1)) / 1024 / 1024 + 1

    @staticmethod
    def wipeHarddisk(devpath):
        with open(devpath, 'wb') as f:
            f.write(bytearray(1024))

    @staticmethod
    def devPathIsDiskOrPartition(devPath):
        if re.fullmatch("/dev/sd[a-z]", devPath) is not None:
            return True
        if re.fullmatch("(/dev/sd[a-z])([0-9]+)", devPath) is not None:
            return False
        if re.fullmatch("/dev/xvd[a-z]", devPath) is not None:
            return True
        if re.fullmatch("(/dev/xvd[a-z])([0-9]+)", devPath) is not None:
            return False
        if re.fullmatch("/dev/vd[a-z]", devPath) is not None:
            return True
        if re.fullmatch("(/dev/vd[a-z])([0-9]+)", devPath) is not None:
            return False
        if re.fullmatch("/dev/nvme[0-9]+n[0-9]+", devPath) is not None:
            return True
        if re.fullmatch("(/dev/nvme[0-9]+n[0-9]+)p([0-9]+)", devPath) is not None:
            return False
        assert False

    @staticmethod
    def devPathPartitionToDiskAndPartitionId(partitionDevPath):
        m = re.fullmatch("(/dev/sd[a-z])([0-9]+)", partitionDevPath)
        if m is not None:
            return (m.group(1), int(m.group(2)))
        m = re.fullmatch("(/dev/xvd[a-z])([0-9]+)", partitionDevPath)
        if m is not None:
            return (m.group(1), int(m.group(2)))
        m = re.fullmatch("(/dev/vd[a-z])([0-9]+)", partitionDevPath)
        if m is not None:
            return (m.group(1), int(m.group(2)))
        m = re.fullmatch("(/dev/nvme[0-9]+n[0-9]+)p([0-9]+)", partitionDevPath)
        if m is not None:
            return (m.group(1), int(m.group(2)))
        assert False

    @staticmethod
    def devPathPartitionToDisk(partitionDevPath):
        return _Util.devPathPartitionToDiskAndPartitionId(partitionDevPath)[0]

    @staticmethod
    def devPathDiskToPartition(diskDevPath, partitionId):
        m = re.fullmatch("/dev/sd[a-z]", diskDevPath)
        if m is not None:
            return diskDevPath + str(partitionId)
        m = re.fullmatch("/dev/xvd[a-z]", diskDevPath)
        if m is not None:
            return diskDevPath + str(partitionId)
        m = re.fullmatch("/dev/vd[a-z]", diskDevPath)
        if m is not None:
            return diskDevPath + str(partitionId)
        m = re.fullmatch("/dev/nvme[0-9]+n[0-9]+", diskDevPath)
        if m is not None:
            return diskDevPath + "p" + str(partitionId)
        assert False

    @staticmethod
    def bcacheMakeDevice(devPath, backingDeviceOrCacheDevice, blockSize=None, bucketSize=None, dataOffset=None):
        assert isinstance(backingDeviceOrCacheDevice, bool)
        assert blockSize is None or (isinstance(blockSize, int) and blockSize > 0)
        assert bucketSize is None or (isinstance(bucketSize, int) and bucketSize > 0)
        assert dataOffset is None or (isinstance(dataOffset, int) and dataOffset > 0)

        #######################################################################
        # code from bcache-tools-1.0.8
        #######################################################################
        # struct cache_sb {
        #     uint64_t        csum;
        #     uint64_t        offset;    /* sector where this sb was written */
        #     uint64_t        version;
        #     uint8_t         magic[16];
        #     uint8_t         uuid[16];
        #     union {
        #         uint8_t     set_uuid[16];
        #         uint64_t    set_magic;
        #     };
        #     uint8_t         label[SB_LABEL_SIZE];
        #     uint64_t        flags;
        #     uint64_t        seq;
        #     uint64_t        pad[8];
        #     union {
        #         struct {
        #             /* Cache devices */
        #             uint64_t    nbuckets;      /* device size */
        #             uint16_t    block_size;    /* sectors */
        #             uint16_t    bucket_size;   /* sectors */
        #             uint16_t    nr_in_set;
        #             uint16_t    nr_this_dev;
        #         };
        #         struct {
        #             /* Backing devices */
        #             uint64_t    data_offset;
        #             /*
        #             * block_size from the cache device section is still used by
        #             * backing devices, so don't add anything here until we fix
        #             * things to not need it for backing devices anymore
        #             */
        #         };
        #     };
        #     uint32_t        last_mount;        /* time_t */
        #     uint16_t        first_bucket;
        #     union {
        #         uint16_t    njournal_buckets;
        #         uint16_t    keys;
        #     };
        #     uint64_t        d[SB_JOURNAL_BUCKETS];    /* journal buckets */
        # };
        bcacheSbFmt = "QQQ16B16B16B32BQQ8QQHHHHIHH"     # without cache_sb.d

        bcacheSbMagic = [0xc6, 0x85, 0x73, 0xf6, 0x4e, 0x1a, 0x45, 0xca,
                         0x82, 0x65, 0xf5, 0x7f, 0x48, 0xba, 0x6d, 0x81]

        if blockSize is None:
            st = os.stat(devPath)
            if stat.S_ISBLK(st.st_mode):
                out = _Util.cmdCall("/sbin/blockdev", "--getss", devPath)
                blockSize = int(out) // 512
            else:
                blockSize = st.st_blksize // 512

        if bucketSize is None:
            bucketSize = 1024
        if bucketSize < blockSize:
            raise Exception("bucket size (%d) cannot be smaller than block size (%d)", bucketSize, blockSize)

        devUuid = uuid.uuid4()
        setUuid = uuid.uuid4()

        bcacheSb = bytearray(struct.calcsize(bcacheSbFmt))
        offset_content = None
        offset_version = None

        # cache_sb.csum
        p = struct.calcsize("Q")
        offset_content = p

        # cache_sb.offset
        value = 8               # SB_SECTOR
        struct.pack_into("Q", bcacheSb, p, value)
        p += struct.calcsize("Q")

        # cache_sb.version
        if backingDeviceOrCacheDevice:
            value = 1           # BCACHE_SB_VERSION_BDEV
        else:
            value = 0           # BCACHE_SB_VERSION_CDEV
        offset_version = p
        struct.pack_into("Q", bcacheSb, p, value)
        p += struct.calcsize("Q")

        # cache_sb.magic
        struct.pack_into("16B", bcacheSb, p, *bcacheSbMagic)
        p += struct.calcsize("16B")

        # cache_sb.uuid
        struct.pack_into("16B", bcacheSb, p, *devUuid.bytes)
        p += struct.calcsize("16B")

        # cache_sb.set_uuid
        struct.pack_into("16B", bcacheSb, p, *setUuid.bytes)
        p += struct.calcsize("16B")

        # cache_sb.label
        p += struct.calcsize("32B")

        # cache_sb.flags
        if backingDeviceOrCacheDevice:
            value = 0x01                        # CACHE_MODE_WRITEBACK
        else:
            value = 0x00
        struct.pack_into("Q", bcacheSb, p, value)
        p += struct.calcsize("Q")

        # cache_sb.seq
        p += struct.calcsize("Q")

        # cache_sb.pad
        p += struct.calcsize("8Q")

        if backingDeviceOrCacheDevice:
            if dataOffset is not None:
                # modify cache_sb.version
                value = 4                       # BCACHE_SB_VERSION_BDEV_WITH_OFFSET
                struct.pack_into("Q", bcacheSb, offset_version, value)

                # cache_sb.data_offset
                struct.pack_into("Q", bcacheSb, p, dataOffset)
                p += struct.calcsize("Q")
            else:
                # cache_sb.data_offset
                p += struct.calcsize("Q")
        else:
            # cache_sb.nbuckets
            value = _Util.getBlkDevSize(devPath) // 512 // bucketSize
            if value < 0x80:
                raise Exception("not enough buckets: %d, need %d", value, 0x80)
            struct.pack_into("Q", bcacheSb, p, value)
            p += struct.calcsize("Q")

        # cache_sb.block_size
        struct.pack_into("H", bcacheSb, p, blockSize)
        p += struct.calcsize("H")

        # cache_sb.bucket_size
        struct.pack_into("H", bcacheSb, p, bucketSize)
        p += struct.calcsize("H")

        # cache_sb.nr_in_set
        if not backingDeviceOrCacheDevice:
            value = 1
            struct.pack_into("H", bcacheSb, p, value)
            p += struct.calcsize("H")

        # cache_sb.nr_this_dev
        p += struct.calcsize("H")

        # cache_sb.last_mount
        p += struct.calcsize("I")

        # cache_sb.first_bucket
        value = (23 // bucketSize) + 1
        struct.pack_into("H", bcacheSb, p, value)
        p += struct.calcsize("H")

        # cache_sb.csum
        crc64 = crcmod.predefined.Crc("crc-64-we")
        crc64.update(bcacheSb[offset_content:])
        struct.pack_into("Q", bcacheSb, 0, crc64.crcValue)

        with open(devPath, "r+b") as f:
            f.write(bytearray(8 * 512))
            f.write(bcacheSb)
            f.write(bytearray(256 * 8))         # cacbe_sb.d

        return (devUuid, setUuid)

    @staticmethod
    def bcacheIsBackingDevice(devPath):
        return _Util._bcacheIsBackingDeviceOrCachDevice(devPath, True)

    @staticmethod
    def bcacheIsCacheDevice(devPath):
        return _Util._bcacheIsBackingDeviceOrCachDevice(devPath, False)

    @staticmethod
    def _bcacheIsBackingDeviceOrCachDevice(devPath, backingDeviceOrCacheDevice):
        # see C struct definition in _Util.bcacheMakeDevice()
        bcacheSbMagicPreFmt = "QQQ"
        bcacheSbMagicFmt = "16B"
        bcacheSbVersionPreFmt = "QQ"
        bcacheSbVersionFmt = "Q"

        bcacheSbMagic = [0xc6, 0x85, 0x73, 0xf6, 0x4e, 0x1a, 0x45, 0xca,
                         0x82, 0x65, 0xf5, 0x7f, 0x48, 0xba, 0x6d, 0x81]
        if backingDeviceOrCacheDevice:
            versionValueList = [
                1,           # BCACHE_SB_VERSION_BDEV
                4,           # BCACHE_SB_VERSION_BDEV_WITH_OFFSET
            ]
        else:
            versionValueList = [
                0,           # BCACHE_SB_VERSION_CDEV
                3,           # BCACHE_SB_VERSION_CDEV_WITH_UUID
            ]

        with open(devPath, "rb") as f:
            f.seek(8 * 512 + struct.calcsize(bcacheSbMagicPreFmt))
            buf = f.read(struct.calcsize(bcacheSbMagicFmt))
            if list(buf) != bcacheSbMagic:
                return False

            f.seek(8 * 512 + struct.calcsize(bcacheSbVersionPreFmt))
            buf = f.read(struct.calcsize(bcacheSbVersionFmt))
            value = struct.unpack(bcacheSbVersionFmt, buf)[0]
            if value not in versionValueList:
                return False

            return True

    @staticmethod
    def bcacheGetSetUuid(devPath):
        # see C struct definition in _Util.bcacheMakeDevice()
        bcacheSbSetUuidPreFmt = "QQQ16B16B"
        bcacheSbSetUuidFmt = "16B"

        assert _Util.bcacheIsCacheDevice(devPath)

        with open(devPath, "rb") as f:
            f.seek(8 * 512 + struct.calcsize(bcacheSbSetUuidPreFmt))
            buf = f.read(struct.calcsize(bcacheSbSetUuidFmt))
            return uuid.UUID(bytes=buf)

    @staticmethod
    def bcacheGetSlaveDevPathList(bcacheDevPath):
        """Last element in the returned list is the backing device, others are cache device"""

        retList = []

        slavePath = "/sys/block/" + os.path.basename(bcacheDevPath) + "/slaves"
        for slaveDev in os.listdir(slavePath):
            retList.append(os.path.join("/dev", slaveDev))

        bcachePath = os.path.realpath("/sys/block/" + os.path.basename(bcacheDevPath) + "/bcache")
        backingDev = os.path.basename(os.path.dirname(bcachePath))
        backingDevPath = os.path.join("/dev", backingDev)

        retList.remove(backingDevPath)
        retList.append(backingDevPath)
        return retList

    @staticmethod
    def bcacheFindByBackingDevice(devPath):
        for fn in glob.glob("/dev/bcache*"):
            if re.fullmatch("/dev/bcache[0-9]+", fn):
                bcachePath = os.path.realpath("/sys/block/" + os.path.basename(devPath) + "/bcache")
                backingDev = os.path.basename(os.path.dirname(bcachePath))
                if os.path.basename(devPath) == backingDev:
                    return fn
        return None

    @staticmethod
    def isBlkDevSsdOrHdd(devPath):
        bn = os.path.basename(devPath)
        with open("/sys/block/%s/queue/rotational" % (bn), "r") as f:
            buf = f.read().strip("\n")
            if buf == "1":
                return False
        return True

    @staticmethod
    def getBlkDevSize(devPath):
        out = _Util.cmdCall("/sbin/blockdev", "--getsz", devPath)
        return int(out) * 512        # unit is byte

    @staticmethod
    def getBlkDevPartitionTableType(devPath):
        if not _Util.devPathIsDiskOrPartition(devPath):
            devPath = _Util.devPathPartitionToDisk(devPath)

        ret = _Util.cmdCall("/sbin/blkid", "-o", "export", devPath)
        m = re.search("^PTTYPE=(\\S+)$", ret, re.M)
        if m is not None:
            return m.group(1)
        else:
            return ""

    @staticmethod
    def getBlkDevFsType(devPath):
        ret = _Util.cmdCall("/sbin/blkid", "-o", "export", devPath)
        m = re.search("^TYPE=(\\S+)$", ret, re.M)
        if m is not None:
            return m.group(1).lower()
        else:
            return ""

    @staticmethod
    def getBlkDevLvmInfo(devPath):
        """Returns (vg-name, lv-name)
           Returns None if the device is not lvm"""

        rc, ret = _Util.cmdCallWithRetCode("/sbin/dmsetup", "info", devPath)
        if rc == 0:
            m = re.search("^Name: *(\\S+)$", ret, re.M)
            assert m is not None
            return m.group(1).split(".")
        else:
            return None

    @staticmethod
    def gptNewGuid(guidStr):
        assert len(guidStr) == 36
        assert guidStr[8] == "-" and guidStr[13] == "-" and guidStr[18] == "-" and guidStr[23] == "-"

        # struct gpt_guid {
        #     uint32_t   time_low;
        #     uint16_t   time_mid;
        #     uint16_t   time_hi_and_version;
        #     uint8_t    clock_seq_hi;
        #     uint8_t    clock_seq_low;
        #     uint8_t    node[6];
        # };
        gptGuidFmt = "IHHBB6s"
        assert struct.calcsize(gptGuidFmt) == 16

        guidStr = guidStr.replace("-", "")

        # really obscure behavior of python3
        # see http://stackoverflow.com/questions/1463306/how-does-exec-work-with-locals
        ldict = {}
        exec("n1 = 0x" + guidStr[0:8], globals(), ldict)
        exec("n2 = 0x" + guidStr[8:12], globals(), ldict)
        exec("n3 = 0x" + guidStr[12:16], globals(), ldict)
        exec("n4 = 0x" + guidStr[16:18], globals(), ldict)
        exec("n5 = 0x" + guidStr[18:20], globals(), ldict)
        exec("n6 = bytearray()", globals(), ldict)
        for i in range(0, 6):
            exec("n6.append(0x" + guidStr[20 + i * 2:20 + (i + 1) * 2] + ")", globals(), ldict)

        return struct.pack(gptGuidFmt, ldict["n1"], ldict["n2"], ldict["n3"], ldict["n4"], ldict["n5"], ldict["n6"])

    @staticmethod
    def gptIsEspPartition(devPath):
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
        mbrPartitionRecordFmt = "8BII"
        assert struct.calcsize(mbrPartitionRecordFmt) == 16

        # struct mbr_header {
        #     uint8_t                     boot_code[440];
        #     uint32_t                    unique_mbr_signature;
        #     uint16_t                    unknown;
        #     struct mbr_partition_record partition_record[4];
        #     uint16_t                    signature;
        # };
        mbrHeaderFmt = "440sIH%dsH" % (struct.calcsize(mbrPartitionRecordFmt) * 4)
        assert struct.calcsize(mbrHeaderFmt) == 512

        # struct gpt_entry {
        #     struct gpt_guid type;
        #     struct gpt_guid partition_guid;
        #     uint64_t        lba_start;
        #     uint64_t        lba_end;
        #     uint64_t        attrs;
        #     uint16_t        name[GPT_PART_NAME_LEN];
        # };
        gptEntryFmt = "16s16sQQQ36H"
        assert struct.calcsize(gptEntryFmt) == 128

        # struct gpt_header {
        #     uint64_t            signature;
        #     uint32_t            revision;
        #     uint32_t            size;
        #     uint32_t            crc32;
        #     uint32_t            reserved1;
        #     uint64_t            my_lba;
        #     uint64_t            alternative_lba;
        #     uint64_t            first_usable_lba;
        #     uint64_t            last_usable_lba;
        #     struct gpt_guid     disk_guid;
        #     uint64_t            partition_entry_lba;
        #     uint32_t            npartition_entries;
        #     uint32_t            sizeof_partition_entry;
        #     uint32_t            partition_entry_array_crc32;
        #     uint8_t             reserved2[512 - 92];
        # };
        gptHeaderFmt = "QIIIIQQQQ16sQIII420s"
        assert struct.calcsize(gptHeaderFmt) == 512

        # do checking
        diskDevPath, partId = _Util.devPathPartitionToDiskAndPartitionId(devPath)
        with open(diskDevPath, "rb") as f:
            # get protective MBR
            mbrHeader = struct.unpack(mbrHeaderFmt, f.read(struct.calcsize(mbrHeaderFmt)))

            # check protective MBR header
            if mbrHeader[4] != 0xAA55:
                return False

            # check protective MBR partition entry
            found = False
            for i in range(0, 4):
                pRec = struct.unpack_from(mbrPartitionRecordFmt, mbrHeader[3], struct.calcsize(mbrPartitionRecordFmt) * i)
                if pRec[4] == 0xEE:
                    found = True
            if not found:
                return False

            # get the specified GPT partition entry
            gptHeader = struct.unpack(gptHeaderFmt, f.read(struct.calcsize(gptHeaderFmt)))
            f.seek(gptHeader[10] * 512 + struct.calcsize(gptEntryFmt) * (partId - 1))
            partEntry = struct.unpack(gptEntryFmt, f.read(struct.calcsize(gptEntryFmt)))

            # check partition GUID
            if partEntry[0] != _Util.gptNewGuid("C12A7328-F81F-11D2-BA4B-00A0C93EC93B"):
                return False

        return True

    @staticmethod
    def initializeDisk(devPath, partitionTableType, partitionInfoList):
        assert partitionTableType in ["mbr", "gpt"]
        assert len(partitionInfoList) >= 1

        if partitionTableType == "mbr":
            partitionTableType = "msdos"

        def _getFreeRegion(disk):
            region = None
            for r in disk.getFreeSpaceRegions():
                if r.length <= disk.device.optimumAlignment.grainSize:
                    continue                                                # ignore alignment gaps
                if region is not None:
                    assert False                                            # there should be only one free region
                region = r
            if region.start < 2048:
                region.start = 2048
            return region

        def _addPartition(disk, pType, pStart, pEnd):
            region = parted.Geometry(device=disk.device, start=pStart, end=pEnd)
            if pType == "":
                partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=region)
            elif pType == "esp":
                assert partitionTableType == "gpt"
                partition = parted.Partition(disk=disk,
                                             type=parted.PARTITION_NORMAL,
                                             fs=parted.FileSystem(type="fat32", geometry=region),
                                             geometry=region)
                partition.setFlag(parted.PARTITION_ESP)     # which also sets flag parted.PARTITION_BOOT
            elif pType == "bcache":
                assert partitionTableType == "gpt"
                partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=region)
            elif pType == "swap":
                partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=region)
                if partitionTableType == "mbr":
                    partition.setFlag(parted.PARTITION_SWAP)
                elif partitionTableType == "gpt":
                    pass            # don't know why, it says gpt partition has no way to setFlag(SWAP)
                else:
                    assert False
            elif pType == "lvm":
                partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=region)
                partition.setFlag(parted.PARTITION_LVM)
            elif pType == "vfat":
                partition = parted.Partition(disk=disk,
                                             type=parted.PARTITION_NORMAL,
                                             fs=parted.FileSystem(type="fat32", geometry=region),
                                             geometry=region)
            elif pType in ["ext2", "ext4", "xfs"]:
                partition = parted.Partition(disk=disk,
                                             type=parted.PARTITION_NORMAL,
                                             fs=parted.FileSystem(type=pType, geometry=region),
                                             geometry=region)
            else:
                assert False
            disk.addPartition(partition=partition,
                              constraint=disk.device.optimalAlignedConstraint)

        def _erasePartitionSignature(devPath, pStart, pEnd):
            # fixme: this implementation is very limited
            with open(devPath, "wb") as f:
                f.seek(pStart * 512)
                if pEnd - pStart + 1 < 32:
                    f.write(bytearray((pEnd - pStart + 1) * 512))
                else:
                    f.write(bytearray(32 * 512))

        # partitionInfoList => preList & postList
        preList = None
        postList = None
        for i in range(0, len(partitionInfoList)):
            pSize, pType = partitionInfoList[i]
            if pSize == "*":
                assert preList is None
                preList = partitionInfoList[:i]
                postList = partitionInfoList[i:]
        if preList is None:
            preList = partitionInfoList
            postList = []

        # delete all partitions
        disk = parted.freshDisk(parted.getDevice(devPath), partitionTableType)
        disk.commit()

        # process preList
        for pSize, pType in preList:
            region = _getFreeRegion(disk)
            constraint = parted.Constraint(maxGeom=region).intersect(disk.device.optimalAlignedConstraint)
            pStart = constraint.startAlign.alignUp(region, region.start)
            pEnd = constraint.endAlign.alignDown(region, region.end)

            m = re.fullmatch("([0-9]+)(MiB|GiB|TiB)", pSize)
            assert m is not None
            sectorNum = parted.sizeToSectors(int(m.group(1)), m.group(2), disk.device.sectorSize)
            if pEnd < pStart + sectorNum - 1:
                raise Exception("not enough space")

            _addPartition(disk, pType, pStart, pStart + sectorNum - 1)
            _erasePartitionSignature(devPath, pStart, pEnd)

        # process postList
        for pSize, pType in postList:
            region = _getFreeRegion(disk)
            constraint = parted.Constraint(maxGeom=region).intersect(disk.device.optimalAlignedConstraint)
            pStart = constraint.startAlign.alignUp(region, region.start)
            pEnd = constraint.endAlign.alignDown(region, region.end)

            if pSize == "*":
                _addPartition(disk, pType, pStart, pEnd)
                _erasePartitionSignature(devPath, pStart, pEnd)
            else:
                assert False

        disk.commit()
        time.sleep(3)           # FIXME, wait kernel picks the change

    @staticmethod
    def isBufferAllZero(buf):
        for b in buf:
            if b != 0:
                return False
        return True

    @staticmethod
    def getDevPathListForFixedHdd():
        ret = []
        for line in _Util.cmdCall("/bin/lsblk", "-o", "NAME,TYPE", "-n").split("\n"):
            m = re.fullmatch("(\\S+)\\s+(\\S+)", line)
            if m is None:
                continue
            if m.group(2) != "disk":
                continue
            if re.search("/usb[0-9]+/", os.path.realpath("/sys/block/%s/device" % (m.group(1)))) is not None:      # USB device
                continue
            ret.append("/dev/" + m.group(1))
        return ret


###############################################################################


if __name__ == "__main__":
    Main().main()
