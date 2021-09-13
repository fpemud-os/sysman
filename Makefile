prefix=/usr

all:

clean:
	make -C clean

install:
	install -d -m 0755 "$(DESTDIR)/$(prefix)/bin"
	install -m 0755 sysman "$(DESTDIR)/$(prefix)/bin"

	install -d -m 0755 "$(DESTDIR)/$(prefix)/lib64/fpemud-os-sysman"
	cp -r lib/* "$(DESTDIR)/$(prefix)/lib64/fpemud-os-sysman"
	find "$(DESTDIR)/$(prefix)/lib64/fpemud-os-sysman" -type f | xargs chmod 644
	find "$(DESTDIR)/$(prefix)/lib64/fpemud-os-sysman" -type d | xargs chmod 755

	install -d -m 0755 "$(DESTDIR)/$(prefix)/libexec/fpemud-os-sysman"
	cp -r libexec/* "$(DESTDIR)/$(prefix)/libexec/fpemud-os-sysman"
	find "$(DESTDIR)/$(prefix)/libexec/fpemud-os-sysman" | xargs chmod 755

	install -d -m 0755 "$(DESTDIR)/$(prefix)/share/fpemud-os-sysman"
	cp -r data/* "$(DESTDIR)/$(prefix)/share/fpemud-os-sysman"
	find "$(DESTDIR)/$(prefix)/share/fpemud-os-sysman" -type f | xargs chmod 644
	find "$(DESTDIR)/$(prefix)/share/fpemud-os-sysman" -type d | xargs chmod 755

	install -d -m 0755 "$(DESTDIR)/$(prefix)/lib64/fpemud-os-sysman/initramfs"
	make -C initramfs
	chmod 644 initramfs/init
	chmod 644 initramfs/lvm-lv-activate
	cp initramfs/init "$(DESTDIR)/$(prefix)/lib64/fpemud-os-sysman/initramfs"
	cp initramfs/lvm-lv-activate "$(DESTDIR)/$(prefix)/lib64/fpemud-os-sysman/initramfs"

	install -d -m 0755 "$(DESTDIR)/lib/udev/rules.d"
	cp udev/*.rules "$(DESTDIR)/lib/udev/rules.d"

	install -d -m 0755 "$(DESTDIR)/lib/systemd/system"
	install -d -m 0755 "$(DESTDIR)/lib/systemd/system/basic.target.wants"
	cp systemd/bless-boot.service "$(DESTDIR)/lib/systemd/system"
	ln -sf "../bless-boot.service" "$(DESTDIR)/lib/systemd/system/basic.target.wants"

.PHONY: all clean install
