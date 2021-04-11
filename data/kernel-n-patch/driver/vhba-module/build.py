#!/usr/bin/python3

import os
import sys
import subprocess

srcDir = os.path.join(sys.argv[1], "vhba-module")
buildTmpDir = sys.argv[2]
kernelVer = sys.argv[3]

os.chdir(buildTmpDir)
subprocess.run("/bin/cp -r %s/* %s" % (srcDir, buildTmpDir), shell=True)
subprocess.run("/usr/bin/make KERNELRELEASE=%s" % (kernelVer), shell=True)
subprocess.run("/usr/bin/make install KERNELRELEASE=%s" % (kernelVer), shell=True)
