#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import base64
import pickle
from fm_util import FmUtil
from fm_param import FmConst
from helper_boot import FkmBootDir
from helper_boot import FkmBootLoader
from helper_boot import FkmMountBootDirRw
from helper_boot_kernel import FkmBootEntry
from helper_boot_kernel import FkmBuildTarget
from helper_boot_kernel import FkmKCache
from helper_boot_initramfs import FkmInitramfsBuilder
from helper_build_server import BuildServerSelector
from helper_pkg_warehouse import PkgWarehouse
from helper_pkg_warehouse import CloudOverlayDb
from helper_dyncfg import DynCfgModifier


class FmSysUpdater:

    def __init__(self, param):
        self.param = param
        self.infoPrinter = self.param.infoPrinter

        self.opSync = os.path.join(FmConst.libexecDir, "op-sync.py")
        self.opFetch = os.path.join(FmConst.libexecDir, "op-fetch.py")
        self.opInstallKernel = os.path.join(FmConst.libexecDir, "op-install-kernel.py")
        self.opEmergeWorld = os.path.join(FmConst.libexecDir, "op-emerge-world.py")
        self.opEmerge9999 = os.path.join(FmConst.libexecDir, "op-emerge-9999.py")

    def update(self, bSync, bFetchAndBuild):
        layout = self.param.storageManager.getStorageLayout()
        helperBootDir = FkmBootDir()
        helperBootLoader = FkmBootLoader()
        pkgwh = PkgWarehouse()
        overlayDb = CloudOverlayDb()
        kcache = FkmKCache()

        # set system to unstable status
        with FkmMountBootDirRw(layout):
            helperBootLoader.setStable(False)

        # modify dynamic config
        self.infoPrinter.printInfo(">> Refreshing system configuration...")
        if True:
            dcm = DynCfgModifier()
            dcm.updateMirrors()
            dcm.updateDownloadCommand()
            dcm.updateParallelism(self.param.hwInfoGetter.current())
        print("")

        # get build server
        if BuildServerSelector.hasBuildServerCfgFile():
            self.infoPrinter.printInfo(">> Selecting build server...")
            buildServer = BuildServerSelector.selectBuildServer()
            print("")
        else:
            buildServer = None

        # sync up and start working
        if buildServer is not None:
            self.infoPrinter.printInfo(">> Synchronizing up...")
            buildServer.syncUp()
            buildServer.startWorking()
            print("")

        # do sync
        if bSync:
            # update cache
            self.infoPrinter.printInfo(">> Retrieving general information...")
            kcache.sync()
            overlayDb.updateCache()
            print("")

            # sync repository directories
            for repoName in pkgwh.repoman.getRepositoryList():
                repoDir = pkgwh.repoman.getRepoDir(repoName)
                self.infoPrinter.printInfo(">> Synchronizing repository \"%s\"..." % (repoName))
                self._execAndSyncDownQuietly(buildServer, self.opSync, "sync-repo %s" % (repoName), repoDir)
                print("")

            # sync overlay directories
            # FIXME: remove sync down dir in future
            for oname in pkgwh.layman.getOverlayList():
                if pkgwh.layman.getOverlayType(oname) == "static":
                    continue
                self.infoPrinter.printInfo(">> Synchronizing overlay \"%s\"..." % (oname))
                self._execAndSyncDownQuietly(buildServer, self.opSync, "sync-overlay %s" % (oname), pkgwh.layman.getOverlayDir(oname))
                print("")

            # add pre-enabled overlays
            for oname, ourl in pkgwh.getPreEnableOverlays().items():
                if not pkgwh.layman.isOverlayExist(oname):
                    self.infoPrinter.printInfo(">> Installing overlay \"%s\"..." % (oname))
                    vcsType = "git"
                    if overlayDb.hasOverlay(oname):
                        vcsType, ourl = overlayDb.getOverlayVcsTypeAndUrl(oname)
                    if ourl is None:
                        raise Exception("no URL for overlay %s" % (oname))
                    argstr = "add-trusted-overlay %s %s \'%s\'" % (oname, vcsType, ourl)
                    if buildServer is None:
                        FmUtil.shellExec(self.opSync + " " + argstr)
                    else:
                        buildServer.sshExec(self.opSync + " " + argstr)
                        buildServer.syncDownWildcardList([
                            os.path.join(pkgwh.layman.getOverlayFilesDir(oname), "***"),
                            pkgwh.layman.getOverlayDir(oname),
                            pkgwh.layman.getOverlayCfgReposFile(oname),
                        ], quiet=True)
                    print("")

            # add pre-enabled overlays by pre-enabled package
            for oname, data in pkgwh.getPreEnablePackages().items():
                ourl = data[0]
                if not pkgwh.layman.isOverlayExist(oname):
                    self.infoPrinter.printInfo(">> Installing overlay \"%s\"..." % (oname))
                    vcsType = "git"
                    if overlayDb.hasOverlay(oname):
                        vcsType, ourl = overlayDb.getOverlayVcsTypeAndUrl(oname)
                    if ourl is None:
                        raise Exception("no URL for overlay %s" % (oname))
                    argstr = "add-transient-overlay %s %s \'%s\'" % (oname, vcsType, ourl)
                    if buildServer is None:
                        FmUtil.shellExec(self.opSync + " " + argstr)
                    else:
                        buildServer.sshExec(self.opSync + " " + argstr)
                        buildServer.syncDownWildcardList([
                            os.path.join(pkgwh.layman.getOverlayFilesDir(oname), "***"),
                            pkgwh.layman.getOverlayDir(oname),
                            pkgwh.layman.getOverlayCfgReposFile(oname),
                        ], quiet=True)
                    print("")

            # add pre-enabled packages
            for oname, data in pkgwh.getPreEnablePackages().items():
                tlist = [x for x in data[1] if not pkgwh.layman.isOverlayPackageEnabled(oname, x)]
                if tlist != []:
                    self.infoPrinter.printInfo(">> Enabling packages in overlay \"%s\"..." % (oname))
                    argstr = "enable-overlay-package %s %s" % (oname, " ".join(["\'%s\'" % (x) for x in tlist]))
                    self._exec(buildServer, self.opSync, argstr)
                    print("")
            if buildServer is not None:
                buildServer.syncDownDirectory(os.path.join(FmConst.portageDataDir, "overlay-*"), quiet=True)

            # refresh package related stuff
            self._execAndSyncDownQuietly(buildServer, self.opSync, "refresh-package-related-stuff", FmConst.portageCfgDir)

            # eliminate "Performing Global Updates"
            self._execAndSyncDownQuietly(buildServer, self.opSync, "touch-portage-tree", FmConst.portageDbDir)     # FIXME

        # do fetch and build
        if bFetchAndBuild:
            resultFile = os.path.join(self.param.tmpDir, "result.txt")
            kernelCfgRules = base64.b64encode(pickle.dumps(self.param.hwInfoGetter.current().kernelCfgRules)).decode("ascii")

            # update kernel in kcache
            if True:
                v = kcache.getLatestKernelVersion()
                fn = os.path.basename(kcache.getKernelFileByVersion(v))
                self.infoPrinter.printInfo(">> Fetching %s..." % (fn))
                self._execAndSyncDownQuietly(buildServer, self.opFetch, "kernel \'%s\'" % (v), FmConst.kcacheDir)
                print("")

            # update firmware in kcache
            if True:
                v = kcache.getLatestFirmwareVersion()
                fn = os.path.basename(kcache.getFirmwareFileByVersion(v))
                self.infoPrinter.printInfo(">> Fetching %s..." % (fn))
                self._execAndSyncDownQuietly(buildServer, self.opFetch, "firmware \'%s\'" % (v), FmConst.kcacheDir)
                print("")

            # update extra kernel driver in kcache
            tset = set()
            for name in kcache.getExtraDriverList():
                sourceName = kcache.getExtraDriverSourceInfo(name)["name"]
                if sourceName in tset:
                    continue
                self.infoPrinter.printInfo(">> Fetching extra source \"%s\"..." % (sourceName))
                self._execAndSyncDownQuietly(buildServer, self.opFetch, "extra-driver-source \'%s\' \'%s\'" % (name, sourceName), FmConst.kcacheDir)
                tset.add(sourceName)
                print("")
            for name in kcache.getExtraFirmwareList():
                sourceName = kcache.getExtraFirmwareSourceInfo(name)["name"]
                if sourceName in tset:
                    continue
                self.infoPrinter.printInfo(">> Fetching extra source \"%s\"..." % (sourceName))
                self._execAndSyncDownQuietly(buildServer, self.opFetch, "extra-firmware-source \'%s\' \'%s\'" % (name, sourceName), FmConst.kcacheDir)
                tset.add(sourceName)
                print("")

            # update wireless-regulatory-database in kcache
            if True:
                v = kcache.getLatestWirelessRegDbVersion()
                fn = os.path.basename(kcache.getWirelessRegDbFileByVersion(v))
                self.infoPrinter.printInfo(">> Fetching %s..." % (fn))
                self._execAndSyncDownQuietly(buildServer, self.opFetch, "wireless-regdb \'%s\'" % (v), FmConst.kcacheDir)
                print("")

            # install kernel, initramfs and bootloader
            with FkmMountBootDirRw(layout):
                self.infoPrinter.printInfo(">> Installing kernel...")
                kernelBuilt = False
                if True:
                    self._exec(buildServer, self.opInstallKernel, kernelCfgRules + " " + resultFile)
                    kernelBuilt, postfix = self._parseKernelBuildResult(self._readResultFile(buildServer, resultFile))
                    print("")

                    if kernelBuilt and buildServer is not None:
                        self.infoPrinter.printInfo(">> Synchronizing down /boot, /lib/modules and /lib/firmware...")
                        buildServer.syncDownKernel()
                        print("")

                self.infoPrinter.printInfo(">> Creating initramfs...")
                initramfsBuilt = False
                if True:
                    if self.param.runMode == "prepare":
                        print("WARNING: Running in \"%s\" mode, do NOT create initramfs!!!" % (self.param.runMode))
                    else:
                        initramfsBuilt = self._installInitramfs(layout, kernelBuilt, postfix)
                    print("")

                self.infoPrinter.printInfo(">> Updating boot-loader...")
                if self.param.runMode == "prepare":
                    print("WARNING: Running in \"%s\" mode, do NOT maniplate boot-loader!!!" % (self.param.runMode))
                else:
                    if kernelBuilt or initramfsBuilt:
                        helperBootDir.updateBootEntry(postfix)
                    if kernelBuilt or initramfsBuilt:
                        helperBootLoader.updateBootloader(self.param.hwInfoGetter.current(), layout, FmConst.kernelInitCmd)
                    if not kernelBuilt and not initramfsBuilt:
                        print("No operation needed.")
                print("")

            # synchronize boot partitions
            if self.param.storageManager.needSyncBootPartition(layout):
                self.infoPrinter.printInfo(">> Synchronizing boot partitions...")
                self.param.storageManager.syncBootPartition(layout)
                print("")

            # emerge @world
            self.infoPrinter.printInfo(">> Updating @world...")
            if buildServer is not None:
                try:
                    buildServer.sshExec(self.opEmergeWorld)
                finally:
                    self.infoPrinter.printInfo(">> Synchronizing down system files...")
                    buildServer.syncDownSystem()
                    print("")
            else:
                FmUtil.shellExec(self.opEmergeWorld)

            # re-emerge all "-9999" packages
            self.infoPrinter.printInfo(">> Updating all \"-9999\" packages...")
            if buildServer is not None:
                try:
                    buildServer.sshExec(self.opEmerge9999)
                finally:
                    self.infoPrinter.printInfo(">> Synchronizing down system files...")
                    buildServer.syncDownSystem()
                    print("")
            else:
                FmUtil.shellExec(self.opEmerge9999)

        # end remote build
        if buildServer is not None:
            buildServer.dispose()

    def stablize(self):
        layout = self.param.storageManager.getStorageLayout()

        with FkmMountBootDirRw(layout):
            self.infoPrinter.printInfo(">> Stablizing...")
            FkmBootLoader().setStable(True)
            print("")

        if self.param.storageManager.needSyncBootPartition(layout):
            self.infoPrinter.printInfo(">> Synchronizing boot partitions...")
            self.param.storageManager.syncBootPartition(layout)
            print("")

    def updateAfterHddAddOrRemove(self, hwInfo, layout):
        ret = FkmBootEntry.findCurrent()
        if ret is None:
            raise Exception("No kernel in /boot, you should build a kernel immediately!")

        with FkmMountBootDirRw(layout):
            self.infoPrinter.printInfo(">> Recreating initramfs...")
            self._installInitramfs(layout, True, ret.buildTarget.postfix)
            print("")

            self.infoPrinter.printInfo(">> Updating boot-loader...")
            FkmBootLoader().updateBootloader(hwInfo, layout, FmConst.kernelInitCmd)
            print("")

        if self.param.storageManager.needSyncBootPartition(layout):
            self.infoPrinter.printInfo(">> Synchronizing boot partitions...")
            self.param.storageManager.syncBootPartition(layout)
            print("")

    def _exec(self, buildServer, cmd, argstr):
        if buildServer is None:
            FmUtil.shellExec(cmd + " " + argstr)
        else:
            buildServer.sshExec(cmd + " " + argstr)

    def _readResultFile(self, buildServer, resultFile):
        if buildServer is None:
            with open(resultFile, "r", encoding="iso8859-1") as f:
                return f.read()
        else:
            return buildServer.getFile(resultFile).decode("iso8859-1")

    def _execAndSyncDownQuietly(self, buildServer, cmd, argstr, directory):
        if buildServer is None:
            FmUtil.shellExec(cmd + " " + argstr)
        else:
            buildServer.sshExec(cmd + " " + argstr)
            buildServer.syncDownDirectory(directory, quiet=True)

    def _installInitramfs(self, storageLayout, kernelBuilt, postfix):
        buildTarget = FkmBuildTarget.newFromPostfix(postfix)

        initramfsBuildNeeded = True
        while True:
            if kernelBuilt:
                break
            if not os.path.exists(os.path.join(FmConst.bootDir, buildTarget.initrdFile)):
                break

            buf = FmUtil.getFileContentFromInitrd(os.path.join(FmConst.bootDir, buildTarget.initrdFile), "startup.rc")
            lineList = buf.split("\n")
            if ("# uuid(root)=%s" % (FmUtil.getBlkDevUuid(storageLayout.getRootDev()))) not in lineList:
                break
            if storageLayout.getType() == "efi":
                if ("# uuid(boot)=%s" % (FmUtil.getBlkDevUuid(storageLayout.getBootDev()))) not in lineList:
                    break
            elif storageLayout.getType() == "bios":
                if re.search("^# uuid\\(boot\\)=", buf, re.M) is not None:
                    break
            else:
                break

            initramfsBuildNeeded = False
            break

        if initramfsBuildNeeded:
            iBuilder = FkmInitramfsBuilder(self.param.tmpDir, buildTarget)
            iBuilder.setMntInfo("root", storageLayout.getRootDev(), "")
            if storageLayout.getType() == "efi":
                iBuilder.setMntInfo("boot", storageLayout.getBootDev(), "ro,umask=0077")
            elif storageLayout.getType() == "bios":
                pass
            else:
                assert False
            iBuilder.build(buildTarget.initrdFile, buildTarget.initrdTarFile)
        else:
            print("No operation needed.")

        return initramfsBuildNeeded

    def _parseKernelBuildResult(self, result):
        lines = result.split("\n")
        lines = [x.rstrip() for x in lines if x.rstrip() != ""]
        assert len(lines) == 2
        return (lines[0] != "0", lines[1])       # (kernelBuilt, postfix)
