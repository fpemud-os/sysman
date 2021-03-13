#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import glob
import shutil
import tarfile
import pylkcutil
from collections import OrderedDict
from multiprocessing import Process
from fm_util import FmUtil
from fm_util import TempChdir
from fm_param import FmConst


class FkmInitramfsKcfgChecker:

    def check(self, ksrcDir, dotCfgFile):
        symDict = {
            "RD_XZ": "y",
            "RD_LZMA": "y",         # it seems RD_XZ has no effect, we have to enable RD_LZMA, kernel bug?
            "BCACHE": "m",
            "BLK_DEV_SD": "m",
            "BLK_DEV_DM": "m",
            "EXT2_FS": "m",
            "EXT4_FS": "m",
            "XFS_FS": "m",
            "VFAT_FS": "m",
        }

        try:
            p = Process(target=pylkcutil.checker.check_values, args=(ksrcDir, dotCfgFile, symDict, ))
            p.start()
            p.join()
        except pylkcutil.checker.CheckError as e:
            raise Exception("config symbol %s must be selected as \"%s\"!" % (e.name, e.value))


class FkmInitramfsBuilder:

    def __init__(self, tmpDir, buildTarget):
        self.buildTarget = buildTarget

        self.bootDir = "/boot"
        self.kernelModuleDir = "/lib/modules/%s" % (self.buildTarget.verstr)
        self.firmwareDir = "/lib/firmware"

        self.initramfsTmpDir = os.path.join(tmpDir, "initramfs")
        self.kernelFile = os.path.join(self.bootDir, self.buildTarget.kernelFile)
        self.dotConfigFile = os.path.join(self.bootDir, self.buildTarget.kernelCfgFile)

        self.mntInfoDict = OrderedDict()
        self.mntInfoDict["root"] = None
        self.mntInfoDict["boot"] = None

        # trick: initramfs debug is seldomly needed
        self.trickDebug = False

    def setMntInfo(self, miType, devPath, mntOpt):
        assert miType in list(self.mntInfoDict.keys())
        self.mntInfoDict[miType] = _MntInfo()
        self.mntInfoDict[miType].devPath = devPath
        self.mntInfoDict[miType].fsType = None
        self.mntInfoDict[miType].mntOpt = mntOpt

    def build(self, targetInitrdFile, targetTarFile):
        assert "/" not in targetInitrdFile
        assert "/" not in targetTarFile and targetTarFile.endswith(".tar.bz2")

        FmUtil.mkDirAndClear(self.initramfsTmpDir)

        # variables
        targetInitrdFile = os.path.join(self.bootDir, targetInitrdFile)
        targetTarFile = os.path.join(self.bootDir, targetTarFile)
        rootDir = self.initramfsTmpDir
        etcDir = os.path.join(rootDir, "etc")

        # checking
        if self.mntInfoDict["root"] is None:
            raise Exception("mount information for root filesystem is not specified")

        # create basic structure for initramfs directory
        self._installDir("/bin", rootDir)
        self._installDir("/dev", rootDir)
        self._installDir("/etc", rootDir)
        self._installDir("/lib", rootDir)
        self._installDir("/lib64", rootDir)
        self._installDir("/proc", rootDir)
        self._installDir("/run", rootDir)
        self._installDir("/sbin", rootDir)
        self._installDir("/sys", rootDir)
        self._installDir("/tmp", rootDir)
        self._installDir("/usr/bin", rootDir)
        self._installDir("/usr/sbin", rootDir)
        self._installDir("/usr/lib", rootDir)
        self._installDir("/usr/lib64", rootDir)
        self._installDir("/var", rootDir)
        self._installDir(self.kernelModuleDir, rootDir)
        self._installDir(self.firmwareDir, rootDir)
        os.makedirs(os.path.join(rootDir, "sysroot"))
        self._generatePasswd(os.path.join(etcDir, "passwd"))
        self._generateGroup(os.path.join(etcDir, "group"))
        os.symlink("/proc/self/mounts", os.path.join(etcDir, "mtab"))

        # get block device list
        blkDevInfoList = []
        if True:
            # get all block devices
            tmpList = []
            for t, mi in list(self.mntInfoDict.items()):
                if mi is not None:
                    tmpList += self._getBlkDevInfoList(mi.devPath)
                    # fill mntInfo.fsType
                    assert tmpList[-1].fsType in ["ext2", "ext4", "reiserfs", "xfs", "btrfs", "vfat"]
                    self.mntInfoDict[t].fsType = tmpList[-1].fsType

            # remove duplication
            nameSet = set()
            for i in tmpList:
                if i.devPath not in nameSet:
                    nameSet.add(i.devPath)
                    blkDevInfoList.append(i)

        # get kernel module and firmware file list (order is important)
        kmodList = []
        firmwareList = []
        if True:
            # get kernel module for block device host controller
            for d in [x for x in blkDevInfoList if x.devType.endswith("_disk")]:
                if d.devType == "scsi_disk":
                    hostDevPath = os.path.join(d.param["scsi_host_path"], "scsi_host", os.path.basename(d.param["scsi_host_path"]))
                    with open(os.path.join(hostDevPath, "proc_name")) as f:
                        hostControllerName = f.read().rstrip()
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, hostControllerName)
                    kmodList += r1
                    firmwareList += r2
                elif d.devType == "virtio_disk":
                    pass
                elif d.devType == "xen_disk":
                    pass
                elif d.devType == "nvme_disk":
                    pass
                else:
                    assert False

            # get kernel module for block device driver
            for d in [x for x in blkDevInfoList if x.devType.endswith("_disk") or x.devType.endswith("_raid")]:
                if d.devType == "scsi_disk":
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "sd_mod")
                    kmodList += r1
                    firmwareList += r2
                elif d.devType == "virtio_disk":
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "virtio_pci")
                    kmodList += r1
                    firmwareList += r2
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "virtio_blk")
                    kmodList += r1
                    firmwareList += r2
                elif d.devType == "xen_disk":
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "xen-blkfront")
                    kmodList += r1
                    firmwareList += r2
                elif d.devType == "nvme_disk":
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "nvme")
                    kmodList += r1
                    firmwareList += r2
                elif d.devType == "lvm2_raid":
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "dm_mod")
                    kmodList += r1
                    firmwareList += r2
                elif d.devType == "bcache_raid":
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "bcache")
                    kmodList += r1
                    firmwareList += r2
                else:
                    assert False

            # get kernel module for partition format
            for d in [x for x in blkDevInfoList if x.devType.endswith("_partition")]:
                if d.devType == "mbr_partition":
                    pass                            # currently, partition support is compiled in kernel
                elif d.devType == "gpt_partition":
                    pass                            # currently, partition support is compiled in kernel
                else:
                    assert False

            # get kernel module for filesystem
            for d in blkDevInfoList:
                if d.fsType == "":
                    pass
                elif d.fsType == "lvm2_member":
                    pass
                elif d.fsType == "bcache":
                    pass
                elif d.fsType in ["ext2", "ext4", "reiserfs", "xfs", "btrfs"]:
                    # coincide: fs type and module name are same
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, d.fsType)
                    kmodList += r1
                    firmwareList += r2
                elif d.fsType == "vfat":
                    buf = ""
                    with open(self.dotConfigFile) as f:
                        buf = f.read()

                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "vfat")
                    kmodList += r1
                    firmwareList += r2

                    m = re.search("^CONFIG_FAT_DEFAULT_CODEPAGE=(\\S+)$", buf, re.M)
                    if m is None:
                        raise Exception("CONFIG_FAT_DEFAULT_CODEPAGE is missing in kernel .config file")
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "nls_cp%s" % (m.group(1)))
                    kmodList += r1
                    firmwareList += r2

                    m = re.search("^CONFIG_FAT_DEFAULT_IOCHARSET=\\\"(\\S+)\\\"$", buf, re.M)
                    if m is None:
                        raise Exception("CONFIG_FAT_DEFAULT_IOCHARSET is missing in kernel .config file")
                    r1, r2 = FmUtil.getFilesByKmodAlias(self.kernelFile, self.kernelModuleDir, self.firmwareDir, "nls_%s" % (m.group(1)))
                    kmodList += r1
                    firmwareList += r2
                else:
                    assert False

            # remove duplications
            kmodList = FmUtil.removeDuplication(kmodList)
            firmwareList = FmUtil.removeDuplication(firmwareList)

        # install kmod files
        for f in kmodList:
            self._copyToInitrd(f, rootDir)

        # install firmware files
        for f in firmwareList:
            self._copyToInitrd(f, rootDir)

        # install insmod binary
        if len(kmodList) > 0:
            self._installBin("/sbin/insmod", rootDir)

        # get block device preparation operation list
        blkOpList = []
        for d in blkDevInfoList:
            if d.devType == "scsi_disk":
                # blkOpList.append("blkdev-wait sd* %s" % (FmUtil.getBlkDevUuid(d.devPath))
                pass
            elif d.devType == "virtio_disk":
                pass
            elif d.devType == "xen_disk":
                pass
            elif d.devType == "nvme_disk":
                pass
            elif d.devType == "lvm2_raid":
                blkOpList.append("lvm-lv-activate %s %s %s" % (FmUtil.getBlkDevUuid(d.devPath), d.param["vg_name"], d.param["lv_name"]))
            elif d.devType == "bcache_raid":
                for cacheDev in d.param["cache_dev_list"]:
                    item = "bcache-cache-device-activate %s" % (FmUtil.getBlkDevUuid(cacheDev))
                    if item not in blkOpList:
                        blkOpList.append(item)
                blkOpList.append("bcache-backing-device-activate %s %s" % (FmUtil.getBlkDevUuid(d.devPath), FmUtil.getBlkDevUuid(d.param["backing_dev"])))
            elif d.devType == "mbr_partition":
                # blkOpList.append("blkdev-wait sd* %s" % (FmUtil.getBlkDevUuid(d.devPath))
                pass
            elif d.devType == "gpt_partition":
                # blkOpList.append("blkdev-wait sd* %s" % (FmUtil.getBlkDevUuid(d.devPath))
                pass
            else:
                assert False

        # install files for block device preparation
        self._installFilesBlkid(rootDir)
        for d in blkDevInfoList:
            if d.devType == "scsi_disk":
                pass
            elif d.devType == "virtio_disk":
                pass
            elif d.devType == "xen_disk":
                pass
            elif d.devType == "nvme_disk":
                pass
            elif d.devType == "lvm2_raid":
                self._installFilesLvm(rootDir)
            elif d.devType == "bcache_raid":
                pass
            elif d.devType == "mbr_partition":
                pass
            elif d.devType == "gpt_partition":
                pass
            else:
                assert False

        # get fsck opertaion list
        fsckOpList = []
        if True:
            for d in blkDevInfoList:
                if d.fsType == "":
                    pass
                elif d.fsType == "lvm2_member":
                    pass
                elif d.fsType == "bcache":
                    pass
                elif d.fsType in ["ext2", "ext4", "reiserfs", "xfs", "vfat"]:
                    fsckOpList.append("fsck %s %s" % (d.fsType, FmUtil.getBlkDevUuid(d.devPath)))
                elif d.fsType in ["btrfs"]:
                    pass
                else:
                    assert False

        # install fsck binaries
        for d in blkDevInfoList:
            if d.fsType == "":
                pass
            elif d.fsType == "lvm2_member":
                pass
            elif d.fsType == "bcache":
                pass
            elif d.fsType in ["ext2", "ext4"]:
                self._installBin("/sbin/e2fsck", rootDir)
            elif d.fsType == "reiserfs":
                self._installBin("/sbin/reiserfsck", rootDir)
            elif d.fsType == "xfs":
                self._installBin("/sbin/fsck.xfs", rootDir)
            elif d.fsType == "btrfs":
                pass
            elif d.fsType == "vfat":
                self._installBin("/usr/sbin/fsck.fat", rootDir)
            else:
                assert False

        # install init executable to initramfs
        self._installInit(rootDir)
        self._installStartupRc(rootDir, kmodList, blkOpList, fsckOpList, self.mntInfoDict, FmConst.kernelInitCmd)

        # install kernel modules, firmwares and executables for debugging, use bash as init
        if self.trickDebug:
            dstdir = os.path.join(rootDir, self.kernelModuleDir[1:])
            if os.path.exists(dstdir):
                shutil.rmtree(dstdir)
            shutil.copytree(self.kernelModuleDir, dstdir, symlinks=True)

            dstdir = os.path.join(rootDir, self.firmwareDir[1:])
            if os.path.exists(dstdir):
                shutil.rmtree(dstdir)
            shutil.copytree(self.firmwareDir, dstdir, symlinks=True)

            self._installBin("/bin/bash", rootDir)
            self._installBin("/bin/cat", rootDir)
            self._installBin("/bin/cp", rootDir)
            self._installBin("/bin/dd", rootDir)
            self._installBin("/bin/echo", rootDir)
            self._installBin("/bin/ls", rootDir)
            self._installBin("/bin/ln", rootDir)
            self._installBin("/bin/mount", rootDir)
            self._installBin("/bin/ps", rootDir)
            self._installBin("/bin/rm", rootDir)
            self._installBin("/bin/touch", rootDir)
            self._installBin("/usr/bin/basename", rootDir)
            self._installBin("/usr/bin/dirname", rootDir)
            self._installBin("/usr/bin/find", rootDir)
            self._installBin("/usr/bin/sleep", rootDir)
            self._installBin("/usr/bin/tree", rootDir)
            self._installBin("/usr/bin/xargs", rootDir)
            self._installBin("/usr/bin/hexdump", rootDir)

            self._installBin("/sbin/blkid", rootDir)
            self._installBin("/sbin/switch_root", rootDir)

            self._installBin("/bin/lsmod", rootDir)
            self._installBin("/bin/modinfo", rootDir)
            self._installBin("/sbin/modprobe", rootDir)
            shutil.copytree("/etc/modprobe.d", os.path.join(rootDir, "etc", "modprobe.d"), symlinks=True)

            self._installBin("/sbin/dmsetup", rootDir)
            self._installBin("/sbin/lvm", rootDir)

            if os.path.exists("/usr/bin/nano"):
                self._installBin("/usr/bin/nano", rootDir)

            os.rename(os.path.join(rootDir, "init"), os.path.join(rootDir, "init.bak"))
            os.symlink("/bin/bash", os.path.join(rootDir, "init"))

            with open(os.path.join(rootDir, ".bashrc"), "w") as f:
                f.write("echo \"<initramfs-debug> Mounting basic file systems\"\n")
                f.write("mount -t sysfs none /sys\n")
                f.write("mount -t proc none /proc\n")
                f.write("mount -t devtmpfs none /dev\n")
                f.write("\n")

                f.write("echo \"<initramfs-debug> Loading all the usb drivers\"\n")
                dstdir = os.path.join(self.kernelModuleDir, "kernel", "drivers", "usb")
                f.write("find \"%s\" -name \"*.ko\" | xargs basename -a -s \".ko\" | xargs /sbin/modprobe -a" % (dstdir))
                f.write("\n")

                f.write("echo \"<initramfs-debug> Loading all the hid drivers\"\n")
                dstdir = os.path.join(self.kernelModuleDir, "kernel", "drivers", "hid")
                f.write("find \"%s\" -name \"*.ko\" | xargs basename -a -s \".ko\" | xargs /sbin/modprobe -a" % (dstdir))
                f.write("\n")

                f.write("echo \"<initramfs-debug> Loading all the input drivers\"\n")
                dstdir = os.path.join(self.kernelModuleDir, "kernel", "drivers", "input")
                f.write("find \"%s\" -name \"*.ko\" | xargs basename -a -s \".ko\" | xargs /sbin/modprobe -a" % (dstdir))
                f.write("\n")

        # build the initramfs file and tar file
        with TempChdir(rootDir):
            # initramfs file
            cmdStr = "/usr/bin/find . -print0 "
            cmdStr += "| /bin/cpio --null -H newc -o "
            cmdStr += "| /usr/bin/xz --format=lzma "            # it seems linux kernel config RD_XZ has bug, so we must use format lzma
            cmdStr += "> \"%s\" " % (targetInitrdFile)
            FmUtil.shellCall(cmdStr)

            # tar file
            with tarfile.open(targetTarFile, "w:bz2") as f:
                for fn in glob.glob("*"):
                    f.add(fn)

    def _generatePasswd(self, filename):
        with open(filename, "w") as f:
            f.write("root:x:0:0::/root:/bin/sh\n")
            f.write("nobody:x:65534:65534::/:/sbin/nologin\n")

    def _generateGroup(self, filename):
        with open(filename, "w") as f:
            f.write("tty:x:5:\n")
            f.write("kmem:x:9:\n")
            f.write("disk:x:6:adm\n")
            f.write("floppy:x:11:\n")
            f.write("cdrom:x:19:\n")

    def _installDir(self, dirFilename, rootDir):
        assert dirFilename.startswith("/")

        if not os.path.isdir(dirFilename):
            raise Exception("\"%s\" is not a directory" % (dirFilename))

        dstDir = rootDir + dirFilename
        if os.path.islink(dirFilename):
            dirname = os.path.dirname(dstDir)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            os.symlink(os.readlink(dirFilename), dstDir)
        else:
            os.makedirs(dstDir)

    def _installBin(self, binFilename, rootDir):
        self._copyToInitrd(binFilename, rootDir)
        for df in FmUtil.libUsed(binFilename):
            self._copyToInitrd(df, rootDir)

    def _installBinFromInitDataDir(self, binFilename, rootDir, targetDir):
        srcFilename = os.path.join(FmConst.libInitrdDir, binFilename)
        dstFilename = os.path.join(rootDir, targetDir, binFilename)

        FmUtil.cmdCall("/bin/cp", "-f", srcFilename, dstFilename)
        FmUtil.cmdCall("/bin/chmod", "755", dstFilename)

        for df in FmUtil.libUsed(dstFilename):
            self._copyToInitrd(df, rootDir)

    def _installFilesLvm(self, rootDir):
        self._installBinFromInitDataDir("lvm-lv-activate", rootDir, "usr/sbin")

        # note: surrounded " would be recognized as part of rootDir, it's a bug of systemd-tmpfiles
        FmUtil.cmdCall("/bin/systemd-tmpfiles", "--create", "--root=%s" % (rootDir), "/usr/lib/tmpfiles.d/lvm2.conf")

        etcDir = os.path.join(rootDir, "etc", "lvm")
        if not os.path.exists(etcDir):
            os.mkdir(etcDir)
        with open(os.path.join(etcDir, "lvm.conf"), "w") as f:
            f.write("global {\n")
            f.write("    locking_type = 4\n")
            f.write("    use_lvmetad = 0\n")
            f.write("}\n")
            f.write("devices {\n")
            f.write("    write_cache_state = 0\n")
            f.write("}\n")
            f.write("backup {\n")
            f.write("    backup = 0\n")
            f.write("    archive = 0\n")
            f.write("}\n")

    def _installFilesBlkid(self, rootDir):
        etcDir = os.path.join(rootDir, "etc")
        if not os.path.exists(etcDir):
            os.mkdir(etcDir)
        with open(os.path.join(etcDir, "blkid.conf"), "w") as f:
            f.write("EVALUATE=scan\n")

    def _installInit(self, rootDir):
        self._installBinFromInitDataDir("init", rootDir, "")

    def _installStartupRc(self, rootDir, kmodList, blkOpList, fsckOpList, mntInfoDict, initCmdline):
        buf = ""

        # write comments
        for name, obj in mntInfoDict.items():
            if obj is not None:
                buf += "# uuid(%s)=%s\n" % (name, FmUtil.getBlkDevUuid(mntInfoDict[name].devPath))
        buf += "\n"

        # load kernel modules
        if len(kmodList) > 0:
            for k in kmodList:
                buf += "insmod \"%s\"\n" % (k)
            buf += "\n"

        # prepare block devices
        if len(blkOpList) > 0:
            for k in blkOpList:
                buf += "%s\n" % (k)
            buf += "\n"

        # do filesystem checking
        if len(fsckOpList) > 0:
            for k in fsckOpList:
                buf += "%s\n" % (k)
            buf += "\n"

        # mount root
        if True:
            mi = mntInfoDict["root"]
            uuid = FmUtil.getBlkDevUuid(mi.devPath)
            buf += "mount -t %s -o \"%s\" \"UUID=%s\" \"%s\"\n" % (mi.fsType, mi.mntOpt, uuid, "/sysroot")
            buf += "\n"

        # mount boot
        if mntInfoDict["boot"] is not None:
            mi = mntInfoDict["boot"]
            uuid = FmUtil.getBlkDevUuid(mi.devPath)
            buf += "mount -t %s -o \"%s\" \"UUID=%s\" \"%s\"\n" % (mi.fsType, mi.mntOpt, uuid, os.path.join("/sysroot", "boot"))
            buf += "\n"

        # switch to new root
        if initCmdline is not None:
            buf += "switchroot \"/sysroot\" %s\n" % (initCmdline)
        else:
            buf += "switchroot \"/sysroot\"\n"
        buf += "\n"

        # write cfg file
        with open(os.path.join(rootDir, "startup.rc"), "w") as f:
            f.write(buf)

    def _getBlkDevInfoList(self, devPath):
        # lvm2_raid
        lvmInfo = FmUtil.getBlkDevLvmInfo(devPath)
        if lvmInfo is not None:
            bdi = _BlkDevInfo()
            bdi.devPath = devPath
            bdi.devType = "lvm2_raid"
            bdi.fsType = FmUtil.getBlkDevFsType(devPath)
            assert bdi.fsType != ""
            bdi.param["vg_name"] = lvmInfo[0]
            bdi.param["lv_name"] = lvmInfo[1]

            retList = []
            for slaveDevPath in FmUtil.lvmGetSlaveDevPathList(lvmInfo[0]):
                retList += self._getBlkDevInfoList(slaveDevPath)
            return retList + [bdi]

        # mbr_partition
        m = re.fullmatch("(/dev/sd[a-z])[0-9]+", devPath)
        if m is None:
            m = re.fullmatch("(/dev/xvd[a-z])[0-9]+", devPath)
            if m is None:
                m = re.fullmatch("(/dev/vd[a-z])[0-9]+", devPath)
                if m is None:
                    m = re.fullmatch("(/dev/nvme[0-9]+n[0-9]+)p[0-9]+", devPath)
        if m is not None:
            bdi = _BlkDevInfo()
            bdi.devPath = devPath
            bdi.devType = "mbr_partition"
            bdi.fsType = FmUtil.getBlkDevFsType(devPath)
            assert bdi.fsType != ""
            return self._getBlkDevInfoList(m.group(1)) + [bdi]

        # scsi_disk
        m = re.fullmatch("/dev/sd[a-z]", devPath)
        if m is not None:
            bdi = _BlkDevInfo()
            bdi.devPath = devPath
            bdi.devType = "scsi_disk"
            bdi.fsType = FmUtil.getBlkDevFsType(devPath).lower()
            bdi.param["scsi_host_path"] = FmUtil.scsiGetHostControllerPath(devPath)
            return [bdi]

        # xen_disk
        m = re.fullmatch("/dev/xvd[a-z]", devPath)
        if m is not None:
            bdi = _BlkDevInfo()
            bdi.devPath = devPath
            bdi.devType = "xen_disk"
            bdi.fsType = FmUtil.getBlkDevFsType(devPath).lower()
            return [bdi]

        # virtio_disk
        m = re.fullmatch("/dev/vd[a-z]", devPath)
        if m is not None:
            bdi = _BlkDevInfo()
            bdi.devPath = devPath
            bdi.devType = "virtio_disk"
            bdi.fsType = FmUtil.getBlkDevFsType(devPath).lower()
            return [bdi]

        # nvme_disk
        m = re.fullmatch("/dev/nvme[0-9]+n[0-9]+", devPath)
        if m is not None:
            bdi = _BlkDevInfo()
            bdi.devPath = devPath
            bdi.devType = "nvme_disk"
            bdi.fsType = FmUtil.getBlkDevFsType(devPath).lower()
            return [bdi]

        # bcache
        m = re.fullmatch("/dev/bcache[0-9]+", devPath)
        if m is not None:
            bdi = _BlkDevInfo()
            bdi.devPath = devPath
            bdi.devType = "bcache_raid"
            bdi.fsType = FmUtil.getBlkDevFsType(devPath).lower()
            assert bdi.fsType != ""

            retList = []

            slist = FmUtil.bcacheGetSlaveDevPathList(devPath)
            assert (len(slist) >= 1)
            bdi.param["cache_dev_list"] = slist[0:-1]
            bdi.param["backing_dev"] = slist[-1]

            for devPath in slist:
                retList += self._getBlkDevInfoList(devPath)

            return retList + [bdi]

        # unknown
        print("devPath = %s" % (devPath))
        assert False

    def _copyToInitrd(self, filename, rootDir):
        assert os.path.isabs(filename)
        while True:
            if os.path.islink(filename):
                self._copyToInitrdImplLink(filename, rootDir)
                filename = os.path.join(os.path.dirname(filename), os.readlink(filename))
            else:
                self._copyToInitrdImplFile(filename, rootDir)
                break

    def _copyToInitrdImplLink(self, filename, rootDir):
        dstfile = os.path.join(rootDir, filename[1:])
        if os.path.exists(dstfile):
            return
        dstdir = os.path.dirname(dstfile)
        if not os.path.exists(dstdir):
            os.makedirs(dstdir)
        linkto = os.readlink(filename)
        os.symlink(linkto, dstfile)

    def _copyToInitrdImplFile(self, filename, rootDir):
        dstfile = os.path.join(rootDir, filename[1:])
        if os.path.exists(dstfile):
            return
        dstdir = os.path.dirname(dstfile)
        if not os.path.exists(dstdir):
            os.makedirs(dstdir)
        FmUtil.cmdCall("/bin/cp", "-f", filename, dstfile)


class _MntInfo:

    def __init__(self):
        self.devPath = None               # str
        self.fsType = None                # str
        self.mntOpt = None                # str


class _BlkDevInfo:

    def __init__(self):
        self.devPath = None               # str
        self.devType = None               # enum, "scsi_disk", "virtio_disk", "xen_disk", "nvme_disk", lvm2_raid", "bcache_raid", "mbr_partition", "gpt_partition"
        self.fsType = None                # enum, "", "lvm2_member", "bcache", "ext2", "ext4", "reiserfs", "xfs", "btrfs", "vfat"
        self.param = dict()
