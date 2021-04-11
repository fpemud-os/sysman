#!/usr/bin/python3

import os
import sys
import glob
import time
import shutil
import subprocess
import lxml.html
import urllib.request
import robust_layer.wget

url = "https://www.virtualbox.org/wiki/Linux_Downloads"
tmpdir = "./__temp__"
origfile = "./original-file.txt"

# get download url
downloadUrl = None
origFile = None
while True:
    try:
        resp = urllib.request.urlopen(url, timeout=robust_layer.TIMEOUT)
        root = lxml.html.parse(resp)
        for link in root.xpath(".//a"):
            if link.get("href").endswith("_amd64.run"):
                downloadUrl = link.get("href")
                origFile = os.path.basename(downloadUrl)
                break
        break
    except Exception as e:
        print("Failed to acces %s, %s" % (url, e))
        time.sleep(1.0)
if downloadUrl is None:
    raise Exception("failed to download VirtualBox driver")

# already downloaded?
if os.path.exists(origfile):
    with open(origfile, "r") as f:
        if f.read() == origFile:
            print("File already downloaded.")
            sys.exit(0)

# download and extract files
subprocess.run("/bin/rm -rf ./*", shell=True)
os.mkdir(tmpdir)
olddir = os.getcwd()
os.chdir(tmpdir)
try:
    runFile = os.path.join(tmpdir, "vbox.run")
    subprocess.run(["/usr/bin/wget", "--show-progress", *robust_layer.wget.additional_param(), "-O", runFile, downloadUrl])
    subprocess.run(["/bin/sh", runFile, "--noexec", "--keep", "--nox11"])
    subprocess.run(["/bin/tar", "-xjf", os.path.join(tmpdir, "install", "VirtualBox.tar.bz2")])

    for fn in glob.glob(os.path.join(tmpdir, "src", "vboxhost", "*")):
        os.rename(fn, ".")

    with open(origfile, "w") as f:
        f.write(origFile)
finally:
    os.chdir(olddir)
    shutil.rmtree(tmpdir)
