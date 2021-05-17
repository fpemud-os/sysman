#!/usr/bin/python3

import os
import sys
import subprocess

srcDir = os.path.join(sys.argv[1])
kernelVer = sys.argv[2]

fnList = os.listdir(srcDir)
if len(fnList) != 1:
    raise Exception("invalid source directory")
subprocess.run("/bin/tar -xJf %s" % (os.path.join(srcDir, fnList[0])), shell=True)

subprocess.run("/usr/bin/make KERN_VER=%s" % (kernelVer), shell=True)
subprocess.run("/usr/bin/make install KERN_VER=%s" % (kernelVer), shell=True)
