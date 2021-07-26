#!/usr/bin/python3

import os
import re
import time
import shutil
import tarfile
import robust_layer
import robust_layer.simple_fops
import lxml.html
import urllib.request

url = "http://www.tbsdtv.com/download/document/tbs6981/tbs6981-windows-driver_v2.0.1.6.zip"

print("Downloading and extracting \"%s\"..." % (url))
try:
    # download content
    while True:
        try:
            resp = urllib.request.urlopen(url, timeout=robust_layer.TIMEOUT)



            with zipfile.ZipFile(fileobj=resp, mode="r") as zipf:
                zipf.extractall(dn)
            break
        except OSError as e:
            print("Failed to acces %s, %s" % (url, e))
            time.sleep(1.0)

    # record directory
    dirSet.add(dn)
except BaseException:
    shutil.rmtree(dn)
    raise
