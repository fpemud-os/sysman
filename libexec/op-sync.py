#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
import strict_hdds
sys.path.append('/usr/lib64/fpemud-os-sysman')
from fm_param import FmConst
from helper_bbki import BbkiWrapper
from helper_pkg_warehouse import PkgWarehouse
from helper_pkg_warehouse import EbuildRepositories
from helper_pkg_warehouse import EbuildOverlays
from helper_pkg_merger import PkgMerger

runMode = sys.argv[1]
item = sys.argv[2]

if item == "sync-bbki-repo":
    repoName = sys.argv[3]
    assert repoName == "main"
    if runMode in ["normal", "setup"]:
        layout = strict_hdds.get_storage_layout()
    else:
        layout = None
    repo = BbkiWrapper(layout).repositories[0]
    repo.sync()
    sys.exit(0)

if item == "sync-repo":
    repoName = sys.argv[3]
    repoman = EbuildRepositories()
    repoman.syncRepository(repoName)
    sys.exit(0)

if item == "sync-overlay":
    overlayName = sys.argv[3]
    EbuildOverlays().syncOverlay(overlayName)
    sys.exit(0)

if item == "add-trusted-overlay":
    overlayName = sys.argv[3]
    overlayVcsType = sys.argv[4]
    overlayUrl = sys.argv[4]
    EbuildOverlays().addTrustedOverlay(overlayName, overlayVcsType, overlayUrl)
    sys.exit(0)

if item == "add-transient-overlay":
    overlayName = sys.argv[3]
    overlayVcsType = sys.argv[4]
    overlayUrl = sys.argv[5]
    EbuildOverlays().addTransientOverlay(overlayName, overlayVcsType, overlayUrl)
    sys.exit(0)

if item == "enable-overlay-package":
    overlayName = sys.argv[3]
    packageList = sys.argv[4:]
    layman = EbuildOverlays()
    for pkg in packageList:
        print("        - \"%s\"..." % (pkg))
        layman.enableOverlayPackage(overlayName, pkg, quiet=True)
    sys.exit(0)

if item == "refresh-package-related-stuff":
    pkgwh = PkgWarehouse()
    pkgwh.refreshTargetUseFlags()
    sys.exit(0)

if item == "touch-portage-tree":
    PkgMerger().touchPortageTree()
    sys.exit(0)

assert False
