#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob

for fn in glob.glob("*.ebuild"):
    with open(fn, "a") as f:
        f.write("""
pkg_extra_files() {
        echo "/usr/bin/corelist"
        echo "/usr/bin/cpan"
        echo "/usr/bin/enc2xs"
        echo "/usr/bin/instmodsh"
        echo "/usr/bin/json_pp"
        echo "/usr/bin/perldoc"
        echo "/usr/bin/piconv"
        echo "/usr/bin/pod2man"
        echo "/usr/bin/pod2text"
        echo "/usr/bin/pod2usage"
        echo "/usr/bin/podchecker"
        echo "/usr/bin/podselect"
        echo "/usr/bin/prove"
        echo "/usr/bin/ptar"
        echo "/usr/bin/ptardiff"
        echo "/usr/bin/ptargrep"
        echo "/usr/bin/shasum"
        echo "/usr/bin/xsubpp"
        echo "/usr/bin/zipdetails"

        echo "/usr/share/man/man1/corelist.1.bz2"
        echo "/usr/share/man/man1/cpan.1.bz2"
        echo "/usr/share/man/man1/enc2xs.1.bz2"
        echo "/usr/share/man/man1/instmodsh.1.bz2"
        echo "/usr/share/man/man1/json_pp.1.bz2"
        echo "/usr/share/man/man1/perldoc.1.bz2"
        echo "/usr/share/man/man1/perlpodstyle.1.bz2"
        echo "/usr/share/man/man1/piconv.1.bz2"
        echo "/usr/share/man/man1/pod2man.1.bz2"
        echo "/usr/share/man/man1/pod2text.1.bz2"
        echo "/usr/share/man/man1/pod2usage.1.bz2"
        echo "/usr/share/man/man1/podchecker.1.bz2"
        echo "/usr/share/man/man1/podselect.1.bz2"
        echo "/usr/share/man/man1/prove.1.bz2"
        echo "/usr/share/man/man1/ptar.1.bz2"
        echo "/usr/share/man/man1/ptardiff.1.bz2"
        echo "/usr/share/man/man1/ptargrep.1.bz2"
        echo "/usr/share/man/man1/shasum.1.bz2"
        echo "/usr/share/man/man1/xsubpp.1.bz2"
        echo "/usr/share/man/man1/zipdetails.1.bz2"
}
""")
