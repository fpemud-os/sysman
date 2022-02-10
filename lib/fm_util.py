#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import bz2
import pwd
import grp
import spwd
import json
import glob
import stat
import time
import errno
import fcntl
import shutil
import parted
import pathlib
import asyncio
import asyncio_pool
import socket
import struct
import filecmp
import fnmatch
import gstage4
import pyudev
import random
import termios
import hashlib
import tempfile
import blessed
import zipfile
import portage
import platform
import threading
import subprocess
import lxml.html
import passlib.hosts
import urllib.request
import urllib.error
import robust_layer
import robust_layer.wget
import robust_layer.simple_fops
from datetime import datetime
from OpenSSL import crypto
from gi.repository import Gio
from gi.repository import GLib


class FmUtil:

    @staticmethod
    def bcacheGetHitRatio(self, setUuid):
        return int(pathlib.Path(os.path.join("/sys", "fs", "bcache", setUuid, "stats_day", "cache_hit_ratio")).read_text().rstrip("\n"))

    @staticmethod
    def makeSquashedRootfsFiles(rootfsDir, dstDir):
        sqfsFile = os.path.join(dstDir, "rootfs.sqfs")
        sqfsSumFile = os.path.join(dstDir, "rootfs.sqfs.sha512")

        FmUtil.shellCall("mksquashfs %s %s -no-progress -noappend -quiet" % (rootfsDir, sqfsFile))
        FmUtil.shellCall("sha512sum %s > %s" % (sqfsFile, sqfsSumFile))

        # remove directory prefix in rootfs.sqfs.sha512, sha512sum sucks
        FmUtil.cmdCall("sed", "-i", "s#%s/\\?##" % (dstDir), sqfsSumFile)

        return (sqfsFile, sqfsSumFile)

    @staticmethod
    def formatDisk(devPath, partitionTableType="mbr", partitionType="", partitionLabel=""):
        assert partitionTableType in ["mbr", "gpt"]
        assert partitionType in ["", "ext4", "btrfs", "bcachefs", "vfat", "exfat"]

        if partitionTableType == "mbr":
            partitionTableType = "msdos"

        if partitionType == "vfat":
            pType = "fat32"
        else:
            pType = partitionType

        disk = parted.freshDisk(parted.getDevice(devPath), partitionTableType)

        assert len(disk.getFreeSpaceRegions()) == 1
        freeRegion = disk.getFreeSpaceRegions()[0]

        pStart = disk.device.optimalAlignedConstraint.startAlign.alignUp(freeRegion, freeRegion.start)
        pEnd = disk.device.optimalAlignedConstraint.endAlign.alignDown(freeRegion, freeRegion.end)
        region = parted.Geometry(device=disk.device, start=pStart, end=pEnd)

        if pType == "":
            partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=region)
        else:
            partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL,
                                         fs=parted.FileSystem(type=pType, geometry=region),
                                         geometry=region)

        if not disk.addPartition(partition=partition, constraint=disk.device.optimalAlignedConstraint):
            # it sucks that disk.addPartition() won't do the job of restricting region INSIDE constraint
            # so we must calculate pStart and pEnd manually beforehand
            raise Exception("failed to format %s" % (devPath))
        if not disk.commit():
            # experiments show that disk.commit() blocks until /dev is updated
            raise Exception("failed to format %s" % (devPath))

        partDevPath = devPath + "1"
        if partitionType == "":
            pass
        elif partitionType == "ext4":
            assert False
        elif partitionType == "btrfs":
            assert False
        elif partitionType == "bcachefs":
            assert False
        elif partitionType == "vfat":
            FmUtil.cmdCall("mkfs.vfat", "-F", "32", "-n", partitionLabel, partDevPath)
        elif partitionType == "exfat":
            assert False
        else:
            assert False

        return partDevPath

    @staticmethod
    def getKernelVerStr(kernelDir):
        version = None
        patchlevel = None
        sublevel = None
        extraversion = None
        with open(os.path.join(kernelDir, "Makefile")) as f:
            buf = f.read()

            m = re.search("VERSION = ([0-9]+)", buf, re.M)
            if m is None:
                raise Exception("illegal kernel source directory")
            version = int(m.group(1))

            m = re.search("PATCHLEVEL = ([0-9]+)", buf, re.M)
            if m is None:
                raise Exception("illegal kernel source directory")
            patchlevel = int(m.group(1))

            m = re.search("SUBLEVEL = ([0-9]+)", buf, re.M)
            if m is None:
                raise Exception("illegal kernel source directory")
            sublevel = int(m.group(1))

            m = re.search("EXTRAVERSION = (\\S+)", buf, re.M)
            if m is not None:
                extraversion = m.group(1)

        if extraversion is not None:
            return "%d.%d.%d%s" % (version, patchlevel, sublevel, extraversion)
        else:
            return "%d.%d.%d" % (version, patchlevel, sublevel)

    @staticmethod
    def syncDirs(srcList, dstDir):
        for fn in os.listdir(dstDir):
            if fn not in srcList:
                robust_layer.simple_fops.rm(os.path.join(dstDir, fn))
        for fn in srcList:
            fullfn = os.path.join(dstDir, fn)
            if not os.path.exists(fullfn):
                os.mkdir(fullfn)

    @staticmethod
    def strListMaxLen(strList):
        maxLen = 0
        for lname in strList:
            if len(lname) > maxLen:
                maxLen = len(lname)
        return maxLen

    @staticmethod
    def getDirLastUpdateTime(dirpath):
        out = FmUtil.shellCall("find \"%s\" -printf \"%%TY%%Tm%%Td%%TH%%TM%%TS\\n\" | /bin/sort | /bin/tail -1" % (dirpath))
        out = re.search(r'^(.*)\.', out).group(1)
        return datetime.strptime(out, "%Y%m%d%H%M%S")

    @staticmethod
    def listDirWithoutKeepFiles(dirpath):
        ret = []
        for fn in os.listdir(dirpath):
            if fn.startswith(".keep"):
                continue
            ret.append((fn, os.path.join(dirpath, fn)))
        return ret

    @staticmethod
    def getLoadAvgStr():
        try:
            avg = os.getloadavg()
        except OSError:
            return 'unknown'

        max_avg = max(avg)
        if max_avg < 10:
            digits = 2
        elif max_avg < 100:
            digits = 1
        else:
            digits = 0

        return ", ".join(("%%.%df" % (digits)) % x for x in avg)

    _dmiDecodeCache = dict()

    @staticmethod
    def dmiDecodeWithCache(key):
        if key in FmUtil._dmiDecodeCache:
            return FmUtil._dmiDecodeCache[key]

        ret = FmUtil.cmdCall("dmidecode", "-s", key)
        FmUtil._dmiDecodeCache[key] = ret
        return ret

    _getMachineInfoCache = dict()

    @staticmethod
    def getMachineInfoWithCache(key):
        if FmUtil._getMachineInfoCache is not None:
            return FmUtil._getMachineInfoCache.get(key, None)

        FmUtil._getMachineInfoCache = dict()
        if os.path.exists("/etc/machine-info"):
            with open("/etc/machine-info", "r") as f:
                for line in f.read().split("\n"):
                    if line.startswith("#"):
                        continue
                    m = re.fullmatch("(.*?)=(.*)", line)
                    if m is None:
                        continue
                    FmUtil._getMachineInfoCache[m.group(1)] = m.group(2).strip("\"")
        return FmUtil._getMachineInfoCache.get(key, None)

    @staticmethod
    def pmdbGetMirrors(name, typeName, countryCode, protocolList, count=None):
        buf = FmUtil.githubGetFileContent("mirrorshq", "public-mirror-db", os.path.join(name, typeName + ".json"))
        jsonList = json.loads(buf)

        # filter by protocolList
        jsonList = [x for x in jsonList if x["protocol"] in protocolList]

        # filter by countryCode
        jsonList = [x for x in jsonList if x["country-code"] == countryCode]

        # filter by count
        if count is not None:
            jsonList = jsonList[0:min(len(jsonList), count)]

        # return value
        return [x["url"] for x in jsonList]

    @staticmethod
    def githubGetFileContent(user, repo, filepath):
        with TempCreateFile() as tmpFile:
            url = "https://github.com/%s/%s/trunk/%s" % (user, repo, filepath)
            FmUtil.cmdCall("svn", "export", "-q", "--force", url, tmpFile)
            return pathlib.Path(tmpFile).read_text()

    @staticmethod
    def pamParseCfgFile(filename):
        # PAM configuration file consists of directives having the following syntax:
        #   module_interface     control_flag     module_name module_arguments
        # For example:
        #   auth                 required         pam_wheel.so use_uid
        modIntfList = ["auth", "-auth", "account", "-account", "password", "-password", "session", "-session"]

        ret = dict()
        cur = None
        i = 0

        for line in pathlib.Path(filename).read_text().split("\n"):
            i += 1
            line = line.strip()
            if line == "" or line.startswith("#"):
                continue
            m = re.fullmatch("(\\S+)\\s+(\\S+)\\s+(.*)", line)
            if m is None:
                raise Exception("Error in PAM config \"%s\" (line %d): invalid line format" % (filename, i))
            try:
                i = modIntfList.index(m.group(1))
                if not (cur is None or cur in modIntfList[:i+1]):
                    raise Exception("Error in PAM config \"%s\" (line %d): invalid order" % (filename, i))
            except ValueError:
                raise Exception("Error in PAM config \"%s\" (line %d): invalid group" % (filename, i))
            cur = m.group(1)
            if cur not in ret:
                ret[cur] = []
            ret[cur].append((m.group(2), m.group(3)))
        return ret

    @staticmethod
    def pamGetModuleTypesProvided(pamModuleName):
        # read information from man pages
        # eg: read information from "/usr/share/man/man8/pam_securetty.8.bz2" for PAM module "pam_securetty.so"

        # sucks: no man page
        if pamModuleName == "pam_gnome_keyring.so":
            return ["password"]
        if pamModuleName == "pam_cracklib.so":
            return ["password"]

        # normal process
        manFile = os.path.join("/usr/share/man/man8", pamModuleName.replace(".so", ".8.bz2"))
        if not os.path.exists(manFile):
            raise Exception("man page file for %s does not exist" % (pamModuleName))
        with bz2.open(manFile, "rt") as f:
            ret = []
            bFlag = False
            for line in f.read().split("\n"):
                if not bFlag:
                    if re.fullmatch(r'\.SH "MODULE TYPES? PROVIDED"', line):    # chapter entered
                        bFlag = True
                else:
                    if line.startswith(".SH "):                                 # next chapter
                        break
                    ret += [x.group(1) for x in re.finditer(r'\\fB(.*?)\\fR', line)]
                    ret += [x.group(1) for x in re.finditer(r'\\fI(.*?)\\fR', line)]
            return ret

    @staticmethod
    def formatSize(value):
        # value is in bytes
        if value > 1024 * 1024 * 1024 * 1024:
            return "%.1fTiB" % (value / 1024 / 1024 / 1024 / 1024)
        elif value > 1024 * 1024 * 1024:
            return "%.1fGiB" % (value / 1024 / 1024 / 1024)
        elif value > 1024 * 1024:
            return "%.1fMiB" % (value / 1024 / 1024)
        elif value > 1024:
            return "%.1fKiB" % (value / 1024)
        else:
            assert False

    @staticmethod
    def formatFlops(value):
        # value is in gflops
        if value > 1024:
            return "%.1fTFLOPs" % (value / 1024)
        else:
            return "%.1fGFLOPs" % (value)

    @staticmethod
    def wipeHarddisk(devpath, fast=True):
        assert not re.fullmatch(".*[0-9]+", devpath)
        assert False
        # with open(devpath, 'wb') as f:
        #     f.write(bytearray(1024))

    @staticmethod
    def path2SwapServiceName(path):
        path = path[1:]                                     # path[1:] is to remove the starting "/"
        path = FmUtil.cmdCall("systemd-escape", path)
        path = path + ".swap"
        return path

    @staticmethod
    def swapServiceName2Path(serviceName):
        serviceName = serviceName[:-5]                          # item[:-5] is to remove ".swap"
        path = FmUtil.cmdCall("systemd-escape", "-u", serviceName)
        path = os.path.join("/", path)
        return path

    @staticmethod
    def systemdFindSwapServiceInDirectory(dirname, path):
        for f in os.listdir(dirname):
            fullf = os.path.join(dirname, f)
            if os.path.isfile(fullf) and fullf.endswith(".swap"):
                if os.path.realpath(path) == os.path.realpath(FmUtil.swapServiceName2Path(f)):
                    return f
        return None

    @staticmethod
    def systemdFindAllSwapServicesInDirectory(dirname):
        # get all the swap service name
        ret = []
        for f in os.listdir(dirname):
            fullf = os.path.join(dirname, f)
            if not os.path.isfile(fullf) or not fullf.endswith(".swap"):
                continue
            ret.append(f)
        return ret

    @staticmethod
    def systemdIsServiceEnabled(serviceName):
        obj = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM,
                                             Gio.DBusProxyFlags.NONE,
                                             None,
                                             "org.freedesktop.systemd1",            # bus_name
                                             "/org/freedesktop/systemd1",           # object_path
                                             "org.freedesktop.systemd1.Manager")    # interface_name
        return (obj.GetUnitFileState("(s)", serviceName) == "enabled")

    @staticmethod
    def systemdGetAllServicesEnabled():
        obj = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM,
                                             Gio.DBusProxyFlags.NONE,
                                             None,
                                             "org.freedesktop.systemd1",            # bus_name
                                             "/org/freedesktop/systemd1",           # object_path
                                             "org.freedesktop.systemd1.Manager")    # interface_name
        ret = []
        for unitFile, unitState in obj.ListUnitFiles():
            if unitState == "enabled":
                ret.append(os.path.basename(unitFile))
        return ret

    @staticmethod
    def systemdIsUnitRunning(unitName):
        obj = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM,
                                             Gio.DBusProxyFlags.NONE,
                                             None,
                                             "org.freedesktop.systemd1",            # bus_name
                                             "/org/freedesktop/systemd1",           # object_path
                                             "org.freedesktop.systemd1.Manager")    # interface_name
        unit = obj.GetUnit("(s)", unitName)
        return (unit.ActiveState == "active")

    @staticmethod
    def findBackendGraphicsDevices():
        ret = []
        context = pyudev.Context()
        for device in context.list_devices(subsystem='drm'):
            if "uaccess" in device.tags:
                continue
            if re.fullmatch("card[0-9]+", device.sys_name) is None:
                continue
            assert device.device_node is not None
            ret.append(device.device_node)
        return ret

    @staticmethod
    def getVendorIdAndDeviceIdByDevNode(path):
        # FIXME:
        # 1. should not udev, we can get sysfs directory major and minor id
        # 2. some device don't have "device" directory in sysfs (why)
        # 3. maybe we should raise Exceptionn when failure
        context = pyudev.Context()
        for device in context.list_devices():
            if device.device_node == path:
                fn1 = os.path.join(device.sys_path, "device", "vendor")
                fn2 = os.path.join(device.sys_path, "device", "device")
                return (int(pathlib.Path(fn1).read_text(), 16), int(pathlib.Path(fn2).read_text(), 16))
        return None

    @staticmethod
    def is_int(s):
        try:
            int(s)
            return True
        except ValueError:
            return False

    @staticmethod
    def testZipFile(filename):
        with zipfile.ZipFile(filename, 'r', zipfile.ZIP_DEFLATED) as z:
            return (z.testzip() is None)

    @staticmethod
    def expandRsyncPatternToParentDirectories(pattern):
        ret = [pattern]
        m = re.fullmatch("(.*)/(\\*+)?", pattern)
        if m is not None:
            pattern = m.group(1)
        pattern = os.path.dirname(pattern)
        while pattern not in ["", "/"]:
            ret.append(pattern)
            pattern = os.path.dirname(pattern)
        return reversed(ret)

    @staticmethod
    def getPhysicalMemorySize():
        with open("/proc/meminfo", "r") as f:
            # We return memory size in GB.
            # Since the memory size shown in /proc/meminfo is always a
            # little less than the real size because various sort of
            # reservation, so we do a "+1"
            m = re.search("^MemTotal:\\s+(\\d+)", f.read())
            return int(m.group(1)) // 1024 // 1024 + 1

    @staticmethod
    def md5hash(s):
        return hashlib.md5(s.encode('utf-8')).hexdigest()

    @staticmethod
    def removeDuplication(theList):
        ret = []
        theSet = set()
        for k in theList:
            if k not in theSet:
                ret.append(k)
                theSet.add(k)
        return ret

    @staticmethod
    def pad(string, length):
        '''Pad a string with spaces.'''
        if len(string) <= length:
            return string + ' ' * (length - len(string))
        else:
            return string[:length - 3] + '...'

    @staticmethod
    def terminal_width():
        '''Determine width of terminal window.'''
        try:
            width = int(os.environ['COLUMNS'])
            if width > 0:
                return width
        except:
            pass
        try:
            query = struct.pack('HHHH', 0, 0, 0, 0)
            response = fcntl.ioctl(1, termios.TIOCGWINSZ, query)
            width = struct.unpack('HHHH', response)[1]
            if width > 0:
                return width
        except:
            pass
        return 80

    @staticmethod
    def realPathSplit(path):
        """os.path.split() only split a path into 2 component, I believe there are reasons, but it is really inconvenient.
           So I write this function to split a unix path into basic components.
           Reference: http://stackoverflow.com/questions/3167154/how-to-split-a-dos-path-into-its-components-in-python"""

        folders = []
        while True:
            path, folder = os.path.split(path)
            if folder != "":
                folders.append(folder)
            else:
                if path != "":
                    folders.append(path)
                break
        if path.startswith("/"):
            folders.append("")
        folders.reverse()
        return folders

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
        return FmUtil.devPathPartitionToDiskAndPartitionId(partitionDevPath)[0]

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
    def devPathTrivialToByUuid(devPath):
        ret = FmUtil.cmdCall("blkid", devPath)
        m = re.search("UUID=\"(\\S*)\"", ret, re.M)
        if m is None:
            raise Exception("the specified device has no UUID")
        ret = os.path.join("/dev/disk/by-uuid", m.group(1))
        if not os.path.exists(ret):
            raise Exception("no corresponding device node in /dev/disk/by-uuid")
        return ret

    @staticmethod
    def isBlkDevUsbStick(devPath):
        devName = os.path.basename(devPath)

        remfile = "/sys/block/%s/removable" % (devName)
        if not os.path.exists(remfile):
            return False
        if pathlib.Path(remfile).read_text().rstrip("\n") != "1":
            return False

        ueventFile = "/sys/block/%s/device/uevent" % (devName)
        if "DRIVER=sd" not in pathlib.Path(ueventFile).read_text().split("\n"):
            return False

        return True

    @staticmethod
    def getBlkDevModel(devPath):
        ret = FmUtil.cmdCall("lsblk", "-o", "MODEL", "-n", devPath)
        ret = ret.strip("\r\n")
        if ret == "":
            return "unknown"
        else:
            return ret

    @staticmethod
    def getBlkDevSize(devPath):
        out = FmUtil.cmdCall("blockdev", "--getsz", devPath)
        return int(out) * 512        # unit is byte

    @staticmethod
    def getBlkDevUuid(devPath):
        """UUID is also called FS-UUID, PARTUUID is another thing"""

        ret = FmUtil.cmdCall("blkid", devPath)
        m = re.search("UUID=\"(\\S*)\"", ret, re.M)
        if m is not None:
            return m.group(1)
        else:
            return ""

    @staticmethod
    def getBlkDevPartitionTableType(devPath):
        if not FmUtil.devPathIsDiskOrPartition(devPath):
            devPath = FmUtil.devPathPartitionToDisk(devPath)

        ret = FmUtil.cmdCall("blkid", "-o", "export", devPath)
        m = re.search("^PTTYPE=(\\S+)$", ret, re.M)
        if m is not None:
            return m.group(1)
        else:
            return ""

    @staticmethod
    def getBlkDevFsType(devPath):
        ret = FmUtil.cmdCall("blkid", "-o", "export", devPath)
        m = re.search("^TYPE=(\\S+)$", ret, re.M)
        if m is not None:
            return m.group(1).lower()
        else:
            return ""

    @staticmethod
    def scsiGetHostControllerPath(devPath):
        ctx = pyudev.Context()
        dev = pyudev.Device.from_device_file(ctx, devPath)

        hostPath = "/sys" + dev["DEVPATH"]
        while True:
            m = re.search("^host[0-9]+$", os.path.basename(hostPath), re.M)
            if m is not None:
                break
            hostPath = os.path.dirname(hostPath)
            assert hostPath != "/"
        return hostPath

    @staticmethod
    def isValidKernelArch(archStr):
        return True

    @staticmethod
    def isValidKernelVer(verStr):
        return True

    @staticmethod
    def getHostArch():
        # Code copied from linux kernel Makefile:
        #   /usr/bin/uname -m | /bin/sed -e s/i.86/i386/ -e s/sun4u/sparc64/
        #                                -e s/arm.*/arm/ -e s/sa110/arm/
        #                                -e s/s390x/s390/ -e s/parisc64/parisc/
        #                                -e s/ppc.*/powerpc/ -e s/mips.*/mips/
        #                                -e s/sh.*/sh/
        ret = platform.machine()
        ret = re.sub("i.86", "i386", ret)
        ret = re.sub("sun4u", "sparc64", ret)
        ret = re.sub("arm.*", "arm", ret)
        ret = re.sub("sall0", "arm", ret)
        ret = re.sub("s390x", "s390", ret)
        ret = re.sub("paris64", "parisc", ret)
        ret = re.sub("ppc.*", "powerpc", ret)
        ret = re.sub("mips.*", "mips", ret)
        ret = re.sub("sh.*", "sh", ret)
        return ret

    @staticmethod
    def isTwoDirSame(dir1, dir2):
        # FIXME: we could use python to do this
        return FmUtil.cmdCallWithRetCode("diff", "-r", dir1, dir2)[0] == 0

    @staticmethod
    def fileHasSameContent(filename1, filename2):
        buf1 = b''
        with open(filename1, "rb") as f:
            buf1 = f.read()
        buf2 = b''
        with open(filename2, "rb") as f:
            buf2 = f.read()
        return buf1 == buf2

    @staticmethod
    def touchFile(filename):
        assert not os.path.exists(filename)
        f = open(filename, 'w')
        f.close()

    @staticmethod
    def compareFile(filename, buf):
        with open(filename, "r") as f:
            return buf == f.read()

    @staticmethod
    def compareVersion(verstr1, verstr2):
        """eg: 3.9.11-gentoo-r1 or 3.10.7-gentoo"""

        partList1 = verstr1.split("-")
        partList2 = verstr2.split("-")

        verList1 = partList1[0].split(".")
        verList2 = partList2[0].split(".")

        if len(verList1) == 3 and len(verList2) == 3:
            ver1 = int(verList1[0]) * 10000 + int(verList1[1]) * 100 + int(verList1[2])
            ver2 = int(verList2[0]) * 10000 + int(verList2[1]) * 100 + int(verList2[2])
        elif len(verList1) == 2 and len(verList2) == 2:
            ver1 = int(verList1[0]) * 100 + int(verList1[1])
            ver2 = int(verList2[0]) * 100 + int(verList2[1])
        elif len(verList1) == 1 and len(verList2) == 1:
            ver1 = int(verList1[0])
            ver2 = int(verList2[0])
        else:
            assert False

        if ver1 > ver2:
            return 1
        elif ver1 < ver2:
            return -1

        if len(partList1) >= 2 and len(partList2) == 1:
            return 1
        elif len(partList1) == 1 and len(partList2) >= 2:
            return -1

        p1 = "-".join(partList1[1:])
        p2 = "-".join(partList2[1:])
        if p1 > p2:
            return 1
        elif p1 < p2:
            return -1

        return 0

    @staticmethod
    def removeDirContentExclude(dirPath, excludeList):
        for fn in os.listdir(dirPath):
            if fn not in excludeList:
                robust_layer.simple_fops.rm(os.path.join(dirPath, fn))

    @staticmethod
    def removeEmptyDir(dirname):
        if len(os.listdir(dirname)) == 0:
            os.rmdir(dirname)

    @staticmethod
    def isCfgFileReallyNotEmpty(filename):
        with open(filename, "r") as f:
            for line in f.read().split("\n"):
                if line.strip() == "":
                    continue
                if line.startswith("#"):
                    continue
                return True
        return False

    @staticmethod
    def ensureAncesterDir(filename):
        assert os.path.isabs(filename)

        splist = []
        while True:
            filename, bf = os.path.split(filename)
            if bf == "":
                break
            splist.insert(0, bf)

        curd = "/"
        for d in splist[:-1]:
            curd = os.path.join(curd, d)
            if not os.path.isdir(curd):
                os.mkdir(curd)

    @staticmethod
    def getDirFreeSpace(dirname):
        """Returns free space in MB"""

        ret = FmUtil.cmdCall("df", "-m", dirname)
        m = re.search("^.* + [0-9]+ +[0-9]+ +([0-9]+) + [0-9]+% .*$", ret, re.M)
        return int(m.group(1))

    @staticmethod
    def getMountDeviceForPath(pathname):
        buf = FmUtil.cmdCall("mount")
        for line in buf.split("\n"):
            m = re.search("^(.*) on (.*) type ", line)
            if m is not None and m.group(2) == pathname:
                return m.group(1)
        return None

    @staticmethod
    def isMountPoint(pathname):
        return FmUtil.getMountDeviceForPath(pathname) is not None

    @staticmethod
    def isDirAncestor(path1, path2):
        """check if path2 is the ancestor of path1"""
        return path1.startswith(path2 + "/")

    @staticmethod
    def getHomeDir(userName):
        if userName == "root":
            return "/root"
        else:
            return os.path.join("/home", userName)

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
    def cmdCallWithInput(cmd, inStr, *kargs):
        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             input=inStr, universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def cmdCallIgnoreResult(cmd, *kargs):
        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)

    @staticmethod
    def cmdCallTestSuccess(cmd, *kargs):
        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        return (ret.returncode == 0)

    @staticmethod
    def shellCall(cmd):
        # call command with shell to execute backstage job
        # scenarios are the same as FmUtil.cmdCall

        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def shellCallWithRetCode(cmd):
        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        return (ret.returncode, ret.stdout.rstrip())

    @staticmethod
    def shellCallIgnoreResult(cmd):
        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)

    @staticmethod
    def cmdExec(cmd, *kargs):
        # call command to execute frontend job
        #
        # scenario 1, process group receives SIGTERM, SIGINT and SIGHUP:
        #   * callee must auto-terminate, and cause no side-effect
        #   * caller must be terminate AFTER child-process, and do neccessary finalization
        #   * termination information should be printed by callee, not caller
        # scenario 2, caller receives SIGTERM, SIGINT, SIGHUP:
        #   * caller should terminate callee, wait callee to stop, do neccessary finalization, print termination information, and be terminated by signal
        #   * callee does not need to treat this scenario specially
        # scenario 3, callee receives SIGTERM, SIGINT, SIGHUP:
        #   * caller detects child-process failure and do appopriate treatment
        #   * callee should print termination information

        # FIXME, the above condition is not met, FmUtil.shellExec has the same problem

        ret = subprocess.run([cmd] + list(kargs), universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        ret.check_returncode()

    @staticmethod
    def shellExec(cmd):
        ret = subprocess.run(cmd, shell=True, universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)
        ret.check_returncode()

    @staticmethod
    async def asyncStartCmdExec(cmd, *kargs, loop=None):
        assert loop is not None
        proc = await asyncio.create_subprocess_exec(cmd, *kargs, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, loop=loop)
        return (proc, proc.stdout)

    @staticmethod
    async def asyncWaitCmdExec(proc):
        retcode = await proc.wait()
        if retcode != 0:
            raise subprocess.CalledProcessError(retcode, [])      # use subprocess.CalledProcessError since there's no equivalent in asyncio

    @staticmethod
    def getFreeTcpPort(start_port=10000, end_port=65536):
        for port in range(start_port, end_port):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind((('', port)))
                return port
            except socket.error:
                continue
            finally:
                s.close()
        raise Exception("No valid tcp port in [%d,%d]." % (start_port, end_port))

    @staticmethod
    def waitTcpService(ip, port):
        ip = ip.replace(".", "\\.")
        while True:
            out = FmUtil.cmdCall("netstat", "-lant")
            m = re.search("tcp +[0-9]+ +[0-9]+ +(%s:%d) +.*" % (ip, port), out)
            if m is not None:
                return
            time.sleep(1.0)

    @staticmethod
    def newBuffer(ch, li):
        ret = bytearray()
        i = 0
        while i < li:
            ret.append(ch)
            i += 1
        return bytes(ret)

    @staticmethod
    def getMakeConfVar(makeConfFile, varName):
        """Returns variable value, returns "" when not found
           Multiline variable definition is not supported yet"""

        buf = ""
        with open(makeConfFile, 'r') as f:
            buf = f.read()

        m = re.search("^%s=\"(.*)\"$" % (varName), buf, re.MULTILINE)
        if m is None:
            return ""
        varVal = m.group(1)

        while True:
            m = re.search("\\${(\\S+)?}", varVal)
            if m is None:
                break
            varName2 = m.group(1)
            varVal2 = FmUtil.getMakeConfVar(makeConfFile, varName2)
            if varVal2 is None:
                varVal2 = ""

            varVal = varVal.replace(m.group(0), varVal2)

        return varVal

    @staticmethod
    def setMakeConfVar(makeConfFile, varName, varValue):
        """Create or set variable in make.conf
           Multiline variable definition is not supported yet"""

        endEnter = False
        buf = ""
        with open(makeConfFile, 'r') as f:
            buf = f.read()
            if buf[-1] == "\n":
                endEnter = True

        m = re.search("^%s=\"(.*)\"$" % (varName), buf, re.MULTILINE)
        if m is not None:
            if m.group(1) != varValue:
                newLine = "%s=\"%s\"" % (varName, varValue)
                buf = buf.replace(m.group(0), newLine)
                with open(makeConfFile, 'w') as f:
                    f.write(buf)
        else:
            with open(makeConfFile, 'a') as f:
                if not endEnter:
                    f.write("\n")
                f.write("%s=\"%s\"\n" % (varName, varValue))

    @staticmethod
    def updateMakeConfVarAsValueSet(makeConfFile, varName, valueList):
        """Check variable in make.conf
           Create or set variable in make.conf"""

        endEnter = False
        buf = ""
        with open(makeConfFile, 'r') as f:
            buf = f.read()
            if buf[-1] == "\n":
                endEnter = True

        m = re.search("^%s=\"(.*)\"$" % (varName), buf, re.MULTILINE)
        if m is not None:
            if set(m.group(1).split(" ")) != set(valueList):
                newLine = "%s=\"%s\"" % (varName, " ".join(valueList))
                buf = buf.replace(m.group(0), newLine)
                with open(makeConfFile, 'w') as f:
                    f.write(buf)
        else:
            with open(makeConfFile, 'a') as f:
                if not endEnter:
                    f.write("\n")
                f.write("%s=\"%s\"\n" % (varName, " ".join(valueList)))

    @staticmethod
    def removeMakeConfVar(makeConfFile, varName):
        """Remove variable in make.conf
           Multiline variable definition is not supported yet"""

        endEnterCount = 0
        lineList = []
        with open(makeConfFile, 'r') as f:
            buf = f.read()
            endEnterCount = len(buf) - len(buf.rstrip("\n"))

            buf = buf.rstrip("\n")
            for line in buf.split("\n"):
                if re.search("^%s=" % (varName), line) is None:
                    lineList.append(line)

        buf = ""
        for line in lineList:
            buf += line + "\n"
        buf = buf.rstrip("\n")
        for i in range(0, endEnterCount):
            buf += "\n"

        with open(makeConfFile, 'w') as f:
            f.write(buf)

    @staticmethod
    def genSelfSignedCertAndKey(cn, keysize):
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, keysize)

        cert = crypto.X509()
        cert.get_subject().CN = cn
        cert.set_serial_number(random.randint(0, 65535))
        cert.gmtime_adj_notBefore(100 * 365 * 24 * 60 * 60 * -1)
        cert.gmtime_adj_notAfter(100 * 365 * 24 * 60 * 60)
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        cert.sign(k, 'sha1')

        return (cert, k)

    @staticmethod
    def dumpCertAndKey(cert, key, certFile, keyFile):
        with open(certFile, "wb") as f:
            buf = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)
            f.write(buf)
            os.fchmod(f.fileno(), 0o644)

        with open(keyFile, "wb") as f:
            buf = crypto.dump_privatekey(crypto.FILETYPE_PEM, key)
            f.write(buf)
            os.fchmod(f.fileno(), 0o600)

    @staticmethod
    def getCpuArch():
        ret = platform.machine()
        if ret == "x86_64":
            return "amd64"
        else:
            return ret

    @staticmethod
    def getCpuModel():
        return FmUtil.cmdCall("uname", "-p")

    @staticmethod
    def repoIsSysFile(fbasename):
        """fbasename value is like "sys-devel", "sys-devel/gcc", "profiles", etc"""

        if fbasename.startswith("."):
            return True
        if fbasename == "licenses" or fbasename.startswith("licenses/"):
            return True
        if fbasename == "metadata" or fbasename.startswith("metadata/"):
            return True
        if fbasename == "profiles" or fbasename.startswith("profiles/"):
            return True
        return False

    @staticmethod
    def repoGetCategoryDirList(repoDir):
        ret = FmUtil.getFileList(repoDir, 1, "d")
        ret = [x for x in ret if not FmUtil.repoIsSysFile(x)]
        return ret

    @staticmethod
    def repoGetEbuildDirList(repoDir):
        ret = FmUtil.getFileList(repoDir, 2, "d")
        ret = [x for x in ret if not FmUtil.repoIsSysFile(x)]
        return ret

    @staticmethod
    def repoRemovePackageAndCategory(repoDir, pkgName):
        ebuildDir = os.path.join(repoDir, pkgName)
        shutil.rmtree(ebuildDir)
        categoryDir = os.path.dirname(ebuildDir)
        if os.listdir(categoryDir) == []:
            os.rmdir(categoryDir)

    @staticmethod
    def repoGetRepoName(repoDir):
        layoutFn = os.path.join(repoDir, "metadata", "layout.conf")
        if os.path.exists(layoutFn):
            m = re.search("repo-name = (\\S+)", pathlib.Path(layoutFn).read_text(), re.M)
            if m is not None:
                return m.group(1)

        repoNameFn = os.path.join(repoDir, "profiles", "repo_name")
        if os.path.exists(repoNameFn):
            ret = pathlib.Path(repoNameFn).read_text()
            ret = ret.rstrip("\n").rstrip()
            ret = ret.replace(" ", "-")                         # it seems this translation is neccessary
            return ret

        # fatal error: can not get repoName
        return None

    @staticmethod
    def repoGetPkgExtraFilesWildcards(pkgDbDir, pkgAtom):
        # get the content of pkg_extra_files()
        ebuildFullFn = glob.glob(os.path.join(pkgDbDir, pkgAtom, "*.ebuild"))[0]
        lineList = pathlib.Path(ebuildFullFn).read_text().split("\n")
        startIdx = None
        endIdx = None
        for i in range(0, len(lineList)):
            if lineList[i] == "pkg_extra_files() {":
                startIdx = i
                continue
            if startIdx is not None and lineList[i] == "}":
                endIdx = i
                break
        if startIdx is None:
            return []

        # run pkg_extra_files(), get the result
        # FIXME: not the context only have CHOST, it lacks a lot
        funcContent = "\n".join(lineList[startIdx:endIdx+1])
        ret = FmUtil.cmdCall("bash", "-c", "%s\nexport CHOST=%s\npkg_extra_files" % (funcContent, FmUtil.portageGetChost()))

        # convert the result to wildcards
        wildcards = []
        for w in ret.split("\n"):
            w = w.strip()
            if w == "" or w.startswith("#"):
                continue
            if w.startswith("~"):
                continue
            wildcards.append("+ %s" % (w))
            if os.path.realpath(w) != w:
                wildcards.append("+ %s" % (os.path.realpath(w)))

        return wildcards

    @staticmethod
    def wgetSpider(url):
        return FmUtil.cmdCallTestSuccess("wget", "--spider", url)

    @staticmethod
    def wgetDownload(url, localFile=None):
        if localFile is None:
            FmUtil.cmdExec("wget", "-q", "--show-progress", *robust_layer.wget.additional_param(), url)
        else:
            FmUtil.cmdExec("wget", "-q", "--show-progress", *robust_layer.wget.additional_param(), "-O", localFile, url)

    @staticmethod
    def downloadIfNewer(url, fullfn):
        if os.path.exists(fullfn):
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=robust_layer.TIMEOUT) as resp:
                remoteTm = datetime.strptime(resp.headers["Last-Modified"], "%a, %d %b %Y %H:%M:%S %Z")
                localTm = datetime.utcfromtimestamp(os.path.getmtime(fullfn))
                if remoteTm <= localTm:
                    return localTm
        with urllib.request.urlopen(url, timeout=robust_layer.TIMEOUT) as resp:
            with open(fullfn, "wb") as f:
                f.write(resp.read())
            remoteTm = datetime.strptime(resp.headers["Last-Modified"], "%a, %d %b %Y %H:%M:%S %Z")
            os.utime(fullfn, (remoteTm.timestamp(), remoteTm.timestamp()))
            return remoteTm

    @staticmethod
    def udevIsPureUaccessRuleFile(filepath):
        if not os.path.basename(filepath).startswith("72-"):
            return False

        lineList = [x.strip() for x in pathlib.Path(filepath).read_text().split("\n")]

        # find and check first line
        firstLineNo = -1
        firstLineTagName = None
        for i in range(0, len(lineList)):
            line = lineList[i]
            if line != "" and not line.startswith("#"):
                firstLineNo = i
                m = re.fullmatch('ACTION=="remove", GOTO="(.*)_end"', line)
                if m is not None:
                    firstLineTagName = m.group(1)
                break
        if firstLineNo == -1:
            return False
        if firstLineTagName is None:
            return False

        # find and check last line
        lastLineNo = -1
        for i in reversed(range(firstLineNo + 1, len(lineList))):
            line = lineList[i]
            if line != "" and not line.startswith("#"):
                if re.fullmatch('LABEL="%s_end"' % (firstLineTagName), line) is not None:
                    lastLineNo = i
                break
        if lastLineNo == -1:
            return False

        # check middle lines
        pat = '.*, TAG-="uaccess", TAG-="seat", TAG-="master-of-seat", ENV{ID_SEAT}="", ENV{ID_AUTOSEAT}="", ENV{ID_FOR_SEAT}=""'
        for i in range(firstLineNo + 1, lastLineNo):
            line = lineList[i]
            if line != "" and not line.startswith("#"):
                if re.fullmatch(pat, line) is None:
                    return False

        return True

    @staticmethod
    def portageGetMakeConfList():
        return FmUtil._portageGetMakeConfListImpl(os.path.realpath("/etc/portage/make.profile"))

    @staticmethod
    def _portageGetMakeConfListImpl(curDir):
        ret = []

        parentFn = os.path.join(curDir, "parent")
        if os.path.exists(parentFn):
            with open(parentFn) as f:
                for line in f.read().split("\n"):
                    if line.strip() != "":
                        ret += FmUtil._portageGetMakeConfListImpl(os.path.realpath(os.path.join(curDir, line)))

        makeConfFn = os.path.join(curDir, "make.defaults")
        if os.path.exists(makeConfFn):
            ret.append(makeConfFn)

        return ret

    @staticmethod
    def portageIsPkgInstalled(pkgName):
        """pkgName can be package-name or package-atom"""

        vartree = portage.db[portage.root]["vartree"]
        varCpvList = vartree.dbapi.match(pkgName)
        return len(varCpvList) != 0

    @staticmethod
    def portageIsPkgInstallable(pkgName):
        """pkgName can be package-name or package-atom"""

        porttree = portage.db[portage.root]["porttree"]
        cpvList = porttree.dbapi.match(pkgName)
        return len(cpvList) > 0

    @staticmethod
    def portageIsPkgMultiSlot(porttree, pkgName):
        cpvList = porttree.dbapi.match(pkgName)
        assert len(cpvList) > 0

        slot = None
        for cpv in cpvList:
            nslot = porttree.dbapi.aux_get(cpv, ["SLOT"])[0]
            if slot is not None and slot != nslot:
                return True
            slot = nslot

        return False

    @staticmethod
    def portageGetPkgNameFromPkgAtom(pkgAtom):
        pkgName = pkgAtom

        while pkgName[0] in ["<", ">", "=", "!", "~"]:
            pkgName = pkgName[1:]

        i = 0
        while i < len(pkgName):
            if pkgName[i] == "-" and i < len(pkgName) - 1 and pkgName[i + 1].isdigit():
                pkgName = pkgName[:i]
                break
            i = i + 1

        return pkgName

    @staticmethod
    def portageIsSimplePkgAtom(pkgAtom):
        if ":" in pkgAtom:
            return False
        for op in [">", ">=", "<", "<=", "=", "~", "!"]:
            if pkgAtom.startswith(op):
                return False
        return True

    @staticmethod
    def portageGetSameSlotPkgAtom(pkgAtom):
        p = portage.db[portage.root]["porttree"].dbapi
        slot = p.aux_get(pkgAtom, ["SLOT"])[0]
        pkgName = portage.versions.pkgsplit(pkgAtom)[0]
        return p.match("%s:%s" % (pkgName, slot))

    @staticmethod
    def portageGetInstalledPkgAtomList(portageDbDir):
        pkgAtomList = []
        for fbasename in sorted(FmUtil.getFileList(portageDbDir, 2, "d")):
            if FmUtil.repoIsSysFile(fbasename):
                continue
            if fbasename.split("/")[1].startswith("-MERGING"):
                continue
            pkgAtomList.append(fbasename)
        return pkgAtomList

    @staticmethod
    def portageGetInstalledFileSet(expanded=False):
        fileSet = set()

        if True:
            cmdStr = r"cat /var/db/pkg/*/*/CONTENTS "
            cmdStr += r'| sed -e "s:^obj \(.*\) [[:xdigit:]]\+ [[:digit:]]\+$:\1:" '
            cmdStr += r'| sed -e "s:^sym \(.*\) -> .* .*$:\1:" '
            cmdStr += r'| sed -e "s:^dir \(.*\)$:\1:" '
            ret = FmUtil.shellCall(cmdStr)
            fileSet = set(ret.split("\n"))

        if expanded:
            # deal with .keep
            nret = set()
            for f in fileSet:
                if os.path.isdir(f) and os.path.exists(os.path.join(f, ".keep")):
                    nret.add(os.path.join(f, ".keep"))
            fileSet |= nret

            # deal with *.py
            nret = set()
            for f in fileSet:
                if f.endswith(".py"):
                    if os.path.exists(f + "c"):
                        nret.add(f + "c")
                    if os.path.exists(f + "o"):
                        nret.add(f + "o")
            fileSet |= nret

            # deal with __pycache__
            for dn in ["/usr/lib", "/usr/lib64", "/usr/libexec"]:
                ret = FmUtil.cmdCall("find", dn, "-regex", r'.*/__pycache__\(/.*\)?')
                fileSet |= set(ret.split("\n"))

            # deal with directory symlink
            nret = set()
            for f in fileSet:
                f2 = os.path.join(os.path.realpath(os.path.dirname(f)), os.path.basename(f))
                if f2 != f:
                    nret.add(f2)
            fileSet |= nret

        return fileSet

    @staticmethod
    def portageReadCfgMaskFile(filename):
        """Returns list<package-atom>"""

        with open(filename, "r") as f:
            ret = []
            for line in f.read().split("\n"):
                if line == "" or line.startswith("#"):
                    continue
                ret.append(line)
            return ret

    @staticmethod
    def portageParseCfgUseFile(buf):
        """Returns list<tuple(package-atom, list<use-flag>)>"""

        ret = []
        for line in buf.split("\n"):
            if line == "" or line.startswith("#"):
                continue
            itemlist = line.split()
            ret.append((itemlist[0], itemlist[1:]))
        return ret

    @staticmethod
    def portageGenerateCfgUseFileByUseFlagList(useFlagList):
        buf = ""
        for pkgAtom, useList in useFlagList:
            buf += "%s %s\n" % (pkgAtom, " ".join(useList))
        return buf

    @staticmethod
    def portageGenerateCfgUseFileByUseMap(useMap):
        useFlagList = []
        for pkgName in sorted(useMap.keys()):
            item = (pkgName, sorted(list(useMap[pkgName])))
            useFlagList.append(item)
        return FmUtil.portageGenerateCfgUseFileByUseFlagList(useFlagList)

    @staticmethod
    def portageGetGentooHttpMirror(makeConf, defaultMirror, filesWanted):
        for mr in FmUtil.getMakeConfVar(makeConf, "GENTOO_MIRRORS").split():
            good = True
            for fn in filesWanted:
                if not FmUtil.wgetSpider("%s/%s" % (mr, fn)):
                    good = False
                    break
            if good:
                return mr
        return defaultMirror

    @staticmethod
    def portageGetGentooPortageRsyncMirror(makeConf, defaultMirror):
        for mr in FmUtil.getMakeConfVar(makeConf, "RSYNC_MIRRORS").split():
            return mr
        return defaultMirror

    @staticmethod
    def portageGetLinuxKernelMirror(makeConf, defaultMirror, kernelVersion, filesWanted):
        # we support two mirror file structure:
        # 1. all files placed under /: a simple structure suitable for local mirrors
        # 2. /{v3.x,v4.x,...}/*:       an overly complicated structure used by official kernel mirrors

        subdir = None
        for i in range(3, 9):
            if kernelVersion.startswith(str(i)):
                subdir = "v%d.x" % (i)
        assert subdir is not None

        mirrorList = FmUtil.getMakeConfVar(makeConf, "KERNEL_MIRRORS").split()

        # try file structure 1
        for mr in mirrorList:
            good = True
            for fn in filesWanted:
                if not FmUtil.wgetSpider("%s/%s" % (mr, fn)):
                    good = False
                    break
            if good:
                return (mr, filesWanted)

        # try file structure 2
        for mr in mirrorList:
            good = True
            for fn in filesWanted:
                if not FmUtil.wgetSpider("%s/%s/%s" % (mr, subdir, fn)):
                    good = False
                    break
            if good:
                return (mr, ["%s/%s" % (subdir, fn) for fn in filesWanted])

        # use default mirror
        return (defaultMirror, ["%s/%s" % (subdir, fn) for fn in filesWanted])

    @staticmethod
    def portageGetLinuxFirmwareMirror(makeConf, defaultMirror, filesWanted):
        ret = defaultMirror
        for mr in FmUtil.getMakeConfVar(makeConf, "KERNEL_MIRRORS").split():
            good = True
            for fn in filesWanted:
                if not FmUtil.wgetSpider("%s/firmware/%s" % (mr, fn)):
                    good = False
                    break
            if good:
                ret = mr
                break
        return (ret, ["firmware/%s" % (fn) for fn in filesWanted])

    @staticmethod
    def portageGetArch():
        return "amd64"

    @staticmethod
    def portageGetArchAndSubArch():
        # FIXME
        return ("amd64", "amd64")

    @staticmethod
    def portageGetChost():
        return FmUtil.shellCall("portageq envvar CHOST 2>/dev/null").rstrip("\n")

    @staticmethod
    def portageGetJobCount(makeConf):
        s = FmUtil.getMakeConfVar(makeConf, "EMERGE_DEFAULT_OPTS")
        m = re.search("--jobs=([0-9]+)", s)
        if m is not None:
            return int(m.group(1))
        else:
            return 1

    @staticmethod
    def portageReadWorldFile(worldFile):
        pkgList = pathlib.Path(worldFile).read_text().split("\n")
        return [x for x in pkgList if x != ""]

    @staticmethod
    def portageGetVcsTypeAndUrlFromReposConfFile(reposConfFile):
        with open(reposConfFile, "r") as f:
            buf = f.read()
            m = re.search("^sync-type *= *(.*)$", buf, re.M)
            if m is None:
                return None
            vcsType = m.group(1)
            url = re.search("^sync-uri *= *(.*)$", buf, re.M).group(1)
            return (vcsType, url)

    @staticmethod
    def portageParseVarDbPkgContentFile(filename):
        # portage must be patched
        #
        # returns [(type, path, XXX)]
        #   when type == "dir", XXX is permission, owner, group
        #   when type == "obj", XXX is md5sum, permission, owner, group
        #   when type == "sym", XXX is target, owner, group

        ret = []
        with open(filename, "r", encoding="UTF-8") as f:
            for line in f.readlines():
                elem_list = line.strip().split()
                if elem_list[0] == "dir":
                    item = ("dir", " ".join(elem_list[1:-3]), int(elem_list[-3], 8), int(elem_list[-2]), int(elem_list[-1]))
                    ret.append(item)
                elif elem_list[0] == "obj":
                    item = ("obj", " ".join(elem_list[1:-5]), elem_list[-5], int(elem_list[-3], 8), int(elem_list[-2]), int(elem_list[-1]))
                    ret.append(item)
                elif elem_list[0] == "sym":
                    middle_list = " ".join(elem_list[1:-3]).split(" -> ")
                    assert len(middle_list) == 2
                    item = ("sym", middle_list[0], middle_list[1], int(elem_list[-2]), int(elem_list[-1]))
                    ret.append(item)
                else:
                    assert False
        return ret

    @staticmethod
    def portagePatchRepository(repoName, repoDir, patchTypeName, patchDir, jobNumber=None):
        # patch eclass files
        eclassDir = os.path.join(patchDir, "eclass")
        if os.path.exists(eclassDir):
            dstDir = os.path.join(repoDir, "eclass")
            FmUtil._portagePatchRepositoryExecScript(repoName, patchTypeName, patchDir, eclassDir, dstDir)

        # patch profile files
        profilesDir = os.path.join(patchDir, "profiles")
        if os.path.exists(profilesDir):
            for profileDir in FmUtil.listLeafDirs(profilesDir):
                srcDir = os.path.join(patchDir, "profiles", profileDir)
                dstDir = os.path.join(repoDir, "profiles", profileDir)
                FmUtil._portagePatchRepositoryExecScript(repoName, patchTypeName, patchDir, srcDir, dstDir)

        # patch packages
        pendingDstDirList = []
        for categoryDir in os.listdir(patchDir):
            if categoryDir in ["README", "eclass", "profiles"]:
                continue
            fullCategoryDir = os.path.join(patchDir, categoryDir)
            for ebuildDir in os.listdir(fullCategoryDir):
                srcDir = os.path.join(fullCategoryDir, ebuildDir)
                dstDir = os.path.join(repoDir, categoryDir, ebuildDir)
                FmUtil._portagePatchRepositoryExecScript(repoName, patchTypeName, patchDir, srcDir, dstDir)
                if len(glob.glob(os.path.join(dstDir, "*.ebuild"))) == 0:
                    # all ebuild files are deleted, it means this package is removed
                    robust_layer.simple_fops.rm(dstDir)
                    if len(os.listdir(fullCategoryDir)) == 0:
                        robust_layer.simple_fops.rm(fullCategoryDir)
                    continue
                pendingDstDirList.append(dstDir)

        # generate manifest for patched packages
        loop = asyncio.get_event_loop()
        if jobNumber is None:
            pool = asyncio_pool.AioPool(loop=loop)
        else:
            pool = asyncio_pool.AioPool(size=jobNumber, loop=loop)
        for dstDir in pendingDstDirList:
            pool.spawn_n(FmUtil._portagePatchRepositoryGenEbuildManifest(dstDir))
        loop.run_until_complete(pool.join())

    @staticmethod
    def _portagePatchRepositoryExecScript(repoName, patchTypeName, patchDir, srcDir, dstDir):
        for fullfn in glob.glob(os.path.join(srcDir, "*")):
            if not os.path.isfile(fullfn):
                continue
            if not os.path.exists(dstDir):
                print("%s script \"%s\" for \"%s\" is outdated." % (patchTypeName, fullfn[len(patchDir) + 1:], repoName))
                continue
            out = None
            with TempChdir(dstDir):
                assert fullfn.endswith(".py")
                out = FmUtil.cmdCall("python3", fullfn)     # FIXME, should respect shebang
            if out == "outdated":
                print("WARNING: %s script \"%s\" for \"%s\" is outdated." % (patchTypeName, fullfn[len(patchDir) + 1:], repoName))
            elif out == "":
                pass
            else:
                raise Exception("%s script \"%s\" for \"%s\" exits with error \"%s\"." % (patchTypeName, fullfn[len(patchDir) + 1:], repoName, out))

    @staticmethod
    async def _portagePatchRepositoryGenEbuildManifest(ebuildDir):
        # operate on any ebuild file generates manifest for the whole ebuild directory
        fn = glob.glob(os.path.join(ebuildDir, "*.ebuild"))[0]
        args = ["ebuild", fn, "manifest"]
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL)
        retcode = await proc.wait()
        if retcode != 0:
            raise subprocess.CalledProcessError(retcode, args)      # use subprocess.CalledProcessError since there's no equivalent in asyncio

    @staticmethod
    def isTrivalFileOrDir(filename):
        if os.path.islink(filename):
            return False
        if stat.S_ISCHR(os.stat(filename).st_mode):
            return False
        if stat.S_ISBLK(os.stat(filename).st_mode):
            return False
        if stat.S_ISFIFO(os.stat(filename).st_mode):
            return False
        if stat.S_ISSOCK(os.stat(filename).st_mode):
            return False
        return True

    @staticmethod
    def getAbsPathList(dirname, pathList):
        pathList2 = []
        for i in range(0, len(pathList)):
            assert not os.path.isabs(pathList[i])
            pathList2.append(os.path.join(dirname, pathList[i]))
        return pathList2

    @staticmethod
    def archConvert(arch):
        if arch == "x86_64":
            return "amd64"
        else:
            return arch

    @staticmethod
    def getFileList(dirName, level, typeList):
        """typeList is a string, value range is "d,f,l,a"
           returns basename"""

        ret = []
        for fbasename in os.listdir(dirName):
            fname = os.path.join(dirName, fbasename)

            if os.path.isdir(fname) and level - 1 > 0:
                for i in FmUtil.getFileList(fname, level - 1, typeList):
                    ret.append(os.path.join(fbasename, i))
                continue

            appended = False
            if not appended and ("a" in typeList or "d" in typeList) and os.path.isdir(fname):         # directory
                ret.append(fbasename)
            if not appended and ("a" in typeList or "f" in typeList) and os.path.isfile(fname):        # file
                ret.append(fbasename)
            if not appended and ("a" in typeList or "l" in typeList) and os.path.islink(fname):        # soft-link
                ret.append(fbasename)

        return ret

    @staticmethod
    def listLeafDirs(dirName):
        ret = []

        dirName = os.path.abspath(dirName)
        if dirName == "/":
            prefixLen = 1
        else:
            prefixLen = len(dirName) + 1

        for root, dirs, files in os.walk(dirName):
            if root == dirName:
                continue
            if len(dirs) == 0:
                ret.append(root[prefixLen:])

        return ret

    @staticmethod
    def updateDir(oriDir, newDir, keepList=[]):
        """Update oriDir by newDir, meta-data is also merged
           Elements in keepList are glob patterns, and they should not appear in newDir"""

        assert os.path.isabs(oriDir) and os.path.isabs(newDir)
        keepList = FmUtil.getAbsPathList(oriDir, keepList)

        # call assistant
        dirCmpObj = filecmp.dircmp(oriDir, newDir)
        FmUtil._updateDirImpl(oriDir, newDir, keepList, dirCmpObj)

    @staticmethod
    def _updateDirImpl(oriDir, newDir, keepAbsList, dirCmpObj):
        # fixme: should consider acl, sparse file, the above is same

        assert len(dirCmpObj.common_funny) == 0
        assert len(dirCmpObj.funny_files) == 0

        # delete files
        for fb in dirCmpObj.left_only:
            of = os.path.join(oriDir, fb)
            if any(x for x in keepAbsList if fnmatch.fnmatch(of, x)):
                continue
            if os.path.isdir(of):
                shutil.rmtree(of)
            else:
                os.remove(of)

        # add new directories and files
        for fb in dirCmpObj.right_only:
            of = os.path.join(oriDir, fb)
            nf = os.path.join(newDir, fb)
            assert not any(x for x in keepAbsList if fnmatch.fnmatch(of, x))
            assert FmUtil.isTrivalFileOrDir(of)
            if os.path.isdir(of):
                shutil.copytree(nf, of)
            else:
                shutil.copy2(nf, of)
            os.chown(of, os.stat(nf).st_uid, os.stat(nf).st_gid)

        # copy stat info for common directories
        for fb in dirCmpObj.common_dirs:
            of = os.path.join(oriDir, fb)
            nf = os.path.join(newDir, fb)
            assert not any(x for x in keepAbsList if fnmatch.fnmatch(of, x))
            assert FmUtil.isTrivalFileOrDir(of)
            shutil.copystat(nf, of)
            os.chown(of, os.stat(nf).st_uid, os.stat(nf).st_gid)

        # copy common files
        for fb in dirCmpObj.common_files:
            of = os.path.join(oriDir, fb)
            nf = os.path.join(newDir, fb)
            assert not any(x for x in keepAbsList if fnmatch.fnmatch(of, x))
            assert FmUtil.isTrivalFileOrDir(of)
            shutil.copy2(nf, of)
            os.chown(of, os.stat(nf).st_uid, os.stat(nf).st_gid)

        # recursive operation
        for fb2, dirCmpObj2 in list(dirCmpObj.subdirs().items()):
            of2 = os.path.join(oriDir, fb2)
            nf2 = os.path.join(newDir, fb2)
            FmUtil._updateDirImpl(of2, nf2, keepAbsList, dirCmpObj2)

    @staticmethod
    def hashDir(dirname):
        h = hashlib.sha1()
        for root, dirs, files in os.walk(dirname):
            for filepath in files:
                with open(os.path.join(root, filepath), "rb") as f1:
                    buf = f1.read(4096)
                    while buf != b'':
                        h.update(hashlib.sha1(buf).digest())
                        buf = f1.read(4096)
        return h.hexdigest()

    @staticmethod
    def readListFile(filename):
        ret = []
        with open(filename, "r") as f:
            for line in f.read().split("\n"):
                line = line.strip()
                if line != "" and not line.startswith("#"):
                    ret.append(line)
        return ret

    @staticmethod
    def gitIsDirty(dirName):
        ret = FmUtil._gitCall(dirName, "status")
        if re.search("^You have unmerged paths.$", ret, re.M) is not None:
            return True
        if re.search("^Changes to be committed:$", ret, re.M) is not None:
            return True
        if re.search("^Changes not staged for commit:$", ret, re.M) is not None:
            return True
        if re.search("^All conflicts fixed but you are still merging.$", ret, re.M) is not None:
            return True
        return False

    @staticmethod
    def gitGetUrl(dirName):
        gitDir = os.path.join(dirName, ".git")
        cmdStr = "git --git-dir=\"%s\" --work-tree=\"%s\" config --get remote.origin.url" % (gitDir, dirName)
        return FmUtil.shellCall(cmdStr)

    @staticmethod
    def gitHasUntrackedFiles(dirName):
        ret = FmUtil._gitCall(dirName, "status")
        if re.search("^Untracked files:$", ret, re.M) is not None:
            return True
        return False

    @staticmethod
    def _gitCall(dirName, command):
        gitDir = os.path.join(dirName, ".git")
        cmdStr = "git --git-dir=\"%s\" --work-tree=\"%s\" %s" % (gitDir, dirName, command)
        return FmUtil.shellCall(cmdStr)

    @staticmethod
    def svnGetUrl(dirName):
        ret = FmUtil.cmdCall("svn", "info", dirName)
        m = re.search("^URL: (.*)$", ret, re.M)
        return m.group(1)

    @staticmethod
    def encodePath(src_path):
        # Use the convert algorithm of systemd:
        # * Some unit names reflect paths existing in the file system namespace.
        # * Example: a device unit dev-sda.device refers to a device with the device node /dev/sda in the file system namespace.
        # * If this applies, a special way to escape the path name is used, so that the result is usable as part of a filename.
        # * Basically, given a path, "/" is replaced by "-", and all unprintable characters and the "-" are replaced by C-style
        #   "\x20" escapes. The root directory "/" is encoded as single dash, while otherwise the initial and ending "/" is
        #   removed from all paths during transformation. This escaping is reversible.
        # Note:
        # * src_path must be a normalized path, we don't accept path like "///foo///bar/"
        # * the encoding of src_path is a bit messy
        # * what about path like "/foo\/bar/foobar2"?

        assert os.path.isabs(src_path)

        if src_path == "/":
            return "-"

        newPath = ""
        for c in src_path.strip("/"):
            if c == "/":
                newPath += "-"
            elif re.fullmatch("[a-zA-Z0-9:_\\.]", c) is not None:
                newPath += c
            else:
                newPath += "\\x%02x" % (ord(c))
        return newPath

    @staticmethod
    def decodePath(dst_path):
        if dst_path == "-":
            return "/"

        newPath = ""
        for i in range(0, len(dst_path)):
            if dst_path[i] == "-":
                newPath += "/"
            elif dst_path[i] == "\\":
                m = re.search("^\\\\x([0-9])+", dst_path[i:])
                if m is None:
                    raise ValueError("encoded path is invalid")
                newPath += chr(int(m.group(1)))
            else:
                newPath += dst_path[i]
        return "/" + newPath

    @staticmethod
    def verifyFileMd5(filename, md5sum):
        with open(filename, "rb") as f:
            thash = hashlib.md5()
            while True:
                block = f.read(65536)
                if len(block) == 0:
                    break
                thash.update(block)
            return thash.hexdigest() == md5sum

    @staticmethod
    def isBufferAllZero(buf):
        for b in buf:
            if b != 0:
                return False
        return True

    @staticmethod
    def efiSetVariable():
        pass

    @staticmethod
    def getDevPathListForFixedHdd():
        ret = []
        for line in FmUtil.cmdCall("lsblk", "-o", "NAME,TYPE", "-n").split("\n"):
            m = re.fullmatch("(\\S+)\\s+(\\S+)", line)
            if m is None:
                continue
            if m.group(2) != "disk":
                continue
            if re.search("/usb[0-9]+/", os.path.realpath("/sys/block/%s/device" % (m.group(1)))) is not None:      # USB device
                continue
            ret.append("/dev/" + m.group(1))
        return ret

    @staticmethod
    def libUsed(binFile):
        """Return a list of the paths of the shared libraries used by binFile"""

        LDD_STYLE1 = re.compile(r'^\t(.+?)\s\=\>\s(.+?)?\s\(0x.+?\)$')
        LDD_STYLE2 = re.compile(r'^\t(.+?)\s\(0x.+?\)$')

        try:
            raw_output = FmUtil.cmdCall("ldd", "--", binFile)
        except subprocess.CalledProcessError as e:
            if 'not a dynamic executable' in e.output:
                raise Exception("not a dynamic executable")
            else:
                raise

        # We can expect output like this:
        # [tab]path1[space][paren]0xaddr[paren]
        # or
        # [tab]path1[space+]=>[space+]path2?[paren]0xaddr[paren]
        # path1 can be ignored if => appears
        # path2 could be empty

        if 'statically linked' in raw_output:
            return []

        result = []
        for line in raw_output.splitlines():
            match = LDD_STYLE1.match(line)
            if match is not None:
                if match.group(2):
                    result.append(match.group(2))
                continue

            match = LDD_STYLE2.match(line)
            if match is not None:
                result.append(match.group(1))
                continue

            assert False

        result.remove("linux-vdso.so.1")
        return result

    @staticmethod
    def unixHasUser(username):
        try:
            pwd.getpwnam(username)
            return True
        except KeyError:
            return False

    @staticmethod
    def unixHasGroup(groupname):
        try:
            grp.getgrnam(groupname)
            return True
        except KeyError:
            return False

    @staticmethod
    def unixVerifyUserPassword(username, password):
        try:
            item = spwd.getspnam(username)
            return passlib.hosts.linux_context.verify(password, item.sp_pwd)
        except KeyError:
            return False

    @staticmethod
    def geoGetCountry():
        """Returns (country-code, country-name)"""
        return ("CN", "China")


