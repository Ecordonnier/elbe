# ELBE - Debian Based Embedded Rootfilesystem Builder
# Copyright (c) 2014-2016 Torben Hohn <torben.hohn@linutronix.de>
# Copyright (c) 2014 Ferdinand Schwenk <ferdinand.schwenk@emtrion.de>
# Copyright (c) 2014-2017 Manuel Traut <manut@linutronix.de>
# Copyright (c) 2017 Benedikt Spranger <b.spranger@linutronix.de>
# Copyright (c) 2017 Philipp Arras <philipp.arras@linutronix.de>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import urlparse
import urllib2

from elbepack.efilesystem import BuildImgFs
from elbepack.templates import (write_pack_template, get_preseed,
                                preseed_to_text)
from elbepack.shellhelper import CommandError


class DebootstrapException (Exception):
    def __init__(self):
        Exception.__init__(self, "Debootstrap Failed")


class BuildEnv ():
    def __init__(self, xml, log, path, build_sources=False, clean=False):

        self.xml = xml
        self.log = log
        self.path = path

        self.rfs = BuildImgFs(path, xml.defs["userinterpr"])

        if clean:
            self.rfs.rmtree("")

        # TODO think about reinitialization if elbe_version differs
        if not self.rfs.isfile("etc/elbe_version"):
            # avoid starting daemons inside the buildenv
            self.rfs.mkdir_p("usr/sbin")
            self.rfs.write_file(
                "usr/sbin/policy-rc.d",
                0o755,
                "#!/bin/sh\nexit 101\n")
            self.debootstrap()
            self.fresh_debootstrap = True
            self.need_dumpdebootstrap = True
        else:
            self.fresh_debootstrap = False
            self.need_dumpdebootstrap = False

        self.initialize_dirs(build_sources=build_sources)
        self.create_apt_prefs()

    def cdrom_umount(self):
        if self.xml.prj.has("mirror/cdrom"):
            cdrompath = self.rfs.fname("cdrom")
            self.log.do('umount "%s"' % cdrompath)

    def cdrom_mount(self):
        if self.xml.has("project/mirror/cdrom"):
            cdrompath = self.rfs.fname("cdrom")
            self.log.do('mkdir -p "%s"' % cdrompath)
            self.log.do('mount -o loop "%s" "%s"'
                        % (self.xml.text("project/mirror/cdrom"), cdrompath))

    def __enter__(self):
        if os.path.exists(self.path + '/../repo/pool'):
            self.log.do("mv %s/../repo %s" % (self.path, self.path))
            self.log.do('echo "deb copy:///repo %s main" > '
                        '%s/etc/apt/sources.list.d/local.list' % (
                            self.xml.text("project/suite"), self.path))
            self.log.do('echo "deb-src copy:///repo %s main" >> '
                        '%s/etc/apt/sources.list.d/local.list' % (
                            self.xml.text("project/suite"), self.path))
        self.cdrom_mount()
        self.rfs.__enter__()
        return self

    def __exit__(self, type, value, traceback):
        self.rfs.__exit__(type, value, traceback)
        self.cdrom_umount()
        if os.path.exists(self.path + '/repo'):
            self.log.do("mv %s/repo %s/../" % (self.path, self.path))
            self.log.do("rm %s/etc/apt/sources.list.d/local.list" % self.path)

    def debootstrap(self):

        cleanup = False
        suite = self.xml.prj.text("suite")

        primary_mirror = self.xml.get_primary_mirror(
            self.rfs.fname('/cdrom/targetrepo'))

        if self.xml.prj.has("mirror/primary_proxy"):
            os.environ["no_proxy"] = "10.0.2.2,localhost,127.0.0.1"
            proxy = self.xml.prj.text("mirror/primary_proxy")
            proxy = proxy.strip().replace("LOCALMACHINE", "localhost")
            os.environ["http_proxy"] = proxy
            os.environ["https_proxy"] = proxy
        else:
            os.environ["no_proxy"] = ""
            os.environ["http_proxy"] = ""
            os.environ["https_proxy"] = ""

        os.environ["LANG"] = "C"
        os.environ["LANGUAGE"] = "C"
        os.environ["LC_ALL"] = "C"
        os.environ["DEBIAN_FRONTEND"] = "noninteractive"
        os.environ["DEBONF_NONINTERACTIVE_SEEN"] = "true"

        self.log.h2("debootstrap log")

        arch = self.xml.text("project/buildimage/arch", key="arch")

        host_arch = self.log.get_command_out(
            "dpkg --print-architecture").strip()

        if not self.xml.is_cross(host_arch):
            # ignore gpg verification if install from cdrom, cause debootstrap
            # seems to ignore /etc/apt/trusted.gpg.d/elbe-keyring.gpg
            # 01/2017 manut
            if self.xml.has(
                    "project/noauth") or self.xml.has("project/mirror/cdrom"):
                cmd = 'debootstrap --no-check-gpg --arch=%s "%s" "%s" "%s"' % (
                    arch, suite, self.rfs.path, primary_mirror)
            else:
                cmd = 'debootstrap --arch=%s "%s" "%s" "%s"' % (
                    arch, suite, self.rfs.path, primary_mirror)

            try:
                self.cdrom_mount()
                self.log.do(cmd)
            except CommandError:
                cleanup = True
                raise DebootstrapException()
            finally:
                self.cdrom_umount()
                if cleanup:
                    self.rfs.rmtree("/")

            return

        if self.xml.has("project/noauth"):
            cmd = 'debootstrap --no-check-gpg --foreign ' \
                  '--arch=%s "%s" "%s" "%s"' % (arch, suite, self.rfs.path,
                                                primary_mirror)
        else:
            if self.xml.has("project/mirror/cdrom"):
                keyring = ' --keyring="%s/targetrepo/elbe-keyring.gpg"' % (
                    self.rfs.fname("cdrom"))
            else:
                keyring = ''
            cmd = 'debootstrap --foreign --arch=%s %s "%s" "%s" "%s"' % (
                arch, keyring, suite, self.rfs.path, primary_mirror)

        try:
            self.cdrom_mount()
            self.log.do(cmd)

            ui = "/usr/share/elbe/qemu-elbe/" + self.xml.defs["userinterpr"]

            if not os.path.exists(ui):
                ui = "/usr/bin/" + self.xml.defs["userinterpr"]

            self.log.do('cp %s %s' % (ui, self.rfs.fname("usr/bin")))

            if self.xml.has("project/noauth"):
                self.log.chroot(
                    self.rfs.path,
                    '/debootstrap/debootstrap --no-check-gpg --second-stage')
            else:
                self.log.chroot(self.rfs.path,
                                '/debootstrap/debootstrap --second-stage')

            self.log.chroot(self.rfs.path, 'dpkg --configure -a')

        except CommandError:
            cleanup = True
            raise DebootstrapException()
        finally:
            self.cdrom_umount()
            if cleanup:
                self.rfs.rmtree("/")

    def virtapt_init_dirs(self):
        self.rfs.mkdir_p("/cache/archives/partial")
        self.rfs.mkdir_p("/etc/apt/preferences.d")
        self.rfs.mkdir_p("/db")
        self.rfs.mkdir_p("/log")
        self.rfs.mkdir_p("/state/lists/partial")
        self.rfs.touch_file("/state/status")

    def import_keys(self):
        if self.xml.has('project/mirror/url-list'):
            for url in self.xml.node('project/mirror/url-list'):
                if url.has('key'):
                    keyurl = url.text('key').strip()    # URL to key
                    name = keyurl.split('/')[-1]        # Filename of key

                    myKey = urllib2.urlopen(keyurl).read()
                    self.log.do(
                        'echo "%s" > %s' %
                        (myKey, self.rfs.fname("tmp/key.pub")))
                    with self.rfs:
                        self.log.chroot(
                            self.rfs.path, 'apt-key add /tmp/key.pub')
                    self.log.do('rm -f %s' % self.rfs.fname("tmp/key.pub"))

    def initialize_dirs(self, build_sources=False):
        mirror = self.xml.create_apt_sources_list(build_sources=build_sources)

        if self.rfs.exists("etc/apt/sources.list"):
            self.rfs.remove("etc/apt/sources.list")

        self.rfs.write_file("etc/apt/sources.list", 0o644, mirror)

        self.rfs.mkdir_p("var/cache/elbe")

        preseed = get_preseed(self.xml)
        preseed_txt = preseed_to_text(preseed)
        self.rfs.write_file("var/cache/elbe/preseed.txt", 0o644, preseed_txt)
        with self.rfs:
            self.log.chroot(
                self.rfs.path, 'debconf-set-selections < %s' %
                self.rfs.fname("var/cache/elbe/preseed.txt"))

    def create_apt_prefs(self):

        filename = self.rfs.path + "/etc/apt/preferences"

        if os.path.exists(filename):
            os.remove(filename)

        self.rfs.mkdir_p("/etc/apt")

        pinned_origins = []
        if self.xml.has('project/mirror/url-list'):
            for url in self.xml.node('project/mirror/url-list'):
                if not url.has('binary'):
                    continue

                repo = url.node('binary')
                if 'pin' not in repo.et.attrib:
                    continue

                origin = urlparse.urlsplit(repo.et.text.strip()).hostname
                pin = repo.et.attrib['pin']
                if 'package' in repo.et.attrib:
                    package = repo.et.attrib['package']
                else:
                    package = '*'
                pinning = {'pin': pin,
                           'origin': origin,
                           'package': package}
                pinned_origins.append(pinning)

        d = {"xml": self.xml,
             "prj": self.xml.node("/project"),
             "pkgs": self.xml.node("/target/pkg-list"),
             "porgs": pinned_origins}

        write_pack_template(filename, "preferences.mako", d)

    def seed_etc(self):
        passwd = self.xml.text("target/passwd")
        self.log.chroot(
            self.rfs.path, """/bin/sh -c 'echo "%s\\n%s\\n" | passwd'""" %
            (passwd, passwd))

        hostname = self.xml.text("target/hostname")
        domain = self.xml.text("target/domain")

        self.log.chroot(
            self.rfs.path,
            """/bin/sh -c 'echo "127.0.0.1 %s.%s %s elbe-daemon" >> """
            """/etc/hosts'""" % (hostname, domain, hostname))

        self.log.chroot(
            self.rfs.path,
            """/bin/sh -c 'echo "%s" > /etc/hostname'""" % hostname)

        self.log.chroot(
            self.rfs.path,
            """/bin/sh -c 'echo "%s.%s" > """
            """/etc/mailname'""" % (hostname, domain))

        if self.xml.has("target/console"):
            serial_con, serial_baud = self.xml.text(
                "target/console").split(',')
            if serial_baud:
                self.log.chroot(
                    self.rfs.path,
                    """/bin/sh -c '[ -f /etc/inittab ] && """
                    """echo "T0:23:respawn:/sbin/getty -L %s %s vt100" >> """
                    """/etc/inittab'""" % (serial_con, serial_baud),
                    allow_fail=True)

                self.log.chroot(
                    self.rfs.path,
                    """/bin/sh -c """
                    """'[ -f /lib/systemd/system/serial-getty@.service ] && """
                    """ln -s /lib/systemd/system/serial-getty@.service """
                    """/etc/systemd/system/getty.target.wants/"""
                    """serial-getty@%s.service'""" % serial_con,
                    allow_fail=True)
            else:
                self.log.printo("parsing console tag failed, needs to be of "
                                "'/dev/ttyS0,115200' format.")
