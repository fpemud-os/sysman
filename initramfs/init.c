/*
 * init.c
 *
 * Simple code to load modules, mount root, and get things going. Uses
 * dietlibc to keep things small.
 *
 * Erik Troan (ewt@redhat.com)
 * Jeremy Katz (katzj@redhat.com)
 *
 * Copyright 2002-2004 Red Hat Software
 *
 * This software may be freely redistributed under the terms of the GNU
 * public license.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
 *
 */

/* init is a very simple script interpretor designed to be as small as
 * possible. It is primarily designed to run simple linuxrc scripts on an initrd
 * image. Arguments to commands may be enclosed in either single or double
 * quotes to allow spaces to be included in the arguments. Spaces outside of
 * quotations always delineate arguments, and so backslash escaping is supported.
 * 
 * There are two types of commands, built in and external. External commands
 * are run from the filesystem via execve(). If commands names are given without
 * a path, init will search it's builtin PATH, which is /usr/bin, /usr/sbin.
 * 
 * Currently, init supports the following built in commands.
 *
 * access -[r][w][x][f] path
 * Tells whether the current user has sufficient permissions to read, write, or
 * execture path, or if the file exists (see access(2) for more
 * information).
 * 
 * echo [item]* [> filename]
 * Echos the text strings given to a file, with a space in between each
 * item. The output may be optionally redirected to a file.
 *
 * findlodev
 * Prints the full path to the first unused loopback block device on the
 * system. If none is available, no output is displayed.
 * 
 * losetup /dev/loopdev file
 * Binds file to the loopback device /dev/loopdev. See
 * losetup(8) for information on loopback devices.
 * 
 * mkdir [-p] path
 * Creates the directory "path". If -p is specified, this command
 * will not complain if the directory exists. Note this is a subset of the
 * standard mkdir -p behavior.
 * 
 * mkrootdev path
 * Makes "path" a block inode for the device which should be mounted
 * as root. To determine this device init uses 
 * the device suggested by the root= kernel command line argument (if
 * root=LABEL is used devices are probed to find one with that label). If
 * no root= argument is available, /proc/sys/kernel/real-root-dev provides
 * the device number.
 * 
 * mount [--ro] -o opts -t type device mntpoint
 * Mounts a filesystem. It does not support NFS, and it must be used in
 * the form given above (arguments must go first).  If "device" is of the form
 * LABEL=foo the devices listed in /proc/partitions will
 * be searched, and the first device with a volume label of "foo" will
 * be mounted. Normal mount(2) options are supported, and --ro will
 * mount the filesystem read only for compatibility with older versions of init.
 * The defaults mount option is silently ignored.
 * 
 * readlink path
 * Displays the value of the symbolic link "path".
 * 
 * setquiet
 * Cause any later echos in this script to not be displayed.
 * 
 * sleep num
 * Sleep for num seconds
 * 
 * switchroot newrootpath [init command]
 * Makes the filesystem mounted at newrootpath the new root
 * filesystem by moving the mountpoint.  This will only work in 2.6 or
 * later kernels.
 * 
 * umount path
 * Unmounts the filesystem mounted at path.
 *
 * lvm-lv-activate uuid vgname lvname
 * Activate the LVM2 logical volume specified by vgname and lvname. The logical
 * volume must have an UUID that is specifed by uuid.
 * 
 * bcache-cache-device-activate dev-uuid
 * Activate the cache device for bcache, the device is specified by dev-uuid.
 * 
 * bcache-backing-device-activate uuid dev-uuid
 * Activate the backing device for bcache, the device is specified by dev-uuid. The
 * bcache device must have an UUID that is specified by uuid
 */

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/ioctl.h>
#include <sys/sysmacros.h>
#include <asm/unistd.h>
#include <linux/loop.h>
#include <linux/cdrom.h>
#include <linux/major.h>
#include <linux/raid/md_u.h>
#include <blkid/blkid.h>

#define MAX(a, b) ((a) > (b) ? a : b)

#define STATFS_RAMFS_MAGIC    0x858458f6
#define STATFS_TMPFS_MAGIC    0x01021994


/*@null@*/ blkid_cache mycache = NULL;
bool testing = false;
bool quiet = 0;

#define PATH "/bin:/sbin:/usr/bin:/usr/sbin"

char * env[] = {
    "PATH=" PATH,
    NULL
};

#define STARTUPRC "startup.rc"

int smartmknod(const char * device, mode_t mode, dev_t dev) {
    char buf[256];
    char * end;

    strncpy(buf, device, 256);

    end = buf;
    while (*end != '\0') {
        if (*end == '/') {
            *end = '\0';
            if (access(buf, F_OK) != 0 && errno == ENOENT) 
                mkdir(buf, 0755);
            *end = '/';
        }

        end++;
    }

    return mknod(device, mode, dev);
}

char * getArg(char * cmd, char * end, char ** arg) {
    char quote = '\0';

    if (!cmd || cmd >= end) return NULL;

    while (isspace(*cmd) && cmd < end) cmd++;
    if (cmd >= end) return NULL;

    if (*cmd == '"')
    cmd++, quote = '"';
    else if (*cmd == '\'')
    cmd++, quote = '\'';

    if (quote != '\0') {
        *arg = cmd;

        /* This doesn't support \ escapes */
        while (cmd < end && *cmd != quote) cmd++;

        if (cmd == end) {
            fprintf(stderr, "error: quote mismatch for %s\n", *arg);
            return NULL;
        }

        *cmd = '\0';
        cmd++;
    } else {
        *arg = cmd;
        while (!isspace(*cmd) && cmd < end) cmd++;
        *cmd = '\0';
        if (**arg == '$')
            *arg = getenv(*arg+1);
        if (*arg == NULL)
            *arg = "";
    }

    cmd++;

    while (isspace(*cmd)) cmd++;

    return cmd;
}