class AvahiServiceBrowser:

    """
    Exampe:
        obj = AvahiServiceBrowser("_http._tcp")
        obj.run()
        obj.get_result_list()
    """

    def __init__(self, service):
        self.service = service

    def run(self):
        self._result_dict = dict()

        self._server = None
        self._browser = None
        self._error_message = None
        try:
            self._server = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM,
                                                          Gio.DBusProxyFlags.NONE,
                                                          None,
                                                          "org.freedesktop.Avahi",
                                                          "/",
                                                          "org.freedesktop.Avahi.Server")

            path = self._server.ServiceBrowserNew("(iissu)",
                                                  -1,                                   # interface = IF_UNSPEC
                                                  0,                                    # protocol = PROTO_INET
                                                  self.service,                         # type
                                                  "",                                   # domain
                                                  0)                                    # flags
            self._browser = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM,
                                                           Gio.DBusProxyFlags.NONE,
                                                           None,
                                                           "org.freedesktop.Avahi",
                                                           path,
                                                           "org.freedesktop.Avahi.ServiceBrowser")
            self._browser.connect("g-signal", self._signal_handler)

            self._mainloop = GLib.MainLoop()
            self._mainloop.run()
            if self._error_message is not None:
                raise Exception(self._error_message)
        except GLib.Error as e:
            # treat dbus error as success but with no result
            if e.domain in ["g-io-error-quark", "g-dbus-error-quark"]:
                return
            raise
        finally:
            self._error_message = None
            if self._browser is not None:
                self._browser.Free()
                self._browser = None
            self._server = None

    def get_result_list(self):
        return self._result_dict.values()

    def _signal_handler(self, proxy, sender, signal, param):
        if signal == "ItemNew":
            interface, protocol, name, stype, domain, flags = param.unpack()
            self._server.ResolveService("(iisssiu)",
                                        interface,
                                        protocol,
                                        name,
                                        stype,
                                        domain,
                                        -1,                                     # interface = IF_UNSPEC
                                        0,                                      # protocol = PROTO_INET
                                        result_handler=self._service_resolved,
                                        error_handler=self._failure_handler)

        if signal == "ItemRemove":
            interface, protocol, name, stype, domain, flags = param.unpack()
            key = (interface, protocol, name, stype, domain)
            if key in self._result_dict:
                del self._result_dict[key]

        if signal == "AllForNow":
            self._mainloop.quit()

        if signal == "Failure":
            self._failure_handler(param)

        return True

    def _service_resolved(self, proxy, result, user_data):
        interface, protocol, name, stype, domain, host, aprotocol, address, port, txt, flags = result
        key = (interface, protocol, name, stype, domain)
        self._result_dict[key] = (name, address, int(port))

    def _failure_handler(self, error):
        self._error_message = error
        self._mainloop.quit()


