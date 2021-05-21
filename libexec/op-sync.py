#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import sys
sys.path.append('/usr/lib64/fpemud-os-sysman')
from helper_pkg_warehouse import PkgWarehouse
from helper_pkg_warehouse import EbuildRepositories
from helper_pkg_warehouse import EbuildOverlays
from helper_pkg_merger import PkgMerger


item = sys.argv[1]

if item == "sync-repo":
    repoName = sys.argv[2]
    repoman = EbuildRepositories()
    repoman.syncRepository(repoName)
    sys.exit(0)

if item == "sync-overlay":
    overlayName = sys.argv[2]
    EbuildOverlays().syncOverlay(overlayName)
    sys.exit(0)

if item == "add-trusted-overlay":
    overlayName = sys.argv[2]
    overlayVcsType = sys.argv[3]
    overlayUrl = sys.argv[4]
    EbuildOverlays().addTrustedOverlay(overlayName, overlayVcsType, overlayUrl)
    sys.exit(0)

if item == "add-transient-overlay":
    overlayName = sys.argv[2]
    overlayVcsType = sys.argv[3]
    overlayUrl = sys.argv[4]
    EbuildOverlays().addTransientOverlay(overlayName, overlayVcsType, overlayUrl)
    sys.exit(0)

if item == "enable-overlay-package":
    overlayName = sys.argv[2]
    packageList = sys.argv[3:]
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
