/*
 * lvm2app.c
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

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <sys/sysmacros.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <c-list.h>
#include <c-dynbuf.h>
#include "lvm2app.h"

/*****************************************************************************/
/* Utilities                                                                 */
/*****************************************************************************/

static char *strncpy_with_nil(char *dest, const char *src, size_t n) {
    strncpy(dest, src, n);
    *(dest + n) = '\0';
    return dest;
}

static int align_8(int value) {
    if (value % 8 == 0)
        return value;
    else
        return (value / 8 + 1) * 8;
}

/*****************************************************************************/
/* Physical structures                                                       */
/*****************************************************************************/

#define LABEL_SIZE            512
#define LABEL_SCAN_SECTORS    4

#define LABEL_ID              "LABELONE"
#define LVM2_LABEL            "LVM2 001"

#define ID_LEN                32
#define ID_STRLEN             38        /* Length of ID string, excluding terminating zero. */

#define MDA_HEADER_SIZE       512
#define FMTT_MAGIC            "\040\114\126\115\062\040\170\133\065\101\045\162\060\116\052\076"
#define FMTT_VERSION          1

/* On disk */
struct label_header {
    int8_t id[8];             /* LABELONE */
    u_int64_t sector_xl;      /* Sector number of this label */
    u_int32_t crc_xl;         /* From next field to end of sector */
    u_int32_t offset_xl;      /* Offset from start of struct to contents */
    int8_t type[8];           /* LVM2 001 */
} __attribute__ ((packed));

/* On disk */
struct disk_locn {
    u_int64_t offset;         /* Offset in bytes to start sector */
    u_int64_t size;           /* Bytes */
} __attribute__ ((packed));

/* On disk */
struct pv_header {
    int8_t pv_uuid[ID_LEN];

    /* This size can be overridden if PV belongs to a VG */
    u_int64_t device_size_xl;    /* Bytes */

    /* NULL-terminated list of data areas followed by */
    /* NULL-terminated list of metadata area headers */
    struct disk_locn disk_areas_xl[0];    /* Two lists */
} __attribute__ ((packed));

/* On disk */
struct raw_locn {
    u_int64_t offset;      /* Offset in bytes to start sector */
    u_int64_t size;        /* Bytes */
    u_int32_t checksum;
    u_int32_t flags;
} __attribute__ ((packed));

/* On disk */
struct mda_header {
    u_int32_t checksum_xl;           /* Checksum of rest of mda_header */
    int8_t magic[16];                /* To aid scans for metadata */
    u_int32_t version;
    u_int64_t start;                 /* Absolute start byte of mda_header */
    u_int64_t size;                  /* Size of metadata area */

    struct raw_locn raw_locns[0];    /* NULL-terminated list */
} __attribute__ ((packed));

/*****************************************************************************/
/* Logical structures                                                         */
/*****************************************************************************/

#define CTX_ERRMSG_SIZE 4096

#define MDA_KEY_LEN 127

struct context {
    int err_id;
    char err_msg[CTX_ERRMSG_SIZE];

    char *func;
    CList vgs;
    int control_fd;
};

struct volume_group {
    struct context *ctx;
    CList link;

    char *name;
    char *uuid;
    char *metadata;
    u_int64_t extent_size;
    CList pvs;                        /* physical volumes */
    CList lvs;                        /* logical volumes */
};

struct physical_volume {
    struct volume_group *vg;
    CList link;

    char *name;
    char *uuid;
    int major;
    int minor;
    u_int64_t part_start;
    u_int64_t part_size;
    u_int64_t start_sector;            /* Sector number where the data area starts. */
};

struct logical_volume {
    struct volume_group *vg;
    CList link;

    char *name;
    char *uuid;

    unsigned int segment_count;
    struct lv_segment *segments;

    /* Optional. */
    int number;
    u_int64_t size;
    int visible;
};

struct lv_segment {
    struct logical_volume *lv;
    CList link;

    u_int64_t start_extent;
    u_int64_t extent_count;

    enum {
        LV_SEGMENT_STRIPED = 0,
        LV_SEGMENT_MIRROR = 1,
        LV_SEGMENT_RAID4 = 4,
        LV_SEGMENT_RAID5 = 5,
        LV_SEGMENT_RAID6 = 6,
        LV_SEGMENT_RAID10 = 10,
    } type;
    unsigned int area_count;
    struct lv_segment_area *areas;

    unsigned int stripe_size;
};

struct lv_segment_area {
    int type;                /* 0 - unknown, 1 - map_to_pv, 2 - map_to_lv */
    union {
        struct {
            struct physical_volume *pv;
            u_int64_t start_extent;
        } map_to_pv;
        struct {
            struct logical_volume *lv;
            u_int64_t start_extent;
        } map_to_lv;
    };
};

struct mda_kv {
    char key[MDA_KEY_LEN + 1];
    struct {
        int type;                /* 0 - unknown, 1 - num, 2 - str */
        union {
            u_int64_t num;
            char *str;
        };
    } value;
};

struct mda_kv_array {
    char key[MDA_KEY_LEN + 1];
    unsigned int value_count;
    struct {
        int type;                /* 0 - unknown, 1 - num, 2 - str */
        union {
            u_int64_t num;
            char *str;
        };
    } values[0];
};

struct mda_block {
    CList link;
    char key[MDA_KEY_LEN + 1];
    char *content;
};

/*****************************************************************************/
/* Utility operations                                                        */
/*****************************************************************************/

