#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import io
import gzip
import time
import glob
import shutil
import configparser
import robust_layer
import robust_layer.simple_git
import robust_layer.simple_subversion
import lxml.html
import urllib.request
import urllib.error
from fm_util import FmUtil
from fm_util import TempChdir
from fm_param import FmConst


class FkmKCache:

    def __init__(self):
        self.ksyncFile = os.path.join(FmConst.kcacheDir, "ksync.txt")

        # kernel information
        self.kernelUrl = "https://www.kernel.org"

        # firmware information
        self.firmwareUrl = "https://www.kernel.org/pub/linux/kernel/firmware"

        # kernel patch information
        self.patchDir = os.path.join(FmConst.dataDir, "kernel-n-patch", "patch")

        # extra kernel drivers
        # FIXME: check
        self.extraDriverDir = os.path.join(FmConst.dataDir, "kernel-n-patch", "driver")
        self.extraDriverDict = dict()
        for fn in os.listdir(self.extraDriverDir):
            self.extraDriverDict[fn] = self._parseExtraDriver(fn, os.path.join(self.extraDriverDir, fn))

        # extra firmwares
        # FIXME: check
        self.extraFirmwareDir = os.path.join(FmConst.dataDir, "kernel-n-patch", "firmware")
        self.extraFirmwareDict = dict()
        for fn in os.listdir(self.extraFirmwareDir):
            name = re.sub(r'\.ini$', "", fn)
            assert name != fn
            self.extraFirmwareDict[name] = self._parseExtraFirmware(name, os.path.join(self.extraFirmwareDir, fn))

        # wireless-regdb
        self.wirelessRegDbDirUrl = "https://www.kernel.org/pub/software/network/wireless-regdb"

    def sync(self):
        # get kernel version from internet
        if True:
            while True:
                ver = self._findKernelVersion("stable")
                if ver is not None:
                    self._writeKsyncFile("kernel", ver)
                    break
                time.sleep(1.0)
            print("Linux kernel: %s" % (self.getLatestKernelVersion()))

        # get firmware version version from internet
        if True:
            while True:
                ver = self._findFirmwareVersion()
                if ver is not None:
                    self._writeKsyncFile("firmware", ver)
                    break
                time.sleep(1.0)
            print("Firmware: %s" % (self.getLatestFirmwareVersion()))

        # get wireless-regulatory-database version from internet
        if True:
            while True:
                ver = self._findWirelessRegDbVersion()
                if ver is not None:
                    self._writeKsyncFile("wireless-regdb", ver)
                    break
                time.sleep(1.0)
            print("Wireless Regulatory Database: %s" % (self.getLatestWirelessRegDbVersion()))

    def getPatchList(self):
        # FIXME: other extension
        return [re.sub(r'\.py$', "", x) for x in os.listdir(self.patchDir)]

    def getExtraDriverList(self):
        return list(self.extraDriverDict.keys())

    def getExtraFirmwareList(self):
        return list(self.extraFirmwareDict.keys())

    def updateKernelCache(self, kernelVersion):
        kernelFile = "linux-%s.tar.xz" % (kernelVersion)
        signFile = "linux-%s.tar.sign" % (kernelVersion)
        myKernelFile = os.path.join(FmConst.kcacheDir, kernelFile)
        mySignFile = os.path.join(FmConst.kcacheDir, signFile)

        # we already have the latest linux kernel?
        if os.path.exists(myKernelFile):
            if os.path.exists(mySignFile):
                print("File already downloaded.")
                return
            else:
                FmUtil.forceDelete(myKernelFile)
                FmUtil.forceDelete(mySignFile)

        # get mirror
        mr, retlist = FmUtil.portageGetLinuxKernelMirror(FmConst.portageCfgMakeConf,
                                                         FmConst.defaultKernelMirror,
                                                         kernelVersion,
                                                         [kernelFile, signFile])
        kernelFile = retlist[0]
        signFile = retlist[1]

        # download the target file
        FmUtil.wgetDownload("%s/%s" % (mr, kernelFile), myKernelFile)
        FmUtil.wgetDownload("%s/%s" % (mr, signFile), mySignFile)

    def updateFirmwareCache(self, firmwareVersion):
        firmwareFile = "linux-firmware-%s.tar.xz" % (firmwareVersion)
        signFile = "linux-firmware-%s.tar.sign" % (firmwareVersion)
        myFirmwareFile = os.path.join(FmConst.kcacheDir, firmwareFile)
        mySignFile = os.path.join(FmConst.kcacheDir, signFile)

        # we already have the latest firmware?
        if os.path.exists(myFirmwareFile):
            if os.path.exists(mySignFile):
                print("File already downloaded.")
                return
            else:
                FmUtil.forceDelete(myFirmwareFile)
                FmUtil.forceDelete(mySignFile)

        # get mirror
        mr, retlist = FmUtil.portageGetLinuxFirmwareMirror(FmConst.portageCfgMakeConf,
                                                           FmConst.defaultKernelMirror,
                                                           [firmwareFile, signFile])
        firmwareFile = retlist[0]
        signFile = retlist[1]

        # download the target file
        FmUtil.wgetDownload("%s/%s" % (mr, firmwareFile), myFirmwareFile)
        FmUtil.wgetDownload("%s/%s" % (mr, signFile), mySignFile)

    def updateExtraSourceCache(self, sourceInfo):
        cacheDir = os.path.join(FmConst.kcacheDir, "source-%s" % (sourceInfo["name"]))

        # source type "git"
        if sourceInfo["update-method"] == "git":
            robust_layer.simple_git.pull(cacheDir, reclone_on_failure=True, url=sourceInfo["url"])
            return

        # source type "svn"
        if sourceInfo["update-method"] == "svn":
            robust_layer.simple_subversion.update(cacheDir, recheckout_on_failure=True, url=sourceInfo["url"])
            return

        # source type "exec"
        if sourceInfo["update-method"] == "exec":
            fullfn = os.path.join(sourceInfo["selfdir"], sourceInfo["executable"])
            os.makedirs(cacheDir, exist_ok=True)
            with TempChdir(cacheDir):
                assert fullfn.endswith(".py")
                FmUtil.cmdExec("python3", fullfn)     # FIXME, should respect shebang
            return

        # invalid source type
        assert False

    def updateWirelessRegDbCache(self, wirelessRegDbVersion):
        filename = "wireless-regdb-%s.tar.xz" % (wirelessRegDbVersion)
        localFile = os.path.join(FmConst.kcacheDir, filename)

        # we already have the latest wireless regulatory database?
        if os.path.exists(localFile):
            print("File already downloaded.")
            return

        # download the target file
        FmUtil.wgetDownload("%s/%s" % (self.wirelessRegDbDirUrl, filename), localFile)

    def getLatestKernelVersion(self):
        kernelVer = self._readDataFromKsyncFile("kernel")
        kernelVer = self._versionMaskCheck("kernel", kernelVer)
        return kernelVer

    def getKernelFileByVersion(self, version):
        """returns absolute file path"""

        fn = "linux-" + version + ".tar.xz"
        fn = os.path.join(FmConst.kcacheDir, fn)
        return fn

    def getKernelUseFlags(self):
        """returns list of USE flags"""

        ret = set()
        for fn in os.listdir(FmConst.kernelUseDir):
            for line in FmUtil.readListFile(os.path.join(FmConst.kernelUseDir, fn)):
                line = line.replace("\t", " ")
                line2 = ""
                while line2 != line:
                    line2 = line
                    line = line.replace("  ", " ")
                for item in line.split(" "):
                    if item.startswith("-"):
                        item = item[1:]
                        ret.remove(item)
                    else:
                        ret.add(item)
        return sorted(list(ret))

    def getLatestFirmwareVersion(self):
        # firmware version is the date when it is generated
        # example: 2019.06.03

        ret = self._readDataFromKsyncFile("firmware")
        ret = self._versionMaskCheck("firmware", ret)
        return ret

    def getFirmwareFileByVersion(self, version):
        """returns absolute file path"""

        fn = "linux-firmware-" + version + ".tar.xz"
        fn = os.path.join(FmConst.kcacheDir, fn)
        return fn

    def getPatchExecFile(self, patchName):
        return os.path.join(FmConst.dataDir, "kernel-n-patch", "patch", patchName + ".py")

    def getExtraDriverSourceInfo(self, driverName):
        return self.extraDriverDict[driverName]["source"]

    def getExtraDriverSourceDir(self, driverName):
        sourceInfo = self.getExtraDriverSourceInfo(driverName)
        return os.path.join(FmConst.kcacheDir, "source-%s" % (sourceInfo["name"]))

    def getExtraDriverExecFile(self, driverName):
        return os.path.join(FmConst.dataDir, "kernel-n-patch", "driver", driverName, "build.py")

    def getExtraFirmwareSourceInfo(self, firmwareName):
        return self.extraFirmwareDict[firmwareName]["source"]

    def getExtraFirmwareSourceDir(self, firmwareName):
        sourceInfo = self.getExtraFirmwareSourceInfo(firmwareName)
        return os.path.join(FmConst.kcacheDir, "source-%s" % (sourceInfo["name"]))

    def getExtraFirmwareFileMapping(self, firmwareName, filePath):
        # return (realFullFilePath, bOverWrite)

        obj = self.extraFirmwareDict[firmwareName]["file-mapping-overwrite"]
        if filePath in obj:
            return (os.path.join(self.getExtraFirmwareSourceDir(firmwareName), obj[filePath]), True)

        obj = self.extraFirmwareDict[firmwareName]["file-mapping"]
        if filePath in obj:
            return (os.path.join(self.getExtraFirmwareSourceDir(firmwareName), obj[filePath]), False)

        return (None, None)

    def getLatestWirelessRegDbVersion(self):
        # wireless regulatory database version is the date when it is generated
        # example: 2019.06.03

        ret = self._readDataFromKsyncFile("wireless-regdb")
        ret = self._versionMaskCheck("wireless-regdb", ret)
        return ret

    def getWirelessRegDbFileByVersion(self, version):
        """returns absolute file path"""

        fn = "wireless-regdb-" + version + ".tar.xz"
        fn = os.path.join(FmConst.kcacheDir, fn)
        return fn

    def getOldKernelFileList(self, cbe):
        kernelFileList = []
        for f in os.listdir(FmConst.kcacheDir):
            if f.startswith("linux-") and f.endswith(".tar.xz") and not f.startswith("linux-firmware-"):
                if FmUtil.compareVersion(f.replace("linux-", "").replace(".tar.xz", ""), cbe.buildTarget.verstr) < 0:
                    kernelFileList.append(f)    # remove lower version
            elif f.startswith("linux-") and f.endswith(".tar.sign") and not f.startswith("linux-firmware-"):
                if FmUtil.compareVersion(f.replace("linux-", "").replace(".tar.sign", ""), cbe.buildTarget.verstr) < 0:
                    kernelFileList.append(f)    # remove lower version
        return sorted(kernelFileList)

    def getOldFirmwareFileList(self):
        fileList = []
        for f in os.listdir(FmConst.kcacheDir):
            if f.startswith("linux-firmware-") and f.endswith(".tar.xz"):
                fileList.append(f)
                fileList.append(f.replace(".xz", ".sign"))
        fileList = sorted(fileList)
        if len(fileList) > 0:
            fileList = fileList[:-2]
        return fileList

    def getOldWirelessRegDbFileList(self):
        fileList = []
        for f in os.listdir(FmConst.kcacheDir):
            if f.startswith("wireless-regdb-") and f.endswith(".tar.xz"):
                fileList.append(f)
        fileList = sorted(fileList)
        if len(fileList) > 0:
            fileList = fileList[:-1]
        return fileList

    def _readDataFromKsyncFile(self, prefix):
        indexDict = {
            "kernel": 0,
            "firmware": 1,
            "wireless-regdb": 2,
        }
        with open(self.ksyncFile, "r") as f:
            return f.read().split("\n")[indexDict[prefix]]

    def _versionMaskCheck(self, prefix, version):
        for fn in os.listdir(FmConst.kernelMaskDir):
            with open(os.path.join(FmConst.kernelMaskDir, fn), "r") as f:
                buf = f.read()
                m = re.search("^%s-(.*)$" % (prefix), buf, re.M)
                if m is not None:
                    if version > m.group(1):
                        version = m.group(1)
        return version

    def _findKernelVersion(self, typename):
        try:
            resp = urllib.request.urlopen(self.kernelUrl, timeout=robust_layer.TIMEOUT)
            if resp.info().get('Content-Encoding') is None:
                fakef = resp
            elif resp.info().get('Content-Encoding') == 'gzip':
                fakef = io.BytesIO(resp.read())
                fakef = gzip.GzipFile(fileobj=fakef)
            else:
                assert False
            root = lxml.html.parse(fakef)

            td = root.xpath(".//td[text()='%s:']" % (typename))[0]
            td = td.getnext()
            while len(td) > 0:
                td = td[0]
            return td.text
        except Exception as e:
            print("Failed to acces %s, %s" % (self.kernelUrl, e))
            return None

    def _findFirmwareVersion(self):
        try:
            resp = urllib.request.urlopen(self.firmwareUrl, timeout=robust_layer.TIMEOUT)
            root = lxml.html.parse(resp)
            ret = None
            for atag in root.xpath(".//a"):
                m = re.fullmatch("linux-firmware-(.*)\\.tar\\.xz", atag.text)
                if m is not None:
                    if ret is None or ret < m.group(1):
                        ret = m.group(1)
            assert ret is not None
            return ret
        except Exception as e:
            print("Failed to acces %s, %s" % (self.firmwareUrl, e))
            return None

    def _findWirelessRegDbVersion(self):
        try:
            ver = None
            resp = urllib.request.urlopen(self.wirelessRegDbDirUrl, timeout=robust_layer.TIMEOUT)
            out = resp.read().decode("iso8859-1")
            for m in re.finditer("wireless-regdb-([0-9]+\\.[0-9]+\\.[0-9]+)\\.tar\\.xz", out, re.M):
                if ver is None or m.group(1) > ver:
                    ver = m.group(1)
            return ver
        except Exception as e:
            print("Failed to acces %s, %s" % (self.wirelessRegDbDirUrl, e))
            return None

    def _writeKsyncFile(self, key, *kargs):
        vlist = ["", "", "", ""]
        if os.path.exists(self.ksyncFile):
            with open(self.ksyncFile) as f:
                vlist = f.read().split("\n")[0:3]
                while len(vlist) < 4:
                    vlist.append("")

        if key == "kernel":
            vlist[0] = kargs[0]
        elif key == "firmware":
            vlist[1] = kargs[0]
        elif key == "wireless-regdb":
            vlist[2] = kargs[0]

        with open(self.ksyncFile, "w") as f:
            for v in vlist:
                f.write(v + "\n")

    def _parseExtraDriver(self, name, dir_path):
        ret = {}

        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(dir_path, "main.ini"))

        updateMethod = cfg.get("source", "update-method")
        if updateMethod == "git":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "git",
                "url": cfg.get("source", "url"),
            }
        elif updateMethod == "svn":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "svn",
                "url": cfg.get("source", "url"),
            }
        elif updateMethod == "exec":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "exec",
                "executable": cfg.get("source", "executable"),
                "selfdir": dir_path,
            }
        else:
            raise Exception("invalid update-method \"%s\" in config file of extra kernel driver \"%s\"", (updateMethod, name))

        return ret

    def _parseExtraFirmware(self, name, file_path):
        ret = {}

        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(file_path))

        updateMethod = cfg.get("source", "update-method")
        if updateMethod == "git":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "git",
                "url": cfg.get("source", "url"),
            }
        elif updateMethod == "svn":
            ret["source"] = {
                "name": cfg.get("source", "name"),
                "update-method": "svn",
                "url": cfg.get("source", "url"),
            }
        else:
            raise Exception("invalid update-method \"%s\" in config file of extra firmware \"%s\"", (updateMethod, name))

        for section in ["file-mapping", "file-mapping-overwrite"]:
            ret[section] = dict()
            if cfg.has_section(section):
                for opt in cfg.options(section):
                    ret[section][opt] = cfg.get(section, opt)

        return ret


