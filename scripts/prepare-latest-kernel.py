#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import io
import sys
import gzip
import shutil
import subprocess
import lxml.html
import urllib.request


def findKernelVersion(url, typename):
    with urllib.request.urlopen(url, timeout=60) as resp:
        if resp.info().get('Content-Encoding') is None:
            fakef = resp
        elif resp.info().get('Content-Encoding') == 'gzip':
            fakef = io.BytesIO(resp.read())
            fakef = gzip.GzipFile(fileobj=fakef)
        else:
            assert False
        root = lxml.html.parse(fakef)

        td = root.xpath(".//td[text()='%s:']" % (typename))[0]
        td = td.getnext()
        while len(td) > 0:
            td = td[0]
        return td.text


def download(url, version, kernelFile):
    subdir = None
    for i in range(3, 9):
        if version.startswith(str(i)):
            subdir = "v%d.x" % (i)
    assert subdir is not None

    urlKernelFile = os.path.join(subdir, kernelFile)
    subprocess.run(["wget", "%s/pub/linux/kernel/%s" % (url, urlKernelFile)])


if __name__ == "__main__":
    ktype = "stable"
    if len(sys.argv) > 1:
        assert sys.argv[1] in ["stable", "mainline", "longterm"]
        ktype = sys.argv[1]

    url = "https://www.kernel.org"
    version = findKernelVersion(url, ktype)

    kernelFile = "linux-%s.tar.xz" % (version)
    fullKernelFile = os.path.join("/var/cache/portage/kcache", kernelFile)
    if os.path.exists(fullKernelFile):
        shutil.copy(fullKernelFile, kernelFile)
    else:
        download(url, version, kernelFile)
    subprocess.run(["tar", "-xJf", kernelFile])
