#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/etc/env.d/05binutils"
        echo "/etc/env.d/binutils/config-${CHOST}"

        echo "/usr/bin/addr2line"
        echo "/usr/bin/ar"
        echo "/usr/bin/as"
        echo "/usr/bin/c++filt"
        echo "/usr/bin/dwp"
        echo "/usr/bin/elfedit"
        echo "/usr/bin/gprof"
        echo "/usr/bin/ld"
        echo "/usr/bin/ld.bfd"
        echo "/usr/bin/ld.gold"
        echo "/usr/bin/nm"
        echo "/usr/bin/objcopy"
        echo "/usr/bin/objdump"
        echo "/usr/bin/ranlib"
        echo "/usr/bin/readelf"
        echo "/usr/bin/size"
        echo "/usr/bin/strings"
        echo "/usr/bin/strip"

        echo "/usr/bin/${CHOST}-addr2line"
        echo "/usr/bin/${CHOST}-ar"
        echo "/usr/bin/${CHOST}-as"
        echo "/usr/bin/${CHOST}-c++filt"
        echo "/usr/bin/${CHOST}-dwp"
        echo "/usr/bin/${CHOST}-elfedit"
        echo "/usr/bin/${CHOST}-gprof"
        echo "/usr/bin/${CHOST}-ld"
        echo "/usr/bin/${CHOST}-ld.bfd"
        echo "/usr/bin/${CHOST}-ld.gold"
        echo "/usr/bin/${CHOST}-nm"
        echo "/usr/bin/${CHOST}-objcopy"
        echo "/usr/bin/${CHOST}-objdump"
        echo "/usr/bin/${CHOST}-ranlib"
        echo "/usr/bin/${CHOST}-readelf"
        echo "/usr/bin/${CHOST}-size"
        echo "/usr/bin/${CHOST}-strings"
        echo "/usr/bin/${CHOST}-strip"

        echo "/usr/${CHOST}/bin/***"
        echo "/usr/${CHOST}/lib/***"
}
""")
