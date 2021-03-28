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
import urllib.parse
import robust_layer.simple_git
import robust_layer.simple_subversion
import robust_layer.rsync
from datetime import datetime
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
                name = cfg.get("main", "name")
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
                FmUtil.forceDelete(usefn)
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
        rc, out = FmUtil.cmdCallWithRetCode("/usr/bin/eselect", "python", "show")
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
            a = float(a.replace("python", "").replace("_", "."))
            b = float(b.replace("python", "").replace("_", "."))
            return FmUtil.cmpSimple(a, b)

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
        rc, out = FmUtil.cmdCallWithRetCode("/usr/bin/eselect", "ruby", "show")
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
            a = int(a.replace("ruby", ""))
            b = int(b.replace("ruby", ""))
            return FmUtil.cmpSimple(a, b)

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
        }
        self._repoGitUrlDict = {
            "guru": "https://github.com/gentoo/guru",
        }

    def getRepositoryList(self):
        return list(self._repoInfoDict.keys())

    def isRepoExist(self, repoName):
        assert repoName in self._repoInfoDict
        return os.path.exists(os.path.join(FmConst.portageDataDir, "repo-%s" % (repoName)))

    def getRepoCfgReposFile(self, repoName):
        # returns /etc/portage/repos.conf/repo-XXXX.conf
        assert repoName in self._repoInfoDict
        return os.path.join(FmConst.portageCfgReposDir, "repo-%s.conf" % (repoName))

    def getRepoDir(self, repoName):
        assert repoName in self._repoInfoDict
        return os.path.join(FmConst.portageDataDir, "repo-%s" % (repoName))

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
        assert self.isRepoExist(repoName)

        cfgFile = self.getRepoCfgReposFile(repoName)
        repoDir = self.getRepoDir(repoName)

        # check repository directory
        if not os.path.exists(repoDir):
            if bAutoFix:
                self.createRepository(repoName)
            else:
                raise RepositoryCheckError("repository directory \"%s\" does not exist" % (repoDir))
        if not os.path.isdir(repoDir):
            if bAutoFix:
                FmUtil.forceDelete(repoDir)
                self.createRepository(repoName)
            else:
                raise RepositoryCheckError("repository directory \"%s\" is invalid" % (repoDir))

        # check cfgFile content
        if True:
            standardContent = self.__generateReposConfContent(repoName)
            if pathlib.Path(cfgFile).read_text() != standardContent:
                if bAutoFix:
                    with open(cfgFile, "w") as f:
                        f.write(standardContent)
                else:
                    raise RepositoryCheckError("file content of \"%s\" is invalid" % (cfgFile))

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

        self.__recordUpdateTime(repoName)

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

        self.__recordUpdateTime(repoName)

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
            FmUtil.portagePatchRepository(repoName2, self.getRepoDir(repoName), "N-patch", modDir, True)

    def __patchRepoS(self, repoName):
        repoName2 = "repo-%s" % (repoName)
        modDir = os.path.join(FmConst.dataDir, "pkgwh-s-patch", repoName2)
        if os.path.exists(modDir):
            FmUtil.portagePatchRepository(repoName2, self.getRepoDir(repoName), "S-patch", modDir, False)

    def __recordUpdateTime(self, repoName):
        with open(os.path.join(self.getRepoDir(repoName), "update-time.txt"), "w") as f:
            f.write(datetime.now().date().strftime("%Y-%m-%d"))
            f.write("\n")


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
        self.repoman = EbuildRepositories()
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
        if self.isOverlayExist(overlayName):
            raise Exception("the specified overlay has already been installed")

        cfgFile = self.getOverlayCfgReposFile(overlayName)
        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)

        vcsType = self._createOverlayFilesDir(overlayName, overlayFilesDir, overlayVcsType, overlayUrl)
        try:
            self._removeOverlayFilesDirDuplicatePackage(overlayFilesDir)
            self._createTrustedOverlayDir(overlayName, overlayDir, overlayFilesDir)
            repoName = FmUtil.repoGetRepoName(overlayDir)
            with open(cfgFile, "w") as f:
                f.write(self._generateCfgReposFile(overlayName, overlayDir, "trusted", vcsType, overlayUrl, repoName))
        except:
            shutil.rmtree(overlayDir)       # keep overlay files directory
            raise

    def addTransientOverlay(self, overlayName, overlayVcsType, overlayUrl):
        if self.isOverlayExist(overlayName):
            raise Exception("the specified overlay has already been installed")

        cfgFile = self.getOverlayCfgReposFile(overlayName)
        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)

        self._createOverlayFilesDir(overlayName, overlayFilesDir, overlayVcsType, overlayUrl)
        try:
            self._createTransientOverlayDir(overlayName, overlayDir, overlayFilesDir)
            repoName = FmUtil.repoGetRepoName(overlayDir)
            with open(cfgFile, "w") as f:
                f.write(self._generateCfgReposFile(overlayName, overlayDir, "transient", overlayVcsType, overlayUrl, repoName))
        except:
            shutil.rmtree(overlayDir)       # keep overlay files directory
            raise

    def removeOverlay(self, overlayName):
        if not self.isOverlayExist(overlayName):
            raise Exception("overlay \"%s\" is not installed" % (overlayName))
        if not os.path.exists(self.getOverlayFilesDir(overlayName)):
            raise Exception("overlay \"%s\" is a static overlay" % (overlayName))

        FmUtil.forceDelete(self.getOverlayFilesDir(overlayName))
        FmUtil.forceDelete(self.getOverlayDir(overlayName))
        FmUtil.forceDelete(self.getOverlayCfgReposFile(overlayName))

    def checkOverlay(self, overlayName, bAutoFix=False):
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
            # doesn't exist or is invalid
            if not os.path.exists(overlayFilesDir) or not os.path.isdir(overlayFilesDir):
                if bAutoFix:
                    ret = self._createOverlayFilesDir(overlayName, overlayFilesDir, vcsType, overlayUrl)
                    assert ret == vcsType
                    self._removeOverlayFilesDirDuplicatePackage(overlayFilesDir)
                    self._createTrustedOverlayDir(overlayName, overlayDir, overlayFilesDir)
                else:
                    raise OverlayCheckError("overlay files directory \"%s\" does not exist or is invalid" % (overlayFilesDir))
            # invalid layout.conf content
            with open(os.path.join(overlayFilesDir, "metadata", "layout.conf"), "r") as f:
                if re.search("^\\s*masters\\s*=\\s*gentoo\\s*$", f.read(), re.M) is None:
                    raise OverlayCheckError("overlay \"%s\" has illegal layout.conf" % (overlayName))
        elif overlayType == "transient":
            # doesn't exist or is invalid
            if not os.path.exists(overlayFilesDir) or not os.path.isdir(overlayFilesDir):
                if bAutoFix:
                    ret = self._createOverlayFilesDir(overlayName, overlayFilesDir, vcsType, overlayUrl)
                    assert ret == vcsType
                    self._createTransientOverlayDir(overlayName, overlayDir, overlayFilesDir)
                else:
                    raise OverlayCheckError("overlay files directory \"%s\" does not exist or is invalid" % (overlayFilesDir))
        else:
            assert False

        # check overlay directory
        if overlayType == "static":
            # doesn't exist or is invalid
            if not os.path.isdir(overlayDir) or os.path.islink(overlayDir):
                if bAutoFix:
                    self._createStaticOverlayDir(overlayName, overlayDir)
                else:
                    raise OverlayCheckError("overlay directory \"%s\" does not exist or is invalid" % (overlayDir))
            # no symlink
            for fbasename in FmUtil.getFileList(overlayDir, 2, "d"):
                fulld = os.path.join(overlayDir, fbasename)
                if os.path.islink(fulld):
                    raise OverlayCheckError("package \"%s\" in overlay \"%s\" is a symlink" % (fbasename, overlayName))
        elif overlayType == "trusted":
            # doesn't exist or is invalid
            if not os.path.isdir(overlayDir) or not os.path.islink(overlayDir) or os.readlink(overlayDir) != overlayFilesDir:
                if bAutoFix:
                    self._createTrustedOverlayDir(overlayName, overlayDir, overlayFilesDir)
                else:
                    raise OverlayCheckError("overlay directory \"%s\" does not exist or is invalid" % (overlayDir))
        elif overlayType == "transient":
            # doesn't exist or is invalid
            if not os.path.isdir(overlayDir) or os.path.islink(overlayDir):
                if bAutoFix:
                    self._createTransientOverlayDir(overlayName, overlayDir, overlayFilesDir)
                else:
                    raise OverlayCheckError("overlay directory \"%s\" does not exist or is invalid" % (overlayDir))
            # all packages must be symlinks, no invalid symlink
            if True:
                flist = []
                for fbasename in FmUtil.getFileList(overlayDir, 2, "d"):
                    if FmUtil.repoIsSysFile(fbasename):
                        continue
                    flist.append(fbasename)
                for d in flist:
                    fulld = os.path.join(overlayDir, d)
                    if not os.path.islink(fulld):
                        raise OverlayCheckError("package \"%s\" in overlay \"%s\" is not a symlink" % (d, overlayName))
                    if not os.path.exists(fulld):
                        raise OverlayCheckError("package \"%s\" in overlay \"%s\" is a broken symlink" % (d, overlayName))
            # no empty category directory
            if True:
                flist = []
                for fbasename in FmUtil.getFileList(overlayDir, 1, "d"):
                    if FmUtil.repoIsSysFile(fbasename):
                        continue
                    flist.append(fbasename)
                for d in flist:
                    fulld = os.path.join(overlayDir, d)
                    if os.listdir(fulld) == []:
                        raise OverlayCheckError("category directory \"%s\" in overlay \"%s\" is empty" % (d, overlayName))
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

    def syncOverlay(self, overlayName):
        if not self.isOverlayExist(overlayName):
            raise Exception("overlay \"%s\" is not installed" % (overlayName))

        cfgFile = self.getOverlayCfgReposFile(overlayName)
        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)
        overlayType = self.getOverlayType(overlayName)
        buf = pathlib.Path(cfgFile).read_text()
        priority, location, overlayType, vcsType, overlayUrl, repoName = self._parseCfgReposFile(buf)

        if overlayType == "static":
            # static overlay is mantained by other means
            pass
        elif overlayType == "trusted":
            if not FmUtil.isUrlPrivate(overlayUrl) or FmUtil.tryPrivateUrl(overlayUrl):
                self._syncOverlayFilesDir(overlayName, overlayFilesDir, vcsType, overlayUrl)
                self._removeOverlayFilesDirDuplicatePackage(overlayFilesDir)
            else:
                print("Overlay not accessible, ignored.")
        elif overlayType == "transient":
            if not FmUtil.isUrlPrivate(overlayUrl) or FmUtil.tryPrivateUrl(overlayUrl):
                self._syncOverlayFilesDir(overlayName, overlayFilesDir, vcsType, overlayUrl)
                self._refreshTransientOverlayDir(overlayName, overlayDir, overlayFilesDir)
            else:
                print("Overlay not accessible, ignored.")
        else:
            assert False

    def isOverlayPackageEnabled(self, overlayName, pkgName):
        assert self.isOverlayExist(overlayName)
        return os.path.isdir(os.path.join(self.getOverlayDir(overlayName), pkgName))

    def enableOverlayPackage(self, overlayName, pkgName, quiet=False):
        assert self.isOverlayExist(overlayName)

        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)

        if os.path.isdir(os.path.join(overlayDir, pkgName)):
            raise Exception("package \"%s\" has already been enabled" % (pkgName))
        if not os.path.isdir(os.path.join(overlayFilesDir, pkgName)):
            raise Exception("package \"%s\" does not exist in overlay \"%s\"" % (pkgName, overlayName))
        if portage.db[portage.root]["porttree"].dbapi.match(pkgName) != []:
            raise Exception("package \"%s\" has already exist" % (pkgName))

        srcEbuildDir = os.path.join(overlayFilesDir, pkgName)
        dstCategoryDir = os.path.join(overlayDir, pkgName.split("/")[0])
        os.makedirs(dstCategoryDir, exist_ok=True)
        FmUtil.cmdCall("/bin/ln", "-sf", srcEbuildDir, dstCategoryDir)

        if not quiet:
            print("Notice: You need to enable any dependent package manually.")

    def disableOverlayPackage(self, overlayName, pkgName):
        assert self.isOverlayExist(overlayName)

        overlayDir = self.getOverlayDir(overlayName)
        overlayFilesDir = self.getOverlayFilesDir(overlayName)

        if os.path.islink(overlayDir):
            raise Exception("overlay \"%s\" is a trusted overlay" % (overlayName))
        if not os.path.exists(overlayFilesDir):
            raise Exception("overlay \"%s\" is a static overlay" % (overlayName))
        if not os.path.isdir(os.path.join(overlayDir, pkgName)):
            raise Exception("package \"%s\" is not enabled" % (pkgName))

        FmUtil.forceDelete(os.path.join(overlayDir, pkgName))
        FmUtil.removeEmptyDir(os.path.join(overlayDir, pkgName.split("/")[0]))

    def _getOverlayUrlPublicOrPrivate(self, overlayUrl):
        domainName = urllib.parse.urlparse(overlayUrl).hostname
        return not FmUtil.isDomainNamePrivate(domainName)

    def _createOverlayFilesDir(self, overlayName, overlayFilesDir, vcsType, url):
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
            self.__overlayFilesDirPatch(overlayName, overlayFilesDir, "N-patch", "pkgwh-n-patch", True)
            self.__overlayFilesDirPatch(overlayName, overlayFilesDir, "S-patch", "pkgwh-s-patch", False)
            print("Done.")

        return vcsType

    def _syncOverlayFilesDir(self, overlayName, overlayFilesDir, vcsType, url):
        if vcsType == "git":
            robust_layer.simple_git.pull(overlayFilesDir, reclone_on_failure=True, url=url)
        elif vcsType == "svn":
            robust_layer.simple_subversion.update(overlayFilesDir, recheckout_on_failure=True, url=url)
        else:
            assert False

        if self.__overlayHasPatch(overlayName, ["pkgwh-n-patch", "pkgwh-s-patch"]):
            print("Patching...")
            self.__overlayFilesDirPatch(overlayName, overlayFilesDir, "N-patch", "pkgwh-n-patch", True)
            self.__overlayFilesDirPatch(overlayName, overlayFilesDir, "S-patch", "pkgwh-s-patch", False)
            print("Done.")

    def _removeOverlayFilesDirDuplicatePackage(self, overlayFilesDir):
        # get all packages in all repositories
        infoDict = dict()
        for repoName in self.repoman.getRepositoryList():
            repoDir = self.repoman.getRepoDir(repoName)
            infoDict[repoName] = set(FmUtil.repoGetEbuildDirList(repoDir))

        # remove packages that duplicates with repository from overlay
        oDirInfo = set(FmUtil.repoGetEbuildDirList(overlayFilesDir))
        for k, v in infoDict.items():
            for item in list(v & oDirInfo):
                FmUtil.repoRemovePackageAndCategory(overlayFilesDir, item)
                print("Duplicate package \"%s\" is automatically removed." % (item))

    def _createStaticOverlayDir(self, overlayName, overlayDir):
        FmUtil.forceDelete(overlayDir)
        os.mkdir(overlayDir)

        os.mkdir(os.path.join(overlayDir, "profiles"))
        with open(os.path.join(overlayDir, "profiles", "repo_name"), "w") as f:
            f.write(overlayName)

        os.mkdir(os.path.join(overlayDir, "metadata"))
        with open(os.path.join(overlayDir, "metadata", "layout.conf"), "w") as f:
            f.write("masters = gentoo\n")
            f.write("thin-manifests = true\n")

    def _createTrustedOverlayDir(self, overlayName, overlayDir, overlayFilesDir):
        FmUtil.forceDelete(overlayDir)
        FmUtil.cmdCall("/bin/ln", "-sf", overlayFilesDir, overlayDir)

    def _createTransientOverlayDir(self, overlayName, overlayDir, overlayFilesDir):
        FmUtil.forceDelete(overlayDir)
        os.mkdir(overlayDir)

        # create profile directory
        srcProfileDir = os.path.join(overlayFilesDir, "profiles")
        profileDir = os.path.join(overlayDir, "profiles")
        if os.path.exists(srcProfileDir):
            FmUtil.cmdCall("/bin/cp", "-r", srcProfileDir, profileDir)
            FmUtil.forceDelete(os.path.join(profileDir, "profiles.desc"))
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
            FmUtil.cmdCall("/bin/ln", "-sf", srcMetaDataDir, overlayDir)
        else:
            os.mkdir(metaDataDir)
            with open(os.path.join(metaDataDir, "layout.conf"), "w") as f:
                f.write("masters = gentoo")

        # create eclass directory
        srcEclassDir = os.path.join(overlayFilesDir, "eclass")
        if os.path.exists(srcEclassDir):
            FmUtil.cmdCall("/bin/ln", "-sf", srcEclassDir, overlayDir)

        # ugly trick
        self.__overlayDirUglyTrick(overlayName, overlayDir, overlayFilesDir)

    def _refreshTransientOverlayDir(self, overlayName, overlayDir, overlayFilesDir):
        profileDir = os.path.join(overlayDir, "profiles")
        FmUtil.forceDelete(profileDir)

        # refresh profile directory
        srcProfileDir = os.path.join(overlayFilesDir, "profiles")
        if os.path.exists(srcProfileDir):
            FmUtil.cmdCall("/bin/cp", "-r", srcProfileDir, profileDir)
            FmUtil.forceDelete(os.path.join(profileDir, "profiles.desc"))
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

        # refresh eclass directory
        srcEclassDir = os.path.join(overlayFilesDir, "eclass")
        eclassDir = os.path.join(overlayDir, "eclass")
        if os.path.exists(srcEclassDir):
            FmUtil.cmdCall("/bin/ln", "-sf", srcEclassDir, overlayDir)
        else:
            FmUtil.forceDelete(eclassDir)

        # ugly trick
        self.__overlayDirUglyTrick(overlayName, overlayDir, overlayFilesDir)

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

    def __overlayFilesDirPatch(self, overlayName, overlayFilesDir, typeName, dirName, bCanPatchSysFiles):
        overlayName2 = "overlay-%s" % (overlayName)
        modDir = os.path.join(FmConst.dataDir, dirName, overlayName2)
        if os.path.exists(modDir):
            FmUtil.portagePatchRepository(overlayName2, overlayFilesDir, typeName, modDir, bCanPatchSysFiles)

    def __overlayDirUglyTrick(self, overlayName, overlayDir, overlayFilesDir):
        # common trick
        if os.path.islink(os.path.join(overlayDir, "metadata")):
            metaDataDir = os.path.join(overlayFilesDir, "metadata")
        else:
            metaDataDir = os.path.join(overlayDir, "metadata")
        with fileinput.FileInput(os.path.join(metaDataDir, "layout.conf"), inplace=True) as f:
            for line in f:
                if line.startswith("masters = "):
                    print("masters = gentoo")
                else:
                    print(line, end='')

        # ugly trick
        if overlayName == "unity":
            with fileinput.FileInput(os.path.join(overlayFilesDir, "eclass", "ubuntu-versionator.eclass"), inplace=True) as f:
                for line in f:
                    print(line.replace("if [ -z \"${UNITY_BUILD_OK}\" ]; then", "if false; then"), end='')


