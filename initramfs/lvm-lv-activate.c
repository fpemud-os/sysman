/*
 * lvm-lv-activate.c
 * 
 * Simple code to activate a specified LVM2 logical volume.
 *
 * Copyright 2014-2014 fpemud@sina.com
 *
 * This software may be freely redistributed under the terms of the GNU
 * public license.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
 *
 */

#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <glob.h>
#include <errno.h>
#include "lvm2app.h"

int main(int argc, char **argv) {
    char *vgname;
    char *lvname;
    lvm_t lh;
    vg_t vg;
    lv_t lv;
    int rc;

    if (argc < 3) {
        fprintf(stderr, "lvm-lv-activate: too few arguments\n");
        return 1;
    }
    vgname = argv[1];
    lvname = argv[2];

    lh = lvm_init(NULL);
    if (lh == NULL) {
        fprintf(stderr, "lvm-lv-activate: failed to initialize LVM\n");
        return 1;
    }

    if (lvm_scan(lh) != 0) {
        fprintf(stderr, "lvm-lv-activate: failed to scan volume groups, %s\n", lvm_errmsg(lh));
        lvm_quit(lh);
        return 1;
    }

    vg = lvm_vg_open(lh, vgname);
    if (vg == NULL) {
        fprintf(stderr, "lvm-lv-activate: failed to open volume group %s, %s\n", vgname, lvm_errmsg(lh));
        lvm_quit(lh);
        return 1;
    }

    lv = lvm_lv_from_name(vg, lvname);
    if (lv == NULL) {
        fprintf(stderr, "lvm-lv-activate: failed to open logical volume %s/%s, %s\n", vgname, lvname, lvm_errmsg(lh));
        lvm_quit(lh);
        return 1;
    }

    rc = lvm_lv_activate(lv);
    if (rc != 0) {
        fprintf(stderr, "lvm-lv-activate: failed to activate logical volume %s/%s, %s\n", vgname, lvname, lvm_errmsg(lh));
        lvm_quit(lh);
        return 1;
    }

    lvm_quit(lh);
    return 0;
}