class TmpHttpDirFs:

    def __init__(self, url, options=None):
        self._url = url
        self._tmppath = tempfile.mkdtemp()

        try:
            cmd = ["httpdirfs"]
            if options is not None:
                cmd.append("-o")
                cmd.append(options)
            cmd.append(self._url)
            cmd.append(self._tmppath)
            # /usr/bin/httpfs sucks: no way to disable it from printing status information on stderr
            subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        except:
            os.rmdir(self._tmppath)
            raise

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    @property
    def mountpoint(self):
        return self._tmppath

    def close(self):
        subprocess.run(["umount", self._tmppath], check=True)
        os.rmdir(self._tmppath)


class TmpMount:

    def __init__(self, path, options=None):
        self._path = path
        self._tmppath = tempfile.mkdtemp()

        try:
            cmd = ["mount"]
            if options is not None:
                cmd.append("-o")
                cmd.append(options)
            cmd.append(self._path)
            cmd.append(self._tmppath)
            subprocess.run(cmd, check=True, universal_newlines=True)
        except:
            os.rmdir(self._tmppath)
            raise

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    @property
    def mountpoint(self):
        return self._tmppath

    def close(self):
        subprocess.run(["umount", self._tmppath], check=True, universal_newlines=True)
        os.rmdir(self._tmppath)


