#!/usr/bin/python3

import os
import sys
import subprocess

srcDir = os.path.join(sys.argv[1])
kernelVer = sys.argv[2]

fnList = os.listdir(srcDir)
if len(fnList) != 1:
    raise Exception("invalid source directory")
fullfn = os.path.join(srcDir, fnList[0])

subprocess.run("/bin/tar -xJf %s" % (fullfn), shell=True)
subprocess.run("/usr/bin/make KERNELRELEASE=%s" % (kernelVer), shell=True)
subprocess.run("/usr/bin/make install KERNELRELEASE=%s" % (kernelVer), shell=True)






#!/usr/bin/python3

# import os
# import sys
# import subprocess

# srcDir = sys.argv[1]
# buildTmpDir = sys.argv[2]
# kerelVer = sys.argv[3]

# os.chdir(buildTmpDir)
# subprocess.run("/bin/cp -r %s/* %s" % (srcDir, buildTmpDir), shell=True)
# subprocess.run("/usr/bin/make KERN_DIR=\"%s\"" % (os.path.join("/lib/modules", kerelVer, "build")), shell=True)