#ifdef __powerpc__
#define CMDLINESIZE 256
#else
#define CMDLINESIZE 1024
#endif

/* get the contents of the kernel command line from /proc/cmdline */
static char * getKernelCmdLine(void) {
    int fd, i;
    char * buf;

    fd = open("/proc/cmdline", O_RDONLY, 0);
    if (fd < 0) {
        fprintf(stderr, "getKernelCmdLine: failed to open /proc/cmdline: %d\n", errno);
        return NULL;
    }

    buf = malloc(CMDLINESIZE);
    if (!buf)
        return buf;

    i = read(fd, buf, CMDLINESIZE);
    if (i < 0) {
        fprintf(stderr, "getKernelCmdLine: failed to read /proc/cmdline: %d\n", errno);
        (void)close(fd);
        return NULL;
    }

    (void)close(fd);
    if (i == 0)
        buf[0] = '\0';
    else
        buf[i - 1] = '\0';
    return buf;
}

static int hasKernelArg(char *arg) {
    char * start, * cmdline;

    cmdline = start = getKernelCmdLine();
    if (start == NULL) {
        return 0;
    }
    while (*start != '\0') {
        if (isspace(*start)) {
            start++;
            continue;
        }
        if (strncmp(start, arg, strlen(arg)) == 0) {
            char * next = start + strlen(arg);
            if (*next == '\0' || isspace(*next)) {
                return 1;
            }
        }
        while (*++start != '\0' && !isspace(*start))
            ;
    }

    return 0;
}

/* get the start of a kernel arg "arg".  returns everything after it
 * (useful for things like getting the args to init=).  so if you only
 * want one arg, you need to terminate it at the n */
static char * getKernelArg(char * arg) {
    char * start, * cmdline;

    cmdline = start = getKernelCmdLine();
    if (start == NULL) {
        return NULL;
    }
    while (*start != '\0') {
        if (isspace(*start)) {
            start++;
            continue;
        }
        if (strncmp(start, arg, strlen(arg)) == 0) {
            return start + strlen(arg);
        }
        while (*++start != '\0' && !isspace(*start))
            ;
    }

    return NULL;
}

static void waitForUuid(const char *uuid) {
    do {
        char * devName = blkid_evaluate_tag("UUID", uuid, &mycache);
        if (devName != NULL) {
            break;
        }
        (void)sleep(1);
    } while(1);
}

/* remove all files/directories below dirName -- don't cross mountpoints */
static int recursiveRemove(int fd)
{
    struct stat rb;
    DIR *dir;
    int rc = -1;
    int dfd;

    if (!(dir = fdopendir(fd))) {
        fprintf(stderr, "failed to open directory\n");
        goto done;
    }

    /* fdopendir() precludes us from continuing to use the input fd */
    dfd = dirfd(dir);

    if (fstat(dfd, &rb)) {
        fprintf(stderr, "stat failed\n");
        goto done;
    }

    while(1) {
        struct dirent *d;
        int isdir = 0;

        errno = 0;
        if (!(d = readdir(dir))) {
            if (errno) {
                fprintf(stderr, "failed to read directory\n");
                goto done;
            }
            break;    /* end of directory */
        }

        if (!strcmp(d->d_name, ".") || !strcmp(d->d_name, ".."))
            continue;
#ifdef _DIRENT_HAVE_D_TYPE
        if (d->d_type == DT_DIR || d->d_type == DT_UNKNOWN)
#endif
        {
            struct stat sb;

            if (fstatat(dfd, d->d_name, &sb, AT_SYMLINK_NOFOLLOW)) {
                fprintf(stderr, "stat failed %s\n", d->d_name);
                continue;
            }

            /* remove subdirectories if device is same as dir */
            if (S_ISDIR(sb.st_mode) && sb.st_dev == rb.st_dev) {
                int cfd;

                cfd = openat(dfd, d->d_name, O_RDONLY);
                if (cfd >= 0) {
                    recursiveRemove(cfd);
                    close(cfd);
                }
                isdir = 1;
            } else
                continue;
        }

        if (unlinkat(dfd, d->d_name, isdir ? AT_REMOVEDIR : 0))
            fprintf(stderr, "failed to unlink %s\n", d->d_name);
    }

    rc = 0;    /* success */

done:
    if (dir)
        closedir(dir);
    return rc;
}

/* va_list causes segment fault, so I use this method */
#define MAX_ARGV_COUNT 127
static int runBinaryImpl(const char *bin, const char *argArray[], int argArrayLen) {
    char ** theArgv;
    char ** nextArg;
    int pid, wpid;
    int status;
    int i;

    if (bin[0] != '/') {
        fprintf(stderr, "init: binary executable \"%s\" is not specified in absolute path\n", bin);
        return 1;
    }
    if (access(bin, X_OK) != 0) {
        fprintf(stderr, "init: invalid binary executable \"%s\"\n", bin);
        return 1;
    }
    if (argArrayLen > MAX_ARGV_COUNT) {
        fprintf(stderr, "init: too many arguments\n");
        return 1;
    }

    theArgv = (char **)malloc(sizeof(char *) * (MAX_ARGV_COUNT + 1));
    if (theArgv == NULL) {
        fprintf(stderr, "init: out of memory\n");
        return 1;
    }

    nextArg = theArgv;
    *nextArg = strdup(bin);
    if (*nextArg == NULL) {
        fprintf(stderr, "init: out of memory\n");
        return 1;
    }
    nextArg++;

    for (i = 0; i < argArrayLen; i++) {
        *nextArg = strdup(argArray[i]);
        if (*nextArg == NULL) {
            fprintf(stderr, "init: out of memory\n");
            return 1;
        }
        nextArg++;
    }
    *nextArg = NULL;

    if (testing) {
        printf("run binary, %s", bin);
        for (nextArg = theArgv; *nextArg != NULL; nextArg++) {
            printf(" %s", *nextArg);
        }
        printf("\n");
    } else {
        if (!(pid = fork())) {
            /* child */
            execve(theArgv[0], theArgv, env);
            fprintf(stderr, "init: failed in exec of %s\n", theArgv[0]);
            return 1;
        }

        for (;;) {
            wpid = wait4(-1, &status, 0, NULL);
            if (wpid == -1) {
                fprintf(stderr, "init: failed to wait for process %d\n", wpid);
                return 1;
            }

            if (wpid != pid)
                continue;

            if (!WIFEXITED(status) || WEXITSTATUS(status)) {
                fprintf(stderr, "init: %s exited abnormally! (pid %d)\n", theArgv[0], pid);
                return 1;
            }
            break;
        }
    }

    return 0;
}