#define FAILURE(ctx, arg_err_id, arg_err_msg, ...) \
    do { \
        ctx->err_id = arg_err_id; \
        snprintf(ctx->err_msg, CTX_ERRMSG_SIZE, arg_err_msg, ##__VA_ARGS__); \
        goto failure; \
    } while(0)

#define FAILURE_ON_ERROR(ctx) \
    do { \
        if (ctx->err_id != 0) { \
            goto failure; \
        } \
    } while(0)

#define FAILURE_ON_CONDITION(ctx, cond, arg_err_id, arg_err_msg, ...) \
    do { \
        if (cond) { \
            ctx->err_id = arg_err_id; \
            snprintf(ctx->err_msg, CTX_ERRMSG_SIZE, arg_err_msg, ##__VA_ARGS__); \
            goto failure; \
        } \
    } while(0)

#define FAILURE_ON_MALLOC(ctx, var) \
    FAILURE_ON_CONDITION(ctx, var == NULL, LVM_ERR_OUT_OF_MEMORY, "Out of memory")

#define FAILURE_ON_DYNBUF_ERROR(ctx, var) \
    do { \
        FAILURE_ON_CONDITION(ctx, var == -ENOMEM, LVM_ERR_DYNBUF, "Out of memory"); \
        FAILURE_ON_CONDITION(ctx, var < 0, LVM_ERR_DYNBUF, "Error %d when operating dynamic buffer", r); \
    } while(0)

#define CLEAR_ERROR(ctx, arg_err_id) \
    do { \
        if (ctx->err_id == arg_err_id) { \
            ctx->err_id = 0; \
            ctx->err_msg[0] = '\0'; \
        } \
    } while(0)

/*****************************************************************************/
/* Block device iteration                                                     */
/*****************************************************************************/

struct blkdev_iter {
    DIR *d;
    int major;
    int minor;
};

static struct blkdev_iter *_blkdev_iter_new(struct context *ctx) {
    const char *path = "/sys/dev/block";
    struct blkdev_iter *iter = NULL;

    iter = (struct blkdev_iter *)malloc(sizeof(*iter));
    FAILURE_ON_MALLOC(ctx, iter);

    iter->d = opendir(path);
    FAILURE_ON_CONDITION(ctx, iter->d == NULL, LVM_ERR_SYSTEM, "Failed to open directory %s.", path);
    iter->major = -1;
    iter->minor = -1;

    return iter;

failure:
    if (iter != NULL && iter->d != NULL) closedir(iter->d);
    if (iter != NULL) free(iter);
    return NULL;
}

static void *_blkdev_iter_next(struct context *ctx, struct blkdev_iter *iter) {
    const char *path = "/sys/dev/block";
    struct dirent *dirent = NULL;
    int r;

    errno = 0;
    if (!(dirent = readdir(iter->d))) {
        FAILURE_ON_CONDITION(ctx, errno != 0, LVM_ERR_SYSTEM, "Failed to open directory %s.", path);
        free(iter);
        return NULL;        /* iteration is over */
    }

    if (strcmp(".", dirent->d_name) == 0 || strcmp("..", dirent->d_name) == 0) {
        return _blkdev_iter_next(ctx, iter);
    }

    r = sscanf(dirent->d_name, "%d:%d", &iter->major, &iter->minor);
    FAILURE_ON_CONDITION(ctx, r != 2, LVM_ERR_SYSTEM, "Invalid file %s in directory %s.", dirent->d_name, path);

    return iter;

failure:
    if (iter != NULL && iter->d != NULL) closedir(iter->d);
    if (iter != NULL) free(iter);
    return NULL;
}

static void _blkdev_iter_free(struct context *ctx, struct blkdev_iter *iter) {
    if (iter->d != NULL) closedir(iter->d);
    free(iter);
}

/*****************************************************************************/
/* Block device I/O                                                          */
/*****************************************************************************/

static int _blkdev_open(struct context *ctx, int major, int minor) {
    const char *path = "/dev";
    DIR *d = NULL;
    struct dirent *dirent;

    d = opendir(path);
    FAILURE_ON_CONDITION(ctx, d == NULL, LVM_ERR_SYSTEM, "Failed to open directory %s.", path);

    while ((dirent = readdir(d))) {
        char fpath[PATH_MAX];
        struct stat sb;
        int r;

        r = snprintf(fpath, sizeof(fpath), "%s/%s", path, dirent->d_name);
        FAILURE_ON_CONDITION(ctx, r < 0, LVM_ERR_SYSTEM, "snprintf() failed for %s/%s.", path, dirent->d_name);

        r = lstat(fpath, &sb);
        FAILURE_ON_CONDITION(ctx, r != 0, LVM_ERR_SYSTEM, "lstat() failed for %s.", fpath);

        if ((sb.st_mode & S_IFMT) != S_IFBLK)
            continue;
        if (sb.st_rdev != makedev(major, minor))
            continue;

        r = open(fpath, O_RDONLY);
        FAILURE_ON_CONDITION(ctx, r == -1, LVM_ERR_DEVICE_OPEN, "Failed to open %s.", fpath);

        closedir(d);
        return r;
    }

    FAILURE(ctx, LVM_ERR_SYSTEM, "No device node for %d:%d.", major, minor);

failure:
    if (d != NULL) closedir(d);
    return -1;
}

/*****************************************************************************/
/* Volume Group Metadata Operation                                                         */
/*****************************************************************************/

static u_int64_t _mda_get_num(struct context *ctx, const char *p, const char *key, const char *key_description, char **endptr) {
    char realkey[MDA_KEY_LEN + 3 + 1];
    char *p2, *p3;
    u_int64_t ret;

    FAILURE_ON_CONDITION(ctx, strlen(key) > MDA_KEY_LEN, -1, "Key too long.");

    strcpy(realkey, key);
    strcat(realkey, " = ");
    p2 = strstr(p, realkey);
    FAILURE_ON_CONDITION(ctx, p2 == NULL, LVM_ERR_VG_METADATA, "Couldn't find %s.", key_description);

    p2 += strlen(realkey);
    ret = strtoull(p2, &p3, 10);
    FAILURE_ON_ERROR(ctx);
    FAILURE_ON_CONDITION(ctx, p3 == p2, LVM_ERR_VG_METADATA, "%s is not a number.", key_description);

    if (endptr != NULL) *endptr = p3;
    return ret;

failure:
    return 0;
}

/* Returns a malloced string */
static char *_mda_get_str(struct context *ctx, const char *p, const char *key, const char *key_description, char **endptr) {
    char realkey[MDA_KEY_LEN + 3 + 1];
    char *p2, *p3;
    char *ret = NULL;

    FAILURE_ON_CONDITION(ctx, strlen(key) > MDA_KEY_LEN, -1, "Key too long.");

    strcpy(realkey, key);
    strcat(realkey, " = ");
    p2 = strstr(p, realkey);
    FAILURE_ON_CONDITION(ctx, p2 == NULL, LVM_ERR_VG_METADATA, "Couldn't find %s.", key_description);

    p2 += strlen(realkey);
    FAILURE_ON_CONDITION(ctx, *p2 != '"', LVM_ERR_VG_METADATA, "%s is not a string.", key_description);

    p3 = strstr(p2 + 1, "\"");
    FAILURE_ON_CONDITION(ctx, p3 == NULL, LVM_ERR_VG_METADATA, "Metadata parse error.");

    ret = strndup(p2 + 1, p3 - (p2 + 1));
    FAILURE_ON_MALLOC(ctx, ret);

    if (endptr != NULL) *endptr = p3 + 1;
    return ret;

failure:
    if (ret != NULL) free(ret);
    return NULL;
}

#if 0
/* Returns a malloced structure */
static mda_kv *_mda_get_kv(struct context *ctx, const char *p, const char *key, char **endptr)
{
    char realkey[MDA_KEY_LEN + 3 + 1];
    char *p2, *p3;
    mda_kv *ret = NULL;

    FAILURE_ON_CONDITION(ctx, strlen(key) > MDA_KEY_LEN, -1, "Key too long.");

    strcpy(realkey, key);
    strcat(realkey, " = ");
    p2 = strstr(p, realkey);
    FAILURE_ON_CONDITION(ctx, p2 == NULL, 0, "");

    ret = malloc(sizeof(*ret));
    FAILURE_ON_MALLOC(ctx, ret);
    strcpy(ret->key, key);
    ret->value.type = 0;

    p2 += strlen(realkey);
    if (*p2 == '"')
    {
        p3 = strstr(p2 + 1, "\"");
        FAILURE_ON_CONDITION(ctx, p3 == NULL, -1, "XXXX");

        ret->value.str = strndup(p2 + 1, p3 - (p2 + 1));
        FAILURE_ON_MALLOC(ctx, ret->value.str);
        ret->value.type = 2;

        p3++;
    }
    else
    {
        ret->value.num = strtoull(p2, &p3, 10);
        FAILURE_ON_ERROR(ctx);
        FAILURE_ON_CONDITION(ctx, p3 == p2, -1, "XXXX");
        ret->value.type = 1;
    }

    if (endptr != NULL) *endptr = p3;
    return ret;

failure:
    if (ret != NULL && ret->value.type == 2) free(ret->value.str);
    if (ret != NULL) free(ret);
    return NULL;
}
#endif

/* Returns a malloced structure */
static struct mda_kv_array *_mda_get_kv_array(struct context *ctx, const char *p, const char *key, char **endptr) {
    char realkey[MDA_KEY_LEN + 4 + 1];
    char value_count = 0;
    char *tmpbuf = NULL;
    char *p2, *p3, *p4;
    int i;
    struct mda_kv_array *ret = NULL;

    FAILURE_ON_CONDITION(ctx, strlen(key) > MDA_KEY_LEN, -1, "Key too long.");

    strcpy(realkey, key);
    strcat(realkey, " = [");
    p2 = strstr(p, realkey);
    FAILURE_ON_CONDITION(ctx, p2 == NULL, 0, "");

    p2 += strlen(realkey);

    /* allocate temporary buffer which store data with all spaces removed and keeps ']' */
    p3 = p2;
    while (*p3 != ']') {
        FAILURE_ON_CONDITION(ctx, *p3 == '\0', LVM_ERR_VG_METADATA, "Can not find right square bracket");
        p3++;
    }

    tmpbuf = malloc(p3 - p2);
    FAILURE_ON_MALLOC(ctx, tmpbuf);

    p4 = tmpbuf;
    while (*p2 != ']') {
        if (*p2 != ' ' && *p2 != '\t' && *p2 != '\n') *p4++ = *p2++;
        else p2++;
    }
    *p4 = *p2;

    /* calculate how many values using ',' as seperator */
    p4 = tmpbuf;
    while (*p4 != ']') {
        if (*p4 == ',') value_count++;
        p4++;
    }
    if (value_count > 0) value_count++;

    /* malloc and initialize kv_array as return value */
    ret = malloc(sizeof(*ret) + value_count * sizeof(*ret->values));
    FAILURE_ON_MALLOC(ctx, ret);
    strcpy(ret->key, key);
    ret->value_count = value_count;
    for (i = 0; i < ret->value_count; i++)
        ret->values[i].type = 0;

    for (p4 = p2 = tmpbuf, i = 0; ; p4++) {
        if (*p4 == ',' || *p4 == ']') {
            if (*p2 == '"' && *(p4 - 1) == '"') {
                ret->values[i].str = strndup(p2 + 1, (p4 - 1) - (p2 + 1));
                FAILURE_ON_MALLOC(ctx, ret->values[i].str);
                ret->values[i].type = 2;
            }
            else {
                char *t;
                ret->values[i].num = strtoull(p2, &t, 10);
                FAILURE_ON_ERROR(ctx);
                FAILURE_ON_CONDITION(ctx, t != p4, LVM_ERR_VG_METADATA, "Invalid number value");
                ret->values[i].type = 1;
            }
            i++;
            p2 = p4 + 1;
        }
        if (*p4 == ']') {
            break;
        }
    };

    if (endptr != NULL) *endptr = p3;
    return ret;

failure:
    if (tmpbuf != NULL) free(tmpbuf);
    if (ret != NULL && ret->value_count > 0)
        for (i = 0; i < ret->value_count; i++)
            if (ret->values[i].type == 2)
                free (ret->values[i].str);
    if (ret != NULL) free(ret);
    return NULL;
}

/* Returns a malloced object */
static struct mda_block *_mda_get_block(struct context *ctx, const char *p, const char *key, char **endptr) {
    char realkey[MDA_KEY_LEN + 2 + 1];
    char *p2, *p3;
    int left_brace_count;
    struct mda_block *ret = NULL;

    FAILURE_ON_CONDITION(ctx, strlen(key) > MDA_KEY_LEN, -1, "Key too long.");

    strcpy(realkey, key);
    strcat(realkey, " {");
    p2 = strstr(p, realkey);
    FAILURE_ON_CONDITION(ctx, p2 == NULL, 0, "");

    ret = malloc(sizeof(*ret));
    FAILURE_ON_MALLOC(ctx, ret);
    c_list_init(&ret->link);
    strcpy(ret->key, key);
    ret->content = NULL;

    p2 += strlen(realkey);

    for (p3 = p2, left_brace_count = 0; ; p3++) {
        FAILURE_ON_CONDITION(ctx, *p3 == '\0', LVM_ERR_VG_METADATA, "Can not find right brace");
        if (*p3 == '{') {
            left_brace_count++;
        }
        else if (*p3 == '}') {
            if (left_brace_count == 0)
                break;
            left_brace_count--;
        }
    }
    ret->content = strndup(p2, p3 - p2);
    FAILURE_ON_MALLOC(ctx, ret->content);

    if (endptr != NULL) *endptr = p3 + 1;
    return ret;

failure:
    if (ret != NULL && ret->content != NULL) free(ret->content);
    if (ret != NULL) free(ret);
    return NULL;
}

static CList *_mda_get_blocks(struct context *ctx, const char *p, char **endptr) {
    struct mda_block *block = NULL;
    CList *ret = NULL;

    ret = malloc(sizeof(*ret));
    FAILURE_ON_MALLOC(ctx, ret);
    c_list_init(ret);

    while (1) {
        const char *p2, *p3;
        int left_brace_count;

        while (isspace (*p))
            p++;
        if (*p == '\0')
            break;

        block = malloc(sizeof(*block));
        FAILURE_ON_MALLOC(ctx, block);
        c_list_init(&block->link);
        block->content = NULL;

        p2 = p;
        while (*p2 != ' ') {
            FAILURE_ON_CONDITION(ctx, *p2 == '\0', -1, "XXXX");
            p2++;
        }
        FAILURE_ON_CONDITION(ctx, p2 - p > MDA_KEY_LEN, LVM_ERR_VG_METADATA, "Key too long");
        strncpy_with_nil(block->key, p, p2 - p);

        p2 = strstr(p, "{");
        FAILURE_ON_CONDITION(ctx, p2 == NULL, LVM_ERR_VG_METADATA, "Can not find left brace");
        p2++;

        for (p3 = p2, left_brace_count = 0; ; p3++) {
            FAILURE_ON_CONDITION(ctx, *p3 == '\0', LVM_ERR_VG_METADATA, "Can not find right brace");
            if (*p3 == '{') {
                left_brace_count++;
            }
            else if (*p3 == '}') {
                if (left_brace_count == 0)
                    break;
                left_brace_count--;
            }
        }
        block->content = strndup(p2, p3 - p2);
        FAILURE_ON_MALLOC(ctx, block->content);

        c_list_link_tail(ret, &block->link);
        block = NULL;
        p = p3 + 1;
    }

    return ret;

failure:
    if (block != NULL) {
        if (block->content != NULL) free(block->content);
        free(block);
    }
    if (ret != NULL) {
        struct mda_block *block_iter;
        struct mda_block *block_safe;
        c_list_for_each_entry_safe(block_iter, block_safe, ret, link) {
            if (block_iter->content != NULL) free(block_iter->content);
            free(block_iter);
        }
        free(ret);
    }
    return NULL;
}

static int _mda_check_flag(struct context *ctx, const char *p, const char *str, const char *flag) {
    size_t len_str = strlen(str);
    size_t len_flag = strlen(flag);

    while (1) {
        const char *q;
        p = strstr(p, str);
        if (!p)
            return 0;
        p += len_str;
        if (memcmp(p, " = [", sizeof(" = [") - 1) != 0)
            continue;
        q = p + sizeof(" = [") - 1;
        while (1) {
            while (isspace(*q))
                q++;
            if (*q != '"')
                return 0;
            q++;
            if (memcmp(q, flag, len_flag) == 0 && q[len_flag] == '"')
                return 1;
            while (*q != '"')
                q++;
            q++;
            if (*q == ']')
                return 0;
            q++;
        }
    }
}

/*****************************************************************************/
/* Physical Volume Operation                                                 */
/*****************************************************************************/

struct physical_volume *_find_pv_by_name(struct context *ctx, struct volume_group *vg, const char *pv_name) {
    struct physical_volume *pv;

    c_list_for_each_entry(pv, &vg->pvs, link)
        if (strcmp(pv->name, pv_name) == 0)
            return pv;

    return NULL;
}

struct physical_volume *_find_pv_by_uuid(struct context *ctx, struct volume_group *vg, const char *pv_uuid) {
    struct physical_volume *pv;

    c_list_for_each_entry(pv, &vg->pvs, link)
        if (strcmp(pv->uuid, pv_uuid) == 0)
            return pv;

    return NULL;
}

static struct physical_volume *_new_pv(struct context *ctx, struct volume_group *vg, struct mda_block *pv_block) {
    struct physical_volume *pv = NULL;

    pv = (struct physical_volume *)malloc(sizeof(*pv));
    FAILURE_ON_MALLOC(ctx, pv);
    memset(pv, 0, sizeof(*pv));

    c_list_init(&pv->link);

    pv->name = strdup(pv_block->key);
    FAILURE_ON_MALLOC(ctx, pv->name);

    pv->uuid = _mda_get_str(ctx, pv_block->content, "id", "PV UUID", NULL);
    FAILURE_ON_ERROR(ctx);

    pv->major = -1;
    pv->minor = -1;

    /*    pv->part_start
        pv->part_size */

    pv->start_sector = _mda_get_num(ctx, pv_block->content, "pe_start", "PV PE-Start", NULL);
    FAILURE_ON_ERROR(ctx);

    pv->vg = vg;
    c_list_link_tail(&vg->pvs, &pv->link);
    return pv;

failure:
    if (pv != NULL && pv->uuid != NULL) free(pv->uuid);
    if (pv != NULL && pv->name != NULL) free(pv->name);
    if (pv != NULL) free(pv);
    return NULL;
}

static void _free_pv(struct context *ctx, struct physical_volume *pv) {
    if (pv->uuid != NULL) free(pv->uuid);
    if (pv->name != NULL) free(pv->name);
    free(pv);
}

/*****************************************************************************/
/* Logical Volume Operation                                                     */
/*****************************************************************************/

static struct logical_volume *_find_lv_by_name(struct context *ctx, struct volume_group *vg, const char *lv_name) {
    struct logical_volume *lv;

    c_list_for_each_entry(lv, &vg->lvs, link)
        if (strcmp(lv->name, lv_name) == 0)
            return lv;

    return NULL;
}

static struct logical_volume *_new_lv(struct context *ctx, struct volume_group *vg, struct mda_block *lv_block) {
    struct logical_volume *lv = NULL;
    struct lv_segment *seg = NULL;
    char *seg_type = NULL;
    struct mda_kv_array *rkva = NULL;
    int is_pvmove;
    char *p;
    int i, j;

    lv = (struct logical_volume *)malloc(sizeof(*lv));
    FAILURE_ON_MALLOC(ctx, lv);
    memset(lv, 0, sizeof(*lv));

    lv->name = strdup(lv_block->key);
    FAILURE_ON_MALLOC(ctx, lv->name);

    lv->uuid = _mda_get_str(ctx, lv_block->content, "id", "LV UUID", NULL);
    FAILURE_ON_ERROR(ctx);

    lv->visible = _mda_check_flag(ctx, lv_block->content, "status", "VISIBLE");

    is_pvmove = _mda_check_flag (ctx, lv_block->content, "status", "PVMOVE");

    lv->segment_count = _mda_get_num(ctx, lv_block->content, "segment_count", "Segment Count", NULL);
    FAILURE_ON_ERROR(ctx);

    lv->segments = malloc(sizeof(*seg) * lv->segment_count);
    FAILURE_ON_MALLOC(ctx, lv->segments);
    memset(lv->segments, 0, sizeof(*seg) * lv->segment_count);

    p = lv_block->content;
    lv->size = 0;
    for (i = 0; i < lv->segment_count; i++) {
        seg = lv->segments + i;

        p = strstr(p, "segment");
        FAILURE_ON_CONDITION(ctx, p == NULL, -1, "NOT FOUNDS.");

        seg->start_extent = _mda_get_num(ctx, p, "start_extent", "Start Extent", &p);
        FAILURE_ON_ERROR(ctx);

        seg->extent_count = _mda_get_num(ctx, p, "extent_count", "Extent Count", &p);
        FAILURE_ON_ERROR(ctx);

        lv->size += seg->extent_count * vg->extent_size;

        seg_type = _mda_get_str(ctx, p, "type", "Segment Type", &p);
        FAILURE_ON_ERROR(ctx);
        if (strcmp(seg_type, "striped") == 0) {
            seg->type = LV_SEGMENT_STRIPED;

            seg->area_count = _mda_get_num(ctx, p, "stripe_count", "Stripe-Count", &p);
            FAILURE_ON_ERROR(ctx);
            if (seg->area_count != 1) {
                seg->stripe_size = _mda_get_num(ctx, p, "stripe_size", "Stripe-Size", &p);
            }

            seg->areas = malloc(sizeof(seg->areas[0]) * seg->area_count);
            FAILURE_ON_MALLOC(ctx, seg->areas);
            memset(seg->areas, 0, sizeof(seg->areas[0]) * seg->area_count);

            rkva = _mda_get_kv_array(ctx, p, "stripes", &p);
            FAILURE_ON_ERROR(ctx);
            FAILURE_ON_CONDITION(ctx, rkva->value_count != seg->area_count * 2, -1, "Invalid Stripes");
            for (j = 0; j < seg->area_count; j++) {
                struct lv_segment_area *area = seg->areas + j;
                char *pv_name;
                struct physical_volume *pv = NULL;

                FAILURE_ON_CONDITION(ctx, rkva->values[j * 2].type != 2, -1, "Invalid Stripes");
                FAILURE_ON_CONDITION(ctx, rkva->values[j * 2 + 1].type != 1, -1, "Invalid Stripes");

                pv_name = rkva->values[j * 2].str;
                pv = _find_pv_by_name(ctx, vg, pv_name);
                FAILURE_ON_CONDITION(ctx, pv == NULL, LVM_ERR_VG_METADATA, "PV %s not in VG %s.", pv_name, vg->name);

                area->type = 1;
                area->map_to_pv.pv = pv;
                area->map_to_pv.start_extent = rkva->values[j * 2 + 1].num;
            }
        }
        else if (strcmp(seg_type, "mirror") == 0) {
            seg->type = LV_SEGMENT_MIRROR;

            seg->area_count = _mda_get_num(ctx, p, "mirror_count", "Mirror-Count", &p);
            FAILURE_ON_ERROR(ctx);

            seg->areas = malloc(sizeof(seg->areas[0]) * seg->area_count);
            FAILURE_ON_MALLOC(ctx, seg->areas);
            memset(seg->areas, 0, sizeof(seg->areas[0]) * seg->area_count);

            rkva = _mda_get_kv_array(ctx, p, "mirrors", &p);
            FAILURE_ON_ERROR(ctx);
            FAILURE_ON_CONDITION(ctx, rkva->value_count != seg->area_count, -1, "Invalid Mirrors");

            FAILURE(ctx, -1, "XXXXXXXXXXXXXXXx");
            #if 0
                for (j = 0; j < seg->area_count; j++)
                {
                    struct lv_segment_area *node = seg->areas;

                    FAILURE_ON_CONDITION(ctx, rkva->values[j].type != 1, -1, "XXXX");
                    node->name = strdup(rkva->values[j].str_value);
                }

                /* Only first (original) is ok with in progress pvmove.  */
                if (is_pvmove)
                    seg->area_count = 1;
            #endif
        }
        else {
            FAILURE(ctx, -1, "XXXXXXXXXXXXXXXx");
        }
    }

    lv->vg = vg;
    c_list_link_tail(&vg->lvs, &lv->link);
    return lv;

failure:
    if (lv != NULL) free(lv);
    return NULL;
}

static void _free_lv(struct context *ctx, struct logical_volume *lv) {
    free(lv);
}

/* Returns a malloced string */
static char *_generate_lv_dm_name(struct context *ctx, struct logical_volume *lv) {
    char *ret = NULL;

    ret = malloc(4096);
    FAILURE_ON_MALLOC(ctx, ret);

    strcpy(ret, lv->vg->name);
    strcat(ret, ".");
    strcat(ret, lv->name);

    return ret;

failure:
    return NULL;
}

/* Returns a malloced string */
static char *_generate_lv_dm_uuid(struct context *ctx, struct logical_volume *lv) {
    char *ret = NULL;
    const char *iptr;
    char *optr;

    ret = malloc(sizeof("LVM-") + ID_STRLEN + 1 + ID_STRLEN + 1);
    FAILURE_ON_MALLOC(ctx, ret);

    strcpy(ret, "LVM-");
    optr = ret + strlen("LVM-");

    for (iptr = lv->vg->uuid; *iptr != '\0'; iptr++) {
        if (*iptr != '-')
            *optr++ = *iptr;
    }

    for (iptr = lv->uuid; *iptr != '\0'; iptr++) {
        if (*iptr != '-')
            *optr++ = *iptr;
    }

    *optr++ = '\0';

    return ret;

failure:
    return NULL;
}

/*****************************************************************************/
/* Volume Group Operation                                                     */
/*****************************************************************************/

static struct volume_group *_find_vg_by_name(struct context *ctx, const char *vg_name) {
    struct volume_group *vg;

    c_list_for_each_entry(vg, &ctx->vgs, link)
        if (strcmp(vg->name, vg_name) == 0)
            return vg;

    return NULL;
}

static struct volume_group *_find_vg_by_uuid(struct context *ctx, const char *vg_uuid) {
    struct volume_group *vg;

    c_list_for_each_entry(vg, &ctx->vgs, link)
        if (strcmp(vg->uuid, vg_uuid) == 0)
            return vg;

    return NULL;
}

/* vg_metadata and vg_uuid should be malloced and consumed by this function */
static struct volume_group *_new_vg(struct context *ctx, char *vg_metadata, char *vg_uuid) {
    struct volume_group *vg = NULL;
    struct mda_block *rblock = NULL;
    struct CList *rblocks = NULL;
    char *p;

    /* Create volume group object */
    vg = malloc(sizeof(*vg));
    FAILURE_ON_MALLOC(ctx, vg);
    memset(vg, 0, sizeof(*vg));

    /* Set basic values */
    vg->metadata = vg_metadata;
    vg->uuid = vg_uuid;
    c_list_init(&vg->pvs);
    c_list_init(&vg->lvs);

    /* Get VG name */
    p = vg->metadata;
    while (*p != ' ') {
        FAILURE_ON_CONDITION(ctx, *p == '\0', -1, "Error parsing metadata.");
        p++;
    }
    vg->name = strndup(vg->metadata, p - vg->metadata);
    FAILURE_ON_MALLOC(ctx, vg->name);

    /* Get VG extent size */
    vg->extent_size = _mda_get_num(ctx, p, "extent_size", "VG extent size", NULL);

    /* Get physical volumes */
    rblock = _mda_get_block(ctx, p, "physical_volumes", NULL);
    FAILURE_ON_ERROR(ctx);
    if (rblock != NULL) {
        struct mda_block *block;
        struct mda_block *block_safe;

        rblocks = _mda_get_blocks(ctx, rblock->content, NULL);
        FAILURE_ON_ERROR(ctx);
        FAILURE_ON_CONDITION(ctx, rblocks == NULL, -1, "xxxxxx.");

        c_list_for_each_entry(block, rblocks, link) {
            _new_pv(ctx, vg, block);
            FAILURE_ON_ERROR(ctx);
        }

        c_list_for_each_entry_safe(block, block_safe, rblocks, link) {
            free(block->content);
            free(block);
        }
        free(rblocks);
        rblocks = NULL;
        free(rblock);
        rblock = NULL;
    }

    rblock = _mda_get_block(ctx, p, "logical_volumes", NULL);
    if (rblock != NULL) {
        struct mda_block *block;
        struct mda_block *block_safe;

        rblocks = _mda_get_blocks(ctx, rblock->content, NULL);
        FAILURE_ON_ERROR(ctx);
        FAILURE_ON_CONDITION(ctx, rblocks == NULL, -1, "xxxxxx.");

        c_list_for_each_entry(block, rblocks, link) {
            _new_lv(ctx, vg, block);
            FAILURE_ON_ERROR(ctx);
        }

        c_list_for_each_entry_safe(block, block_safe, rblocks, link) {
            free(block->content);
            free(block);
        }
        free(rblocks);
        rblocks = NULL;
        free(rblock);
        rblock = NULL;
    }

    vg->ctx = ctx;
    c_list_link_tail(&ctx->vgs, &vg->link);
    return vg;

failure:
    if (rblocks != NULL) {
        struct mda_block *block;
        struct mda_block *block_safe;
        c_list_for_each_entry_safe(block, block_safe, rblocks, link) {
            free(block->content);
            free(block);
        }
        free(rblocks);
    }
    if (rblock != NULL) free(rblock);
    if (vg != NULL && vg->name != NULL) free(vg->name);
    if (vg != NULL) free(vg);
    return NULL;
}

/*****************************************************************************/
/* Device Mapper Operation                                                     */
/*****************************************************************************/

#define DM_NAME_LEN 128
#define DM_UUID_LEN 129
#define DM_MAX_TYPE_NAME 16

#define DM_DEV_CREATE    _IOWR(0xfd, 3, struct dm_ioctl)
#define DM_DEV_SUSPEND   _IOWR(0xfd, 6, struct dm_ioctl)
#define DM_TABLE_LOAD    _IOWR(0xfd, 9, struct dm_ioctl)

#define DM_TARGET_TYPE_CACHE               "cache"
#define DM_TARGET_TYPE_ERROR               "error"
#define DM_TARGET_TYPE_LINEAR              "linear"
#define DM_TARGET_TYPE_MIRROR              "mirror"
#define DM_TARGET_TYPE_RAID                "raid"
#define DM_TARGET_TYPE_SNAPSHOT            "snapshot"
#define DM_TARGET_TYPE_SNAPSHOT_MERGE      "snapshot-merge"
#define DM_TARGET_TYPE_SNAPSHOT_ORIGIN     "snapshot-origin"
#define DM_TARGET_TYPE_STRIPED             "striped"
#define DM_TARGET_TYPE_THIN                "thin"
#define DM_TARGET_TYPE_THIN_POOL           "thin-pool"
#define DM_TARGET_TYPE_ZERO                "zero"

struct dm_ioctl {
    u_int32_t version[3];          /* in/out */
    u_int32_t data_size;           /* total size of data passed in including this struct */
    u_int32_t data_start;          /* offset to start of data relative to start of this struct */

    u_int32_t target_count;        /* in/out */
    int32_t open_count;            /* out */
    u_int32_t flags;               /* in/out */

    /*
     * event_nr holds either the event number (input and output) or the
     * udev cookie value (input only).
     * The DM_DEV_WAIT ioctl takes an event number as input.
     * The DM_SUSPEND, DM_DEV_REMOVE and DM_DEV_RENAME ioctls
     * use the field as a cookie to return in the DM_COOKIE
     * variable with the uevents they issue.
     * For output, the ioctls return the event number, not the cookie.
     */
    u_int32_t event_nr;            /* in/out */
    u_int32_t padding;

    u_int64_t dev;                 /* in/out */

    char name[DM_NAME_LEN];        /* device name */
    char uuid[DM_UUID_LEN];        /* unique identifier for the block device */
    char data[7];                  /* padding or data */
};

struct dm_target_spec {
    u_int64_t start;
    u_int64_t length;
    int32_t status;                /* used when reading from kernel only */
    u_int32_t next;
    char target_type[DM_MAX_TYPE_NAME];
};

static void *__dm_open_control_file(struct context *ctx) {
    const char *path = "/dev/mapper/control";

    if (ctx->control_fd == -1) {
        ctx->control_fd = open(path, O_RDWR);
        FAILURE_ON_CONDITION(ctx, ctx->control_fd < 0, LVM_ERR_SYSTEM, "Failed to open %s", path);
    }

    return (void *)0x01;

failure:
    return NULL;
}

static void *__dm_generate_target_param(struct context *ctx, char **bufp, int *lenp, const char *format, ...) {
    va_list args;
    char *tmp = NULL;
    int len;
    char *pt;
    char *out;
    char *ret = NULL;

    tmp = malloc(4096);
    FAILURE_ON_MALLOC(ctx, tmp);

    va_start(args, format);
    vsprintf(tmp, format, args);
    va_end(args);

    len = strlen(tmp);
    pt = tmp;
    while (*pt)
        if (*pt++ == '\\')
            len++;
    len = align_8(sizeof(struct dm_target_spec) + len);

    ret = malloc(len);
    FAILURE_ON_MALLOC(ctx, ret);

    /* replace "\" with "\\" */
    pt = tmp;
    out = ret;
    while (*pt) {
        if (*pt == '\\')
            *out++ = '\\';
        *out++ = *pt++;
    }
    while (out - ret < len) {
        *out++ = '\0';
    } 

    free(tmp);
    *bufp = ret;
    *lenp = len;
    return (void *)0x01;

failure:
    if (tmp != NULL) free(tmp);
    if (ret != NULL) free(ret);
    return NULL;
}

char *_dm_dev_create(struct context *ctx, const char *dm_name, const char *dm_uuid) {
    static char newfile[PATH_MAX] = "/dev/dm-0";

    struct dm_ioctl *dmi = NULL;
    int r;

    FAILURE_ON_CONDITION(ctx, strlen(dm_name) >= DM_NAME_LEN, -1, "XXXXXXXXx");
    FAILURE_ON_CONDITION(ctx, strlen(dm_uuid) >= DM_UUID_LEN, -1, "XXXXXXXXx");
    FAILURE_ON_CONDITION(ctx, access(newfile, F_OK) == 0, -1, "%s already exists", newfile);

    /* open /dev/mapper/control */
    __dm_open_control_file(ctx);
    FAILURE_ON_ERROR(ctx);

    /* malloc dm_ioctl structure */
    dmi = malloc(sizeof(*dmi));
    FAILURE_ON_MALLOC(ctx, dmi);
    memset(dmi, 0, sizeof(*dmi));

    dmi->version[0] = 4;
    dmi->version[1] = 0;
    dmi->version[2] = 0;
    dmi->data_size = sizeof(*dmi);
    dmi->data_start = sizeof(*dmi);
    strcpy(dmi->name, dm_name);
    strcpy(dmi->uuid, dm_uuid);

    /* do ioctl */
    r = ioctl(ctx->control_fd, DM_DEV_CREATE, dmi);
    FAILURE_ON_CONDITION(ctx, r != 0, -1, "%s", strerror(errno));
    FAILURE_ON_CONDITION(ctx, access(newfile, F_OK) != 0, -1, "XXXXXX");

    free(dmi);
    return newfile;

failure:
    if (dmi != NULL) free(dmi);
    return NULL;
}

void *_dm_dev_resume(struct context *ctx, const char *dm_uuid) {
    struct dm_ioctl *dmi = NULL;
    int r;

    FAILURE_ON_CONDITION(ctx, strlen(dm_uuid) >= DM_UUID_LEN, -1, "XXXXXXXXx");

    /* open /dev/mapper/control */
    __dm_open_control_file(ctx);
    FAILURE_ON_ERROR(ctx);

    /* malloc dm_ioctl structure */
    dmi = malloc(sizeof(*dmi));
    FAILURE_ON_MALLOC(ctx, dmi);
    memset(dmi, 0, sizeof(*dmi));

    dmi->version[0] = 4;
    dmi->version[1] = 0;
    dmi->version[2] = 0;
    dmi->data_size = sizeof(*dmi);
    dmi->data_start = sizeof(*dmi);
    strcpy(dmi->uuid, dm_uuid);

    /* do ioctl */
    r = ioctl(ctx->control_fd, DM_DEV_SUSPEND, dmi);
    FAILURE_ON_CONDITION(ctx, r != 0, -1, "%s", strerror(errno));

    free(dmi);
    return (void *)0x01;

failure:
    if (dmi != NULL) free(dmi);
    return NULL;
}

/* In lvm2 code, target_param are created by _emit_segment_line(), _emit_areas_line() */
void *_dm_load_table(struct context *ctx, const char *dm_uuid, struct logical_volume *lv) {
    CDynBuf *dynbuf = NULL;
    struct dm_ioctl *dmi;
    struct dm_target_spec sp;
    char *param = NULL;
    int param_len;
    int i, j;
    int r;

    /* open /dev/mapper/control */
    __dm_open_control_file(ctx);
    FAILURE_ON_ERROR(ctx);

    /* malloc dm_ioctl structure */
    r = c_dynbuf_new(&dynbuf);
    FAILURE_ON_DYNBUF_ERROR(ctx, r);
    r = c_dynbuf_write_c(dynbuf, 0, 0, sizeof(*dmi));
    FAILURE_ON_DYNBUF_ERROR(ctx, r);

    /* fill dm_ioctl structure */
    dmi = (struct dm_ioctl *)dynbuf->p;
    dmi->version[0] = 4;
    dmi->version[1] = 0;
    dmi->version[2] = 0;
    dmi->data_start = sizeof(*dmi);
    strcpy(dmi->uuid, dm_uuid);

    /* fill targets */
    dmi = (struct dm_ioctl *)dynbuf->p;
    dmi->target_count = lv->segment_count;
    for (i = 0; i < lv->segment_count; i++) {
        sp.start = lv->segments[i].start_extent * lv->vg->extent_size;
        sp.length = lv->segments[i].extent_count * lv->vg->extent_size;

        sp.status = 0;

        if (lv->segments[i].type == LV_SEGMENT_STRIPED) {
            for (j = 0; j < lv->segments[i].area_count; j++) {
                struct lv_segment_area *area = &lv->segments[i].areas[j];
                struct physical_volume *pv = area->map_to_pv.pv;
                FAILURE_ON_CONDITION(ctx, area->type != 1, -1, "Segment %d of LV %s only supports map_to_pv area", j + 1, lv->name);
                FAILURE_ON_CONDITION(ctx, (pv->major < 0 || pv->minor < 0), -1, "Incomplete information for PV %s", pv->name);
            }

            if (lv->segments[i].area_count == 1) {
                struct lv_segment_area *area = &lv->segments[i].areas[0];
                struct physical_volume *pv = area->map_to_pv.pv;

                strcpy(sp.target_type, DM_TARGET_TYPE_LINEAR);

                __dm_generate_target_param(ctx, &param, &param_len, "%d:%d %lu", pv->major, pv->minor,
                                           pv->start_sector + area->map_to_pv.start_extent * lv->vg->extent_size);
                FAILURE_ON_ERROR(ctx);
            }
            else {
                strcpy(sp.target_type, DM_TARGET_TYPE_STRIPED);
                FAILURE(ctx, -1, "XXXXX");
            }
        }
        else if (lv->segments[i].type == LV_SEGMENT_MIRROR) {
            FAILURE(ctx, -1, "XXXXX");
        }
        else {
            FAILURE(ctx, -1, "XXXXX");
        }

        sp.next = sizeof(sp) + param_len;

        r = c_dynbuf_append(dynbuf, &sp, sizeof(sp));
        FAILURE_ON_DYNBUF_ERROR(ctx, r);

        r = c_dynbuf_append(dynbuf, param, param_len);
        FAILURE_ON_DYNBUF_ERROR(ctx, r);

        free(param);
        param = NULL;
    }

    /* fill data_size in dm_ioctl */
    dmi = (struct dm_ioctl *)dynbuf->p;
    dmi->data_size = dynbuf->len;

    /* do ioctl */
    r = ioctl(ctx->control_fd, DM_TABLE_LOAD, dmi);
    FAILURE_ON_CONDITION(ctx, r != 0, -1, "%s", strerror(errno));

    c_dynbuf_free(dynbuf);
    return (void *)0x01;

failure:
    if (dynbuf != NULL) c_dynbuf_free(dynbuf);
    return NULL;
}

/*****************************************************************************/
/* Functions                                                                 */
/*****************************************************************************/

/* Return 0x01 when success, NULL when error. */
/* When success, output parameter pv_id and metadata are assigned as malloced string */
static void *_get_pvid_and_metadata(struct context *ctx, int major, int minor, char **pv_id, char **metadata) {
    int fd = 0;
    char buf[LABEL_SIZE];
    struct label_header *lh;
    struct pv_header *pvh;
    struct disk_locn *dlocn;
    struct raw_locn *rlocn;
    char mda_header_buf[MDA_HEADER_SIZE];
    struct mda_header *mdah;
    u_int64_t mda_offset;
    u_int64_t mda_size;
    size_t rlen;
    off_t roff;
    int i, j;

    *pv_id = NULL;
    *metadata = NULL;

    /* Open device */
    fd = _blkdev_open(ctx, major, minor);
    FAILURE_ON_ERROR(ctx);

    /* Search for label, */
    /* Variable buf, lh, pvh, dlocn will be used after for loop */
    for (i = 0; i < LABEL_SCAN_SECTORS; i++) {
        /* read one sector */
        rlen = read(fd, buf, sizeof(buf));
        FAILURE_ON_CONDITION(ctx, rlen == -1, LVM_ERR_DEVICE_IO, "Failed to read device %u:%u.", major, minor);
        if (rlen < sizeof(buf))
        {
            i = LABEL_SCAN_SECTORS;
            break;                                /* not found */
        }

        /* Find headers */
        lh = (struct label_header *)buf;
        pvh = (struct pv_header *)(buf + le32toh(lh->offset_xl));
        dlocn = pvh->disk_areas_xl;

        /* Compare labels */
        if (strncmp((char *)lh->id, LABEL_ID, sizeof(lh->id)) == 0 && 
            strncmp((char *)lh->type, LVM2_LABEL, sizeof(lh->type)) == 0)
        {
            break;                                /* found */
        }
    }
    FAILURE_ON_CONDITION(ctx, i == LABEL_SCAN_SECTORS, 0, "");

    /* Retrive output parameter pv_id */
    *pv_id = malloc(ID_STRLEN + 1);
    FAILURE_ON_MALLOC(ctx, *pv_id);
    for (i = 0, j = 0; i < ID_LEN; i++) {
        (*pv_id)[j++] = pvh->pv_uuid[i];
        if ((i != 1) && (i != 29) && (i % 4 == 1)) {
            (*pv_id)[j++] = '-';
        }
    }
    (*pv_id)[j] = '\0';

    /* Is it possible to have multiple data areas? I haven't seen devices that have it. */
    dlocn++;
    FAILURE_ON_CONDITION(ctx, dlocn->offset != 0, LVM_ERR_DATA_AREA, "Device %u:%u has multiple LVM data areas which is not supported.", major, minor);

    /* It's possible to have multiple copies of metadata areas, we just use the first one.  */
    dlocn++;
    mda_offset = le64toh(dlocn->offset);
    mda_size = le64toh(dlocn->size);

    /* Load mda header */
    roff = lseek(fd, mda_offset, SEEK_SET);
    FAILURE_ON_CONDITION(ctx, roff == -1, LVM_ERR_DEVICE_IO, "Failed to read device %u:%u.", major, minor);

    rlen = read(fd, mda_header_buf, MDA_HEADER_SIZE);
    FAILURE_ON_CONDITION(ctx, rlen != MDA_HEADER_SIZE, LVM_ERR_DEVICE_IO, "Failed to read device %u:%u.", major, minor);

    mdah = (struct mda_header *)mda_header_buf;
    if (strncmp((char *)mdah->magic, FMTT_MAGIC, sizeof(mdah->magic)) != 0 || le32toh(mdah->version) != FMTT_VERSION) {
        FAILURE(ctx, LVM_ERR_VG_METADATA, "Unknown LVM metadata header.");
    }

    rlocn = mdah->raw_locns;
    FAILURE_ON_CONDITION(ctx, le64toh(rlocn->offset) < MDA_HEADER_SIZE, -1, "Invalid raw location offset.");

    /* Load metadata */
    *metadata = malloc(le64toh(rlocn->size));
    FAILURE_ON_MALLOC(ctx, *metadata);

    if (le64toh(rlocn->offset) + le64toh(rlocn->size) > le64toh(mdah->size)) {
        u_int64_t pre_size = mda_size - le64toh(rlocn->offset);
        u_int64_t post_size = le64toh(rlocn->offset) + le64toh(rlocn->size) - le64toh(mdah->size);

          roff = lseek(fd, mda_offset + le64toh(rlocn->offset), SEEK_SET);
        FAILURE_ON_CONDITION(ctx, roff == -1, LVM_ERR_DEVICE_IO, "Failed to read device %u:%u.", major, minor);
        rlen = read(fd, *metadata, pre_size);
        FAILURE_ON_CONDITION(ctx, rlen != pre_size, LVM_ERR_DEVICE_IO, "Failed to read device %u:%u.", major, minor);

        roff = lseek(fd, mda_offset + MDA_HEADER_SIZE, SEEK_SET);
        FAILURE_ON_CONDITION(ctx, roff == -1, LVM_ERR_DEVICE_IO, "Failed to read device %u:%u.", major, minor);
        rlen = read(fd, *metadata + pre_size, post_size);
        FAILURE_ON_CONDITION(ctx, rlen != post_size, LVM_ERR_DEVICE_IO, "Failed to read device %u:%u.", major, minor);
    }
    else {
        roff = lseek(fd, mda_offset + le64toh(rlocn->offset), SEEK_SET);
        FAILURE_ON_CONDITION(ctx, roff == -1, LVM_ERR_DEVICE_IO, "Failed to read device %u:%u.", major, minor);
        rlen = read(fd, *metadata, le64toh(rlocn->size));
        FAILURE_ON_CONDITION(ctx, rlen != le64toh(rlocn->size), LVM_ERR_DEVICE_IO, "Failed to read device %u:%u.", major, minor);
    }

    close(fd);
    return (void *)0x01;

failure:
    if (*metadata != NULL) {
        free(*metadata);
        *metadata = NULL;
    }
    if (*pv_id != NULL) {
        free(*pv_id);
        *pv_id = NULL;
    }
    if (fd != 0) {
        close(fd);
    }
    return NULL;
}

/* Return 0x01 when success, NULL when error. */
static void *_scan_one_device(struct context *ctx, int major, int minor) {
    char *pv_id = NULL;
    char *metadata = NULL;
    char *vg_uuid = NULL;
    struct volume_group *vg;
    struct physical_volume *pv;
    void *rptr;

    /* Get pv_id and metadata from device. */
    rptr = _get_pvid_and_metadata(ctx, major, minor, &pv_id, &metadata);
    FAILURE_ON_ERROR(ctx);
    FAILURE_ON_CONDITION(ctx, rptr == NULL, 0, "");    /* ignore this device when not found */

    /* Get VG UUID */
    vg_uuid = _mda_get_str(ctx, metadata, "id", "VG UUID", NULL);
    FAILURE_ON_ERROR(ctx);
    FAILURE_ON_CONDITION(ctx, strlen(vg_uuid) != ID_STRLEN, LVM_ERR_VG_METADATA, "Invalid volume group ID.");

    /* Register VG */
    vg = _find_vg_by_uuid(ctx, vg_uuid);
    if (vg != NULL) {
        FAILURE_ON_CONDITION(ctx, strcmp(vg->metadata, metadata) != 0, LVM_ERR_VG_METADATA, "VG has different metadata on different PV.");
        free(metadata);
        free(vg_uuid);
    }
    else {
        vg = _new_vg(ctx, metadata, vg_uuid);
        FAILURE_ON_ERROR(ctx);
    }
    metadata = NULL;
    vg_uuid = NULL;

    /* Update PV info */
    pv = _find_pv_by_uuid(ctx, vg, pv_id);
    FAILURE_ON_CONDITION(ctx, pv == NULL, LVM_ERR_VG_METADATA, "PV not in VG.");
    FAILURE_ON_CONDITION(ctx, pv->major != -1 || pv->minor != -1, LVM_ERR_PV, "Incomplete PV information.");
    pv->major = major;
    pv->minor = minor;

    free(pv_id);
    return (void *)0x01;

failure:
    if (pv_id != NULL) free(pv_id);
    if (metadata != NULL) free(metadata);
    if (vg_uuid != NULL) free(vg_uuid);
    return NULL;
}

/*****************************************************************************/
/* Interface implementation                                                  */
/*****************************************************************************/

lvm_t lvm_init() {
    struct context *ctx = NULL;

    ctx = (struct context *)malloc(sizeof(*ctx));
    if (ctx == NULL) {
        return NULL;
    }

    ctx->err_id = 0;
    ctx->err_msg[0] = '\0';
    ctx->func = NULL;
    ctx->control_fd = -1;
    c_list_init(&ctx->vgs);

    return (lvm_t)ctx;
}

void lvm_quit(lvm_t libh) {
    struct context *ctx = (struct context *)libh;
    if (ctx->control_fd != -1) close(ctx->control_fd);
    free(ctx);
}

int lvm_errno(lvm_t libh) {
    struct context *ctx = (struct context *)libh;
    return ctx->err_id;
}

const char *lvm_errmsg(lvm_t libh) {
    struct context *ctx = (struct context *)libh;
    return ctx->err_msg;
}

int lvm_scan(lvm_t libh) {
    struct context *ctx = (struct context *)libh;
    struct blkdev_iter *bdi = NULL;

    bdi = _blkdev_iter_new(ctx);
    FAILURE_ON_ERROR(ctx);

    while (1) {
        bdi = _blkdev_iter_next(ctx, bdi);
        FAILURE_ON_ERROR(ctx);
        if (bdi == NULL) {
            break;
        }

        _scan_one_device(ctx, bdi->major, bdi->minor);
        CLEAR_ERROR(ctx, LVM_ERR_DEVICE_OPEN);
        FAILURE_ON_ERROR(ctx);
    }

    return 0;

failure:
    if (bdi != NULL) _blkdev_iter_free(ctx, bdi);
    return -1;
}

vg_t lvm_vg_open(lvm_t libh, const char *vgname) {
    struct context *ctx = (struct context *)libh;
    struct volume_group *ret;

    ret = _find_vg_by_name(ctx, vgname);
    FAILURE_ON_ERROR(ctx);
    FAILURE_ON_CONDITION(ctx, ret == NULL, -1, "volume group not found.");

    return (vg_t)ret;

failure:
    return NULL;
}

void lvm_vg_close(vg_t vg) {
    return;
}

lv_t lvm_lv_from_name(vg_t vg, const char *name) {
    struct volume_group *real_vg = (struct volume_group *)vg;
    struct logical_volume *ret;

    ret = _find_lv_by_name(real_vg->ctx, real_vg, name);
    FAILURE_ON_ERROR(real_vg->ctx);
    FAILURE_ON_CONDITION(real_vg->ctx, ret == NULL, -1, "logical volume not found.");

    return (lv_t)ret;

failure:
    return NULL;
}

int lvm_lv_activate(lv_t lv) {
    struct logical_volume *real_lv = (struct logical_volume *)lv;
    char *dm_name = NULL;
    char *dm_uuid = NULL;
    char *dev_filename;
    char *dev_basename;
    char fpath1[PATH_MAX];
    char fpath2[PATH_MAX];
    int r;

    dm_name = _generate_lv_dm_name(real_lv->vg->ctx, real_lv);
    FAILURE_ON_ERROR(real_lv->vg->ctx);

    dm_uuid = _generate_lv_dm_uuid(real_lv->vg->ctx, real_lv);
    FAILURE_ON_ERROR(real_lv->vg->ctx);

    dev_filename = _dm_dev_create(real_lv->vg->ctx, dm_name, dm_uuid);
    FAILURE_ON_ERROR(real_lv->vg->ctx);
    dev_basename = dev_filename + strlen("/dev/");

    _dm_load_table(real_lv->vg->ctx, dm_uuid, real_lv);
    FAILURE_ON_ERROR(real_lv->vg->ctx);

    _dm_dev_resume(real_lv->vg->ctx, dm_uuid);
    FAILURE_ON_ERROR(real_lv->vg->ctx);

    /* create symlink */
    r = snprintf(fpath1, sizeof(fpath1), "../%s", dev_basename);
    FAILURE_ON_CONDITION(real_lv->vg->ctx, r < 0, LVM_ERR_SYSTEM, "snprintf() failed for ../%s.", dev_basename);
    r = snprintf(fpath2, sizeof(fpath2), "/dev/mapper/%s", dm_name);
    FAILURE_ON_CONDITION(real_lv->vg->ctx, r < 0, LVM_ERR_SYSTEM, "snprintf() failed for /dev/mapper/%s.", dm_name);
    r = symlink(fpath1, fpath2);
    FAILURE_ON_CONDITION(real_lv->vg->ctx, r != 0, LVM_ERR_SYSTEM, "symlink() failed.");

    free(dm_uuid);
    free(dm_name);
    return 0;

failure:
    if (dm_name != NULL) free(dm_name);
    if (dm_uuid != NULL) free(dm_uuid);
    return -1;
}
