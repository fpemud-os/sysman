PACKAGE_VERSION=$(shell awk -F= '/^PACKAGE_VERSION=/ { print $$2 }' ../Makefile)
CFLAGS=-Wall -Wextra -Werror -Wno-unused-function -Wno-unused-parameter -Wno-sign-compare -Wno-pointer-sign -Wno-unused-but-set-variable -Wno-format-zero-length -Wno-format-truncation -DVERSION=\"$(PACKAGE_VERSION)\" -g
LIBS=`pkg-config --libs libclist libcdynbuf blkid`

all: init lvm-lv-activate

init: init.o
	$(CC) $(LDFLAGS) $^ $(LIBS) -o $@

lvm-lv-activate: lvm2app.o lvm-lv-activate.o
	$(CC) $(LDFLAGS) $^ $(LIBS) -o $@

clean:
	rm -f init lvm-lv-activate $(MINILIBC) *.o
