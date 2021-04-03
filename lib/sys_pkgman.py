#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

from fm_util import FmUtil
from helper_build_server import BuildServerSelector
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
            dcm.updateParallelism(self.param.hwInfoGetter.current())
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
        cmd = "%s %s %d" % (cmd, pkgName, tmpOp)
        if buildServer is not None:
            try:
                buildServer.sshExec(cmd)
            finally:
                self.infoPrinter.printInfo(">> Synchronizing down system files...")
                buildServer.syncDownSystem()
                print("")
        else:
            FmUtil.shellExec(cmd)

        # end remote build
        if buildServer is not None:
            buildServer.dispose()

    def uninstallPackage(self, pkgName):
        PkgMerger().unmergePkg(pkgName)
