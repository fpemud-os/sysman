#!/usr/bin/python3

import os
import lxml
import time
import shutil
import tarfile
import robust_layer
import urllib.request

# parse files
remoteFileList = []
if True:
    resp = urllib.request.urlopen("https://wireless.wiki.kernel.org/en/users/drivers/iwlwifi", timeout=robust_layer.TIMEOUT)
    root = lxml.html.parse(resp)
    for aTag in root.xpath(".//table/tr/td[3]/a"):
        remoteFileList.append((aTag.text, aTag.href))

# download and extract files
dirSet = set()
for dn, url in remoteFileList:
    if os.path.exists(dn):
        continue

    # create directory and download content
    os.mkdir(dn)
    while True:
        try:
            resp = urllib.request.urlopen(url, timeout=robust_layer.TIMEOUT)
            with tarfile.TarFile(fileobj=resp) as tarf:
                tarf.extractall(dn)
            break
        except BaseException as e:
            print("Failed to acces %s, %s" % (url, e))
            time.sleep(1.0)

    # create symlinks
    for fn in os.listdir(dn):
        if fn.endswith(".ucode"):
            os.symlink(os.path.join(dn, fn), fn)

    # record directory
    dirSet.add(dn)

# remove obselete directories
for dn in os.listdir("."):
    if os.path.isdir(dn) and dn not in dirSet:
        shutil.rmtree(dn)

# remove obselete symlinks (they become broken symlinks after obselete directories are deleted)
for fn in os.listdir("."):
    if not os.path.exists(fn):
        os.unlink(fn)
