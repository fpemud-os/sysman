#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import re
import requests
from fm_util import FmUtil
from fm_util import AvahiServiceBrowser
from fm_param import FmConst


class DynCfgModifier:

    def updateMirrors(self):
        # local mirrors
        localGentooMirror = ""
        localRsyncMirror = ""
        localKernelMirror = ""
        localArchMirror = ""
        localPortageMirrorDict = dict()
        if True:
            gentooMirrors = []
            rsyncMirrors = []
            kernelMirrors = []
            archMirrors = []

            browser = AvahiServiceBrowser("_mirrors._tcp")
            browser.run()
            for name, addr, port in browser.get_result_list():
                for key, value in requests.get("http://%s:%d/api/mirrors" % (addr, port)).json().items():
                    if not value.get("available", False):
                        continue

                    if key == "gentoo":
                        if "http" in value["interface-file"]:
                            s = value["interface-file"]["http"]["url"]
                            s = s.replace("{IP}", addr)
                            gentooMirrors.append(s)
                        elif "ftp" in value["interface-file"]:
                            s = value["interface-file"]["ftp"]["url"]
                            s = s.replace("{IP}", addr)
                            gentooMirrors.append(s)

                    if key == "gentoo-portage":
                        if "rsync" in value["interface-file"]:
                            s = value["interface-file"]["rsync"]["url"]
                            s = s.replace("{IP}", addr)
                            rsyncMirrors.append(s)

                    if key == "kernel":
                        if "http" in value["interface-file"]:
                            s = value["interface-file"]["http"]["url"]
                            s = s.replace("{IP}", addr)
                            kernelMirrors.append(s)
                        elif "ftp" in value["interface-file"]:
                            s = value["interface-file"]["ftp"]["url"]
                            s = s.replace("{IP}", addr)
                            kernelMirrors.append(s)

                    if key == "archlinux":
                        if "http" in value["interface-file"]:
                            s = value["interface-file"]["http"]["url"]
                            s = s.replace("{IP}", addr)
                            archMirrors.append(s)

                    if "interface-file" in value:
                        if "http" in value["interface-file"]:
                            s = value["interface-file"]["http"]["url"]
                            s = s.replace("{IP}", addr)
                            if key not in localPortageMirrorDict:
                                localPortageMirrorDict[key] = []
                            localPortageMirrorDict[key].append(s)
                        elif "ftp" in value["interface-file"]:
                            s = value["interface-file"]["ftp"]["url"]
                            s = s.replace("{IP}", addr)
                            if key not in localPortageMirrorDict:
                                localPortageMirrorDict[key] = []
                            localPortageMirrorDict[key].append(s)

            localGentooMirror = " ".join(gentooMirrors)
            localRsyncMirror = " ".join(rsyncMirrors)
            localKernelMirror = " ".join(kernelMirrors)
            localArchMirror = " ".join(archMirrors)

        # regional public mirrors
        gentooMirrors = []
        rsyncMirrors = []
        kernelMirrors = []
        archMirrors = []
        if True:
            countryCode, countryName = FmUtil.geoGetCountry()
            # gentooMirrors = FmUtil.pmdbGetMirrors("gentoo", "gentoo", countryCode, ["http", "https", "ftp"], 2)
            # rsyncMirrors = FmUtil.pmdbGetMirrors("gentoo", "gentoo-portage", countryCode, ["rsync"], 2)
            # kernelMirrors = FmUtil.pmdbGetMirrors("kernel", "kernel", countryCode, ["http", "https", "ftp"], 2)
            # archMirrors = FmUtil.pmdbGetMirrors("archlinux", "archlinux", countryCode, ["http", "https", "ftp"], 2)
            gentooMirrors = ["https://mirrors.tuna.tsinghua.edu.cn/gentoo"]                     # FIXME
            rsyncMirrors = ["rsync://rsync1.cn.gentoo.org/gentoo-portage"]                      # FIXME
            kernelMirrors = ["https://mirrors.tuna.tsinghua.edu.cn/kernel"]                     # FIXME
            archMirrors = ["http://mirror.lzu.edu.cn/archlinux/"]                               # FIXME

        # write to make.conf
        if True:
            FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "LOCAL_GENTOO_MIRRORS", localGentooMirror)
            FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "LOCAL_RSYNC_MIRRORS", localRsyncMirror)
            FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "LOCAL_KERNEL_MIRRORS", localKernelMirror)
            FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "LOCAL_ARCHLINUX_MIRRORS", localArchMirror)

            FmUtil.updateMakeConfVarAsValueSet(FmConst.portageCfgMakeConf, "REGIONAL_GENTOO_MIRRORS", gentooMirrors)
            FmUtil.updateMakeConfVarAsValueSet(FmConst.portageCfgMakeConf, "REGIONAL_RSYNC_MIRRORS", rsyncMirrors)
            FmUtil.updateMakeConfVarAsValueSet(FmConst.portageCfgMakeConf, "REGIONAL_KERNEL_MIRRORS", kernelMirrors)
            FmUtil.updateMakeConfVarAsValueSet(FmConst.portageCfgMakeConf, "REGIONAL_ARCHLINUX_MIRRORS", archMirrors)

            FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "GENTOO_MIRRORS", "${LOCAL_GENTOO_MIRRORS} ${REGIONAL_GENTOO_MIRRORS} ${GENTOO_DEFAULT_MIRROR}")
            FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "RSYNC_MIRRORS", "${LOCAL_RSYNC_MIRRORS} ${REGIONAL_RSYNC_MIRRORS} ${RSYNC_DEFAULT_MIRROR}")
            FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "KERNEL_MIRRORS", "${LOCAL_KERNEL_MIRRORS} ${REGIONAL_KERNEL_MIRRORS} ${KERNEL_DEFAULT_MIRROR}")
            FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "ARCHLINUX_MIRRORS", "${LOCAL_ARCHLINUX_MIRRORS} ${REGIONAL_ARCHLINUX_MIRRORS}")

        # write to /etc/portage/mirrors
        if len(localPortageMirrorDict) > 0:
            with open(FmConst.portageMirrorsFile, "w") as f:
                for name, mlist in localPortageMirrorDict.items():
                    f.write(name + "\t" + " ".join(mlist) + "\n")
        else:
            FmUtil.forceDelete(FmConst.portageMirrorsFile)

    def updateDownloadCommand(self):
        fetchCmd = "/usr/bin/wget " + FmUtil.wgetCommonDownloadParam() + " -O \\\"\\${DISTDIR}/\\${FILE}\\\" \\\"\\${URI}\\\""
        resumeCmd = "/usr/bin/wget -c " + FmUtil.wgetCommonDownloadParam() + " -O \\\"\\${DISTDIR}/\\${FILE}\\\" \\\"\\${URI}\\\""
        FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "FETCHCOMMAND", fetchCmd)
        FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "RESUMECOMMAND", resumeCmd)

    def updateParallelism(self, hwInfo):
        # gather system information
        cpuNum = hwInfo.hwDict["cpu"]["cores"]
        memSize = hwInfo.hwDict["memory"]["size"]
        bFanless = ("fan" not in hwInfo.hwDict)
        bHugeMemory = (memSize >= 24)

        # determine parallelism parameters
        if bFanless:
            jobcountMake = 1
            jobcountEmerge = 1
            loadavg = 1
        else:
            if bHugeMemory:
                jobcountMake = cpuNum + 2
                jobcountEmerge = cpuNum
                loadavg = cpuNum
            else:
                jobcountMake = cpuNum
                jobcountEmerge = cpuNum
                loadavg = max(1, cpuNum - 1)

        # check/fix MAKEOPTS variable
        # for bug 559064 and 592660, we need to add -j and -l, it sucks
        value = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS")
        if True:
            m = re.search("\\B--jobs(=([0-9]+))?\\b", value)
            if m is None:
                value += " --jobs=%d" % (jobcountMake)
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS", value.lstrip())
            elif m.group(2) is None or int(m.group(2)) != jobcountMake:
                value = value.replace(m.group(0), "--jobs=%d" % (jobcountMake))
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS", value.lstrip())
        value = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS")
        if True:
            m = re.search("\\B--load-average(=([0-9\\.]+))?\\b", value)
            if m is None:
                value += " --load-average=%d" % (loadavg)
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS", value.lstrip())
            elif m.group(2) is None or int(m.group(2)) != loadavg:
                value = value.replace(m.group(0), "--load-average=%d" % (loadavg))
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS", value.lstrip())
        value = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS")
        if True:
            m = re.search("\\B-j([0-9]+)?\\b", value)
            if m is None:
                value += " -j%d" % (jobcountMake)
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS", value.lstrip())
            elif m.group(1) is None or int(m.group(1)) != jobcountMake:
                value = value.replace(m.group(0), "-j%d" % (jobcountMake))
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS", value.lstrip())
        value = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS")
        if True:
            m = re.search("\\B-l([0-9]+)?\\b", value)
            if m is None:
                value += " -l%d" % (loadavg)
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS", value.lstrip())
            elif m.group(1) is None or int(m.group(1)) != loadavg:
                value = value.replace(m.group(0), "-l%d" % (loadavg))
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "MAKEOPTS", value.lstrip())

        # check/fix EMERGE_DEFAULT_OPTS variable
        value = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS")
        if True:
            m = re.search("\\B--jobs(=([0-9]+))?\\b", value)
            if m is None:
                value += " --jobs=%d" % (jobcountEmerge)
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS", value.lstrip())
            elif m.group(2) is None or int(m.group(2)) != jobcountEmerge:
                value = value.replace(m.group(0), "--jobs=%d" % (jobcountEmerge))
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS", value.lstrip())
        value = FmUtil.getMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS")
        if True:
            m = re.search("\\B--load-average(=([0-9\\.]+))?\\b", value)
            if m is None:
                value += " --load-average=%d" % (loadavg)
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS", value.lstrip())
            elif m.group(2) is None or int(m.group(2)) != loadavg:
                value = value.replace(m.group(0), "--load-average=%d" % (loadavg))
                FmUtil.setMakeConfVar(FmConst.portageCfgMakeConf, "EMERGE_DEFAULT_OPTS", value.lstrip())
