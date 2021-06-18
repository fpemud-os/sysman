#!/usr/bin/python3

import os
import io
import time
import shutil
import tarfile
import robust_layer
import lxml.html
import urllib.request

# parse files
remoteFileList = []
while True:
    baseUrl = "https://wireless.wiki.kernel.org"
    homepageUrl = os.path.join(baseUrl, "en/users/drivers/iwlwifi")
    try:
        resp = urllib.request.urlopen(homepageUrl, timeout=robust_layer.TIMEOUT)
        root = lxml.html.parse(resp)
        for aTag in root.xpath(".//table/tr/td/a"):
            relativeUrl = aTag.get("href")
            relativeUrl = relativeUrl[1:] if relativeUrl.startswith("/") else relativeUrl
            remoteFileList.append((aTag.text, os.path.join(baseUrl, relativeUrl)))
        break
    except BaseException as e:                                          # FIXME: should replace with urlopen Exception
        print("Failed to acces %s, %s" % (baseUrl, e))
        time.sleep(1.0)

# download and extract files
dirSet = set()
for dn, url in remoteFileList:
    if os.path.exists(dn):
        continue

    print("Downloading and extracting \"%s\"..." % (dn))
    os.mkdir(dn)
    try:
        # download content
        while True:
            try:
                resp = urllib.request.urlopen(url, timeout=robust_layer.TIMEOUT)
                with tarfile.open(fileobj=resp, mode="r:gz") as tarf:
                    tarf.extractall(dn)
                break
            except BaseException as e:                                  # FIXME: should replace with urlopen Exception
                print("Failed to acces %s, %s" % (url, e))
                time.sleep(1.0)

        # create symlinks
        if True:
            flist = os.listdir(dn)
            if len(flist) != 1:
                raise Exception("invalid content for file \"%s\"" % (dn))
            dn2 = os.path.join(dn, flist[0])
            for fn in os.listdir(dn2):
                if fn.endswith(".ucode"):
                    os.symlink(os.path.join(dn2, fn), fn)

        # record directory
        dirSet.add(dn)
    except BaseException:
        shutil.rmtree(dn)
        raise

# remove obselete directories
for dn in os.listdir("."):
    if os.path.isdir(dn) and dn not in dirSet:
        shutil.rmtree(dn)

# remove obselete symlinks (they become broken symlinks after obselete directories are deleted)
for fn in os.listdir("."):
    if not os.path.exists(fn):
        os.unlink(fn)