class FkmBuildTarget:

    def __init__(self):
        self._arch = None
        self._verstr = None

    @property
    def name(self):
        # string, eg: "linux-x86_64-3.9.11-gentoo-r1"
        return "linux-" + self._arch + "-" + self._verstr

    @property
    def postfix(self):
        # string, eg: "x86_64-3.9.11-gentoo-r1"
        return self._arch + "-" + self._verstr

    @property
    def arch(self):
        # string, eg: "x86_64".
        return self._arch

    @property
    def srcArch(self):
        if self._arch == "i386" or self._arch == "x86_64":
            return "x86"
        elif self._arch == "sparc32" or self._arch == "sparc64":
            return "sparc"
        elif self._arch == "sh":
            return "sh64"
        else:
            return self._arch

    @property
    def verstr(self):
        # string, eg: "3.9.11-gentoo-r1"
        return self._verstr

    @property
    def ver(self):
        # string, eg: "3.9.11"
        try:
            return self._verstr[:self._verstr.index("-")]
        except ValueError:
            return self._verstr

    @property
    def kernelFile(self):
        return "kernel-" + self.postfix

    @property
    def kernelCfgFile(self):
        return "config-" + self.postfix

    @property
    def kernelCfgRuleFile(self):
        return "config-" + self.postfix + ".rules"

    @property
    def kernelMapFile(self):
        return "System.map-" + self.postfix

    @property
    def kernelSrcSignatureFile(self):
        return "signature-" + self.postfix

    @property
    def initrdFile(self):
        return "initramfs-" + self.postfix

    @property
    def initrdTarFile(self):
        return "initramfs-files-" + self.postfix + ".tar.bz2"

    @staticmethod
    def newFromPostfix(postfix):
        partList = postfix.split("-")
        if len(partList) < 2:
            raise Exception("illegal postfix")

        bTarget = FkmBuildTarget()
        bTarget._arch = partList[0]
        bTarget._verstr = "-".join(partList[1:])
        return bTarget

    @staticmethod
    def newFromKernelFilename(kernelFilename):
        """kernelFilename format: kernel-x86_64-3.9.11-gentoo-r1"""

        assert os.path.basename(kernelFilename) == kernelFilename

        partList = kernelFilename.split("-")
        if len(partList) < 3:
            raise Exception("illegal kernel file")
        if not FmUtil.isValidKernelArch(partList[1]):
            raise Exception("illegal kernel file")
        if not FmUtil.isValidKernelVer(partList[2]):
            raise Exception("illegal kernel file")

        bTarget = FkmBuildTarget()
        bTarget._arch = partList[1]
        bTarget._verstr = "-".join(partList[2:])
        return bTarget

    @staticmethod
    def newFromKernelDir(hostArch, kernelDir):
        assert os.path.isabs(kernelDir)

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

        bTarget = FkmBuildTarget()
        bTarget._arch = hostArch
        if extraversion is not None:
            bTarget._verstr = "%d.%d.%d%s" % (version, patchlevel, sublevel, extraversion)
        else:
            bTarget._verstr = "%d.%d.%d" % (version, patchlevel, sublevel)
        return bTarget