class DirListMount:

    @staticmethod
    def standardDirList(tdir):
        mountList = []
        if True:
            tstr = os.path.join(tdir, "proc")
            mountList.append((tstr, "-t proc -o nosuid,noexec,nodev proc %s" % (tstr)))
        if True:
            tstr = os.path.join(tdir, "sys")
            mountList.append((tstr, "--rbind /sys %s" % (tstr), "--make-rslave %s" % (tstr)))
        if True:
            tstr = os.path.join(tdir, "dev")
            mountList.append((tstr, "--rbind /dev %s" % (tstr), "--make-rslave %s" % (tstr)))
        if True:
            tstr = os.path.join(tdir, "run")
            mountList.append((tstr, "--bind /run %s" % (tstr)))
        if True:
            tstr = os.path.join(tdir, "tmp")
            mountList.append((tstr, "-t tmpfs -o mode=1777,strictatime,nodev,nosuid tmpfs %s" % (tstr)))
        return mountList

    def __init__(self, mountList):
        self.okList = []
        for item in mountList:      # mountList = (directory, mount-commad-1, mount-command-2, ...)
            dir = item[0]
            if not os.path.exists(dir):
                os.makedirs(dir)
            for i in range(1, len(item)):
                mcmd = "mount %s" % (item[i])
                rc, out = FmUtil.shellCallWithRetCode(mcmd)
                if rc == 0:
                    self.okList.insert(0, dir)
                else:
                    for dir2 in self.okList:
                        FmUtil.cmdCallIgnoreResult("umount", "-l", dir2)
                    raise Exception("error when executing \"%s\"" % (mcmd))

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        for d in self.okList:
            FmUtil.cmdCallIgnoreResult("umount", "-l", d)


