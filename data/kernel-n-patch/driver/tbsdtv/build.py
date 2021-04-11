#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

# import sys
# import json

# # extract tbs driver
# tbsLinuxMediaDir = os.path.join(FmConst.kcacheDir, "linux_media")
# tbsMediaBuildDir = os.path.join(self.tbsdtvTmpDir, "media_build")
# if True:
#     srcdir = os.path.join(FmConst.kcacheDir, "media_build")
#     os.makedirs(tbsMediaBuildDir)
#     FmUtil.shellCall("/bin/cp -r %s/* %s" % (srcdir, tbsMediaBuildDir))

# # prepare kernel source directory
# self._makeAuxillary(self.realSrcDir, "prepare")

# # do make operation
# t = []
# for i in range(0, tbsMediaBuildDir.count("/")):
#     t.append("..")
# t = "/".join(t)
# self._makeAuxillary(tbsMediaBuildDir, "dir", ["DIR=\"%s%s\"" % (t, tbsLinuxMediaDir)])     # DIR must be a path relative to tbsMediaBuildDir

# self._makeAuxillary(tbsMediaBuildDir, "allmodconfig", ["KERNELRELEASE=%s" % (self.kernelVer)])

# self._makeMain(tbsMediaBuildDir, ["KERNELRELEASE=%s" % (self.kernelVer)])

# self._makeAuxillary(tbsMediaBuildDir, "install")

# fn = "signature.tbs-%s" % (self.dstTarget.postfix)
# with open(os.path.join(_bootDir, fn), "w") as f:
#     f.write(FmUtil.hashDir(tbsLinuxMediaDir))