static int runBinary1(const char *bin, const char *arg1) {
    const char *argArray[1];
    argArray[0] = arg1;
    return runBinaryImpl(bin, argArray, 1);
}

static int runBinary2(const char *bin, const char *arg1, const char *arg2) {
    const char *argArray[2];
    argArray[0] = arg1;
    argArray[1] = arg2;
    return runBinaryImpl(bin, argArray, 2);
}

static int runBinary3(const char *bin, const char *arg1, const char *arg2, const char *arg3) {
    const char *argArray[3];
    argArray[0] = arg1;
    argArray[1] = arg2;
    argArray[2] = arg3;
    return runBinaryImpl(bin, argArray, 3);
}

static int runBinary4(const char *bin, const char *arg1, const char *arg2, const char *arg3, const char *arg4) {
    const char *argArray[4];
    argArray[0] = arg1;
    argArray[1] = arg2;
    argArray[2] = arg3;
    argArray[3] = arg4;
    return runBinaryImpl(bin, argArray, 4);
}

int mountCommand(char * cmd, char * end) {
    char * fsType = NULL;
    char * device;
    char * mntPoint;
    char * deviceDir = NULL;
    char * options = NULL;
    int mustRemove = 0;
    int mustRemoveDir = 0;
    int rc = 0;
    int flags = MS_MGC_VAL;
    char * newOpts;

    cmd = getArg(cmd, end, &device);
    if (!cmd) {
        fprintf(stderr, "usage: mount [--ro] [-o <opts>] -t <type> <device> <mntpoint>\n");
        return 1;
    }

    while (cmd && *device == '-') {
        if (!strcmp(device, "--ro")) {
            flags |= MS_RDONLY;
        } else if (!strcmp(device, "--bind")) {
            flags = MS_BIND;
            fsType = "none";
        } else if (!strcmp(device, "-o")) {
            cmd = getArg(cmd, end, &options);
            if (!cmd) {
                fprintf(stderr, "mount: -o requires arguments\n");
                return 1;
            }
        } else if (!strcmp(device, "-t")) {
            if (!(cmd = getArg(cmd, end, &fsType))) {
                fprintf(stderr, "mount: missing filesystem type\n");
                return 1;
            }
        }

        cmd = getArg(cmd, end, &device);
    }

    if (!cmd) {
        fprintf(stderr, "mount: missing device\n");
        return 1;
    }

    if (!(cmd = getArg(cmd, end, &mntPoint))) {
        fprintf(stderr, "mount: missing mount point\n");
        return 1;
    }

    if (!fsType) {
        fprintf(stderr, "mount: filesystem type expected\n");
        return 1;
    }

    if (cmd < end) {
        fprintf(stderr, "mount: unexpected arguments\n");
        return 1;
    }

    /* need to deal with options */ 
    if (options) {
        char * end;
        char * start = options;

        newOpts = alloca(strlen(options) + 1);
        *newOpts = '\0';

        while (*start) {
            end = strchr(start, ',');
            if (!end) {
                end = start + strlen(start);
            } else {
                *end = '\0';
                end++;
            }

            if (!strcmp(start, "ro"))
                flags |= MS_RDONLY;
            else if (!strcmp(start, "rw"))
                flags &= ~MS_RDONLY;
            else if (!strcmp(start, "nosuid"))
                flags |= MS_NOSUID;
            else if (!strcmp(start, "suid"))
                flags &= ~MS_NOSUID;
            else if (!strcmp(start, "nodev"))
                flags |= MS_NODEV;
            else if (!strcmp(start, "dev"))
                flags &= ~MS_NODEV;
            else if (!strcmp(start, "noexec"))
                flags |= MS_NOEXEC;
            else if (!strcmp(start, "exec"))
                flags &= ~MS_NOEXEC;
            else if (!strcmp(start, "sync"))
                flags |= MS_SYNCHRONOUS;
            else if (!strcmp(start, "async"))
                flags &= ~MS_SYNCHRONOUS;
            else if (!strcmp(start, "nodiratime"))
                flags |= MS_NODIRATIME;
            else if (!strcmp(start, "diratime"))
                flags &= ~MS_NODIRATIME;
            else if (!strcmp(start, "noatime"))
                flags |= MS_NOATIME;
            else if (!strcmp(start, "atime"))
                flags &= ~MS_NOATIME;
            else if (!strcmp(start, "strictatime"))
                flags |= MS_STRICTATIME;
            else if (!strcmp(start, "remount"))
                flags |= MS_REMOUNT;
            else if (!strcmp(start, "defaults"))
                ;
            else {
                if (*newOpts)
                    strcat(newOpts, ",");
                strcat(newOpts, start);
            }

            start = end;
        }

        options = newOpts;
    }

    if (!strncmp("LABEL=", device, 6)) {
        char * devName = blkid_evaluate_tag("LABEL", device + 6, &mycache);
        if (devName == NULL) {
            fprintf(stderr, "mount: failed to get device by LABEL %s\n", device + 6);
            return 1;
        }
        device = devName;
    } else if (!strncmp("UUID=", device, 5)) {
        char * devName = blkid_evaluate_tag("UUID", device + 5, &mycache);
        if (devName == NULL) {
            fprintf(stderr, "mount: failed to get device by UUID %s\n", device + 5);
            return 1;
        }
        device = devName;
    }

    if (testing) {
        printf("mount %s%s%s-t '%s' '%s' '%s' (%s%s%s%s%s%s%s)\n", 
            options ? "-o '" : "",    
            options ? options : "",    
            options ? "\' " : "",    
            fsType, device, mntPoint,
            (flags & MS_RDONLY) ? "ro " : "",
            (flags & MS_NOSUID) ? "nosuid " : "",
            (flags & MS_NODEV) ? "nodev " : "",
            (flags & MS_NOEXEC) ? "noexec " : "",
            (flags & MS_SYNCHRONOUS) ? "sync " : "",
            (flags & MS_REMOUNT) ? "remount " : "",
            (flags & MS_NOATIME) ? "noatime " : ""
            );
    } else {
        if (mount(device, mntPoint, fsType, flags, options)) {
            fprintf(stderr, "mount: error %d mounting %s\n", errno, fsType);
            rc = 1;
        }
    }

    if (mustRemove) unlink(device);
    if (mustRemoveDir) rmdir(deviceDir);

    return rc;
}

