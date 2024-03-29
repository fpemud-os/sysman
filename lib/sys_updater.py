#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import json
import strict_hdds
from fm_util import FmUtil
from fm_util import ParallelRunSequencialPrint
from fm_param import FmConst
from client_build_server import BuildServerSelector
from helper_bbki import BbkiWrapper
from helper_bbki import BootDirWriter
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
        if self.param.runMode in ["normal", "setup"]:
            layout = strict_hdds.get_storage_layout()
        else:
            layout = None
        bbkiObj = BbkiWrapper(layout)
        pkgwh = PkgWarehouse()
        overlayDb = CloudOverlayDb()

        # set system to unstable status
        if self.param.runMode in ["normal", "setup"]:
            if bbkiObj.isStable():
                with BootDirWriter(layout):
                    bbkiObj.setStable(False)

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

        # do sync
        if bSync:
            # sync bbki repositories
            with ParallelRunSequencialPrint() as prspObj:
                if buildServer is not None:
                    startCoro = buildServer.asyncStartSshExec
                    waitCoro = buildServer.asyncWaitSshExec
                else:
                    startCoro = FmUtil.asyncStartCmdExec
                    waitCoro = FmUtil.asyncWaitCmdExec
                for repo in bbkiObj.repositories:
                    prspObj.add_task(
                        startCoro, [self.opSync, self.param.runMode, "sync-bbki-repo", repo.name],
                        waitCoro,
                        pre_func=lambda x=repo.name: self.infoPrinter.printInfo(">> Synchronizing BBKI repository \"%s\"..." % (x)),
                        post_func=lambda: print(""),
                    )
            # FIXME: there should be no sync down after realtime network filesystem support is done
            if buildServer is not None:
                buildServer.syncDownDirectory(FmConst.portageDataDir)

            # sync repository directories
            for repoName in pkgwh.repoman.getRepositoryList():
                repoDir = pkgwh.repoman.getRepoDir(repoName)
                self.infoPrinter.printInfo(">> Synchronizing repository \"%s\"..." % (repoName))
                self._execAndSyncDownQuietly(buildServer, self.opSync, self.param.runMode, "sync-repo", repoName, directory=repoDir)
                print("")

            # update cloud overlay db
            self.infoPrinter.printInfo(">> Synchronizing cloud overlay database...")
            overlayDb.update()
            print("")

            # sync overlay directories
            with ParallelRunSequencialPrint() as prspObj:
                if buildServer is not None:
                    startCoro = buildServer.asyncStartSshExec
                    waitCoro = buildServer.asyncWaitSshExec
                else:
                    startCoro = FmUtil.asyncStartCmdExec
                    waitCoro = FmUtil.asyncWaitCmdExec
                for repo in pkgwh.layman.getOverlayList():
                    if pkgwh.layman.getOverlayType(repo) == "static":
                        continue
                    prspObj.add_task(
                        startCoro, [self.opSync, self.param.runMode, "sync-overlay", repo],
                        waitCoro,
                        pre_func=lambda x=repo: self.infoPrinter.printInfo(">> Synchronizing overlay \"%s\"..." % (x)),
                        post_func=lambda: print(""),
                    )
            # FIXME: there should be no sync down after realtime network filesystem support is done
            if buildServer is not None:
                buildServer.syncDownDirectory(FmConst.portageDataDir)

            # add pre-enabled overlays
            for repo, ourl in pkgwh.getPreEnableOverlays().items():
                if not pkgwh.layman.isOverlayExist(repo):
                    self.infoPrinter.printInfo(">> Installing overlay \"%s\"..." % repo)
                    vcsType = "git"
                    if overlayDb.hasOverlay(repo):
                        vcsType, ourl = overlayDb.getOverlayVcsTypeAndUrl(repo)
                    if ourl is None:
                        raise Exception("no URL for overlay %s" % repo)
                    if buildServer is None:
                        FmUtil.cmdExec(self.opSync, self.param.runMode, "add-trusted-overlay", repo, vcsType, ourl)
                    else:
                        buildServer.sshExec(self.opSync, "add-trusted-overlay", repo, vcsType, ourl)
                        buildServer.syncDownWildcardList([
                            os.path.join(pkgwh.layman.getOverlayFilesDir(repo), "***"),
                            pkgwh.layman.getOverlayDir(repo),
                            pkgwh.layman.getOverlayCfgReposFile(repo),
                        ], quiet=True)
                    print("")

            # add pre-enabled overlays by pre-enabled package
            for repo, data in pkgwh.getPreEnablePackages().items():
                ourl = data[0]
                if not pkgwh.layman.isOverlayExist(repo):
                    self.infoPrinter.printInfo(">> Installing overlay \"%s\"..." % repo)
                    vcsType = "git"
                    if overlayDb.hasOverlay(repo):
                        vcsType, ourl = overlayDb.getOverlayVcsTypeAndUrl(repo)
                    if ourl is None:
                        raise Exception("no URL for overlay %s" % repo)
                    if buildServer is None:
                        FmUtil.cmdExec(self.opSync, self.param.runMode, "add-transient-overlay", repo, vcsType, ourl)
                    else:
                        buildServer.sshExec(self.opSync, self.param.runMode, "add-transient-overlay", repo, vcsType, ourl)
                        buildServer.syncDownWildcardList([
                            os.path.join(pkgwh.layman.getOverlayFilesDir(repo), "***"),
                            pkgwh.layman.getOverlayDir(repo),
                            pkgwh.layman.getOverlayCfgReposFile(repo),
                        ], quiet=True)
                    print("")

            # add pre-enabled packages
            for repo, data in pkgwh.getPreEnablePackages().items():
                tlist = [x for x in data[1] if not pkgwh.layman.isOverlayPackageEnabled(repo, x)]
                if tlist != []:
                    self.infoPrinter.printInfo(">> Enabling packages in overlay \"%s\"..." % repo)
                    self._exec(buildServer, self.opSync, self.param.runMode, "enable-overlay-package", repo, *tlist)
                    print("")
            if buildServer is not None:
                buildServer.syncDownDirectory(os.path.join(FmConst.portageDataDir, "overlay-*"), quiet=True)

            # refresh package related stuff
            self._execAndSyncDownQuietly(buildServer, self.opSync, self.param.runMode, "refresh-package-related-stuff", directory=FmConst.portageCfgDir)

            # eliminate "Performing Global Updates"
            self._execAndSyncDownQuietly(buildServer, self.opSync, self.param.runMode, "touch-portage-tree", directory=FmConst.portageDbDir)     # FIXME

        # do fetch and build
        if True:
            resultFile = os.path.join(self.param.tmpDir, "result.txt")
            kernelCfgRules = json.dumps(self.param.machineInfoGetter.hwInfo().kernelCfgRules)

            # install kernel, initramfs and bootloader
            with BootDirWriter(layout):
                self.infoPrinter.printInfo(">> Installing %s-%s..." % (bbkiObj.get_kernel_atom().fullname, bbkiObj.get_kernel_atom().ver))
                if True:
                    self._exec(buildServer, self.opInstallKernel, self.param.runMode, kernelCfgRules, resultFile)
                    # kernelBuilt, postfix = self._parseKernelBuildResult(self._readResultFile(buildServer, resultFile))
                    print("")

                    if buildServer is not None:
                        self.infoPrinter.printInfo(">> Synchronizing down /boot, /lib/modules and /lib/firmware...")
                        buildServer.syncDownKernel()
                        print("")

                self.infoPrinter.printInfo(">> Creating initramfs...")
                if True:
                    if self.param.runMode in ["normal", "setup"]:
                        bbkiObj.installInitramfs()
                    else:
                        print("WARNING: Running in \"%s\" mode, do NOT create initramfs!!!" % (self.param.runMode))
                    print("")

                self.infoPrinter.printInfo(">> Updating boot-loader...")
                if self.param.runMode in ["normal", "setup"]:
                    bbkiObj.updateBootloader()
                else:
                    print("WARNING: Running in \"%s\" mode, do NOT maniplate boot-loader!!!" % (self.param.runMode))
                print("")

            # synchronize boot partitions
            if layout.name in ["efi-btrfs", "efi-bcache-btrfs", "efi-bcachefs"]:
                dstList = layout.get_pending_esp_list()
                if len(dstList) > 0:
                    with self.infoPrinter.printInfoAndIndent(">> Synchronizing boot partitions..."):
                        for dst in dstList:
                            self.infoPrinter.printInfo("        - %s to %s..." % (layout.get_esp(), dst))
                            layout.sync_esp(dst)
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
                FmUtil.cmdExec(self.opEmergeWorld)

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
                FmUtil.cmdExec(self.opEmerge9999)

        # end remote build
        if buildServer is not None:
            buildServer.dispose()

    def stablize(self):
        layout = strict_hdds.get_storage_layout()
        bbkiObj = BbkiWrapper(layout)

        self.infoPrinter.printInfo(">> Stablizing...")
        with BootDirWriter(layout):
            bbkiObj.setStable(True)
        print("")

        if layout.name in ["efi-btrfs", "efi-bcache-btrfs", "efi-bcachefs"]:
            dstList = layout.get_pending_esp_list()
            if len(dstList) > 0:
                with self.infoPrinter.printInfoAndIndent(">> Synchronizing boot partitions..."):
                    for dst in dstList:
                        self.infoPrinter.printInfo("        - %s to %s..." % (layout.get_esp(), dst))
                        layout.sync_esp(dst)
                print("")

    def updateAfterHddAddOrRemove(self, hwInfo, layout, bbkiObj):
        pendingBe = bbkiObj.get_pending_boot_entry()
        if pendingBe is None:
            raise Exception("No boot entry found!")

        # re-create initramfs
        with BootDirWriter(layout):
            self.infoPrinter.printInfo(">> Recreating initramfs...")
            bbkiObj.installInitramfs()
            print("")

            self.infoPrinter.printInfo(">> Updating boot-loader...")
            bbkiObj.updateBootloader()
            print("")

        # synchronize boot partitions
        if layout.name in ["efi-btrfs", "efi-bcache-btrfs", "efi-bcachefs"]:
            dstList = layout.get_pending_esp_list()
            if len(dstList) > 0:
                with self.infoPrinter.printInfoAndIndent(">> Synchronizing boot partitions..."):
                    for dst in dstList:
                        self.infoPrinter.printInfo("        - %s to %s..." % (layout.get_esp(), dst))
                        layout.sync_esp(dst)
                print("")

    def _exec(self, buildServer, *args, base64=False):
        if buildServer is None:
            FmUtil.cmdExec(*args)
        else:
            buildServer.sshExec(*args, base64=base64)

    def _readResultFile(self, buildServer, resultFile):
        if buildServer is None:
            with open(resultFile, "r", encoding="iso8859-1") as f:
                return f.read()
        else:
            return buildServer.getFile(resultFile).decode("iso8859-1")

    def _execAndSyncDownQuietly(self, buildServer, *args, directory=None):
        if buildServer is None:
            FmUtil.cmdExec(*args)
        else:
            buildServer.sshExec(*args)
            buildServer.syncDownDirectory(directory, quiet=True)

    def _parseKernelBuildResult(self, result):
        lines = result.split("\n")
        lines = [x.rstrip() for x in lines if x.rstrip() != ""]
        assert len(lines) == 2
        return (lines[0] != "0", lines[1])       # (kernelBuilt, postfix)
