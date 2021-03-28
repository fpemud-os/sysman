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
import errno
import shutil
import crcmod
import pathlib
import asyncio
import asyncio_pool
import filecmp
import fnmatch
import socket
import subprocess
import struct
import time
import fcntl
import termios
import hashlib
import pyudev
import kmod
import selectors
import tempfile
import random
import parted
import zipfile
import portage
import uuid
import urllib.request
import urllib.error
import lxml.html
import passlib.hosts
import robust_layer
import robust_layer.wget
from datetime import datetime
from OpenSSL import crypto
from gi.repository import Gio
from gi.repository import GLib


class FmUtil:

    def getLoadAvgStr(self):
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
            FmUtil.cmdCall("/usr/bin/svn", "export", "-q", "--force", url, tmpFile)
            return pathlib.Path(tmpFile).read_text()

    @staticmethod
    def isDomainNamePrivate(domainName):
        tldList = [".intranet", ".internal", ".private", ".corp", ".home", ".lan"]    # from RFC6762
        tldList.append(".local")
        return any(domainName.endswith(x) for x in tldList)

    @staticmethod
    def tryPrivateDomainName(domainName):
        # return True: the private domain name is accessabile
        # return False: the private domain name is not accessabile after some test

        assert FmUtil.isDomainNamePrivate(domainName)

        while True:
            try:
                socket.gethostbyname(domainName)
                return True
            except socket.gaierror as e:
                if e.errno == -2:           # Name or service not known
                    return False
                elif e.errno == -3:         # Temporary failure in name resolution
                    pass
                elif e.errno == -5:         # No address associated with hostname
                    return False
                else:
                    raise
                sys.stderr.write(e.strerror)
                time.sleep(1.0)

    @staticmethod
    def isUrlPrivate(url):
        domainName = urllib.parse.urlparse(url).hostname
        return FmUtil.isDomainNamePrivate(domainName)

    @staticmethod
    def tryPrivateUrl(url):
        # return True: the private URL is accessabile
        # return False: the private URL is not accessabile after some test
        domainName = urllib.parse.urlparse(url).hostname
        return FmUtil.tryPrivateDomainName(domainName)

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
    def dotCfgFileCompare(file1, file2):
        # Returns True if two files are same

        lineList1 = []
        with open(file1) as f:
            lineList1 = f.read().split("\n")
        lineList1 = [x for x in lineList1 if x.strip() != "" and not x.strip().startswith("#")]
        lineList1.sort()

        lineList2 = []
        with open(file2) as f:
            lineList2 = f.read().split("\n")
        lineList2 = [x for x in lineList2 if x.strip() != "" and not x.strip().startswith("#")]
        lineList2.sort()

        if len(lineList1) != len(lineList2):
            return False
        for i in range(0, len(lineList1)):
            if lineList1[i] != lineList2[i]:
                return False
        return True

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
        path = FmUtil.cmdCall("/bin/systemd-escape", path)
        path = path + ".swap"
        return path

    @staticmethod
    def swapServiceName2Path(serviceName):
        serviceName = serviceName[:-5]                          # item[:-5] is to remove ".swap"
        path = FmUtil.cmdCall("/bin/systemd-escape", "-u", serviceName)
        path = os.path.join("/", path)
        return path

    @staticmethod
    def findSwapDevices():
        ret = []
        context = pyudev.Context()
        for device in context.list_devices(subsystem='block', ID_FS_TYPE='swap'):
            ret.append("/dev/disk/by-uuid/" + device.get("ID_FS_UUID"))
        return ret

    @staticmethod
    def findSwapFiles():
        ret = []
        for d in ["/var", "/"]:
            for f in os.listdir(d):
                fullf = os.path.join(d, f)
                if fullf.endswith(".swap"):
                    if FmUtil.cmdCallTestSuccess("/sbin/swaplabel", fullf):
                        ret.append(fullf)
        return ret

    @staticmethod
    def getSystemSwapInfo():
        # return (swap-total, swap-free), unit: byte
        buf = ""
        with open("/proc/meminfo") as f:
            buf = f.read()
        m = re.search("^SwapTotal: +([0-9]+) kB$", buf, re.M)
        if m is None:
            raise Exception("get system \"SwapTotal\" from /proc/meminfo failed")
        m2 = re.search("^SwapFree: +([0-9]+) kB$", buf, re.M)
        if m is None:
            raise Exception("get system \"SwapFree\" from /proc/meminfo failed")
        return (int(m.group(1)) * 1024, int(m2.group(1)) * 1024)

    @staticmethod
    def systemdFindSwapService(path):
        for f in os.listdir("/etc/systemd/system"):
            fullf = os.path.join("/etc/systemd/system", f)
            if os.path.isfile(fullf) and fullf.endswith(".swap"):
                if os.path.realpath(path) == os.path.realpath(FmUtil.swapServiceName2Path(f)):
                    return f
        return None

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
    def systemdFindAllSwapServices():
        # get all the swap service name
        ret = []
        for f in os.listdir("/etc/systemd/system"):
            fullf = os.path.join("/etc/systemd/system", f)
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
    def cmpSimple(a, b):
        if a > b:
            return 1
        if a < b:
            return -1
        return 0

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
    def isEfi():
        return os.path.exists("/sys/firmware/efi")

    @staticmethod
    def isInChroot():
        # This technique is used in a few maintenance scripts in Debian
        out1 = FmUtil.cmdCall("/usr/bin/stat", "-c", "%%d:%%i", "/")
        out2 = FmUtil.cmdCall("/usr/bin/stat", "-c", "%%d:%%i", "/proc/1/root/.")
        return out1 != out2

    @staticmethod
    def getMajorMinor(devfile):
        info = os.stat(devfile)
        return (os.major(info.st_dev), os.minor(info.st_dev))

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
        ret = FmUtil.cmdCall("/sbin/blkid", devPath)
        m = re.search("UUID=\"(\\S*)\"", ret, re.M)
        if m is None:
            raise Exception("the specified device has no UUID")
        ret = os.path.join("/dev/disk/by-uuid", m.group(1))
        if not os.path.exists(ret):
            raise Exception("no corresponding device node in /dev/disk/by-uuid")
        return ret

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
                out = FmUtil.cmdCall("/sbin/blockdev", "--getss", devPath)
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
            value = FmUtil.getBlkDevSize(devPath) // 512 // bucketSize
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
        return FmUtil._bcacheIsBackingDeviceOrCachDevice(devPath, True)

    @staticmethod
    def bcacheIsCacheDevice(devPath):
        return FmUtil._bcacheIsBackingDeviceOrCachDevice(devPath, False)

    @staticmethod
    def _bcacheIsBackingDeviceOrCachDevice(devPath, backingDeviceOrCacheDevice):
        # see C struct definition in FmUtil.bcacheMakeDevice()
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
        # see C struct definition in FmUtil.bcacheMakeDevice()
        bcacheSbSetUuidPreFmt = "QQQ16B16B"
        bcacheSbSetUuidFmt = "16B"

        assert FmUtil.bcacheIsCacheDevice(devPath)

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
    def isBlkDevCdrom(devPath):
        assert False

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
        ret = FmUtil.cmdCall("/bin/lsblk", "-o", "MODEL", "-n", devPath)
        ret = ret.strip("\r\n")
        if ret == "":
            return "unknown"
        else:
            return ret

    @staticmethod
    def getBlkDevSize(devPath):
        out = FmUtil.cmdCall("/sbin/blockdev", "--getsz", devPath)
        return int(out) * 512        # unit is byte

    @staticmethod
    def getBlkDevUuid(devPath):
        """UUID is also called FS-UUID, PARTUUID is another thing"""

        ret = FmUtil.cmdCall("/sbin/blkid", devPath)
        m = re.search("UUID=\"(\\S*)\"", ret, re.M)
        if m is not None:
            return m.group(1)
        else:
            return ""

    @staticmethod
    def getBlkDevPartitionTableType(devPath):
        if not FmUtil.devPathIsDiskOrPartition(devPath):
            devPath = FmUtil.devPathPartitionToDisk(devPath)

        ret = FmUtil.cmdCall("/sbin/blkid", "-o", "export", devPath)
        m = re.search("^PTTYPE=(\\S+)$", ret, re.M)
        if m is not None:
            return m.group(1)
        else:
            return ""

    @staticmethod
    def getBlkDevFsType(devPath):
        ret = FmUtil.cmdCall("/sbin/blkid", "-o", "export", devPath)
        m = re.search("^TYPE=(\\S+)$", ret, re.M)
        if m is not None:
            return m.group(1).lower()
        else:
            return ""

    @staticmethod
    def getBlkDevLvmInfo(devPath):
        """Returns (vg-name, lv-name)
           Returns None if the device is not lvm"""

        rc, out = FmUtil.shellCallWithRetCode("/sbin/dmsetup info %s" % (devPath))
        if rc == 0:
            m = re.search("^Name: *(\\S+)$", out, re.M)
            assert m is not None
            ret = m.group(1).split(".")
            if len(ret) == 2:
                return ret
            ret = m.group(1).split("-")         # compatible with old lvm version
            if len(ret) == 2:
                return ret

        m = re.fullmatch("(/dev/mapper/\\S+)-(\\S+)", devPath)          # compatible with old lvm version
        if m is not None:
            return FmUtil.getBlkDevLvmInfo("%s-%s" % (m.group(1), m.group(2)))

        return None

    @staticmethod
    def getBlkDevCapacity(devPath):
        ret = FmUtil.cmdCall("/bin/df", "-BM", devPath)
        m = re.search("%s +(\\d+)M +(\\d+)M +\\d+M", ret, re.M)
        total = int(m.group(1))
        used = int(m.group(2))
        return (total, used)        # unit: MB

    @staticmethod
    def syncBlkDev(devPath1, devPath2, mountPoint1=None, mountPoint2=None):
        if FmUtil.getBlkDevSize(devPath1) != FmUtil.getBlkDevSize(devPath2):
            raise Exception("%s and %s have different size" % (devPath1, devPath2))
        if FmUtil.getBlkDevFsType(devPath1) != FmUtil.getBlkDevFsType(devPath2):
            raise Exception("%s and %s have different filesystem" % (devPath1, devPath2))

        cmd = "/usr/bin/rsync -q -a --delete \"%s/\" \"%s\""        # SRC parameter has "/" postfix so that whole directory is synchronized
        if mountPoint1 is not None and mountPoint2 is not None:
            FmUtil.shellExec(cmd % (mountPoint1, mountPoint2))
        elif mountPoint1 is not None and mountPoint2 is None:
            with TmpMount(devPath2) as mp2:
                FmUtil.shellExec(cmd % (mountPoint1, mp2.mountpoint))
        elif mountPoint1 is None and mountPoint2 is not None:
            with TmpMount(devPath1, "ro") as mp1:
                FmUtil.shellExec(cmd % (mp1.mountpoint, mountPoint2))
        else:
            with TmpMount(devPath1, "ro") as mp1:
                with TmpMount(devPath2) as mp2:
                    FmUtil.shellExec(cmd % (mp1.mountpoint, mp2.mountpoint))

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
    def lvmGetSlaveDevPathList(vgName):
        ret = []
        out = FmUtil.cmdCall("/sbin/lvm", "pvdisplay", "-c")
        for m in re.finditer("^\\s*(\\S+):%s:.*" % (vgName), out, re.M):
            if m.group(1) == "[unknown]":
                raise Exception("volume group %s not fully loaded" % (vgName))
            ret.append(m.group(1))
        return ret

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
        ret = FmUtil.cmdCall("/usr/bin/uname", "-m")
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
        assert len(verList1) == 3 and len(verList2) == 3

        ver1 = int(verList1[0]) * 10000 + int(verList1[1]) * 100 + int(verList1[2])
        ver2 = int(verList2[0]) * 10000 + int(verList2[1]) * 100 + int(verList2[2])
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
    def mkDirWithParent(dirname):
        assert os.path.isabs(dirname)

        cdir = "/"
        for d in dirname.split("/"):        # fixme: don't support special character currently
            cdir = os.path.join(cdir, d)
            if not os.path.exists(cdir):
                os.mkdir(cdir)

    @staticmethod
    def mkDirAndClear(dirname):
        FmUtil.forceDelete(dirname)
        os.mkdir(dirname)

    @staticmethod
    def forceDelete(path):
        if os.path.islink(path):
            os.remove(path)
        elif os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):      # FIXME: device node, how to check it?
            os.remove(path)
        else:
            pass                        # path not exists, do nothing

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

        ret = FmUtil.cmdCall("/bin/df", "-m", dirname)
        m = re.search("^.* + [0-9]+ +[0-9]+ +([0-9]+) + [0-9]+% .*$", ret, re.M)
        return int(m.group(1))

    @staticmethod
    def getMountDeviceForPath(pathname):
        buf = FmUtil.cmdCall("/bin/mount")
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
    def shellExecWithStuckCheck(cmd, timeout=60, quiet=False):
        if hasattr(selectors, 'PollSelector'):
            pselector = selectors.PollSelector
        else:
            pselector = selectors.SelectSelector

        # run the process
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                shell=True, universal_newlines=True)

        # redirect proc.stdout/proc.stderr to stdout/stderr
        # make CalledProcessError contain stdout/stderr content
        # terminate the process and raise exception if they stuck
        sStdout = ""
        sStderr = ""
        bStuck = False
        with pselector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            selector.register(proc.stderr, selectors.EVENT_READ)
            while selector.get_map():
                res = selector.select(timeout)
                if res == []:
                    bStuck = True
                    if not quiet:
                        sys.stderr.write("Process stuck for %d second(s), terminated.\n" % (timeout))
                    proc.terminate()
                    break
                for key, events in res:
                    data = key.fileobj.read()
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    if key.fileobj == proc.stdout:
                        sStdout += data
                        sys.stdout.write(data)
                    elif key.fileobj == proc.stderr:
                        sStderr += data
                        sys.stderr.write(data)
                    else:
                        assert False

        proc.communicate()

        if proc.returncode > 128:
            time.sleep(1.0)
        if bStuck:
            raise FmUtil.ProcessStuckError(proc.args, timeout)
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, proc.args, sStdout, sStderr)

    class ProcessStuckError(Exception):

        def __init__(self, cmd, timeout):
            self.timeout = timeout
            self.cmd = cmd

        def __str__(self):
            return "Command '%s' stucked for %d seconds." % (self.cmd, self.timeout)

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
            out = FmUtil.cmdCall("/bin/netstat", "-lant")
            m = re.search("tcp +[0-9]+ +[0-9]+ +(%s:%d) +.*" % (ip, port), out)
            if m is not None:
                return
            time.sleep(1.0)

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
        diskDevPath, partId = FmUtil.devPathPartitionToDiskAndPartitionId(devPath)
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
            if partEntry[0] != FmUtil.gptNewGuid("C12A7328-F81F-11D2-BA4B-00A0C93EC93B"):
                return False

        return True

    @staticmethod
    def gptToggleEspPartition(devPath, espOrRegular):
        assert isinstance(espOrRegular, bool)

        diskDevPath, partId = FmUtil.devPathPartitionToDiskAndPartitionId(devPath)

        diskObj = parted.newDisk(parted.getDevice(diskDevPath))
        partObj = diskObj.partitions[partId - 1]
        if espOrRegular:
            partObj.setFlag(parted.PARTITION_ESP)
        else:
            partObj.unsetFlag(parted.PARTITION_ESP)
        diskObj.commit()

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
        FmUtil.shellCall("/bin/dd if=/dev/zero of=%s bs=512 count=1000" % (devPath))      # FIXME: this job should be done by parted.freshDisk()
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
        ret = FmUtil.cmdCall("/usr/bin/uname", "-m")
        if ret == "x86_64":
            return "amd64"
        else:
            return ret

    @staticmethod
    def getCpuModel():
        return FmUtil.cmdCall("/usr/bin/uname", "-p")

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
            ret = pathlib.Path(repoNameFn).read_text().rstrip("\n")
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
        ret = FmUtil.cmdCall("/bin/bash", "-c", "%s\nexport CHOST=%s\npkg_extra_files" % (funcContent, FmUtil.portageGetChost()))

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
        return FmUtil.cmdCallTestSuccess("/usr/bin/wget", "--spider", url)

    @staticmethod
    def wgetDownload(url, localFile=None):
        if localFile is None:
            FmUtil.cmdExec("/usr/bin/wget", "-q", "--show-progress", *robust_layer.wget.additional_param(), url)
        else:
            FmUtil.cmdExec("/usr/bin/wget", "-q", "--show-progress", *robust_layer.wget.additional_param(), "-O", localFile, url)

    @staticmethod
    def downloadIfNewer(url, fullfn):
        if os.path.exists(fullfn):
            resp = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=robust_layer.TIMEOUT)
            remoteTm = datetime.strptime(resp.info().get("Last-Modified"), "%a, %d %b %Y %H:%M:%S %Z")
            localTm = datetime.utcfromtimestamp(os.path.getmtime(fullfn))
            if remoteTm <= localTm:
                return localTm
        dummy, resp = urllib.request.urlretrieve(url, fullfn)
        remoteTm = datetime.strptime(resp.info().get("Last-Modified"), "%a, %d %b %Y %H:%M:%S %Z")
        os.utime(fullfn, (remoteTm.timestamp(), remoteTm.timestamp()))
        return remoteTm

    @staticmethod
    def urlopenTimeout():
        return 60

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
            cmdStr = r"/bin/cat /var/db/pkg/*/*/CONTENTS "
            cmdStr += r'| /bin/sed -e "s:^obj \(.*\) [[:xdigit:]]\+ [[:digit:]]\+$:\1:" '
            cmdStr += r'| /bin/sed -e "s:^sym \(.*\) -> .* .*$:\1:" '
            cmdStr += r'| /bin/sed -e "s:^dir \(.*\)$:\1:" '
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
                ret = FmUtil.cmdCall("/usr/bin/find", dn, "-regex", r'.*/__pycache__\(/.*\)?')
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
    def portageGetChost():
        return FmUtil.shellCall("/usr/bin/portageq envvar CHOST 2>/dev/null").rstrip("\n")

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
    def portagePatchRepository(repoName, repoDir, patchTypeName, patchDir, bCanPatchSysFiles, jobNumber=None):
        # patch eclass files
        eclassDir = os.path.join(patchDir, "eclass")
        if os.path.exists(eclassDir):
            if not bCanPatchSysFiles:
                assert False
            dstDir = os.path.join(repoDir, "eclass")
            FmUtil._portagePatchRepositoryExecScript(repoName, patchTypeName, patchDir, eclassDir, dstDir)

        # patch profile files
        profilesDir = os.path.join(patchDir, "profiles")
        if os.path.exists(profilesDir):
            if not bCanPatchSysFiles:
                assert False
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
                    FmUtil.forceDelete(dstDir)
                    if len(os.listdir(fullCategoryDir)) == 0:
                        FmUtil.forceDelete(fullCategoryDir)
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
                print("%s script \"%s\" for \"%s\" is outdated." % (patchTypeName, fullfn[len(patchDir) + 1:], repoName))
            elif out == "":
                pass
            else:
                raise Exception("%s script \"%s\" for \"%s\" exits with error \"%s\"." % (patchTypeName, fullfn[len(patchDir) + 1:], repoName, out))

    @staticmethod
    async def _portagePatchRepositoryGenEbuildManifest(ebuildDir):
        # operate on any ebuild file generates manifest for the whole ebuild directory
        fn = glob.glob(os.path.join(ebuildDir, "*.ebuild"))[0]
        args = ["/usr/bin/ebuild", fn, "manifest"]
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
    def removeDirContent(dirname, ignoreList=[]):
        dirname = os.path.abspath(dirname)
        ignoreList = FmUtil.getAbsPathList(dirname, ignoreList)

        # call assistant
        assert FmUtil.isTrivalFileOrDir(dirname)
        FmUtil._removeDirContentImpl(dirname, ignoreList)

    @staticmethod
    def _removeDirContentImpl(dirname, ignoreAbsList):
        for fb in os.listdir(dirname):
            f = os.path.join(dirname, fb)
            if any(x for x in ignoreAbsList if fnmatch.fnmatch(f, x)):
                continue
            assert FmUtil.isTrivalFileOrDir(f)
            if os.path.isdir(f):
                FmUtil._removeDirContentImpl(f, ignoreAbsList)
            else:
                os.remove(f)
        if len(os.listdir(dirname)) == 0:
            os.rmdir(dirname)

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
    def gitHasUntrackedFiles(dirName):
        ret = FmUtil._gitCall(dirName, "status")
        if re.search("^Untracked files:$", ret, re.M) is not None:
            return True
        return False

    @staticmethod
    def _gitCall(dirName, command):
        gitDir = os.path.join(dirName, ".git")
        cmdStr = "/usr/bin/git --git-dir=\"%s\" --work-tree=\"%s\" %s" % (gitDir, dirName, command)
        return FmUtil.shellCall(cmdStr)

    @staticmethod
    def getMachineInfo(filename):
        ret = dict()
        with open(filename, "r") as f:
            for line in f.read().split("\n"):
                if line.startswith("#"):
                    continue
                m = re.fullmatch("(.*?)=(.*)", line)
                if m is None:
                    continue
                ret[m.group(1)] = m.group(2).strip("\"")
        return ret

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
        for line in FmUtil.cmdCall("/bin/lsblk", "-o", "NAME,TYPE", "-n").split("\n"):
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
    def getFileContentFromInitrd(initrdFile, targetFile):
        cmdStr = "/usr/bin/xzcat \"%s\" | /bin/cpio -i -H newc --quiet --to-stdout %s" % (initrdFile, targetFile)
        return FmUtil.shellCall(cmdStr)

    @staticmethod
    def libUsed(binFile):
        """Return a list of the paths of the shared libraries used by binFile"""

        LDD_STYLE1 = re.compile(r'^\t(.+?)\s\=\>\s(.+?)?\s\(0x.+?\)$')
        LDD_STYLE2 = re.compile(r'^\t(.+?)\s\(0x.+?\)$')

        try:
            raw_output = FmUtil.cmdCall("/usr/bin/ldd", "--", binFile)
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
    def getFilesByKmodAlias(kernelFile, kernelModuleDir, firmwareDir, kmodAlias):
        # Returns (kmodList, firmwareList), which is the list of the paths of files
        # need for kmodAlias, including dependencies

        ctx = kmod.Kmod(kernelModuleDir.encode("utf-8"))    # FIXME: why encode is neccessary?

        # get kernel module file
        mList = list(ctx.lookup(kmodAlias))
        if len(mList) == 0:
            return ([], [])
        assert len(mList) == 1

        # get all the dependency
        kmodList = FmUtil._getFilesByKmodAliasGetKmodDepsList(ctx, mList[0])
        if mList[0].path is not None:
            # this module is built into the kernel
            kmodList.append(mList[0].path)

        # remove duplications
        kmodList2 = []
        kmodSet = set()
        for k in kmodList:
            if k not in kmodSet:
                kmodList2.append(k)
                kmodSet.add(k)
        kmodList = kmodList2

        # get firmware file list
        firmwareList = []
        for k in kmodList:
            # python-kmod bug: can only recognize the last firmware in modinfo
            # so use the command output of modinfo directly
            for line in FmUtil.cmdCall("/bin/modinfo", k).split("\n"):
                m = re.fullmatch("firmware: +(\\S.*)", line)
                if m is None:
                    continue
                firmwareList.append(os.path.join(firmwareDir, m.group(1)))

        return (kmodList, firmwareList)

    @staticmethod
    def _getFilesByKmodAliasGetKmodDepsList(ctx, kmodObj):
        if "depends" not in kmodObj.info or kmodObj.info["depends"] == "":
            return []

        ret = []
        for kmodAlias in kmodObj.info["depends"].split(","):
            mList = list(ctx.lookup(kmodAlias))
            if len(mList) == 0:
                continue
            assert len(mList) == 1

            ret += FmUtil._getFilesByKmodAliasGetKmodDepsList(ctx, mList[0])
            if mList[0].path is not None:
                # this module is built into the kernel
                ret.append(mList[0].path)
        return ret

    @staticmethod
    def printInfo(msgStr):
        print(FmUtil.fmt("*", "GOOD") + " " + msgStr)

    @staticmethod
    def fmt(msgStr, fmtStr):

        FMT_GOOD = "\x1B[32;01m"
        FMT_WARN = "\x1B[33;01m"
        FMT_BAD = "\x1B[31;01m"
        FMT_NORMAL = "\x1B[0m"
        FMT_BOLD = "\x1B[0;01m"
        FMT_UNDER = "\x1B[4m"

        for fo in fmtStr.split("+"):
            if fo == "GOOD":
                return FMT_GOOD + msgStr + FMT_NORMAL
            elif fo == "WARN":
                return FMT_WARN + msgStr + FMT_NORMAL
            elif fo == "BAD":
                return FMT_BAD + msgStr + FMT_NORMAL
            elif fo == "BOLD":
                return FMT_BOLD + msgStr + FMT_NORMAL
            elif fo == "UNDER":
                return FMT_UNDER + msgStr + FMT_NORMAL
            else:
                assert False

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