int otherCommand(char * bin, char * cmd, char * end, int doFork) {
    char ** args;
    char ** nextArg;
    int pid, wpid;
    int status;
    char fullPath[255];
    static const char * sysPath = PATH;
    const char * pathStart;
    const char * pathEnd;
    char * stdoutFile = NULL;
    int stdoutFd = 0;

    args = (char **)malloc(sizeof(char *) * 128);
    if (!args)
        return 1;
    nextArg = args;

    if (!strchr(bin, '/')) {
        pathStart = sysPath;
        while (*pathStart) {
            pathEnd = strchr(pathStart, ':');

            if (!pathEnd) pathEnd = pathStart + strlen(pathStart);

            strncpy(fullPath, pathStart, pathEnd - pathStart);
            fullPath[pathEnd - pathStart] = '/';
            strcpy(fullPath + (pathEnd - pathStart + 1), bin); 

            pathStart = pathEnd;
            if (*pathStart) pathStart++;

            if (!access(fullPath, X_OK)) {
            bin = fullPath;
            break;
            }
        }
    }

    *nextArg = strdup(bin);

    while (cmd && cmd < end) {
        nextArg++;
        cmd = getArg(cmd, end, nextArg);
    }
    
    if (cmd) nextArg++;
    *nextArg = NULL;

    /* if the next-to-last arg is a >, redirect the output properly */
    if (((nextArg - args) >= 2) && !strcmp(*(nextArg - 2), ">")) {
        stdoutFile = *(nextArg - 1);
        *(nextArg - 2) = NULL;

        stdoutFd = open(stdoutFile, O_CREAT | O_RDWR | O_TRUNC, 0600);
        if (stdoutFd < 0) {
            fprintf(stderr, "init: failed to open %s: %d\n", stdoutFile, errno);
            return 1;
        }
    }

    if (testing) {
        printf("%s ", bin);
        nextArg = args + 1;
        while (*nextArg)
            printf(" '%s'", *nextArg++);
        if (stdoutFile)
            printf(" (> %s)", stdoutFile);
        printf("\n");
    } else {
        if (!doFork || !(pid = fork())) {
            /* child */
            dup2(stdoutFd, 1);
            execve(args[0], args, env);
            fprintf(stderr, "ERROR: failed in exec of %s\n", args[0]);
            return 1;
        }

        close(stdoutFd);

        for (;;) {
            wpid = wait4(-1, &status, 0, NULL);
            if (wpid == -1) {
                fprintf(stderr, "ERROR: Failed to wait for process %d\n", wpid);
                return 1;
            }

            if (wpid != pid)
                continue;

            if (!WIFEXITED(status) || WEXITSTATUS(status)) {
                fprintf(stderr, "ERROR: %s exited abnormally! (pid %d)\n", args[0], pid);
                return 1;
            }
            break;
        }
    }

    return 0;
}

int losetupCommand(char * cmd, char * end) {
    char * device;
    char * file;
    int fd;
    struct loop_info loopInfo;
    int dev;

    if (!(cmd = getArg(cmd, end, &device))) {
        fprintf(stderr, "losetup: missing device\n");
        return 1;
    }

    if (!(cmd = getArg(cmd, end, &file))) {
        fprintf(stderr, "losetup: missing file\n");
        return 1;
    }

    if (cmd < end) {
        fprintf(stderr, "losetup: unexpected arguments\n");
        return 1;
    }

    if (testing) {
        printf("losetup '%s' '%s'\n", device, file);
    } else {
        dev = open(device, O_RDWR, 0);
        if (dev < 0) {
            fprintf(stderr, "losetup: failed to open %s: %d\n", device, errno);
            return 1;
        }

        fd = open(file, O_RDWR, 0);
        if (fd < 0) {
            fprintf(stderr, "losetup: failed to open %s: %d\n", file, errno);
            close(dev);
            return 1;
        }

        if (ioctl(dev, LOOP_SET_FD, (long) fd)) {
            fprintf(stderr, "losetup: LOOP_SET_FD failed: %d\n", errno);
            close(dev);
            close(fd);
            return 1;
        }

        close(fd);

        memset(&loopInfo, 0, sizeof(loopInfo));
        strcpy(loopInfo.lo_name, file);

        if (ioctl(dev, LOOP_SET_STATUS, &loopInfo)) 
            printf("losetup: LOOP_SET_STATUS failed: %d\n", errno);

        close(dev);
    }

    return 0;
}

