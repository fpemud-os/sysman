/*
 * lvm2app.h
 * 
 * Operating LVM volume group and logical volume in initramfs.
 *
 * Copyright 2014-2018 fpemud@sina.com
 *
 * This software may be freely redistributed under the terms of the GNU
 * public license.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
 *
 */

#ifndef __LIB_LVM2APP_H__
#define __LIB_LVM2APP_H__

#ifdef __cplusplus
extern "C" {
#endif

/**
 * This is the base handle that is needed to open and create objects such as
 * volume groups and logical volumes.  In addition, this handle provides a
 * context for error handling information, saving any error number (see
 * lvm_errno()) and error message (see lvm_errmsg()) that any function may
 * generate.
 */
typedef void* lvm_t;

/**
 * This handle represents a read-only volume group object.
 */
typedef void* vg_t;

/**
 * This handle represents a logical volume object, which is also
 * read-only, same as vg_t.
 */
typedef void* lv_t;

/**
 * Create a LVM handle.
 *
 * Once all LVM operations have been completed, use lvm_quit() to release
 * the handle and any associated resources.
 *
 * \return
 * A valid LVM handle is returned or NULL if there has been a
 * memory allocation problem. You have to check if an error occured
 * with the lvm_errno() or lvm_errmsg() function.
 */
lvm_t lvm_init();

/**
 * Destroy a LVM handle allocated with lvm_init().
 *
 * This function should be used after all LVM operations are complete or after
 * an unrecoverable error.  Destroying the LVM handle frees the memory and
 * other resources associated with the handle.  Once destroyed, the handle
 * cannot be used subsequently.
 *
 * \param   libh
 * Handle obtained from lvm_init().
 */
void lvm_quit(lvm_t libh);

/**
 * Return stored error no describing last LVM API error.
 *
 * Users of liblvm should use lvm_errno to determine the details of a any
 * failure of the last call.  A basic success or fail is always returned by
 * every function, either by returning a 0 or -1, or a non-NULL / NULL.
 * If a function has failed, lvm_errno may be used to get a more specific
 * error code describing the failure.  In this way, lvm_errno may be used
 * after every function call, even after a 'get' function call that simply
 * returns a value.
 *
 * \param   libh
 * Handle obtained from lvm_init().
 *
 * \return
 * An errno value describing the last LVM error.
 */
int lvm_errno(lvm_t libh);

/**
 * Return stored error message describing last LVM error.
 *
 * This function may be used in conjunction with lvm_errno() to obtain more
 * specific error information for a function that is known to have failed.
 *
 * \param   libh
 * Handle obtained from lvm_init().
 *
 * \return
 * An error string describing the last LVM error.
 */
const char *lvm_errmsg(lvm_t libh);

/**
 * Scan all devices on the system for VGs and LVM metadata.
 *
 * \return
 * 0 (success) or -1 (failure).
 */
int lvm_scan(lvm_t libh);

/**
 * Open an existing VG.
 *
 * Open a VG for reading or writing.
 *
 * \param   libh
 * Handle obtained from lvm_init().
 *
 * \param   vgname
 * Name of the VG to open.
 *
 * \return  non-NULL VG handle (success) or NULL (failure).
 */
vg_t lvm_vg_open(lvm_t libh, const char *vgname);

/**
 * Close a VG opened with lvm_vg_create() or lvm_vg_open().
 *
 * \memberof vg_t
 *
 * This function releases a VG handle and any resources associated with the
 * handle.
 *
 * \param   vg
 * VG handle obtained from lvm_vg_create() or lvm_vg_open().
 */
void lvm_vg_close(vg_t vg);

/**
 * Lookup an LV handle in a VG by the LV name.
 *
 * \param   vg
 * VG handle obtained from lvm_vg_open().
 *
 * \param   name
 * Name of LV to lookup.
 *
 * \return
 * non-NULL handle to the LV 'name' attached to the VG.
 * NULL is returned if the LV name is not associated with the VG handle.
 */
lv_t lvm_lv_from_name(vg_t vg, const char *name);

/**
 * Activate a logical volume.
 *
 * \param   lv
 * Logical volume handle.
 *
 * \return
 * 0 (success) or -1 (failure).
 */
int lvm_lv_activate(lv_t lv);

/**
 * LVM errno
 */
#define LVM_ERR_OUT_OF_MEMORY        -100
#define LVM_ERR_SYSTEM               -2
#define LVM_ERR_DEVICE_OPEN          -3
#define LVM_ERR_DEVICE_IO            -4
#define LVM_ERR_DATA_AREA            -5
#define LVM_ERR_VG_METADATA          -6
#define LVM_ERR_PV                   -7
#define LVM_ERR_DYNBUF               -8

#ifdef __cplusplus
}
#endif
#endif /* __LIB_LVM2APP_H__ */
