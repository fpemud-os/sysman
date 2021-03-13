#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
from fm_util import FmUtil
from fm_param import FmConst
from helper_boot import FkmBootLoader
from helper_boot import FkmMountBootDirRw
from helper_build_server import BuildServerSelector
from helper_dyncfg import DynCfgModifier


class FmSysCleaner:

    def __init__(self, param):
        self.param = param
        self.infoPrinter = self.param.infoPrinter

        self.opCleanKernel = os.path.join(FmConst.libexecDir, "op-clean-kernel.py")
        self.opCleanPkgAndUse = os.path.join(FmConst.libexecDir, "op-clean-packages-useflags.py")
        self.opCleanKcache = os.path.join(FmConst.libexecDir, "op-clean-kcache.py")

    def clean(self, bPretend):
        layout = self.param.storageManager.getStorageLayout()

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

        # clean old kernel files
        self.infoPrinter.printInfo(">> Removing old kernel files...")
        if True:
            resultFile = os.path.join(self.param.tmpDir, "result.txt")
            bFileRemoved = False
            with FkmMountBootDirRw(self.param.storageManager.getStorageLayout()):
                self._exec(buildServer, self.opCleanKernel, resultFile)
                if buildServer is None:
                    with open(resultFile, "r", encoding="iso8859-1") as f:
                        data = f.read()
                else:
                    data = buildServer.getFile(resultFile).decode("iso8859-1")
                bFileRemoved = self._parseKernelCleanResult(data)
                print("")

                if bFileRemoved:
                    if buildServer is not None:
                        self.infoPrinter.printInfo(">> Synchronizing down /boot, /lib/modules and /lib/firmware...")
                        buildServer.syncDownKernel()
                        print("")

                    self.infoPrinter.printInfo(">> Updating boot-loader...")
                    if self.param.runMode == "prepare":
                        print("WARNING: Running in \"%s\" mode, do NOT maniplate boot-loader!!!" % (self.param.runMode))
                    else:
                        FkmBootLoader().updateBootloader(self.param.hwInfoGetter.current(), layout, FmConst.kernelInitCmd)
                    print("")

            if bFileRemoved and self.param.storageManager.needSyncBootPartition(layout):
                self.infoPrinter.printInfo(">> Synchronizing boot partitions...")
                self.param.storageManager.syncBootPartition(layout)
                print("")

        # clean kcache
        self.infoPrinter.printInfo(">> Cleaning %s..." % (FmConst.kcacheDir))
        self._execAndSyncDownQuietly(buildServer, self.opCleanKcache, "", FmConst.kcacheDir)
        print("")

        # clean not-used packages and USE flags
        self.infoPrinter.printInfo(">> Cleaning packages...")
        self._exec(buildServer, self.opCleanPkgAndUse, "%d" % (bPretend))
        print("")

        # sync down system files
        if not bPretend and buildServer is not None:
            self.infoPrinter.printInfo(">> Synchronizing down system files...")
            buildServer.syncDownSystem()
            print("")

        # clean distfiles
        # sync down distfiles directory quietly since there's only deletion
        self.infoPrinter.printInfo(">> Cleaning %s..." % (FmConst.distDir))
        self._execAndSyncDownQuietly(buildServer, "/usr/bin/eclean-dist", "", FmConst.distDir)
        print("")

        # end remote build
        if buildServer is not None:
            buildServer.dispose()

    def _exec(self, buildServer, cmd, argstr):
        if buildServer is None:
            FmUtil.shellExec(cmd + " " + argstr)
        else:
            buildServer.sshExec(cmd + " " + argstr)

    def _execAndSyncDownQuietly(self, buildServer, cmd, argstr, directory):
        if buildServer is None:
            FmUtil.shellExec(cmd + " " + argstr)
        else:
            buildServer.sshExec(cmd + " " + argstr)
            buildServer.syncDownDirectory(directory, quiet=True)

    def _parseKernelCleanResult(self, result):
        lines = result.split("\n")
        lines = [x.rstrip() for x in lines if x.rstrip() != ""]
        assert len(lines) == 1
        return (lines[0] != "0")
