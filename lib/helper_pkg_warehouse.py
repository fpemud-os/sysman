#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import glob
import time
import shutil
import portage
import pathlib
import fileinput
import configparser
import lxml.etree
import urllib.request
import robust_layer.git
import robust_layer.simple_git
import robust_layer.subversion
import robust_layer.simple_subversion
import robust_layer.rsync
import robust_layer.simple_fops
from fm_util import FmUtil
from fm_param import FmConst


class PkgWarehouse:

    def __init__(self):
        self.repoman = EbuildRepositories()
        self.layman = EbuildOverlays()

    def getPreEnableOverlays(self):
        ret = dict()
        modDir = os.path.join(FmConst.dataDir, "pre-enable")
        if os.path.exists(modDir):
            fullfnList = []
            fullfnList += list(glob.glob(os.path.join(modDir, "*.new_overlay")))
            for fullfn in fullfnList:
                cfg = configparser.ConfigParser()
                cfg.read(fullfn)
                name = cfg.get("main", "name", fallback=os.path.basename(fullfn).replace(".new_overlay", ""))
                url = cfg.get("main", "url", fallback=None)
                ret[name] = url
        return ret

    def getPreEnablePackages(self):
        ret = dict()
        modDir = os.path.join(FmConst.dataDir, "pre-enable")
        if os.path.exists(modDir):
            fullfnList = []
            fullfnList += list(glob.glob(os.path.join(modDir, "*.new_package")))
            for fullfn in fullfnList:
                cfg = configparser.ConfigParser()
                cfg.read(fullfn)
                name = cfg.get("main", "name")
                url = cfg.get("main", "url", fallback=None)
                package = cfg.get("main", "package")
                if name in ret:
                    assert url is None or url == ret[name][0]
                    ret[name][1].append(package)
                else:
                    ret[name] = (url, [package])
        return ret

    def getKeywordList(self):
        chost = FmUtil.portageGetChost()
        arch = chost[:chost.index("-")]
        if arch == "x86":
            return ["x86"]
        elif arch == "x86_64":
            return ["x86", "amd64"]
        else:
            assert False

    def checkHardwareUseFlags(self, hwInfo):
        self._operateHardwareUseFlags(True, "30", "hardware", hwInfo)

    def refreshHardwareUseFlags(self, hwInfo):
        self._operateHardwareUseFlags(False, "30", "hardware", hwInfo)

    def checkTargetUseFlags(self):
        self._operateTargetsUseFlags(True,
                                     "90", "python",
                                     self.__pythonGetDefaultTargetsUseFlag,
                                     self.__pythonCompareTargetsUseFlag,
                                     self.__pythonCheckMainPackageOfTargetUseFlag)
        self._operateTargetsUseFlags(True,
                                     "91", "ruby",
                                     self.__rubyGetDefaultTargetsUseFlag,
                                     self.__rubyCompareDefaultTargetsUseFlag,
                                     self.__rubyCheckMainPackageOfTargetUseFlag)

    def refreshTargetUseFlags(self):
        self._operateTargetsUseFlags(False,
                                     "90", "python",
                                     self.__pythonGetDefaultTargetsUseFlag,
                                     self.__pythonCompareTargetsUseFlag,
                                     self.__pythonCheckMainPackageOfTargetUseFlag)
        self._operateTargetsUseFlags(False,
                                     "91", "ruby",
                                     self.__rubyGetDefaultTargetsUseFlag,
                                     self.__rubyCompareDefaultTargetsUseFlag,
                                     self.__rubyCheckMainPackageOfTargetUseFlag)

    def checkLinguasUseFlags(self):
        self._operateLinguasUseFlags(True, "97", "linguas")

    def refreshLinguasUseFlags(self):
        self._operateLinguasUseFlags(False, "97", "linguas")

    def _operateHardwareUseFlags(self, checkOrRefresh, id, name, hwInfo):
        usefn = os.path.join(FmConst.portageCfgUseDir, "%s-%s" % (id, name))
        fnContent = self.__generateUseFlagsFileContent(hwInfo.useFlags)

        if checkOrRefresh:
            if not os.path.exists(usefn):
                raise Exception("\"%s\" does not exist" % (usefn))
            with open(usefn, "r") as f:
                if f.read() != fnContent:
                    raise Exception("\"%s\" has invalid content" % (usefn))
        else:
            with open(usefn, "w") as f:
                f.write(fnContent)

    def _operateTargetsUseFlags(self, checkOrRefresh, id, name, getDefaultTargetsUseFlag, cmpTargetsUseFlag, checkMainPackageOfTargetUseFlag):
        usefn = os.path.join(FmConst.portageCfgUseDir, "%s-%s-targets" % (id, name))

        # default use flag
        defaultUse = getDefaultTargetsUseFlag()
        if defaultUse is None:
            if checkOrRefresh:
                if os.path.exists(usefn):
                    raise Exception("\"%s\" should not exist" % (usefn))
            else:
                robust_layer.simple_fops.rm(usefn)
        else:
            ret, mainPackage = checkMainPackageOfTargetUseFlag(defaultUse)
            if not ret:
                raise Exception("main package \"%s\" for USE flag \"%s\" is masked" % (mainPackage, defaultUse))

            fnContent = ""
            fnContent += "# default version\n"
            fnContent += "*/* %s\n" % (defaultUse)

            # use flag of higher versions
            if True:
                useSet = set()
                if True:
                    for repoName in self.repoman.getRepositoryList():
                        repoDir = self.repoman.getRepoDir(repoName)
                        fn = os.path.join(repoDir, "profiles", "desc", "%s_targets.desc" % (name))
                        if os.path.exists(fn):
                            useSet |= set(self.__getTargetsUseFlagList(fn))
                    for overlayName in self.layman.getOverlayList():
                        fn = os.path.join(self.layman.getOverlayDir(overlayName), "profiles", "desc", "%s_targets.desc" % (name))
                        if os.path.exists(fn):
                            useSet |= set(self.__getTargetsUseFlagList(fn))
                fnContent += "\n"
                fnContent += "# higher versions\n"
                if True:
                    line = ""
                    for u in sorted(list(useSet)):
                        if not checkMainPackageOfTargetUseFlag(u)[0]:
                            continue
                        if cmpTargetsUseFlag(useSet, u, defaultUse) <= 0:
                            continue
                        line += " " + u
                    if line != "":
                        fnContent += "*/*%s\n" % (line)
                    else:
                        fnContent += "\n"

            # operate configuration file
            if checkOrRefresh:
                if not os.path.exists(usefn):
                    raise Exception("\"%s\" does not exist" % (usefn))
                with open(usefn, "r") as f:
                    if fnContent != f.read():
                        raise Exception("\"%s\" has invalid content" % (usefn))
            else:
                with open(usefn, "w") as f:
                    f.write(fnContent)

    def _operateLinguasUseFlags(self, checkOrRefresh, id, name):
        usefn = os.path.join(FmConst.portageCfgUseDir, "%s-%s" % (id, name))
        portree = portage.db[portage.root]["porttree"]

        # get all languages
        useSet = set()
        for repoName in self.repoman.getRepositoryList():
            for pkgName in FmUtil.repoGetEbuildDirList(self.repoman.getRepoDir(repoName)):
                for cpv in portree.dbapi.match(pkgName):
                    for use in portree.dbapi.aux_get(cpv, ["IUSE"])[0].split():
                        if use.startswith("l10n_"):
                            useSet.add(use[len("l10n_"):])
                        elif use.startswith("+l10n_"):
                            useSet.add(use[len("+l10n_"):])

        # trick: we keep "no" since "nb" and "no" conflict, see https://bugs.gentoo.org/775734
        if "nb" in useSet and "no" in useSet:
            useSet.remove("nb")

        # construct L10N line
        useList = sorted(list(useSet))
        fnContent = "*/*     L10N: %s" % (" ".join(useList))

        # file operation
        if checkOrRefresh:
            if not os.path.exists(usefn):
                raise Exception("\"%s\" does not exist" % (usefn))
            with open(usefn, "r") as f:
                if fnContent != f.read():
                    raise Exception("\"%s\" has invalid content" % (usefn))
        else:
            with open(usefn, "w") as f:
                f.write(fnContent)

    def __generateUseFlagsFileContent(self, *kargs):
        ret = ""
        for useFlagsMap in kargs:
            for name, buf in useFlagsMap.items():
                ret += "## %s ##\n" % (name)
                ret += "\n"
                ret += buf
                ret += "\n"
                ret += "\n"
        return ret

    def __getTargetsUseFlagList(self, descFile):
        prefix = os.path.splitext(os.path.basename(descFile))[0]
        ret = []
        with open(descFile, "r") as f:
            for m in re.finditer("^(.*?)\\s+-\\s+.*", f.read(), re.M):
                if m.group(1).startswith("#"):
                    continue
                ret.append(prefix + "_" + m.group(1))
        return ret

    def __pythonGetDefaultTargetsUseFlag(self):
        rc, out = FmUtil.cmdCallWithRetCode("eselect", "python", "show")
        if rc == 0:
            return "python_targets_" + out.replace(".", "_")
        else:
            return None

    def __pythonCompareTargetsUseFlag(self, useSet, a, b):
        assert a.startswith("python_targets_")
        assert b.startswith("python_targets_")
        a = a.replace("python_targets_", "")
        b = b.replace("python_targets_", "")

        if a.startswith("python") and b.startswith("python"):
            a = a.replace("python", "").replace("_", ".")
            b = b.replace("python", "").replace("_", ".")
            return FmUtil.compareVersion(a, b)

        # we think "pypy" always be less than "pythonX.Y", so it won't be selected
        if a.startswith("pypy") and b.startswith("pypy"):
            return 0
        if a.startswith("python") and b.startswith("pypy"):
            return 1
        if a.startswith("pypy") and b.startswith("python"):
            return -1

        # we think "jython" always be less than "pythonX.Y", so it won't be selected
        if a.startswith("jython") or b.startswith("jython"):
            return 0
        if a.startswith("python") and b.startswith("jython"):
            return 1
        if a.startswith("jython") and b.startswith("python"):
            return -1

        assert False

    def __pythonCheckMainPackageOfTargetUseFlag(self, useFlag):
        assert useFlag.startswith("python_targets_")
        useFlag = useFlag.replace("python_targets_", "")

        if useFlag.startswith("python"):
            useFlag = useFlag.replace("python", "")
            slot = useFlag.replace("_", ".")
            pkgName = "dev-lang/python:%s" % (slot)
            return (FmUtil.portageIsPkgInstallable(pkgName), pkgName)

        if useFlag.startswith("pypy"):
            ver = useFlag.replace("pypy", "")
            assert ver in ["", "3"]
            pkgName = "dev-python/pypy%s" % (ver)
            return (FmUtil.portageIsPkgInstallable(pkgName), pkgName)

        if useFlag.startswith("jython"):
            # FIXME
            assert False

        assert False

    def __rubyGetDefaultTargetsUseFlag(self):
        rc, out = FmUtil.cmdCallWithRetCode("eselect", "ruby", "show")
        if rc == 0:
            m = re.search("ruby[0-9]+", out, re.M)
            return "ruby_targets_" + m.group(0)
        else:
            return None

    def __rubyCompareDefaultTargetsUseFlag(self, useSet, a, b):
        assert a.startswith("ruby_targets_")
        assert b.startswith("ruby_targets_")
        a = a.replace("ruby_targets_", "")
        b = b.replace("ruby_targets_", "")

        if a == "rbx" and b == "rbx":
            return 0

        # we think "rbx" always be less than "rubyXX", so it won't be selected
        if a.startswith("ruby") and b == "rbx":
            return 1
        if a == "rbx" and b.startswith("ruby"):
            return -1

        if a.startswith("ruby") and b.startswith("ruby"):
            a = a.replace("ruby", "")
            b = b.replace("ruby", "")
            return FmUtil.compareVersion(a, b)

        assert False

    def __rubyCheckMainPackageOfTargetUseFlag(self, useFlag):
        assert useFlag.startswith("ruby_targets_")
        useFlag = useFlag.replace("ruby_targets_", "")

        if useFlag.startswith("ruby"):
            slot = useFlag[4] + "." + useFlag[5:]         # "ruby27" -> "2.7", "ruby210" -> "2.10"
            pkgName = "dev-lang/ruby:%s" % (slot)
            return (FmUtil.portageIsPkgInstallable(pkgName), pkgName)

        if useFlag.startswith("rbx"):
            # FIXME: I don't know what rbx means...
            return (True, "")

        assert False