#define RAID_MAJOR 9
int raidautorunCommand(char * cmd, char * end) {
    char * device;
    int fd;

    if (!(cmd = getArg(cmd, end, &device))) {
    fprintf(stderr, "raidautorun: raid device expected as first argument\n");
    return 1;
    }

    if (cmd < end) {
    fprintf(stderr, "raidautorun: unexpected arguments\n");
    return 1;
    }

    /* with udev, the raid devices don't exist until they get started.
     * this won't work so well with raidautorun.  so, let's be smart
     * and create them ourselves if we need to */
    if (access(device, R_OK & W_OK)) {
        int minor;
        if (sscanf(device, "/dev/md%d", &minor) != 1) {
            fprintf(stderr, "raidautorun: unable to autocreate %s\n", device);
            return 1;
        }

        if (smartmknod(device, S_IFBLK | 0600, makedev(RAID_MAJOR, minor))) {
            fprintf(stderr, "raidautorun: unable to autocreate %s\n", device);
            return 1;
        }
    }

    fd = open(device, O_RDWR, 0);
    if (fd < 0) {
        fprintf(stderr, "raidautorun: failed to open %s: %d\n", device, errno);
        return 1;
    }

    if (ioctl(fd, RAID_AUTORUN, 0)) {
        fprintf(stderr, "raidautorun: RAID_AUTORUN failed: %d\n", errno);
        close(fd);
        return 1;
    }

    close(fd);
    return 0;
}

#define MAX_INIT_ARGS 32
/* This is based on code from util-linux/sys-utils/run_init.c */
int switchrootCommand(char * cmd, char * end) {
    char * newroot;
    const char * initprogs[] = { "/sbin/init", "/etc/init", "/bin/init", "/bin/sh", NULL };
    const char * umounts[] = { "/dev", "/proc", "/sys", NULL };
    struct stat newroot_stat;
    char * init = NULL, * cmdline = NULL;
    char ** initargs;
    int fd, cfd, i;
    struct statfs stfs;

    if (!(cmd = getArg(cmd, end, &newroot))) {
        fprintf(stderr, "switchroot: new root mount point expected\n");
        return 1;
    }

    if (cmd < end) {
        if (!(cmd = getArg(cmd, end, &init))) {
            fprintf(stderr, "switchroot: init program expected\n");
            return 1;
        }

        if (cmd < end) {
            cmdline = strndup(cmd, end - cmd);
        }
    }

    if (init == NULL) {
        init = getKernelArg("init=");
        if (init == NULL)
            cmdline = getKernelCmdLine();
    }

    if ((fd = open("/dev/console", O_RDWR)) < 0) {
        fprintf(stderr, "switchroot: error opening /dev/console!!!!: %d\n", errno);
        return 1;
    }

    if (dup2(fd, 0) != 0) {
        fprintf(stderr, "switchroot: error dup2'ing fd of %d to 0\n", fd);
    }
    if (dup2(fd, 1) != 1) {
        fprintf(stderr, "switchroot: error dup2'ing fd of %d to 1\n", fd);
    }
    if (dup2(fd, 2) != 2) {
        fprintf(stderr, "switchroot: error dup2'ing fd of %d to 2\n", fd);
    }
    if (fd > 2) {
        close(fd);
    }

    cfd = open("/", O_RDONLY);
    if (cfd < 0) {
        fprintf(stderr, "switchroot: cannot open /\n");
        return 1;
    }

    if (fstatfs(cfd, &stfs) != 0) {
        fprintf(stderr, "switchroot: stat failed /\n");
        return 1;
    }

    if (stfs.f_type != (__SWORD_TYPE)STATFS_RAMFS_MAGIC && stfs.f_type != (__SWORD_TYPE)STATFS_TMPFS_MAGIC) {
        fprintf(stderr, "switchroot: old root filesystem is not an initramfs");
        return 1;
    }

    if (stat(newroot, &newroot_stat) != 0) {
        fprintf(stderr, "switchroot: stat failed %s\n", newroot);
        return 1;
    }

    for (i = 0; umounts[i] != NULL; i++) {
        char newmount[PATH_MAX];
        struct stat sb;

        snprintf(newmount, sizeof(newmount), "%s%s", newroot, umounts[i]);

        if (stat(newmount, &sb) != 0) {
            fprintf(stderr, "switchroot: stat failed %s\n", newmount);
            return 1;
        }

        if (sb.st_dev != newroot_stat.st_dev) {
            /* mount point seems to be mounted already */
            umount2(umounts[i], MNT_DETACH);
            continue;
        }

        if (mount(umounts[i], newmount, NULL, MS_MOVE, NULL) < 0) {
            fprintf(stderr, "switchroot: failed to mount moving %s to %s\n", umounts[i], newmount);
            return 1;
        }
    }

    if (chdir(newroot)) {
        fprintf(stderr, "switchroot: chdir(%s) failed: %d\n", newroot, errno);
        return 1;
    }

    if (mount(".", "/", NULL, MS_MOVE, NULL) < 0) {
        fprintf(stderr, "switchroot: mount failed: %d\n", errno);
        return 1;
    }

    if (chroot(".") || chdir("/")) {
        fprintf(stderr, "switchroot: chroot() failed: %d\n", errno);
        return 1;
    }

    recursiveRemove(cfd);
    close(cfd);

    if (init == NULL) {
        for (i = 0; initprogs[i] != NULL; i++) {
            if (!access(initprogs[i], X_OK)) {
                init = strdup(initprogs[i]);
                break;
            }
        }
    }

    i = 0;
    initargs = (char **)malloc(sizeof(char *)*(MAX_INIT_ARGS+1));
    if (cmdline && init) {
        initargs[i++] = strdup(init);
    } else {
        cmdline = init;
        initargs[0] = NULL;
    }

    if (cmdline != NULL) {
        char * chptr, * start;

        start = chptr = cmdline;
        for (; (i < MAX_INIT_ARGS) && (*start != '\0'); i++) {
            while (*chptr && !isspace(*chptr)) chptr++;
            if (*chptr != '\0') *(chptr++) = '\0';
            initargs[i] = strdup(start);
            start = chptr;
        }
    }

    initargs[i] = NULL;

    if (access(initargs[0], X_OK)) {
        printf("WARNING: can't access %s\n", initargs[0]);
    }

    execv(initargs[0], initargs);
    fprintf(stderr, "exec of init (%s) failed!!!: %d\n", initargs[0], errno);
    return 1;
}

