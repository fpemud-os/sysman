#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from fm_util import FmUtil
from client_build_server import BuildServerSelector
from helper_pkg_merger import PkgMerger
from helper_dyncfg import DynCfgModifier


class FmPkgman:

    def __init__(self, param):
        self.param = param
        self.infoPrinter = self.param.infoPrinter

    def installPackage(self, pkgName, tmpOp):
        # modify dynamic config
        self.infoPrinter.printInfo(">> Refreshing system configuration...")
        if True:
            dcm = DynCfgModifier()
            dcm.updateMirrors()
            dcm.updateDownloadCommand()
            dcm.updateParallelism(self.param.machineInfoGetter.hwInfo())
        print("")

        # get build server
        if BuildServerSelector.hasBuildServerCfgFile():
            self.infoPrinter.printInfo(">> Selecting build server...")
            buildServer = BuildServerSelector.selectBuildServer()
            print("")
        else:
            buildServer = None

        # sync up files to server
        if buildServer is not None:
            self.infoPrinter.printInfo(">> Synchronizing up...")
            buildServer.syncUp()
            buildServer.startWorking()
            print("")

        # emerge package
        self.infoPrinter.printInfo(">> Installing %s..." % (pkgName))
        cmd = "/usr/libexec/fpemud-os-sysman/op-emerge-package.py"
        if buildServer is not None:
            try:
                buildServer.sshExec(cmd, pkgName, tmpOp)
            finally:
                self.infoPrinter.printInfo(">> Synchronizing down system files...")
                buildServer.syncDownSystem()
                print("")
        else:
            FmUtil.cmdExec(cmd, pkgName, tmpOp)

        # end remote build
        if buildServer is not None:
            buildServer.dispose()

    def uninstallPackage(self, pkgName):
        PkgMerger().unmergePkg(pkgName)