class EbuildRepositories:

    """
    When operating repositories, we think every existing repository is complete.
    The completeness check is done in checkRepository().
    """

    def __init__(self):
        self._repoInfoDict = {
            "gentoo": 5000,
            "guru": 4900,
            "mirrorshq": 4800,      # app-admin/fpemud-os-sysman in fpemud-os repository needs dev-python/robust_layer in mirrorshq repository
            "bombyx-netutils": 4800,
            "fpemud-os": 4800,
        }
        self._repoGitUrlDict = {
            "guru": "https://github.com/gentoo/guru",
            "mirrorshq": "https://gitee.com/mirrorshq/gentoo-overlay",
            "bombyx-netutils": "https://gitee.com/bombyx-netutils/gentoo-overlay",
            "fpemud-os": "https://github.com/fpemud-os/gentoo-overlay",
        }

    def getRepositoryList(self):
        return list(self._repoInfoDict.keys())

    def getRepoCfgReposFile(self, repoName):
        # returns /etc/portage/repos.conf/repo-XXXX.conf
        assert repoName in self._repoInfoDict
        return os.path.join(FmConst.portageCfgReposDir, "repo-%s.conf" % (repoName))

    def getRepoDir(self, repoName):
        assert repoName in self._repoInfoDict
        return os.path.join(FmConst.portageDataDir, "repo-%s" % (repoName))

    def isRepoExist(self, repoName):
        assert repoName in self._repoInfoDict
        return os.path.exists(self.getRepoCfgReposFile(repoName))

    def getRepoMetadata(self, repoName, key):
        # meta-data:
        #   1. repo-name: XXXX

        assert repoName in self._repoInfoDict
        assert self.isRepoExist(repoName)

        if key == "repo-name":
            return FmUtil.repoGetRepoName(self.getRepoDir(repoName))
        else:
            assert False

    def checkRepository(self, repoName, bAutoFix=False):
        assert repoName in self._repoInfoDict

        # check existence
        if not self.isRepoExist(repoName):
            if bAutoFix:
                self.createRepository(repoName)
            else:
                raise RepositoryCheckError("repository \"%s\" does not exist" % (repoName))

        cfgFile = self.getRepoCfgReposFile(repoName)
        repoDir = self.getRepoDir(repoName)

        # check cfgFile content
        if True:
            standardContent = self.__generateReposConfContent(repoName)
            if pathlib.Path(cfgFile).read_text() != standardContent:
                if bAutoFix:
                    with open(cfgFile, "w") as f:
                        f.write(standardContent)
                else:
                    raise RepositoryCheckError("file content of \"%s\" is invalid" % (cfgFile))

        # check repository directory existence
        if not os.path.exists(repoDir):
            if bAutoFix:
                self.createRepository(repoName)
            else:
                raise RepositoryCheckError("repository directory \"%s\" does not exist" % (repoDir))

        # check repository directory validity
        if not os.path.isdir(repoDir):
            if bAutoFix:
                robust_layer.simple_fops.rm(repoDir)
                self.createRepository(repoName)
            else:
                raise RepositoryCheckError("repository directory \"%s\" is invalid" % (repoDir))

        # check repository source url
        if repoName in self._repoGitUrlDict and FmUtil.gitGetUrl(repoDir) != self._repoGitUrlDict[repoName]:
            if bAutoFix:
                robust_layer.simple_fops.rm(repoDir)
                self.createRepository(repoName)
            else:
                raise RepositoryCheckError("repository directory \"%s\" should have URL \"%s\"" % (repoDir, self._repoGitUrlDict[repoName]))

    def createRepository(self, repoName):
        """Business exception should not be raise, but be printed as error message"""

        if repoName == "gentoo":
            self._repoGentooCreate(self.getRepoDir("gentoo"))
        else:
            if repoName in self._repoGitUrlDict:
                robust_layer.simple_git.pull(self.getRepoDir(repoName), reclone_on_failure=True, url=self._repoGitUrlDict[repoName])
            else:
                assert False

        if self.__hasPatch(repoName):
            print("Patching...")
            self.__patchRepoN(repoName)
            self.__patchRepoS(repoName)
            print("Done.")

        with open(self.getRepoCfgReposFile(repoName), "w") as f:
            f.write(self.__generateReposConfContent(repoName))

    def syncRepository(self, repoName):
        """Business exception should not be raise, but be printed as error message"""

        if repoName == "gentoo":
            self._repoGentooSync(self.getRepoDir("gentoo"))
        else:
            if repoName in self._repoGitUrlDict:
                robust_layer.simple_git.pull(self.getRepoDir(repoName), reclone_on_failure=True, url=self._repoGitUrlDict[repoName])
            else:
                assert False

        if self.__hasPatch(repoName):
            print("Patching...")
            self.__patchRepoN(repoName)
            self.__patchRepoS(repoName)
            print("Done.")

    def _repoGentooCreate(self, repoDir):
        os.makedirs(repoDir, exist_ok=True)
        self._repoGentooSync(repoDir)

    def _repoGentooSync(self, repoDir):
        mr = FmUtil.portageGetGentooPortageRsyncMirror(FmConst.portageCfgMakeConf, FmConst.defaultRsyncMirror)
        robust_layer.rsync.exec("-rlptD", "-z", "-hhh", "--no-motd", "--delete", "--info=progress2", mr, repoDir)   # we use "-rlptD" insead of "-a" so that the remote user/group is ignored

    def __generateReposConfContent(self, repoName):
        repoDir = self.getRepoDir(repoName)
        buf = ""
        buf += "[%s]\n" % (FmUtil.repoGetRepoName(repoDir))
        buf += "auto-sync = no\n"
        buf += "priority = %d\n" % (self._repoInfoDict[repoName])
        buf += "location = %s\n" % (repoDir)
        return buf

    def __hasPatch(self, repoName):
        repoName2 = "repo-%s" % (repoName)
        for dirName in ["pkgwh-n-patch", "pkgwh-s-patch"]:
            modDir = os.path.join(FmConst.dataDir, dirName, repoName2)
            if os.path.exists(modDir):
                return True
        return False

    def __patchRepoN(self, repoName):
        repoName2 = "repo-%s" % (repoName)
        modDir = os.path.join(FmConst.dataDir, "pkgwh-n-patch", repoName2)
        if os.path.exists(modDir):
            jobCount = FmUtil.portageGetJobCount(FmConst.portageCfgMakeConf)
            FmUtil.portagePatchRepository(repoName2, self.getRepoDir(repoName), "N-patch", modDir, jobCount)

    def __patchRepoS(self, repoName):
        repoName2 = "repo-%s" % (repoName)
        modDir = os.path.join(FmConst.dataDir, "pkgwh-s-patch", repoName2)
        if os.path.exists(modDir):
            jobCount = FmUtil.portageGetJobCount(FmConst.portageCfgMakeConf)
            FmUtil.portagePatchRepository(repoName2, self.getRepoDir(repoName), "S-patch", modDir, jobCount)


