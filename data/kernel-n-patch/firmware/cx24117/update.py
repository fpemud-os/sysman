#!/usr/bin/python3

import time
import zipfile
import robust_layer
import robust_layer.simple_fops
import urllib.request

url = "http://www.tbsdtv.com/download/document/tbs6981/tbs6981-windows-driver_v2.0.1.6.zip"
targetFn = "dvb-fe-cx24117.fw"

print("Downloading and extracting \"%s\"..." % (url))
try:
    # download content
    while True:
        try:
            with urllib.request.urlopen(url, timeout=robust_layer.TIMEOUT) as resp:
                buf = None
                with zipfile.ZipFile(resp, mode="r") as zipf:
                    buf = zipf.open("tbs6981_x86/TBS6981.sys").read()
                with open(targetFn, "wb") as f:
                    s = 166120
                    l = 55352
                    f.write(buf[s:s+l])
                # FIXME: chksum targetFn as 96ae79acb8e51d90c90fa9759a1ce9df
            break
        except OSError as e:
            print("Failed to acces %s, %s" % (url, e))
            time.sleep(robust_layer.RETRY_WAIT)
except BaseException:
    robust_layer.simple_fops.rm(targetFn)
    raise