class OverlayCheckError(Exception):

    def __init__(self, message):
        self.message = message


class CloudOverlayDb:

    def __init__(self):
        self.itemDict = {
            "gentoo-overlays": ("Gentoo Overlay Database", "https://api.gentoo.org/overlays/repositories.xml"),
        }
        self.parseDict = {k: None for k in self.itemDict}

    def updateCache(self):
        os.makedirs(FmConst.cloudOverlayDbDir, exist_ok=True)
        for itemName, val in self.itemDict.items():
            dispName, url = val
            fullfn = os.path.join(FmConst.cloudOverlayDbDir, itemName)
            tm = None
            while True:
                try:
                    tm = FmUtil.downloadIfNewer(url, fullfn)
                    break
                except Exception as e:
                    print("Failed to acces %s, %s" % (url, e))
                    time.sleep(1.0)
            self.parseDict[itemName] = None
            print("%s: %s" % (dispName, tm.strftime("%Y%m%d%H%M%S")))

    def hasOverlay(self, overlayName):
        return self._getOverlayVcsTypeAndUrl(overlayName) is not None

    def getOverlayVcsTypeAndUrl(self, overlayName):
        ret = self._getOverlayVcsTypeAndUrl(overlayName)
        assert ret is not None
        return ret

    def _getOverlayVcsTypeAndUrl(self, overlayName):
        for itemName in self.itemDict.keys():
            if self.parseDict[itemName] is None:
                fullfn = os.path.join(FmConst.cloudOverlayDbDir, itemName)
                if os.path.exists(fullfn):
                    self.parseDict[itemName] = self.__parse(fullfn)
                else:
                    self.parseDict[itemName] = dict()
            if overlayName in self.parseDict[itemName]:
                return self.parseDict[itemName][overlayName]
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
                    if tVcsType == vcsType and tUrl.startswith(urlPrefix + "://"):
                        ret[overlayName] = (tVcsType, tUrl)
                        break
                if overlayName in ret:
                    break

            if overlayName not in ret:
                raise Exception("no appropriate source for overlay \"%s\"" % (overlayName))

        return ret