class RepositoryCheckError(Exception):

    def __init__(self, message):
        self.message = message


class EbuildOverlays:

    """
    When operating overlays, we think overlay that exists is complete. Completeness check is done in basic post check stage.
    There're 3 types of overlays: staic, trusted, transient
    Overlay of type transient and trusted has vcs-type and url property
    """

    def __init__(self):
        self._repoman = EbuildRepositories()
        self._priority = "7000"

    def getOverlayList(self):
        if os.path.exists(FmConst.portageCfgReposDir):
            ret = glob.glob(os.path.join(FmConst.portageCfgReposDir, "overlay-*.conf"))
        else:
            ret = []
        ret = [re.fullmatch("overlay-(.*)\\.conf", os.path.basename(x)).group(1) for x in ret]
        ret.sort()
        return ret

    def getOverlayCfgReposFile(self, overlayName):
        # returns /etc/portage/repos.conf/overlay-XXXX.conf
        return os.path.join(FmConst.portageCfgReposDir, "overlay-%s.conf" % (overlayName))

    def getOverlayDir(self, overlayName):
        # returns /var/lib/portage/overlay-XXXX
        return os.path.join(FmConst.portageDataDir, "overlay-%s" % (overlayName))

    # deprecated
    def getOverlayFilesDir(self, overlayName):
        # returns /var/cache/portage/laymanfiles/XXXX
        return os.path.join(FmConst.laymanfilesDir, overlayName)

    def isOverlayExist(self, overlayName):
        return os.path.exists(self.getOverlayCfgReposFile(overlayName))

    def getOverlayType(self, overlayName):
        assert self.isOverlayExist(overlayName)
        buf = pathlib.Path(self.getOverlayCfgReposFile(overlayName)).read_text()
        priority, location, overlayType, vcsType, url, repoName = self._parseCfgReposFile(buf)
        assert overlayType in ["static", "trusted", "transient"]
        return overlayType

    def getOverlayVcsTypeAndUrl(self, overlayName):
        assert self.isOverlayExist(overlayName)
        buf = pathlib.Path(self.getOverlayCfgReposFile(overlayName)).read_text()
        priority, location, overlayType, vcsType, url, repoName = self._parseCfgReposFile(buf)
        assert overlayType in ["trusted", "transient"]
        assert vcsType is not None
        assert url is not None
        return (vcsType, url)

    def getOverlayMetadata(self, overlayName, key):
        # meta-data:
        #   1. repo-name: XXXX
        assert self.isOverlayExist(overlayName)

        if key == "repo-name":
            buf = pathlib.Path(self.getOverlayCfgReposFile(overlayName)).read_text()
            priority, location, overlayType, vcsType, url, repoName = self._parseCfgReposFile(buf)
            assert repoName is not None
            return repoName
        else:
            assert False

    def addTrustedOverlay(self, overlayName, overlayVcsType, overlayUrl):
        assert not self.isOverlayExist(overlayName)

        cfgFile = self.getOverlayCfgReposFile(overlayName)
        overlayDir = self.getOverlayDir(overlayName)

        self._createOverlaySourceDir(overlayName, overlayDir, overlayVcsType, overlayUrl)
        try:
            self._removeDuplicatePackage(overlayDir)
            with open(cfgFile, "w") as f:
                f.write(self._generateCfgReposFile(overlayName, overlayDir, "trusted", overlayVcsType, overlayUrl, FmUtil.repoGetRepoName(overlayDir)))
        except:
            shutil.rmtree(overlayDir)       # keep overlay files directory
            raise

    def addTransientOverlay(self, overlayName, overlayVcsType, overlayUrl):
        assert not self.isOverlayExist(overlayName)

        cfgFile = self.getOverlayCfgReposFile(overlayName)
        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)

        self._createOverlaySourceDir(overlayName, overlayFilesDir, overlayVcsType, overlayUrl)
        try:
            self._createTransientOverlayDirFromOverlayFilesDir(overlayName, overlayDir, overlayFilesDir)
            with open(cfgFile, "w") as f:
                f.write(self._generateCfgReposFile(overlayName, overlayDir, "transient", overlayVcsType, overlayUrl, FmUtil.repoGetRepoName(overlayDir)))
        except:
            shutil.rmtree(overlayDir)       # keep overlay files directory
            raise

    def removeOverlay(self, overlayName):
        assert self.isOverlayExist(overlayName)

        robust_layer.simple_fops.rm(self.getOverlayFilesDir(overlayName))
        robust_layer.simple_fops.rm(self.getOverlayDir(overlayName))
        robust_layer.simple_fops.rm(self.getOverlayCfgReposFile(overlayName))

    def modifyOverlayVcsTypeAndUrl(self, overlayName, overlayVcsType, overlayUrl):
        assert self.isOverlayExist(overlayName)

        cfgFile = self.getOverlayCfgReposFile(overlayName)
        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)

        overlayType = self._parseCfgReposFile(pathlib.Path(cfgFile).read_text())[2]
        if overlayType == "static":
            assert False
        elif overlayType == "trusted":
            robust_layer.simple_fops.rm(overlayDir)
            self._createOverlaySourceDir(overlayName, overlayDir, overlayVcsType, overlayUrl)
            self._removeDuplicatePackage(overlayDir)
            with open(cfgFile, "w") as f:
                f.write(self._generateCfgReposFile(overlayName, overlayDir, "trusted", overlayVcsType, overlayUrl, FmUtil.repoGetRepoName(overlayDir)))
        elif overlayType == "transient":
            robust_layer.simple_fops.rm(overlayFilesDir)
            self._createOverlaySourceDir(overlayName, overlayFilesDir, overlayVcsType, overlayUrl)
            self._refreshTransientOverlayDir(overlayName, overlayDir, overlayFilesDir)
            with open(cfgFile, "w") as f:
                f.write(self._generateCfgReposFile(overlayName, overlayDir, "transient", overlayVcsType, overlayUrl, FmUtil.repoGetRepoName(overlayDir)))
        else:
            assert False

    def checkOverlay(self, overlayName, bCheckContent, bAutoFix=False):
        assert self.isOverlayExist(overlayName)

        cfgFile = self.getOverlayCfgReposFile(overlayName)
        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)
        buf = pathlib.Path(cfgFile).read_text()
        priority, location, overlayType, vcsType, overlayUrl, repoName = self._parseCfgReposFile(buf)

        # check cfgFile
        if True:
            bRewrite = False
            if repoName is None:
                raise OverlayCheckError("no \"repo-name\" in file \"%s\", strange?!" % (cfgFile))
            if overlayType is None:
                raise OverlayCheckError("no \"overlay-type\" in file \"%s\"" % (cfgFile))
            if overlayType not in ["static", "trusted", "transient"]:
                raise OverlayCheckError("invalid \"overlay-type\" in file \"%s\"" % (cfgFile))
            if overlayType in ["trusted", "transient"]:
                if vcsType is None:
                    raise OverlayCheckError("no \"sync-type\" in file \"%s\"" % (cfgFile))
                if vcsType not in ["git", "svn"]:
                    raise OverlayCheckError("invalid \"sync-type\" in file \"%s\"" % (cfgFile))
                if overlayUrl is None:
                    raise OverlayCheckError("no \"sync-uri\" in file \"%s\"" % (cfgFile))
            if priority is None:
                if bAutoFix:
                    bRewrite = True
                else:
                    raise OverlayCheckError("no \"priority\" in file \"%s\"" % (cfgFile))
            if priority != self._priority:
                if bAutoFix:
                    bRewrite = True
                else:
                    raise OverlayCheckError("invalid \"priority\" in file \"%s\"" % (cfgFile))
            if location is None:
                if bAutoFix:
                    bRewrite = True
                else:
                    raise OverlayCheckError("no \"location\" in file \"%s\"" % (cfgFile))
            if location != overlayDir:
                if bAutoFix:
                    bRewrite = True
                else:
                    raise OverlayCheckError("invalid \"location\" in file \"%s\"" % (cfgFile))
            if bRewrite:
                with open(cfgFile, "w") as f:
                    f.write(self._generateCfgReposFile(overlayName, overlayDir, overlayType, vcsType, overlayUrl, repoName))

        # check overlay files directory
        if overlayType == "static":
            # overlay files directory should not exist
            if os.path.exists(overlayFilesDir):
                raise OverlayCheckError("\"%s\" should not have overlay files directory \"%s\"" % (overlayName, overlayFilesDir))
        elif overlayType == "trusted":
            # overlay files directory should not exist
            if os.path.exists(overlayFilesDir):
                if bAutoFix:
                    robust_layer.simple_fops.rm(overlayFilesDir)
                else:
                    raise OverlayCheckError("\"%s\" should not have overlay files directory \"%s\"" % (overlayName, overlayFilesDir))
        elif overlayType == "transient":
            # doesn't exist or is invalid
            if not os.path.exists(overlayFilesDir) or not os.path.isdir(overlayFilesDir):
                if bAutoFix:
                    self._createOverlaySourceDir(overlayName, overlayFilesDir, vcsType, overlayUrl)
                    self._createTransientOverlayDirFromOverlayFilesDir(overlayName, overlayDir, overlayFilesDir)
                else:
                    raise OverlayCheckError("overlay files directory \"%s\" does not exist or is invalid" % (overlayFilesDir))
            # source url is invalid
            if True:
                if vcsType == "git":
                    realUrl = FmUtil.gitGetUrl(overlayFilesDir)
                elif vcsType == "svn":
                    realUrl = FmUtil.svnGetUrl(overlayFilesDir)
                else:
                    assert False
                if realUrl != overlayUrl:
                    if bAutoFix:
                        robust_layer.simple_fops.rm(overlayFilesDir)
                        self._createOverlaySourceDir(overlayName, overlayFilesDir, vcsType, overlayUrl)
                        self._refreshTransientOverlayDir(overlayName, overlayDir, overlayFilesDir)
                    else:
                        raise RepositoryCheckError("overlay files directory \"%s\" should have URL \"%s\"" % (overlayFilesDir, overlayUrl))
        else:
            assert False

        # check overlay directory
        if overlayType == "static":
            # doesn't exist or is invalid
            if not os.path.isdir(overlayDir) or os.path.islink(overlayDir):
                if bAutoFix:
                    self._createEmptyStaticOverlayDir(overlayName, overlayDir)
                else:
                    raise OverlayCheckError("overlay directory \"%s\" does not exist or is invalid" % (overlayDir))
        elif overlayType == "trusted":
            # doesn't exist or is invalid
            if not os.path.isdir(overlayDir):
                if bAutoFix:
                    robust_layer.simple_fops.rm(overlayDir)
                    self._createOverlaySourceDir(overlayName, overlayDir, vcsType, overlayUrl)
                    self._removeDuplicatePackage(overlayDir)
                else:
                    raise OverlayCheckError("overlay directory \"%s\" does not exist or is invalid" % (overlayDir))
            # source url is invalid
            if True:
                if vcsType == "git":
                    realUrl = FmUtil.gitGetUrl(overlayDir)
                elif vcsType == "svn":
                    realUrl = FmUtil.svnGetUrl(overlayDir)
                else:
                    assert False
                if realUrl != overlayUrl:
                    if bAutoFix:
                        robust_layer.simple_fops.rm(overlayDir)
                        self._createOverlaySourceDir(overlayName, overlayDir, vcsType, overlayUrl)
                        self._removeDuplicatePackage(overlayDir)
                    else:
                        raise RepositoryCheckError("overlay directory \"%s\" should have URL \"%s\"" % (overlayDir, overlayUrl))
        elif overlayType == "transient":
            # doesn't exist or is invalid
            if not os.path.isdir(overlayDir) or os.path.islink(overlayDir):
                if bAutoFix:
                    self._createTransientOverlayDirFromOverlayFilesDir(overlayName, overlayDir, overlayFilesDir)
                else:
                    raise OverlayCheckError("overlay directory \"%s\" does not exist or is invalid" % (overlayDir))
        else:
            assert False

        # get repoName of overlay
        realRepoName = FmUtil.repoGetRepoName(overlayDir)
        if realRepoName is None:
            raise OverlayCheckError("can not get repo-name of overlay \"%s\"" % (overlayName))

        # check cfgFile again
        if repoName != realRepoName:
            if bAutoFix:
                with open(cfgFile, "w") as f:
                    f.write(self._generateCfgReposFile(overlayName, overlayDir, overlayType, vcsType, overlayUrl, realRepoName))
            else:
                raise OverlayCheckError("invalid \"repo-name\" in \"%s\"" % (cfgFile))

        # check overlay directory again
        if bCheckContent:
            if overlayType == "static":
                pass
            elif overlayType == "trusted":
                # invalid layout.conf content
                with open(os.path.join(overlayDir, "metadata", "layout.conf"), "r") as f:
                    if re.search("^\\s*masters\\s*=\\s*gentoo\\s*$", f.read(), re.M) is None:
                        raise OverlayCheckError("overlay \"%s\" has illegal layout.conf" % (overlayName))
            elif overlayType == "transient":
                # all packages must be the same as overlay files directory
                for d in FmUtil.repoGetEbuildDirList(overlayDir):
                    srcEbuildDir = os.path.join(overlayFilesDir, d)
                    dstEbuildDir = os.path.join(overlayDir, d)
                    if not os.path.exists(srcEbuildDir):
                        if bAutoFix:
                            robust_layer.simple_fops.rm(dstEbuildDir)
                        else:
                            raise OverlayCheckError("package \"%s\" in overlay \"%s\" should not exist any more" % (d, overlayName))
                    if not FmUtil.isTwoDirSame(srcEbuildDir, dstEbuildDir):
                        if bAutoFix:
                            robust_layer.simple_fops.rm(dstEbuildDir)
                            shutil.copytree(srcEbuildDir, dstEbuildDir)
                        else:
                            raise OverlayCheckError("package \"%s\" in overlay \"%s\" is corrupt" % (d, overlayName))
                # no empty category directory
                for d in FmUtil.repoGetCategoryDirList(overlayDir):
                    fulld = os.path.join(overlayDir, d)
                    if os.listdir(fulld) == []:
                        if bAutoFix:
                            os.rmdir(fulld)
                        else:
                            raise OverlayCheckError("category directory \"%s\" in overlay \"%s\" is empty" % (d, overlayName))
            else:
                assert False

    def syncOverlay(self, overlayName):
        if not self.isOverlayExist(overlayName):
            raise Exception("overlay \"%s\" is not installed" % (overlayName))

        cfgFile = self.getOverlayCfgReposFile(overlayName)
        overlayDir = self.getOverlayDir(overlayName)
        overlayType = self.getOverlayType(overlayName)
        buf = pathlib.Path(cfgFile).read_text()
        priority, location, overlayType, vcsType, overlayUrl, repoName = self._parseCfgReposFile(buf)

        if overlayType == "static":
            # static overlay is mantained by other means
            pass
        elif overlayType == "trusted":
            try:
                self._syncOverlaySourceDir(overlayName, overlayDir, vcsType, overlayUrl)
                self._removeDuplicatePackage(overlayDir)
            except PrivateOverlayNotAccessiableError:
                print("Overlay not accessible, ignored.")
        elif overlayType == "transient":
            overlayFilesDir = self.getOverlayFilesDir(overlayName)
            try:
                self._syncOverlaySourceDir(overlayName, overlayFilesDir, vcsType, overlayUrl)
                self._refreshTransientOverlayDir(overlayName, overlayDir, overlayFilesDir)
            except PrivateOverlayNotAccessiableError:
                print("Overlay not accessible, ignored.")
        else:
            assert False

    def isOverlayPackageEnabled(self, overlayName, pkgName):
        assert self.isOverlayExist(overlayName)
        return os.path.isdir(os.path.join(self.getOverlayDir(overlayName), pkgName))

    def enableOverlayPackage(self, overlayName, pkgName, quiet=False):
        assert self.isOverlayExist(overlayName)
        assert self.getOverlayType(overlayName) == "transient"

        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)
        srcEbuildDir = os.path.join(overlayFilesDir, pkgName)
        dstEbuildDir = os.path.join(overlayDir, pkgName)

        if os.path.isdir(dstEbuildDir):
            raise Exception("package \"%s\" has already been enabled" % (pkgName))
        if not os.path.isdir(srcEbuildDir):
            raise Exception("package \"%s\" does not exist in overlay \"%s\"" % (pkgName, overlayName))
        if portage.db[portage.root]["porttree"].dbapi.match(pkgName) != []:
            raise Exception("package \"%s\" has already exist" % (pkgName))

        os.makedirs(os.path.dirname(dstEbuildDir), exist_ok=True)
        shutil.copytree(srcEbuildDir, dstEbuildDir)

        if not quiet:
            print("Notice: You need to enable any dependent package manually.")

    def disableOverlayPackage(self, overlayName, pkgName):
        assert self.isOverlayExist(overlayName)
        assert self.getOverlayType(overlayName) == "transient"

        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)

        if os.path.islink(overlayDir):
            raise Exception("overlay \"%s\" is a trusted overlay" % (overlayName))
        if not os.path.exists(overlayFilesDir):
            raise Exception("overlay \"%s\" is a static overlay" % (overlayName))
        if not os.path.isdir(os.path.join(overlayDir, pkgName)):
            raise Exception("package \"%s\" is not enabled" % (pkgName))

        robust_layer.simple_fops.rm(os.path.join(overlayDir, pkgName))
        FmUtil.removeEmptyDir(os.path.join(overlayDir, pkgName.split("/")[0]))

    def _createOverlaySourceDir(self, overlayName, overlayFilesDir, vcsType, url):
        if vcsType == "git":
            # overlayFilesDir may already exist
            robust_layer.simple_git.pull(overlayFilesDir, reclone_on_failure=True, url=url)
        elif vcsType == "svn":
            # overlayFilesDir may already exist
            robust_layer.simple_subversion.update(overlayFilesDir, recheckout_on_failure=True, url=url)
        elif vcsType == "mercurial":
            # FIXME
            assert False
        elif vcsType == "rsync":
            # FIXME
            assert False
        else:
            assert False

        if self.__overlayHasPatch(overlayName, ["pkgwh-n-patch", "pkgwh-s-patch"]):
            print("Patching...")
            self.__overlaySourceDirPatch(overlayName, overlayFilesDir, "N-patch", "pkgwh-n-patch")
            self.__overlaySourceDirPatch(overlayName, overlayFilesDir, "S-patch", "pkgwh-s-patch")
            print("Done.")

    def _syncOverlaySourceDir(self, overlayName, overlayFilesDir, vcsType, url):
        if vcsType == "git":
            try:
                robust_layer.simple_git.pull(overlayFilesDir, reclone_on_failure=True, url=url)
            except robust_layer.git.PrivateUrlNotExistError:
                raise PrivateOverlayNotAccessiableError()
        elif vcsType == "svn":
            try:
                robust_layer.simple_subversion.update(overlayFilesDir, recheckout_on_failure=True, url=url)
            except robust_layer.subversion.PrivateUrlNotExistError:
                raise PrivateOverlayNotAccessiableError()
        else:
            assert False

        if self.__overlayHasPatch(overlayName, ["pkgwh-n-patch", "pkgwh-s-patch"]):
            print("Patching...")
            self.__overlaySourceDirPatch(overlayName, overlayFilesDir, "N-patch", "pkgwh-n-patch")
            self.__overlaySourceDirPatch(overlayName, overlayFilesDir, "S-patch", "pkgwh-s-patch")
            print("Done.")

    def _removeDuplicatePackage(self, overlayFilesDir):
        # get all packages in all repositories
        infoDict = dict()
        for repoName in self._repoman.getRepositoryList():
            repoDir = self._repoman.getRepoDir(repoName)
            infoDict[repoName] = set(FmUtil.repoGetEbuildDirList(repoDir))

        # get to-be-removed packages that duplicates with repository from overlay
        pkgRemoved = []
        oDirInfo = set(FmUtil.repoGetEbuildDirList(overlayFilesDir))
        for k, v in infoDict.items():
            for item in list(v & oDirInfo):
                pkgRemoved.append(item)

        # record to-be-removed packages
        if len(pkgRemoved) > 0:
            with open(os.path.join(overlayFilesDir, "packages.removed"), "w") as f:
                for item in pkgRemoved:
                    f.write(item + "\n")

        # do remove
        for item in pkgRemoved:
            FmUtil.repoRemovePackageAndCategory(overlayFilesDir, item)
            print("Duplicate package \"%s\" is automatically removed." % (item))

    def _createEmptyStaticOverlayDir(self, overlayName, overlayDir):
        robust_layer.simple_fops.rm(overlayDir)
        os.mkdir(overlayDir)

        os.mkdir(os.path.join(overlayDir, "profiles"))
        with open(os.path.join(overlayDir, "profiles", "repo_name"), "w") as f:
            f.write(overlayName)

        os.mkdir(os.path.join(overlayDir, "metadata"))
        with open(os.path.join(overlayDir, "metadata", "layout.conf"), "w") as f:
            f.write("masters = gentoo\n")
            f.write("thin-manifests = true\n")

    def _createTransientOverlayDirFromOverlayFilesDir(self, overlayName, overlayDir, overlayFilesDir):
        robust_layer.simple_fops.rm(overlayDir)
        os.mkdir(overlayDir)

        # create profile directory
        srcProfileDir = os.path.join(overlayFilesDir, "profiles")
        profileDir = os.path.join(overlayDir, "profiles")
        if os.path.exists(srcProfileDir):
            FmUtil.cmdCall("cp", "-r", srcProfileDir, profileDir)
            robust_layer.simple_fops.rm(os.path.join(profileDir, "profiles.desc"))
        else:
            os.mkdir(profileDir)
            layoutFn = os.path.join(overlayFilesDir, "metadata", "layout.conf")
            if os.path.exists(layoutFn):
                repoName = re.search("repo-name = (\\S+)", pathlib.Path(layoutFn).read_text(), re.M).group(1)
            else:
                repoName = overlayName
            with open(os.path.join(profileDir, "repo_name"), "w") as f:
                f.write(repoName)

        # create metadata directory
        srcMetaDataDir = os.path.join(overlayFilesDir, "metadata")
        metaDataDir = os.path.join(overlayDir, "metadata")
        if os.path.exists(srcMetaDataDir):
            shutil.copytree(srcMetaDataDir, metaDataDir)
        else:
            os.mkdir(metaDataDir)
            with open(os.path.join(metaDataDir, "layout.conf"), "w") as f:
                f.write("masters = gentoo")

        # create eclass directory
        srcEclassDir = os.path.join(overlayFilesDir, "eclass")
        eclassDir = os.path.join(overlayDir, "eclass")
        if os.path.exists(srcEclassDir):
            shutil.copytree(srcEclassDir, eclassDir)

        # ugly trick
        self.__overlayDirUglyTrick(overlayName, overlayDir)

    def _refreshTransientOverlayDir(self, overlayName, overlayDir, overlayFilesDir):
        profileDir = os.path.join(overlayDir, "profiles")
        robust_layer.simple_fops.rm(profileDir)

        # refresh profile directory
        srcProfileDir = os.path.join(overlayFilesDir, "profiles")
        if os.path.exists(srcProfileDir):
            FmUtil.cmdCall("cp", "-r", srcProfileDir, profileDir)
            robust_layer.simple_fops.rm(os.path.join(profileDir, "profiles.desc"))
        else:
            os.mkdir(profileDir)
            layoutFn = os.path.join(overlayFilesDir, "metadata", "layout.conf")
            if os.path.exists(layoutFn):
                repoName = re.search("repo-name = (\\S+)", pathlib.Path(layoutFn).read_text(), re.M).group(1)
            else:
                repoName = overlayName
            with open(os.path.join(profileDir, "repo_name"), "w") as f:
                f.write(repoName)
        FmUtil.touchFile(os.path.join(profileDir, "transient"))

        # refresh metadata directory
        srcMetaDataDir = os.path.join(overlayFilesDir, "metadata")
        metaDataDir = os.path.join(overlayDir, "metadata")
        if os.path.exists(srcMetaDataDir):
            robust_layer.simple_fops.rm(metaDataDir)
            shutil.copytree(srcMetaDataDir, metaDataDir)

        # refresh eclass directory
        srcEclassDir = os.path.join(overlayFilesDir, "eclass")
        dstEclassDir = os.path.join(overlayDir, "eclass")
        if os.path.exists(srcEclassDir):
            robust_layer.simple_fops.rm(dstEclassDir)
            shutil.copytree(srcEclassDir, dstEclassDir)
        else:
            robust_layer.simple_fops.rm(dstEclassDir)

        # refresh ebuild directories
        for d in FmUtil.repoGetEbuildDirList(overlayDir):
            srcEbuildDir = os.path.join(overlayFilesDir, d)
            dstEbuildDir = os.path.join(overlayDir, d)
            robust_layer.simple_fops.rm(dstEbuildDir)
            if os.path.exists(srcEbuildDir):
                shutil.copytree(srcEbuildDir, dstEbuildDir)

        # remove empty category directories
        for d in FmUtil.repoGetCategoryDirList(overlayDir):
            FmUtil.removeEmptyDir(os.path.join(overlayDir, d))

        # ugly trick
        self.__overlayDirUglyTrick(overlayName, overlayDir)

    def _parseCfgReposFile(self, buf):
        m = re.search("^\\[(.*)\\]$", buf, re.M)
        if m is not None:
            innerRepoName = m.group(1)
        else:
            innerRepoName = None

        m = re.search("^priority *= *(.*)$", buf, re.M)
        if m is not None:
            priority = m.group(1)
        else:
            priority = None

        m = re.search("^location *= *(.*)$", buf, re.M)
        if m is not None:
            location = m.group(1)
        else:
            location = None

        m = re.search("^overlay-type *= *(.*)$", buf, re.M)
        if m is not None:
            overlayType = m.group(1)
        else:
            overlayType = None

        m = re.search("^sync-type *= *(.*)$", buf, re.M)
        if m is not None:
            vcsType = m.group(1)
        else:
            vcsType = None

        m = re.search("^sync-uri *= *(.*)$", buf, re.M)
        if m is not None:
            overlayUrl = m.group(1)
        else:
            overlayUrl = None

        return (priority, location, overlayType, vcsType, overlayUrl, innerRepoName)

    def _generateCfgReposFile(self, overlayName, overlayDir, overlayType, overlayVcsType, overlayUrl, innerRepoName):
        buf = ""
        buf += "[%s]\n" % (innerRepoName)
        buf += "auto-sync = no\n"
        buf += "priority = %s\n" % (self._priority)
        buf += "location = %s\n" % (overlayDir)
        buf += "overlay-type = %s\n" % (overlayType)
        if overlayVcsType is not None:
            buf += "sync-type = %s\n" % (overlayVcsType)
            buf += "sync-uri = %s\n" % (overlayUrl)
        return buf

    def __overlayHasPatch(self, overlayName, dirNameList):
        overlayName2 = "overlay-%s" % (overlayName)
        for dirName in dirNameList:
            modDir = os.path.join(FmConst.dataDir, dirName, overlayName2)
            if os.path.exists(modDir):
                return True
        return False

    def __overlaySourceDirPatch(self, overlayName, overlaySourceDir, typeName, dirName):
        overlayName2 = "overlay-%s" % (overlayName)
        modDir = os.path.join(FmConst.dataDir, dirName, overlayName2)
        if os.path.exists(modDir):
            jobCount = FmUtil.portageGetJobCount(FmConst.portageCfgMakeConf)
            FmUtil.portagePatchRepository(overlayName2, overlaySourceDir, typeName, modDir, jobCount)

    def __overlayDirUglyTrick(self, overlayName, overlayDir):
        # common trick
        with fileinput.FileInput(os.path.join(overlayDir, "metadata", "layout.conf"), inplace=True) as f:
            for line in f:
                if line.startswith("masters = "):
                    print("masters = gentoo")
                else:
                    print(line, end='')

        # ugly trick
        if overlayName == "unity":
            with fileinput.FileInput(os.path.join(overlayDir, "eclass", "ubuntu-versionator.eclass"), inplace=True) as f:
                for line in f:
                    print(line.replace("if [ -z \"${UNITY_BUILD_OK}\" ]; then", "if false; then"), end='')