class FkmBootEntry:

    def __init__(self, buildTarget):
        self.buildTarget = buildTarget

    @property
    def kernelFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelFile)

    @property
    def kernelCfgFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelCfgFile)

    @property
    def kernelCfgRuleFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelCfgRuleFile)

    @property
    def kernelSrcSignatureFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelSrcSignatureFile)

    @property
    def kernelMapFile(self):
        return os.path.join(_bootDir, self.buildTarget.kernelMapFile)

    @property
    def initrdFile(self):
        return os.path.join(_bootDir, self.buildTarget.initrdFile)

    @property
    def initrdTarFile(self):
        return os.path.join(_bootDir, self.buildTarget.initrdTarFile)

    def kernelFilesExists(self):
        if not os.path.exists(self.kernelFile):
            return False
        if not os.path.exists(self.kernelCfgFile):
            return False
        if not os.path.exists(self.kernelCfgRuleFile):
            return False
        if not os.path.exists(self.kernelMapFile):
            return False
        if not os.path.exists(self.kernelSrcSignatureFile):
            return False
        return True

    def initrdFileExists(self):
        if not os.path.exists(self.initrdFile):
            return False
        if not os.path.exists(self.initrdTarFile):
            return False
        return True

    @staticmethod
    def findCurrent(strict=True):
        ret = [x for x in sorted(os.listdir(_bootDir)) if x.startswith("kernel-")]
        if ret == []:
            return None

        buildTarget = FkmBuildTarget.newFromKernelFilename(ret[-1])
        cbe = FkmBootEntry(buildTarget)
        if strict:
            if not cbe.kernelFilesExists():
                return None
            if not cbe.initrdFileExists():
                return None
        return cbe


