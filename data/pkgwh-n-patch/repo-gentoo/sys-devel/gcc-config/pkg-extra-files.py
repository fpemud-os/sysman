#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/env.d/04gcc-${CHOST}"
        echo "/etc/env.d/gcc/config-${CHOST}"

        echo "/etc/ld.so.conf.d/05gcc-${CHOST}.conf"

        echo "/usr/bin/cc"
        echo "/usr/bin/c++"
        echo "/usr/bin/cpp"
        echo "/usr/bin/g++"
        echo "/usr/bin/gcc"
        echo "/usr/bin/gcc-ar"
        echo "/usr/bin/gcc-nm"
        echo "/usr/bin/gcc-ranlib"
        echo "/usr/bin/gcov"
        echo "/usr/bin/gcov-dump"
        echo "/usr/bin/gcov-tool"
        echo "/usr/bin/gfortran"
        echo "/usr/bin/gkeytool"
        echo "/usr/bin/gorbd"
        echo "/usr/bin/grmic"
        echo "/usr/bin/grmid"
        echo "/usr/bin/grmiregistry"
        echo "/usr/bin/gserialver"
        echo "/usr/bin/gtnameserv"

        echo "/usr/bin/${CHOST}-c++"
        echo "/usr/bin/${CHOST}-cpp"
        echo "/usr/bin/${CHOST}-g++"
        echo "/usr/bin/${CHOST}-gcc"
        echo "/usr/bin/${CHOST}-gcc-ar"
        echo "/usr/bin/${CHOST}-gcc-nm"
        echo "/usr/bin/${CHOST}-gcc-ranlib"
        echo "/usr/bin/${CHOST}-gcov"
        echo "/usr/bin/${CHOST}-gcov-dump"
        echo "/usr/bin/${CHOST}-gcov-tool"
        echo "/usr/bin/${CHOST}-gfortran"
        echo "/usr/bin/${CHOST}-gkeytool"
        echo "/usr/bin/${CHOST}-gorbd"
        echo "/usr/bin/${CHOST}-grmic"
        echo "/usr/bin/${CHOST}-grmid"
        echo "/usr/bin/${CHOST}-grmiregistry"
        echo "/usr/bin/${CHOST}-gserialver"
        echo "/usr/bin/${CHOST}-gtnameserv"

        echo "/usr/${CHOST}/binutils-bin/lib"
        echo "/usr/${CHOST}/binutils-bin/lib/bfd-plugins"
        echo "/usr/${CHOST}/binutils-bin/lib/bfd-plugins/liblto_plugin.so"
}
""")