class OverlayCheckError(Exception):

    def __init__(self, message):
        self.message = message


class PrivateOverlayNotAccessiableError(Exception):
    pass


class CloudStage3Urls:

    def __init__(self, arch, **kwargs):
        self._arch = arch
        self._kwargs = kwargs

        if self._arch == "alpha":
            assert False
        elif self._arch == "amd64":
            assert self._kwargs["sys_type"] in ["musl", "no-multilib-openrc", "no-multilib-systemd", "openrc", "systemd"]
        elif self._arch == "arm":
            assert False
        elif self._arch == "arm64":
            assert False
        elif self._arch == "hppa":
            assert False
        elif self._arch == "ia64":
            assert False
        elif self._arch == "m68k":
            assert False
        elif self._arch == "ppc":
            assert False
        elif self._arch == "riscv":
            assert False
        elif self._arch == "s390":
            assert False
        elif self._arch == "sh":
            assert False
        elif self._arch == "sparc":
            assert False
        elif self._arch == "x86":
            assert False
        else:
            assert False

    def communicate(self):
        self.stage3FileUrl = None
        self.stage3ContentGzUrl = None
        self.stage3DigestUrl = None
        self.stage3DigestAscUrl = None

        if self._arch == "alpha":
            assert False
        elif self._arch == "amd64":
            indexFileName = "latest-stage3-amd64-%s.txt" % (self._kwargs["sys_type"])
        elif self._arch == "arm":
            assert False
        elif self._arch == "arm64":
            assert False
        elif self._arch == "hppa":
            assert False
        elif self._arch == "ia64":
            assert False
        elif self._arch == "m68k":
            assert False
        elif self._arch == "ppc":
            assert False
        elif self._arch == "riscv":
            assert False
        elif self._arch == "s390":
            assert False
        elif self._arch == "sh":
            assert False
        elif self._arch == "sparc":
            assert False
        elif self._arch == "x86":
            assert False
        else:
            assert False

        baseUrl = "https://mirrors.tuna.tsinghua.edu.cn/gentoo"
        autoBuildsUrl = os.path.join(baseUrl, "releases", self._arch, "autobuilds")

        with urllib.request.urlopen(os.path.join(autoBuildsUrl, indexFileName), timeout=robust_layer.TIMEOUT) as resp:
            m = re.search(r'^(\S+) [0-9]+', resp.read(), re.M)
            self.stage3FileUrl = os.path.join(autoBuildsUrl, m.group(1))

        self.stage3ContentGzUrl = self.stage3FileUrl + ".CONTENTS.gz"
        self.stage3DigestUrl = self.stage3FileUrl + ".DIGESTS"
        self.stage3DigestAscUrl = self.stage3FileUrl + ".DIGESTS.asc"

    def dispose(self):
        if hasattr(self, "stage3FileUrl"):
            del self.stage3FileUrl
        if hasattr(self, "stage3ContentGzUrl"):
            del self.stage3ContentGzUrl
        if hasattr(self, "stage3DigestUrl"):
            del self.stage3DigestUrl
        if hasattr(self, "stage3DigestAscUrl"):
            del self.stage3DigestAscUrl