int isEchoQuiet(int fd) {
    if (!quiet) return 0;
    if (fd != 1) return 0;
    return 1;
}

int echoCommand(char * cmd, char * end) {
    char * args[256];
    char ** nextArg = args;
    int outFd = 1;
    int num = 0;
    int i;
    int newline = 1;
    int length = 0;
    char *string;

    if (testing && !quiet) {
        printf("(echo) ");
        fflush(stdout);
    }

    while ((cmd = getArg(cmd, end, nextArg))) {
        if (!strncmp("-n", *nextArg, MAX(2, strlen(*nextArg)))) {
            newline = 0;
        } else {
            length += strlen(*nextArg);
            nextArg++, num++;
        }
    }
    length += num + 1;

    if ((nextArg - args >= 2) && !strcmp(*(nextArg - 2), ">")) {
        outFd = open(*(nextArg - 1), O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (outFd < 0) {
            fprintf(stderr, "echo: cannot open %s for write: %d\n", 
                *(nextArg - 1), errno);
            return 1;
        }

        newline = 0;
        num -= 2;
    }
    string = (char *)malloc(length * sizeof(char));
    *string = '\0';
    for (i = 0; i < num;i ++) {
        if (i) strcat(string, " ");
        strncat(string, args[i], strlen(args[i]));
    }

    if (newline) strcat(string, "\n");
    if (!isEchoQuiet(outFd)) write(outFd, string, strlen(string));

    if (outFd != 1) close(outFd);
    free(string);

    return 0;
}

int umountCommand(char * cmd, char * end) {
    char * path;

    if (!(cmd = getArg(cmd, end, &path))) {
        fprintf(stderr, "umount: path expected\n");
        return 1;
    }

    if (cmd < end) {
        fprintf(stderr, "umount: unexpected arguments\n");
        return 1;
    }

    if (umount(path)) {
        fprintf(stderr, "umount %s failed: %d\n", path, errno);
        return 1;
    }

    return 0;
}

int mkdirCommand(char * cmd, char * end) {
    char * dir;
    int ignoreExists = 0;

    cmd = getArg(cmd, end, &dir);

    if (cmd && !strcmp(dir, "-p")) {
        ignoreExists = 1;
        cmd = getArg(cmd, end, &dir);
    }

    if (!cmd) {
        fprintf(stderr, "mkdir: directory expected\n");
        return 1;
    }

    if (mkdir(dir, 0755)) {
        if (!ignoreExists && errno == EEXIST) {
            fprintf(stderr, "mkdir: failed to create %s: %d\n", dir, errno);
            return 1;
        }
    }

    return 0;
}

int accessCommand(char * cmd, char * end) {
    char * permStr;
    int perms = 0;
    char * file = NULL;

    cmd = getArg(cmd, end, &permStr);
    if (cmd) cmd = getArg(cmd, end, &file);

    if (!cmd || *permStr != '-') {
        fprintf(stderr, "usage: access -[perm] file\n");
        return 1;
    }

    permStr++;
    while (*permStr) {
        switch (*permStr) {
            case 'r': perms |= R_OK; break;
            case 'w': perms |= W_OK; break;
            case 'x': perms |= X_OK; break;
            case 'f': perms |= F_OK; break;
            default:
                fprintf(stderr, "perms must be -[r][w][x][f]\n");
                return 1;
        }

        permStr++;
    }

    if ((file == NULL) || (access(file, perms))) {
        return 1;
    }

    return 0;
}

int sleepCommand(char * cmd, char * end) {
    char *delaystr;
    int delay;

    if (!(cmd = getArg(cmd, end, &delaystr))) {
        fprintf(stderr, "sleep: delay expected\n");
        return 1;
    }

    delay = atoi(delaystr);
    (void)sleep(delay);

    return 0;
}

int readlinkCommand(char * cmd, char * end) {
    char * path;
    char * buf, * respath, * fullpath;
    struct stat sb;
    int rc = 0;

    if (!(cmd = getArg(cmd, end, &path))) {
        fprintf(stderr, "readlink: file expected\n");
        return 1;
    }

    if (lstat(path, &sb) == -1) {
        fprintf(stderr, "unable to stat %s: %d\n", path, errno);
        return 1;
    }

    if (!S_ISLNK(sb.st_mode)) {
        printf("%s\n", path);
        return 0;
    }
    
    buf = malloc(512);
    if (readlink(path, buf, 512) == -1) {
        fprintf(stderr, "error readlink %s: %d\n", path, errno);
        free(buf);
        return 1;
    }

    /* symlink is absolute */
    if (buf[0] == '/') {
        printf("%s\n", buf);
        free(buf);
        return 0;
    } 
   
    /* nope, need to handle the relative symlink case too */
    respath = strrchr(path, '/');
    if (respath) {
        *respath = '\0';
    }

    fullpath = malloc(512);
    /* and normalize it */
    snprintf(fullpath, 512, "%s/%s", path, buf);
    respath = malloc(PATH_MAX);
    if (!(respath = realpath(fullpath, respath))) {
        fprintf(stderr, "error realpath %s: %d\n", fullpath, errno);
        rc = 1;
        goto readlinkout;
    }

    printf("%s\n", respath);
readlinkout:
    free(buf);
    free(respath);
    free(fullpath);
    return rc;
}

int lvmlvactivateCommand(char * cmd, char * end) {
    char * uuid;
    char * vgname;
    char * lvname;

    if (!(cmd = getArg(cmd, end, &uuid))) {
        fprintf(stderr, "lvm-lv-activate: missing uuid\n");
        return 1;
    }

    if (!(cmd = getArg(cmd, end, &vgname))) {
        fprintf(stderr, "lvm-lv-activate: missing vgname\n");
        return 1;
    }

    if (!(cmd = getArg(cmd, end, &lvname))) {
        fprintf(stderr, "lvm-lv-activate: missing lvname\n");
        return 1;
    }

    if (cmd < end) {
        fprintf(stderr, "lvm-lv-activate: unexpected arguments\n");
        return 1;
    }

    if (runBinary2("/usr/sbin/lvm-lv-activate", vgname, lvname) != 0) {
        /* callee prints error message */
        return 1;
    }

    waitForUuid(uuid);

    return 0;
}

int bcacheActivateCacheDeviceCommand(char * cmd, char *end) {
    char * bcacheRegisterFile;
    char * devuuid;
    char * device;
    int fd;

    if (!quiet) {
        bcacheRegisterFile = "/sys/fs/bcache/register";
    } else {
        bcacheRegisterFile = "/sys/fs/bcache/register_quiet";
    }

    if (!(cmd = getArg(cmd, end, &devuuid))) {
        fprintf(stderr, "bcache-cache-device-activate: missing devuuid\n");
        return 1;
    }

    if (cmd < end) {
        fprintf(stderr, "bcache-cache-device-activate: unexpected arguments\n");
        return 1;
    }

    device = blkid_evaluate_tag("UUID", devuuid, &mycache);
    if (device == NULL) {
        fprintf(stderr, "bcache-cache-device-activate: failed to get device by UUID %s\n", devuuid);
        return 1;
    }

    if (!testing) {
        fd = open(bcacheRegisterFile, O_WRONLY, 0);
        if (fd < 0) {
            fprintf(stderr, "bcache-cache-device-activate: failed to open %s: %d\n", bcacheRegisterFile, errno);
            return 1;
        }

        if (write(fd, device, strlen(device)) != strlen(device)) {
            fprintf(stderr, "bcache-cache-device-activate: failed to write %s: %d\n", bcacheRegisterFile, errno);
            close(fd);
            return 1;
        }

        close(fd);
    }

    return 0;
}

int bcacheActivateBackingDeviceCommand(char * cmd, char *end) {
    char * bcacheRegisterFile;
    char * uuid;
    char * devuuid;
    char * device;
    int fd;

    if (!quiet) {
        bcacheRegisterFile = "/sys/fs/bcache/register";
    } else {
        bcacheRegisterFile = "/sys/fs/bcache/register_quiet";
    }

    if (!(cmd = getArg(cmd, end, &uuid))) {
        fprintf(stderr, "bcache-backing-device-activate: missing uuid\n");
        return 1;
    }

    if (!(cmd = getArg(cmd, end, &devuuid))) {
        fprintf(stderr, "bcache-backing-device-activate: missing devuuid\n");
        return 1;
    }

    if (cmd < end) {
        fprintf(stderr, "bcache-backing-device-activate: unexpected arguments\n");
        return 1;
    }

    device = blkid_evaluate_tag("UUID", devuuid, &mycache);
    if (device == NULL) {
        fprintf(stderr, "bcache-backing-device-activate: failed to get device by UUID %s\n", devuuid);
        return 1;
    }

    if (!testing) {
        fd = open(bcacheRegisterFile, O_WRONLY, 0);
        if (fd < 0) {
            fprintf(stderr, "bcache-backing-device-activate: failed to open %s: %d\n", bcacheRegisterFile, errno);
            return 1;
        }

        if (write(fd, device, strlen(device)) != strlen(device)) {
            fprintf(stderr, "bcache-backing-device-activate: failed to write %s: %d\n", bcacheRegisterFile, errno);
            close(fd);
            return 1;
        }

        close(fd);
    }

    waitForUuid(uuid);

    return 0;
}

int fsckCommand(char * cmd, char * end) {
    char * fstype;
    char * uuid;
    char * device;

    if (!(cmd = getArg(cmd, end, &fstype))) {
        fprintf(stderr, "fsck: missing fstype\n");
        return 1;
    }

    if (!(cmd = getArg(cmd, end, &uuid))) {
        fprintf(stderr, "fsck: missing uuid\n");
        return 1;
    }

    if (cmd < end) {
        fprintf(stderr, "fsck: unexpected arguments\n");
        return 1;
    }

    device = blkid_evaluate_tag("UUID", uuid, &mycache);
    if (device == NULL) {
        fprintf(stderr, "fsck: failed to get device by UUID %s\n", uuid);
        return 1;
    }

    if (strcmp(fstype, "ext2") == 0 || strcmp(fstype, "ext4") == 0) {
        if (!quiet) {
            return runBinary3("/sbin/e2fsck", "-p", "-v", device);
        } else {
            return runBinary2("/sbin/e2fsck", "-p", device);
        }
    } else if (strcmp(fstype, "xfs") == 0) {
        return runBinary1("/sbin/fsck.xfs", device);
    } else if (strcmp(fstype, "vfat") == 0) {
        /* fsck.fat is unable to check for any real errors */
        if (!quiet) {
            runBinary2("/usr/sbin/fsck.fat", "-av", device);
        } else {
            runBinary2("/usr/sbin/fsck.fat", "-a", device);
        }
        return 0;
    }

    fprintf(stderr, "fsck: unknown fstype %s\n", fstype);
    return 1;
}

int findlodevCommand(char * cmd, char * end) {
    char devName[20];
    int devNum;
    int fd;
    struct loop_info loopInfo;
    char separator[2] = "";

    if (*end != '\n') {
        fprintf(stderr, "usage: findlodev\n");
        return 1;
    }

    if (!access("/dev/.devfsd", X_OK)) {
        strcpy(separator, "/");
    }

    for (devNum = 0; devNum < 256; devNum++) {
        sprintf(devName, "/dev/loop%s%d", separator, devNum);
        if ((fd = open(devName, O_RDONLY)) < 0) return 0;

        if (ioctl(fd, LOOP_GET_STATUS, &loopInfo)) {
            close(fd);
            printf("%s\n", devName);
            return 0;
        }

        close(fd);
    }

    return 0;
}

#define COMMAND_COMPARE(cmd, start, next) \
    (sizeof((cmd)) - 1 == (next) - (start) && strncmp((cmd), (start), (next) - (start)) == 0)

int runStartup() {
    int fd;
    char contents[32768];
    int i;
    char * start, * end;
    char * chptr;
    int rc;

    fd = open(STARTUPRC, O_RDONLY, 0);
    if (fd < 0) {
        fprintf(stderr, "Cannot open %s: %d\n", STARTUPRC, errno);
        return 1;
    }

    i = read(fd, contents, sizeof(contents) - 1);
    if (i == (sizeof(contents) - 1)) {
        fprintf(stderr, "Failed to read %s -- file too large.\n", STARTUPRC);
        close(fd);
        return 1;
    }

    contents[i] = '\0';

    start = contents;
    while (*start) {
        while (isspace(*start) && *start && (*start != '\n')) start++;

        if (*start == '#')
            while (*start && (*start != '\n')) start++;

        if (*start == '\n') {
            start++;
            continue;
        }

        if (!*start) {
            if (!quiet) {
                printf("<init> (last line in %s is empty)\n", STARTUPRC);
            }
            continue;
        }

        /* start points to the beginning of the command */
        end = start + 1;
        while (*end && (*end != '\n')) end++;
        if (!*end) {
            if (!quiet) {
                printf("<init> (last line in %s missing \\n -- skipping)\n", STARTUPRC);
            }
            start = end;
            continue;
        }

        /* end points to the \n at the end of the command */
        chptr = start;
        while (chptr < end && !isspace(*chptr)) chptr++;

        /* print command */
        if (!quiet) {
            printf("<init> %.*s\n", (int)(end - start), start);
        }

        /* execute command */
        if (COMMAND_COMPARE("mount", start, chptr)) {
            rc = mountCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("losetup", start, chptr)) {
            rc = losetupCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("echo", start, chptr)) {
            rc = echoCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("raidautorun", start, chptr)) {
            rc = raidautorunCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("switchroot", start, chptr)) {
            rc = switchrootCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("umount", start, chptr)) {
            rc = umountCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("mkdir", start, chptr)) {
            rc = mkdirCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("access", start, chptr)) {
            rc = accessCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("findlodev", start, chptr)) {
            rc = findlodevCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("sleep", start, chptr)) {
            rc = sleepCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("readlink", start, chptr)) {
            rc = readlinkCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("lvm-lv-activate", start, chptr)) {
            rc = lvmlvactivateCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("bcache-cache-device-activate", start, chptr)) {
            rc = bcacheActivateCacheDeviceCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("bcache-backing-device-activate", start, chptr)) {
            rc = bcacheActivateBackingDeviceCommand(chptr, end);
        }
        else if (COMMAND_COMPARE("fsck", start, chptr)) {
            rc = fsckCommand(chptr, end);
        }
        else {
            *chptr = '\0';
            rc = otherCommand(start, chptr + 1, end, 1);
        }

        /* give user a chance to inspect errors, it won't affect the normal procedure since no error should occur */
        if (rc) {
            (void)sleep(10);
        }

        start = end + 1;
    }

    close(fd);
    return rc;
}

int main(int argc, char **argv) {
    char * name;
    int rc;
    int force = 0;

    name = strrchr(argv[0], '/');
    if (!name) 
        name = argv[0];
    else
        name++;

    testing = (getppid() != 0) && (getppid() != 1);

    if (testing) {
        argv++, argc--;
        while (argc && **argv == '-') {
            if (!strcmp(*argv, "--force")) {
                force = 1;
                argv++, argc--;
                testing = 0;
            } else if (!strcmp(*argv, "--quiet")) {
                quiet = 1;
                argv++, argc--;
            } else {
                fprintf(stderr, "unknown argument %s\n", *argv);
                return 1;
            }
        }
    }

    if (!testing) {
        if (mount("sysfs", "/sys", "sysfs", MS_NOSUID|MS_NOEXEC|MS_NODEV, NULL)) {
            fprintf(stderr, "init: error %d mounting %s as %s\n", errno, "/sys", "sysfs");
            return 1;
        }
        if (mount("proc", "/proc", "proc", MS_NOSUID|MS_NOEXEC|MS_NODEV, NULL)) {
            fprintf(stderr, "init: error %d mounting %s as %s\n", errno, "/proc", "proc");
            return 1;
        }
        if (mount("devtmpfs", "/dev", "devtmpfs", MS_NOSUID|MS_STRICTATIME, "mode=755")) {
            fprintf(stderr, "init: error %d mounting %s as %s\n", errno, "/dev", "devtmpfs");
            return 1;
        }
    }

    if (!testing) {
        if (hasKernelArg("quiet")) {
            quiet = 1;
        }
    }

    if (!quiet) {
        printf("<init> fpemud-os init program version %s starting)\n", VERSION);
    }

    if (force && !quiet) {
        printf("<init> (forcing normal run)\n");
    }

    if (testing && !quiet) {
        printf("<init> (running in test mode).\n");
    }

    if (blkid_get_cache(&mycache, NULL) < 0) {
        fprintf(stderr, "init: error get blkid cache\n");
        return 1;
    }

    rc = runStartup();

    return rc;
}
