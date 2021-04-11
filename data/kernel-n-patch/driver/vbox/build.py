#!/usr/bin/python3

import os
import sys
import subprocess

srcDir = sys.argv[1]
buildTmpDir = sys.argv[2]
kerelVer = sys.argv[3]

os.chdir(buildTmpDir)
subprocess.run("/bin/cp -r %s/* %s" % (srcDir, buildTmpDir), shell=True)
subprocess.run("/usr/bin/make KERN_DIR=\"%s\"" % (os.path.join("/lib/modules", kerelVer, "build")), shell=True)