class CloudSnapshotUrls:

    def __init__(self, name):
        self._name = name

    def communicate(self):
        baseUrl = "https://mirrors.tuna.tsinghua.edu.cn/gentoo"

        self.snapshotUrl = os.path.join(baseUrl, "snapshots", "%s-latest.tar.xz" % (self._name))
        self.snapshotGpgUrl = self.snapshotUrl + ".gpgsig"
        self.snapshotMd5Url = self.snapshotUrl + ".md5sum"

    def dispose(self):
        if hasattr(self, "snapshotUrl"):
            del self.snapshotUrl
        if hasattr(self, "snapshotGpgUrl"):
            del self.snapshotGpgUrl
        if hasattr(self, "snapshotMd5Url"):
            del self.snapshotMd5Url


class CloudOverlayDb:

    """We expand overlay name "bgo" to ["bgo", "bgo-overlay", "bgo_overlay"]"""

    def __init__(self):
        self.itemDict = {
            "gentoo-overlays": [
                "Gentoo Overlay Database",                              # elem0: display name
                "https://api.gentoo.org/overlays/repositories.xml",     # elem1: url
                None,                                                   # elem2: parsed data
            ],
        }

        # try parse all items
        for itemName, val in self.itemDict.items():
            fullfn = os.path.join(FmConst.cloudOverlayDbDir, itemName)
            try:
                val[2] = self.__parse(fullfn)
            except BaseException:
                pass

    def update(self):
        for itemName, val in self.itemDict.items():
            fullfn = os.path.join(FmConst.cloudOverlayDbDir, itemName)
            tm = None
            while True:
                try:
                    tm = FmUtil.downloadIfNewer(val[1], fullfn)
                    val[2] = self.__parse(fullfn)
                    break
                except lxml.etree.XMLSyntaxError as e:
                    print("Failed to parse %s, %s" % (fullfn, e))
                    robust_layer.simple_fops.rm(fullfn)
                    time.sleep(1.0)
                except BaseException as e:
                    print("Failed to acces %s, %s" % (val[1], e))
                    time.sleep(1.0)
            print("%s: %s" % (val[0], tm.strftime("%Y%m%d%H%M%S")))

    def isUpdateComplete(self):
        return all([val[2] is not None for val in self.itemDict.values()])

    def hasOverlay(self, overlayName):
        assert self.isUpdateComplete()
        return self._getOverlayVcsTypeAndUrl(overlayName) is not None

    def getOverlayVcsTypeAndUrl(self, overlayName):
        assert self.isUpdateComplete()
        ret = self._getOverlayVcsTypeAndUrl(overlayName)
        assert ret is not None
        return ret

    def _getOverlayVcsTypeAndUrl(self, overlayName):
        # expand overlay name
        if overlayName.endswith("-overlay") or overlayName.endswith("_overlay"):
            overlayNameList = [overlayName]
        else:
            overlayNameList = [overlayName, overlayName + "-overlay", overlayName + "_overlay"]

        # find overlay
        for overlayName in overlayNameList:
            for val in self.itemDict.values():
                if overlayName in val[2]:
                    return val[2][overlayName]
        return None

    def __parse(self, fullfn):
        cList = [
            ("git", "https"),
            ("git", "http"),
            ("git", "git"),
            ("svn", "https"),
            ("svn", "http"),
            ("mercurial", "https"),
            ("mercurial", "http"),
            ("rsync", "rsync"),
        ]

        ret = dict()
        rootElem = lxml.etree.parse(fullfn).getroot()
        for nameTag in rootElem.xpath(".//repo/name"):
            overlayName = nameTag.text
            if overlayName in ret:
                raise Exception("duplicate overlay \"%s\"" % (overlayName))

            for vcsType, urlPrefix in cList:
                for sourceTag in nameTag.xpath("../source"):
                    tVcsType = sourceTag.get("type")
                    tUrl = sourceTag.text
                    if tUrl.startswith("git://github.com/"):        # FIXME: github does not support git:// anymore
                        tUrl = tUrl.replace("git://", "https://")
                    if tVcsType == vcsType and tUrl.startswith(urlPrefix + "://"):
                        ret[overlayName] = (tVcsType, tUrl)
                        break
                if overlayName in ret:
                    break

            if overlayName not in ret:
                raise Exception("no appropriate source for overlay \"%s\"" % (overlayName))

        return ret
