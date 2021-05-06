#!/usr/bin/python3

import os
import sys
import subprocess

srcDir = sys.argv[1]
kernelVer = sys.argv[2]

subprocess.run("/bin/cp -r %s/* ." % (srcDir), shell=True)
subprocess.run("/usr/bin/make KERNELRELEASE=%s" % (kernelVer), shell=True)
subprocess.run("/usr/bin/make install KERNELRELEASE=%s" % (kernelVer), shell=True)