class TmpMount:

    def __init__(self, path, options=None):
        self._path = path
        self._tmppath = tempfile.mkdtemp()

        try:
            cmd = ["/bin/mount"]
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
        subprocess.run(["/bin/umount", self._tmppath], check=True, universal_newlines=True)
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
                mcmd = "/bin/mount %s" % (item[i])
                rc, out = FmUtil.shellCallWithRetCode(mcmd)
                if rc == 0:
                    self.okList.insert(0, dir)
                else:
                    for dir2 in self.okList:
                        FmUtil.cmdCallIgnoreResult("/bin/umount", "-l", dir2)
                    raise Exception("error when executing \"%s\"" % (mcmd))

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        for d in self.okList:
            FmUtil.cmdCallIgnoreResult("/bin/umount", "-l", d)


class ArchLinuxBasedOsBuilder:

    def __init__(self, mirrorList, cacheDir, tmpDir):
        self.mirrorList = mirrorList
        self.cacheDir = cacheDir
        self.pkgCacheDir = os.path.join(cacheDir, "pkg")
        self.tmpDir = tmpDir

    def bootstrapPrepare(self):
        try:
            # get cached file
            cachedDataFile = None
            if os.path.exists(self.cacheDir):
                for fn in sorted(os.listdir(self.cacheDir)):
                    if re.fullmatch("archlinux-bootstrap-(.*)-x86_64.tar.gz", fn) is None:
                        continue
                    if not os.path.exists(os.path.join(self.cacheDir, fn + ".sig")):
                        continue
                    cachedDataFile = fn

            # select mirror
            mr = None
            if len(self.mirrorList) == 0:
                if cachedDataFile is not None:
                    dataFile = cachedDataFile
                    signFile = cachedDataFile + ".sig"
                    return False
                else:
                    raise Exception("no Arch Linux mirror")
            else:
                mr = self.mirrorList[0]

            # get remote file
            dataFile = None
            signFile = None
            if True:
                url = "%s/iso/latest" % (mr)
                resp = urllib.request.urlopen(url, timeout=robust_layer.TIMEOUT)
                root = lxml.html.parse(resp)
                for link in root.xpath(".//a"):
                    fn = os.path.basename(link.get("href"))
                    if re.fullmatch("archlinux-bootstrap-(.*)-x86_64.tar.gz", fn) is not None:
                        dataFile = fn
                        signFile = fn + ".sig"

            # changed?
            return (cachedDataFile != dataFile)
        finally:
            self.dataFile = dataFile
            self.signFile = signFile
            self.bootstrapDir = os.path.join(self.tmpDir, "bootstrap")
            self.rootfsDir = os.path.join(self.tmpDir, "airootfs")

    def bootstrapDownload(self):
        os.makedirs(self.cacheDir, exist_ok=True)
        mr = self.mirrorList[0]
        FmUtil.wgetDownload("%s/iso/latest/%s" % (mr, self.dataFile), os.path.join(self.cacheDir, self.dataFile))
        FmUtil.wgetDownload("%s/iso/latest/%s" % (mr, self.signFile), os.path.join(self.cacheDir, self.signFile))

    def bootstrapExtract(self):
        os.makedirs(self.tmpDir, exist_ok=True)
        FmUtil.cmdCall("/bin/tar", "-xzf", os.path.join(self.cacheDir, self.dataFile), "-C", self.tmpDir)
        FmUtil.forceDelete(self.bootstrapDir)
        os.rename(os.path.join(self.tmpDir, "root.x86_64"), self.bootstrapDir)

    def createRootfs(self, initcpioHooksDir=None, pkgList=[], localPkgFileList=[], fileList=[], cmdList=[]):
        FmUtil.mkDirAndClear(self.rootfsDir)
        os.makedirs(self.pkgCacheDir, exist_ok=True)

        # copy resolv.conf
        FmUtil.cmdCall("/bin/cp", "-L", "/etc/resolv.conf", os.path.join(self.bootstrapDir, "etc"))

        # modify mirror
        with open(os.path.join(self.bootstrapDir, "etc", "pacman.d", "mirrorlist"), "w") as f:
            for mr in self.mirrorList:
                f.write("Server = %s/$repo/os/$arch\n" % (mr))

        # initialize, add packages
        mountList = DirListMount.standardDirList(self.bootstrapDir)
        tstr = os.path.join(self.bootstrapDir, "var", "cache", "pacman", "pkg")
        mountList.append((tstr, "--bind %s %s" % (self.pkgCacheDir, tstr)))
        tstr = os.path.join(self.bootstrapDir, "mnt")
        mountList.append((tstr, "--bind %s %s" % (self.rootfsDir, tstr)))     # mount rootfs directory as /mnt
        with DirListMount(mountList):
            # prepare pacman
            FmUtil.cmdCall("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacman-key", "--init")
            FmUtil.cmdCall("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacman-key", "--populate", "archlinux")

            # install basic system files
            FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", "base")
            FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", "lvm2")

            # install mkinitcpio and modify it's configuration
            FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", "mkinitcpio")
            if initcpioHooksDir is not None:
                # copy /etc/mkinitcpio/hooks files
                for fullfn in glob.glob(os.path.join(initcpioHooksDir, "hooks", "*")):
                    dstFn = os.path.join(self.rootfsDir, "etc", "initcpio", "hooks", os.path.basename(fullfn))
                    shutil.copy(fullfn, dstFn)
                    os.chmod(dstFn, 0o644)

                # record after information
                afterDict = dict()
                for fullfn in glob.glob(os.path.join(initcpioHooksDir, "install", "*.after")):
                    fn = os.path.basename(fullfn)
                    name = fn.split(".")[0]
                    afterDict[name] = pathlib.Path(fullfn).read_text().rstrip("\n")

                # copy /etc/mkinitcpio/install files
                # add hook to /etc/mkinitcpio.conf
                confFile = os.path.join(self.rootfsDir, "etc", "mkinitcpio.conf")
                self._removeMkInitcpioHook(confFile, "fsck")
                self._addMkInitcpioHook(confFile, "lvm2", "block")
                for fullfn in glob.glob(os.path.join(initcpioHooksDir, "install", "*")):
                    if fullfn.endswith(".after"):
                        continue
                    name = os.path.basename(fullfn)
                    dstFn = os.path.join(self.rootfsDir, "etc", "initcpio", "install", name)
                    shutil.copy(fullfn, dstFn)
                    os.chmod(dstFn, 0o644)
                    self._addMkInitcpioHook(confFile, name, afterDict.get(name))

            # install linux kernel
            FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", "linux-lts")

            # install packages
            for pkg in pkgList:
                FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", pkg)

            # install packages from local repository
            for fullfn in localPkgFileList:
                fn = os.path.basename(fullfn)
                dstFn = os.path.join(self.bootstrapDir, "var", "cache", "pacman", "pkg", fn)
                shutil.copy(fullfn, dstFn)
                try:
                    fn2 = os.path.join("/var", "cache", "pacman", "pkg", fn)
                    FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "-U", "/mnt", fn2)
                finally:
                    os.remove(dstFn)

        # add files
        for fullfn, mode, dstDir in fileList:
            assert dstDir.startswith("/")
            dstDir = self.rootfsDir + dstDir
            dstFn = os.path.join(dstDir, os.path.basename(fullfn))
            os.makedirs(dstDir, exist_ok=True)
            shutil.copy(fullfn, dstFn)
            os.chmod(dstFn, mode)

        # exec custom script
        for cmd in cmdList:
            FmUtil.shellCall("/usr/bin/chroot %s %s" % (self.rootfsDir, cmd))

    def squashRootfs(self, rootfsDataFile, rootfsMd5File, kernelFile, initcpioFile):
        assert rootfsDataFile.startswith("/")
        assert rootfsMd5File.startswith("/")
        assert kernelFile.startswith("/")
        assert initcpioFile.startswith("/")

        FmUtil.cmdCall("/bin/mv", os.path.join(self.rootfsDir, "boot", "vmlinuz-linux-lts"), kernelFile)
        FmUtil.cmdCall("/bin/mv", os.path.join(self.rootfsDir, "boot", "initramfs-linux-lts-fallback.img"), initcpioFile)
        shutil.rmtree(os.path.join(self.rootfsDir, "boot"))

        FmUtil.cmdExec("/usr/bin/mksquashfs", self.rootfsDir, rootfsDataFile, "-no-progress", "-noappend", "-quiet")
        with TempChdir(os.path.dirname(rootfsDataFile)):
            FmUtil.shellExec("/usr/bin/sha512sum \"%s\" > \"%s\"" % (os.path.basename(rootfsDataFile), rootfsMd5File))

    def clean(self):
        FmUtil.forceDelete(self.rootfsDir)
        FmUtil.forceDelete(self.bootstrapDir)
        del self.rootfsDir
        del self.bootstrapDir
        del self.signFile
        del self.dataFile

    def _addMkInitcpioHook(self, confFile, name, after=None):
        buf = pathlib.Path(confFile).read_text()
        hookList = re.search("^HOOKS=\\((.*)\\)", buf, re.M).group(1).split(" ")
        assert name not in hookList
        if after is not None:
            try:
                i = hookList.index(after)
                hookList.insert(i + 1, name)
            except ValueError:
                hookList.append(name)
        else:
            hookList.append(name)
        with open(confFile, "w") as f:
            f.write(re.sub("^HOOKS=\\(.*\\)", "HOOKS=(%s)" % (" ".join(hookList)), buf, 0, re.M))

    def _removeMkInitcpioHook(self, confFile, name):
        buf = pathlib.Path(confFile).read_text()
        hookList = re.search("^HOOKS=\\((.*)\\)", buf, re.M).group(1).split(" ")
        if name in hookList:
            hookList.remove(name)
            with open(confFile, "w") as f:
                f.write(re.sub("^HOOKS=\\(.*\\)", "HOOKS=(%s)" % (" ".join(hookList)), buf, 0, re.M))


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

    GOOD = '\033[32;01m'
    WARN = '\033[33;01m'
    BAD = '\033[31;01m'
    NORMAL = '\033[0m'
    BOLD = '\033[0;01m'
    UNDER = '\033[4m'

    class _InfoPrinterInfoIndenter:

        def __init__(self, parent, message):
            self._parent = parent
            self._parent.printInfo(message)
            self._parent.incIndent()

        def __enter__(self):
            return self

        def __exit__(self, type, value, traceback):
            self._parent.decIndent()

    class _InfoPrinterErrorIndenter:

        def __init__(self, parent, message):
            self._parent = parent
            self._parent.printError(message)
            self._parent.incIndent()

        def __enter__(self):
            return self

        def __exit__(self, type, value, traceback):
            self._parent.decIndent()

    def __init__(self):
        self.logFileList = []
        self.indent = 0

    def addLogFile(self, logFile):
        assert logFile not in self.logFileList
        self.logFileList.append(logFile)

    def incIndent(self):
        self.indent = self.indent + 1

    def decIndent(self):
        assert self.indent > 0
        self.indent = self.indent - 1

    def printInfo(self, s):
        line = ""
        line += self.GOOD + "*" + self.NORMAL + " "
        line += "\t" * self.indent
        line += s
        line += "\n"

        if not hasattr(self, "printByErrorBuffer"):
            print(line, end='')
        else:
            self.printByErrorBuffer += line

    def printInfoAndIndent(self, s):
        return self._InfoPrinterInfoIndenter(self, s)

    def printError(self, s):
        line = ""
        line += self.BAD + "*" + self.NORMAL + " "
        line += "\t" * self.indent
        line += s
        line += "\n"

        if not hasattr(self, "printByErrorBuffer"):
            print(line, end='')
        else:
            self.printByErrorBuffer += line
            self.printByErrorHasError = True

    def printErrorAndIndent(self, s):
        return self._InfoPrinterErrorIndenter(self, s)

    def startPrintByError(self):
        self.printByErrorBuffer = ""
        self.printByErrorStartIndent = self.indent
        self.printByErrorHasError = False

    def endPrintByError(self):
        assert self.indent == self.printByErrorStartIndent

        if self.printByErrorHasError:
            print(self.printByErrorBuffer, end='')

        del self.printByErrorHasError
        del self.printByErrorStartIndent
        del self.printByErrorBuffer