class FkmKernelBuilder:

    def __init__(self, kcacheObj, kernelCfgRules):
        self.kcache = kcacheObj
        self.kernelCfgRules = kernelCfgRules

        self.tmpDir = None
        if True:
            tDir = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "PORTAGE_TMPDIR")
            if tDir == "":
                tDir = "/var/tmp"
            self.tmpDir = os.path.join(tDir, "kernel")

        self.ksrcTmpDir = os.path.join(self.tmpDir, "ksrc")
        self.firmwareTmpDir = os.path.join(self.tmpDir, "firmware")
        self.wirelessRegDbTmpDir = os.path.join(self.tmpDir, "wireless-regdb")
        self.kcfgRulesTmpFile = os.path.join(self.tmpDir, "kconfig.rules")

        fn = self.kcache.getKernelFileByVersion(self.kcache.getLatestKernelVersion())
        if not os.path.exists(fn):
            raise Exception("\"%s\" does not exist" % (fn))

        fn = self.kcache.getFirmwareFileByVersion(self.kcache.getLatestFirmwareVersion())
        if not os.path.exists(fn):
            raise Exception("\"%s\" does not exist" % (fn))

        self.kernelVer = self.kcache.getLatestKernelVersion()
        self.firmwareVer = self.kcache.getLatestFirmwareVersion()
        self.wirelessRegDbVer = self.kcache.getLatestWirelessRegDbVersion()

        self.realSrcDir = None
        self.dotCfgFile = None
        self.dstTarget = None
        self.srcSignature = None

        # trick: kernel debug is seldomly needed
        self.trickDebug = False

    def buildStepExtract(self):
        FmUtil.forceDelete(self.tmpDir)         # FIXME

        # extract kernel source
        os.makedirs(self.ksrcTmpDir)
        fn = self.kcache.getKernelFileByVersion(self.kernelVer)
        FmUtil.cmdCall("/bin/tar", "-xJf", fn, "-C", self.ksrcTmpDir)
        realSrcDir = os.path.join(self.ksrcTmpDir, os.listdir(self.ksrcTmpDir)[0])

        # patch kernel source
        for name in self.kcache.getPatchList():
            fullfn = self.kcache.getPatchExecFile(name)
            out = None
            with TempChdir(realSrcDir):
                assert fullfn.endswith(".py")
                out = FmUtil.cmdCall("python3", fullfn)     # FIXME, should respect shebang
            if out == "outdated":
                print("WARNING: Kernel patch \"%s\" is outdated." % (name))
            elif out == "":
                pass
            else:
                raise Exception("Kernel patch \"%s\" exits with error \"%s\"." % (name, out))

        # extract kernel firmware
        os.makedirs(self.firmwareTmpDir)
        fn = self.kcache.getFirmwareFileByVersion(self.firmwareVer)
        FmUtil.cmdCall("/bin/tar", "-xJf", fn, "-C", self.firmwareTmpDir)

        # extract wireless regulatory database
        os.makedirs(self.wirelessRegDbTmpDir)
        fn = self.kcache.getWirelessRegDbFileByVersion(self.wirelessRegDbVer)
        FmUtil.cmdCall("/bin/tar", "-xJf", fn, "-C", self.wirelessRegDbTmpDir)

        # get real source directory
        self.realSrcDir = realSrcDir
        self.dotCfgFile = os.path.join(self.realSrcDir, ".config")
        self.dstTarget = FkmBuildTarget.newFromKernelDir(FmUtil.getHostArch(), self.realSrcDir)

        # calculate source signature
        self.srcSignature = "kernel: %s\n" % (FmUtil.hashDir(self.realSrcDir))
        for name in self.kcache.getExtraDriverList():
            sourceDir = self.kcache.getExtraDriverSourceDir(name)
            self.srcSignature += "edrv-src-%s: %s\n" % (name, FmUtil.hashDir(sourceDir))

    def buildStepGenerateDotCfg(self):
        # head rules
        buf = ""
        if True:
            # default hostname
            buf += "DEFAULT_HOSTNAME=\"(none)\"\n"
            buf += "\n"

            # deprecated symbol, but many drivers still need it
            buf += "FW_LOADER=y\n"
            buf += "\n"

            # atk9k depends on it
            buf += "DEBUG_FS=y\n"
            buf += "\n"

            # H3C CAS 2.0 still use legacy virtio device, so it is needed
            buf += "VIRTIO_PCI_LEGACY=y\n"
            buf += "\n"

            # we still need iptables
            buf += "NETFILTER_XTABLES=y\n"
            buf += "IP_NF_IPTABLES=y\n"
            buf += "IP_NF_ARPTABLES=y\n"
            buf += "\n"

            # it seems we still need this, why?
            buf += "FB=y\n"
            buf += "DRM_FBDEV_EMULATION=y\n"
            buf += "\n"

            # net-wireless/iwd needs them, FIXME
            buf += "PKCS8_PRIVATE_KEY_PARSER=y\n"
            buf += "KEY_DH_OPERATIONS=y\n"
            buf += "\n"

            # android features need by anbox program
            if "anbox" in self.kcache.getKernelUseFlags():
                buf += "[symbols:/Device drivers/Android]=y\n"
                buf += "STAGING=y\n"
                buf += "ASHMEM=y\n"
                buf += "\n"

            # debug feature
            if True:
                # killing CONFIG_VT is failed for now
                buf += "TTY=y\n"
                buf += "[symbols:VT]=y\n"
                buf += "[symbols:/Device Drivers/Graphics support/Console display driver support]=y\n"
                buf += "\n"
            if self.trickDebug:
                pass

            # symbols we dislike
            buf += "[debugging-symbols:/]=n\n"
            buf += "[deprecated-symbols:/]=n\n"
            buf += "[workaround-symbols:/]=n\n"
            buf += "[experimental-symbols:/]=n\n"
            buf += "[dangerous-symbols:/]=n\n"
            buf += "\n"

        # generate rules file
        self._generateKernelCfgRulesFile(self.kcfgRulesTmpFile,
                                         {"head": buf},
                                         self.kernelCfgRules)

        # debug feature
        if True:
            # killing CONFIG_VT is failed for now
            FmUtil.shellCall("/bin/sed -i '/VT=n/d' %s" % (self.kcfgRulesTmpFile))
        if self.trickDebug:
            FmUtil.shellCall("/bin/sed -i 's/=m,y/=y/g' %s" % (self.kcfgRulesTmpFile))
            FmUtil.shellCall("/bin/sed -i 's/=m/=y/g' %s" % (self.kcfgRulesTmpFile))

        # generate the real ".config"
        FmUtil.cmdCall("/usr/libexec/fpemud-os-sysman/bugfix-generate-dotcfgfile.py",
                       self.realSrcDir, self.kcfgRulesTmpFile, self.dotCfgFile)

        # "make olddefconfig" may change the .config file further
        self._makeAuxillary(self.realSrcDir, "olddefconfig")

    def buildStepMakeInstall(self):
        self._makeMain(self.realSrcDir)
        FmUtil.cmdCall("/bin/cp", "-f",
                       "%s/arch/%s/boot/bzImage" % (self.realSrcDir, self.dstTarget.arch),
                       os.path.join(_bootDir, self.dstTarget.kernelFile))
        FmUtil.cmdCall("/bin/cp", "-f",
                       "%s/System.map" % (self.realSrcDir),
                       os.path.join(_bootDir, self.dstTarget.kernelMapFile))
        FmUtil.cmdCall("/bin/cp", "-f",
                       "%s/.config" % (self.realSrcDir),
                       os.path.join(_bootDir, self.dstTarget.kernelCfgFile))
        FmUtil.cmdCall("/bin/cp", "-f",
                       self.kcfgRulesTmpFile,
                       os.path.join(_bootDir, self.dstTarget.kernelCfgRuleFile))

        self._makeAuxillary(self.realSrcDir, "modules_install")

    def buildStepInstallFirmware(self):
        # get add all *used* firmware file
        # FIXME:
        # 1. should consider built-in modules by parsing /lib/modules/X.Y.Z/modules.builtin.modinfo
        # 2. currently it seems built-in modules don't need firmware
        firmwareList = []
        for fullfn in glob.glob(os.path.join("/lib/modules", self.dstTarget.verstr, "**", "*.ko"), recursive=True):
            # python-kmod bug: can only recognize the last firmware in modinfo
            # so use the command output of modinfo directly
            for line in FmUtil.cmdCall("/bin/modinfo", fullfn).split("\n"):
                m = re.fullmatch("firmware: +(\\S.*)", line)
                if m is not None:
                    firmwareList.append((m.group(1), fullfn.replace("/lib/modules/%s/" % (self.dstTarget.verstr), "")))

        # copy firmware from official firmware repository
        os.makedirs("/lib/firmware", exist_ok=True)
        for fn, kn in firmwareList:
            srcFn = os.path.join(self.firmwareTmpDir, fn)
            dstFn = os.path.join("/lib/firmware", fn)
            if os.path.exists(srcFn):
                os.makedirs(os.path.dirname(dstFn), exist_ok=True)
                shutil.copy(srcFn, dstFn)

        # copy firmware from extra firmware repositories
        if True:
            usedExtraNames = set()
            for fn, kn in firmwareList:
                dstFn = os.path.join("/lib/firmware", fn)
                for firmwareName in self.kcache.getExtraFirmwareList():
                    fullfn, bOverWrite = self.kcache.getExtraFirmwareFileMapping(firmwareName, fn)
                    if fullfn is None:
                        continue
                    if os.path.exists(dstFn) and not bOverWrite:
                        continue
                    os.makedirs(os.path.dirname(dstFn), exist_ok=True)
                    shutil.copy(fullfn, dstFn)
                    usedExtraNames.add(firmwareName)
            for firmwareName in set(self.kcache.getExtraFirmwareList()) - usedExtraNames:
                print("WARNING: Extra firmware \"%s\" is outdated." % (firmwareName))

        # copy wireless-regdb
        if True:
            ret = glob.glob(os.path.join(self.wirelessRegDbTmpDir, "**", "regulatory.db"), recursive=True)
            assert len(ret) == 1
            shutil.copy(ret[0], "/lib/firmware")
        if True:
            ret = glob.glob(os.path.join(self.wirelessRegDbTmpDir, "**", "regulatory.db.p7s"), recursive=True)
            assert len(ret) == 1
            shutil.copy(ret[0], "/lib/firmware")

        # ensure corrent permission
        FmUtil.shellCall("/usr/bin/find /lib/firmware -type f | xargs chmod 644")
        FmUtil.shellCall("/usr/bin/find /lib/firmware -type d | xargs chmod 755")

        # record
        with open("/lib/firmware/.ctime", "w") as f:
            f.write(self.firmwareVer + "\n")
            f.write(self.wirelessRegDbVer + "\n")

    def buildStepBuildAndInstallExtraDriver(self, driverName):
        cacheDir = self.kcache.getExtraDriverSourceDir(driverName)
        fullfn = self.kcache.getExtraDriverExecFile(driverName)
        buildTmpDir = os.path.join(self.tmpDir, driverName)
        os.mkdir(buildTmpDir)
        with TempChdir(buildTmpDir):
            assert fullfn.endswith(".py")
            FmUtil.cmdExec("python3", fullfn, cacheDir, self.kernelVer)     # FIXME, should respect shebang

    def buildStepClean(self):
        with open(os.path.join(_bootDir, self.dstTarget.kernelSrcSignatureFile), "w") as f:
            f.write(self.srcSignature)
        os.unlink(os.path.join(self._getModulesDir(), "source"))
        os.unlink(os.path.join(self._getModulesDir(), "build"))

    def _getModulesDir(self):
        return "/lib/modules/%s" % (self.kernelVer)

    def _makeMain(self, dirname, envVarList=[]):
        optList = []

        # CFLAGS
        optList.append("CFLAGS=\"-Wno-error\"")

        # from /etc/portage/make.conf
        optList.append(FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS"))

        # from envVarList
        optList += envVarList

        # execute command
        with TempChdir(dirname):
            FmUtil.shellCall("/usr/bin/make %s" % (" ".join(optList)))

    def _makeAuxillary(self, dirname, target, envVarList=[]):
        with TempChdir(dirname):
            FmUtil.shellCall("/usr/bin/make %s %s" % (" ".join(envVarList), target))

    def _generateKernelCfgRulesFile(self, filename, *kargs):
        with open(filename, "w") as f:
            for kcfgRulesMap in kargs:
                for name, buf in kcfgRulesMap.items():
                    f.write("## %s ######################\n" % (name))
                    f.write("\n")
                    f.write(buf)
                    f.write("\n")
                    f.write("\n")
                    f.write("\n")


_bootDir = "/boot"