class StructUtil:

    class Exception(Exception):
        pass

    @staticmethod
    def readStream(f, fmt):
        buf = bytes()
        while len(buf) < struct.calcsize(fmt):
            buf2 = f.read(struct.calcsize(fmt) - len(buf))
            if buf2 is None:
                raise StructUtil.Exception("not enough data")
            buf += buf2
        return struct.unpack(fmt, buf)


class SingletonProcess:

    class AlreadyExistException(Exception):
        pass

    def __init__(self, filename):
        self._lockfile = filename
        self._lockFd = os.open(self._lockfile, os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            fcntl.lockf(self._lockFd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except Exception as e:
            os.close(self._lockFd)
            self._lockFd = None
            if isinstance(e, IOError):
                if e.errno == errno.EACCES or e.errno == errno.EAGAIN:
                    raise self.AlreadyExistException()
            raise

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        os.close(self._lockFd)
        self._lockFd = None
        os.unlink(self._lockfile)
        self._lockfile = None


class TempChdir:

    def __init__(self, dirname):
        self.olddir = os.getcwd()
        os.chdir(dirname)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        os.chdir(self.olddir)


class TempCreateFile:

    def __init__(self, dir=None):
        f, self._fn = tempfile.mkstemp(dir=dir)
        os.close(f)

    def __enter__(self):
        return self._fn

    def __exit__(self, type, value, traceback):
        os.unlink(self._fn)


class InfoPrinter:

    class _InfoPrinterInfoIndenter:

        def __init__(self, parent, message, bRecallable=False):
            self._parent = parent
            self._bRecallable = bRecallable

            self._savedIndenter = self._parent._curIndenter
            self._parent._curIndenter = self

            self._printLen = -1
            self._parent.printInfo(message)
            self._printLen = len(message)

            self._parent.incIndent()

        def __enter__(self):
            return self

        def __exit__(self, type, value, traceback):
            self._parent.decIndent()

            if self._bRecallable and self._printLen >= 0:
                sys.stdout.write("\r" + self._parent._t.clear_eol)       # clear current line
                sys.stdout.flush()

            self._parent._curIndenter = self._savedIndenter

    def __init__(self):
        self._t = blessed.Terminal()
        self._indent = 0
        self._curIndenter = None

    def incIndent(self):
        self._indent = self._indent + 1

    def decIndent(self):
        assert self._indent > 0
        self._indent = self._indent - 1

    def printInfo(self, s):
        line = ""
        line += self._t.green("*") + " "
        line += "\t" * self._indent
        line += s

        if self._curIndenter is not None and self._curIndenter._bRecallable:
            if self._curIndenter._printLen == -1:
                print(line, end='')
            else:
                self._curIndenter._bRecallable = False
                print("")
                print(line)
        else:
            print(line)

    def printError(self, s):
        line = ""
        line += self._t.red("*") + " "
        line += "\t" * self._indent
        line += s

        if self._curIndenter is not None and self._curIndenter._bRecallable:
            if self._curIndenter._printLen == -1:
                print(line, end='')
            else:
                self._curIndenter._bRecallable = False
                print("")
                print(line)
        else:
            print(line)

    def printInfoAndIndent(self, s, bRecallable=False):
        return self._InfoPrinterInfoIndenter(self, s, bRecallable)


class PrintLoadAvgThread(threading.Thread):

    def __init__(self, msg):
        super().__init__()

        self._min_display_latency = 2
        self._max_width = 80
        self._t = blessed.Terminal()

        self._msg = msg
        self._width = min(self._t.width, self._max_width)
        self._stopEvent = threading.Event()
        self._firstTime = True

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        self.stop()

    def start(self):
        self._print_message()
        super().start()

    def stop(self):
        self._stopEvent.set()
        self.join()

    def run(self):
        while not self._stopEvent.is_set():
            self._print_message()
            self._stopEvent.wait(self._min_display_latency)
        sys.stdout.write("\n")

    def _print_message(self):
        if self._firstTime:
            self._firstTime = False
        else:
            sys.stdout.write("\r" + self._t.clear_eol)                                     # clear current line

        sys.stdout.write(self._msg)                                                        # print message
        sys.stdout.write(" " * (self._width - len(self._msg)))                             # print padding
        sys.stdout.write("Load avg: %s" % (FmUtil.getLoadAvgStr()))                        # print load average
        sys.stdout.flush()


class ParallelRunSequencialPrint:

    def __init__(self):
        self.preFuncList = []
        self.postFuncList = []
        self.taskDataList = []
        self.stdoutList = []

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.run()

    # pre_func can't be a coroutine because there's no "async lambda" in python
    def add_task(self, start_coro, start_coro_param, wait_coro, pre_func=None, post_func=None):
        self.preFuncList.append(pre_func)
        self.postFuncList.append(post_func)
        self.taskDataList.append((start_coro, start_coro_param, wait_coro))

    def run(self):
        loop = asyncio.get_event_loop()

        tlist = []
        for start_coro, start_coro_param, wait_coro in self.taskDataList:
            proc, outf = loop.run_until_complete(start_coro(*start_coro_param, loop=loop))
            self.stdoutList.append(outf)
            tlist.append((proc, wait_coro))

        pool = asyncio_pool.AioPool(loop=loop)
        pool.spawn_n(self._showResult())
        for proc, wait_coro in tlist:
            pool.spawn_n(wait_coro(proc))
        loop.run_until_complete(pool.join())

        self.preFuncList = []
        self.postFuncList = []
        self.taskDataList = []
        self.stdoutList = []

    async def _showResult(self):
        for i in range(0, len(self.preFuncList)):
            if self.preFuncList[i] is not None:
                self.preFuncList[i]()
            while True:
                buf = await self.stdoutList[i].read(1)      # no way to read all data in buffer, sucks
                if buf == b'':
                    break
                sys.stdout.buffer.write(buf)
                sys.stdout.flush()
            if self.postFuncList[i] is not None:
                self.postFuncList[i]()


class SysfsHwMon:

    SENSOR_TYPE_TEMP = "temp"

    def get_sensors(self, hwmon_name_pattern, sensor_label_pattern, sensor_type=None):
        # return [(hwmon_name, sensor_label, sensor_type, sysfs_path_prefix)]

        assert sensor_type is None or sensor_type in [self.SENSOR_TYPE_TEMP]

        ret = []
        if not os.path.exists("/sys/class/hwmon"):
            return ret

        for dn in os.listdir("/sys/class/hwmon"):
            fulldn = os.path.join("/sys/class/hwmon", dn)

            namefn = os.path.join(fulldn, "name")
            chipName = pathlib.Path(namefn).read_text()
            if not fnmatch.fnmatch(chipName, hwmon_name_pattern):
                continue

            if sensor_type is None:
                pat = os.path.join("/sys/class/hwmon", fulldn, "*_label")
            else:
                pat = os.path.join("/sys/class/hwmon", fulldn, "%s*_label" % (sensor_type))
            for fullfn in glob.glob(pat):
                label = pathlib.Path(namefn).read_text()
                if not fnmatch.fnmatch(label, sensor_label_pattern):
                    continue
                m = re.fullmatch(r'((.*)[0-9]+)_label', os.path.basename(fullfn))
                ret.append((chipName, label, m.group(1), os.path.join(fulldn, m.group(2))))

        return ret

    def get_sensor(self, hwmon_name, sensor_label, sensor_type=None):
        # return (hwmon_name, sensor_label, sensor_type, sysfs_path_prefix)

        ret = self.get_sensors(hwmon_name, sensor_label, sensor_type)
        if len(ret) == 1:
            return ret[0]
        elif len(ret) == 0:
            return None
        else:
            assert False


class BootDirWriter:

    def __init__(self, layout):
        self._ctrl = layout.get_bootdir_rw_controller()
        self._origIsWritable = None

    def __enter__(self):
        self._origIsWritable = self._ctrl.is_writable()
        if not self._origIsWritable:
            self._ctrl.to_read_write()
        return self

    def __exit__(self, type, value, traceback):
        if not self._origIsWritable:
            self._ctrl.to_read_only()


class CloudCacheGentoo:

    def __init__(self, cacheDir):
        self._baseUrl = "https://mirrors.tuna.tsinghua.edu.cn/gentoo"

        self._dir = cacheDir
        self._releasesDir = os.path.join(self._dir, "releases")
        self._snapshotsDir = os.path.join(self._dir, "snapshots")

        self._bSynced = (os.path.exists(self._releasesDir) and len(os.listdir(self._releasesDir)) > 0)

    def sync(self):
        os.makedirs(self._releasesDir, exist_ok=True)
        os.makedirs(self._snapshotsDir, exist_ok=True)

        # fill arch directories
        if True:
            archList = []
            while True:
                try:
                    with urllib.request.urlopen(os.path.join(self._baseUrl, "releases"), timeout=robust_layer.TIMEOUT) as resp:
                        root = lxml.html.parse(resp)
                        for elem in root.xpath(".//a"):
                            if elem.text is None:
                                continue
                            m = re.fullmatch("(\\S+)/", elem.text)
                            if m is None:
                                continue
                            archList.append(m.group(1))
                        break
                except Exception:
                    print("Failed, retrying...")
                    time.sleep(robust_layer.RETRY_WAIT)

            # fill arch directories
            FmUtil.syncDirs(archList, self._releasesDir)

        # fill variant and release directories
        for arch in archList:
            variantList = []
            versionList = []
            while True:
                try:
                    with urllib.request.urlopen(self._getAutoBuildsUrl(arch), timeout=robust_layer.TIMEOUT) as resp:
                        for elem in lxml.html.parse(resp).xpath(".//a"):
                            if elem.text is not None:
                                m = re.fullmatch("current-(\\S+)/", elem.text)
                                if m is not None:
                                    variantList.append(m.group(1))
                                m = re.fullmatch("([0-9]+T[0-9]+Z)/", elem.text)
                                if m is not None:
                                    versionList.append(m.group(1))
                        break
                except Exception:
                    print("Failed, retrying...")
                    time.sleep(robust_layer.RETRY_WAIT)

            # fill variant directories
            archDir = os.path.join(self._releasesDir, arch)
            FmUtil.syncDirs(variantList, archDir)

            # fill release directories in variant directories
            for variant in variantList:
                FmUtil.syncDirs(versionList, os.path.join(archDir, variant))

        # fill snapshots directory
        if True:
            versionList = []
            while True:
                try:
                    with urllib.request.urlopen(os.path.join(self._baseUrl, "snapshots", "squashfs"), timeout=robust_layer.TIMEOUT) as resp:
                        for elem in lxml.html.parse(resp).xpath(".//a"):
                            if elem.text is not None:
                                m = re.fullmatch("gentoo-([0-9]+).xz.sqfs", elem.text)
                                if m is not None:
                                    versionList.append(m.group(1))
                        break
                except Exception:
                    print("Failed, retrying...")
                    time.sleep(robust_layer.RETRY_WAIT)

            # fill snapshots directories
            FmUtil.syncDirs(versionList, self._snapshotsDir)

        self._bSynced = True

    def get_arch_list(self):
        assert self._bSynced
        return os.listdir(self._releasesDir)

    def get_subarch_list(self, arch):
        assert self._bSynced
        ret = set()
        for d in os.listdir(os.path.join(self._releasesDir, arch)):
            ret.add(d.split("-")[1])
        return sorted(list(ret))

    def get_release_variant_list(self, arch):
        assert self._bSynced
        return os.listdir(os.path.join(self._releasesDir, arch))

    def get_release_version_list(self, arch):
        assert self._bSynced
        return os.listdir(os.path.join(self._releasesDir, arch, self.get_release_variant_list(arch)[0]))

    def get_snapshot_version_list(self):
        assert self._bSynced
        return os.listdir(self._snapshotsDir)

    def get_stage3(self, arch, subarch, stage3_release_variant, release_version, cached_only=False):
        assert self._bSynced

        releaseVariant = self._stage3GetReleaseVariant(subarch, stage3_release_variant)

        myDir = os.path.join(self._releasesDir, arch, releaseVariant, release_version)
        if not os.path.exists(myDir):
            raise FileNotFoundError("the specified stage3 does not exist")

        fn, fnDigest = self._getFn(releaseVariant, release_version)
        fullfn = os.path.join(myDir, fn)
        fullfnDigest = os.path.join(myDir, fnDigest)

        url = os.path.join(self._getAutoBuildsUrl(arch), release_version, fn)
        urlDigest = os.path.join(self._getAutoBuildsUrl(arch), release_version, fnDigest)

        if os.path.exists(fullfn) and os.path.exists(fullfnDigest):
            print("Files already downloaded.")
            return (fullfn, fullfnDigest)

        if cached_only:
            raise FileNotFoundError("the specified stage3 does not exist")

        FmUtil.wgetDownload(url, fullfn)
        FmUtil.wgetDownload(urlDigest, fullfnDigest)
        return (fullfn, fullfnDigest)

    def get_latest_stage3(self, arch, subarch, stage3_release_variant, cached_only=False):
        assert self._bSynced

        releaseVariant = self._stage3GetReleaseVariant(subarch, stage3_release_variant)

        variantDir = os.path.join(self._releasesDir, arch, releaseVariant)
        for ver in sorted(os.listdir(variantDir), reverse=True):
            myDir = os.path.join(variantDir, ver)

            fn, fnDigest = self._getFn(releaseVariant, ver)
            fullfn = os.path.join(myDir, fn)
            fullfnDigest = os.path.join(myDir, fnDigest)

            url = os.path.join(self._getAutoBuildsUrl(arch), ver, fn)
            urlDigest = os.path.join(self._getAutoBuildsUrl(arch), ver, fnDigest)

            if os.path.exists(fullfn) and os.path.exists(fullfnDigest):
                print("Files already downloaded.")
                return (fullfn, fullfnDigest)

            if not cached_only:
                FmUtil.wgetDownload(url, fullfn)
                FmUtil.wgetDownload(urlDigest, fullfnDigest)
                return (fullfn, fullfnDigest)

        raise FileNotFoundError("no stage3 found")

    def get_snapshot(self, snapshot_version, cached_only=False):
        assert self._bSynced

        myDir = os.path.join(self._snapshotsDir, snapshot_version)
        if not os.path.exists(myDir):
            raise FileNotFoundError("the specified snapshot does not exist")

        fn = "gentoo-%s.xz.sqfs" % (snapshot_version)
        fullfn = os.path.join(myDir, fn)
        url = os.path.join(self._baseUrl, "snapshots", "squashfs", fn)

        if os.path.exists(fullfn):
            print("Files already downloaded.")
            return fullfn

        if cached_only:
            raise FileNotFoundError("the specified snapshot does not exist")

        FmUtil.wgetDownload(url, fullfn)
        return fullfn

    def get_latest_snapshot(self, cached_only=False):
        assert self._bSynced

        for ver in sorted(os.listdir(self._snapshotsDir), reverse=True):
            myDir = os.path.join(self._snapshotsDir, ver)
            fn = "gentoo-%s.xz.sqfs" % (ver)
            fullfn = os.path.join(myDir, fn)
            url = os.path.join(self._baseUrl, "snapshots", "squashfs", fn)

            if os.path.exists(fullfn):
                print("Files already downloaded.")
                return fullfn

            if not cached_only:
                FmUtil.wgetDownload(url, fullfn)
                return fullfn

        raise FileNotFoundError("no snapshot found")

    def _getAutoBuildsUrl(self, arch):
        return os.path.join(self._baseUrl, "releases", arch, "autobuilds")

    def _stage3GetReleaseVariant(self, subarch, stage3ReleaseVariant):
        ret = "stage3-%s" % (subarch)
        if stage3ReleaseVariant != "":
            ret += "-%s" % (stage3ReleaseVariant)
        return ret

    def _getFn(self, releaseVariant, releaseVersion):
        fn = releaseVariant + "-" + releaseVersion + ".tar.xz"
        fnDigest = fn + ".DIGESTS"
        return (fn, fnDigest)


class CcacheLocalService:

    """
    We think ccache can be used as a local service if the following conditions are met:
       1. /etc/ccache.conf exists
       2. ccache_dir is specified in /etc/ccache.conf
       3. no user specific configuration for root
    """

    def __init__(self):
        self._binFile = "/usr/bin/ccache"
        self._cfgFile = "/etc/ccache.conf"
        self._rootCfgDir = "/root/.config/ccache"

        if not os.path.exists(self._cfgFile):
            self._ccacheDir = None
        else:
            if not os.path.exists(self._binFile):
                raise Exception("%s does not exist while you have a %s" % (self._binFile, self._cfgFile))
            if os.path.exists(self._rootCfgDir):
                raise Exception("%s should not exist" % (self._rootCfgDir))

            buf = pathlib.Path(self._cfgFile).read_text()
            m = re.search("^cache_dir = (.*)$", buf, re.M)
            if m is None:
                raise Exception("no \"cache_dir\" specified in %s" % (self._cfgFile))
            self._ccacheDir = m.group(1)

    def is_enabled(self):
        return (self._ccacheDir is not None)

    def get_ccache_dir(self):
        assert self._ccacheDir is not None
        return self._ccacheDir


class Stage4Overlay(gstage4.ManualSyncRepository):

    """download overlay files using robust_layer.git in host system, "emerge --sync" is not robust enough"""

    def __init__(self, name, url):
        self._name = name
        self._url = url

    def get_name(self):
        return self._name

    def get_datadir_path(self):
        return "/var/db/overlays/%s" % (self._name)

    def sync(self, datadir_hostpath):
        FmUtil.cmdCall("/usr/libexec/robust_layer/git", "clone", "--depth", "1", self._url, datadir_hostpath)


class Stage4ScriptUseRobustLayer(gstage4.ScriptInChroot):

    def __init__(self, gentoo_repo_dirpath):
        self._gentooRepoDir = gentoo_repo_dirpath

    def fill_script_dir(self, script_dir_hostpath):
        srcDir = os.path.join(script_dir_hostpath, "robust_layer")
        FmUtil.cmdCall("/usr/libexec/robust_layer/git", "clone", "--depth", "1", "https://github.com/mirrorshq/robust_layer", srcDir)

        fullfn = os.path.join(script_dir_hostpath, "main.sh")
        with open(fullfn, "w") as f:
            f.write("#!/bin/sh\n")
            f.write("\n")

            # install robust_layer
            f.write("cd robust_layer\n")
            f.write("python setup.py install\n")
            f.write("cp -r libexec /usr/libexec/robust_layer\n")
            f.write("chmod -R 755 /usr/libexec/robust_layer\n")
            f.write("\n")

            # modify make.conf
            f.write("cd /etc/portage\n")
            f.write("echo '%s' >> make.conf\n" % (r'FETCHCOMMAND="/usr/libexec/robust_layer/wget -q --show-progress -O \"\${DISTDIR}/\${FILE}\" \"\${URI}\""'))
            f.write("echo '%s' >> make.conf\n" % (r'RESUMECOMMAND="/usr/libexec/robust_layer/wget -q --show-progress -c -O \"\${DISTDIR}/\${FILE}\" \"\${URI}\""'))
            f.write("\n")

            # modify git-r3.eclass
            f.write("cd %s\n" % (self._gentooRepoDir))
            f.write("sed -i 's#git fetch#/usr/libexec/robust_layer/git fetch#' eclass/git-r3.eclass\n")
            f.write("\n")
        os.chmod(fullfn, 0o755)

    def get_description(self):
        return "Use robust_layer"

    def get_script(self):
        return "main.sh"
