#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import strict_hdds
from fm_util import BootDirWriter, FmUtil
from fm_param import FmConst
from client_build_server import BuildServerSelector
from helper_dyncfg import DynCfgModifier
from helper_bbki import BbkiWrapper


class FmSysCleaner:

    def __init__(self, param):
        self.param = param
        self.infoPrinter = self.param.infoPrinter

        self.opCleanKernel = os.path.join(FmConst.libexecDir, "op-clean-kernel.py")
        self.opCleanPkgAndUse = os.path.join(FmConst.libexecDir, "op-clean-packages-useflags.py")
        self.opCleanKcache = os.path.join(FmConst.libexecDir, "op-clean-kcache.py")

    def clean(self, bPretend):
        # modify dynamic config
        self.infoPrinter.printInfo(">> Preparing...")
        if True:
            dcm = DynCfgModifier()
            dcm.updateMirrors()
            dcm.updateDownloadCommand()
            dcm.updateParallelism(self.param.machineInfoGetter.hwInfo())
            dcm.updateCcache()
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
            layout = strict_hdds.get_storage_layout()
            bbkiObj = BbkiWrapper(layout)
            resultFile = os.path.join(self.param.tmpDir, "result.txt")
            bFileRemoved = False

            with BootDirWriter(layout):
                self._exec(buildServer, self.opCleanKernel, "%d" % (bPretend), resultFile)
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
                        bbkiObj.updateBootloaderAfterCleaning()
                    print("")

            if layout.name in ["efi-btrfs", "efi-bcache-btrfs", "efi-bcachefs"]:
                dstList = layout.get_pending_esp_list()
                if bFileRemoved and len(dstList) > 0:
                    with self.infoPrinter.printInfoAndIndent(">> Synchronizing boot partitions..."):
                        for dst in dstList:
                            self.infoPrinter.printInfo("        - %s to %s..." % (layout.get_esp(), dst))
                            layout.sync_esp(dst)
                    print("")

        # clean kcache
        self.infoPrinter.printInfo(">> Cleaning %s..." % (FmConst.kcacheDir))
        self._execAndSyncDownQuietly(buildServer, self.opCleanKcache, "%d" % (bPretend), directory=FmConst.kcacheDir)
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
        self._execAndSyncDownQuietly(buildServer, "eclean-dist", directory=FmConst.distDir)
        print("")

        # end remote build
        if buildServer is not None:
            buildServer.dispose()

    def _exec(self, buildServer, *args):
        if buildServer is None:
            FmUtil.cmdExec(*args)
        else:
            buildServer.sshExec(*args)

    def _execAndSyncDownQuietly(self, buildServer, *args, directory=None):
        if buildServer is None:
            FmUtil.cmdExec(*args)
        else:
            buildServer.sshExec(*args)
            buildServer.syncDownDirectory(directory, quiet=True)

    def _parseKernelCleanResult(self, result):
        lines = result.split("\n")
        lines = [x.rstrip() for x in lines if x.rstrip() != ""]
        assert len(lines) == 1
        return (lines[0] != "0")
