#!/usr/bin/env python
#
# ELBE - Debian Based Embedded Rootfilesystem Builder
# Copyright (C) 2016  Linutronix GmbH
#
# This file is part of ELBE.
#
# ELBE is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ELBE is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ELBE.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import npyscreen
from npyscreen import TitleText, TitleSelectOne

from mako import exceptions
from mako.template import Template
from shutil import copyfile

from elbepack.directories import mako_template_dir

def template (deb, fname):
    return Template(filename=fname).render(**deb)

class Debianize (npyscreen.NPSApp):
    def __init__ (self):
        self.deb = { }
        npyscreen.NPSApp.__init__ (self)

    def main (self):
        self.w = npyscreen.Form (name="ELBE Debianize")
        self.p_name    = self.w.add (TitleText, name="Name:",    value="elbe")
        self.p_version = self.w.add (TitleText, name="Version:", value="1.0")
        self.p_arch    = self.w.add (TitleSelectOne, name="Arch:",
          values = ["armhf","armel","amd64","i586","powerpc"], scroll_exit=True)
        self.source_format = self.w.add (TitleSelectOne, name="Format:",
          values = ["native","git","quilt"], scroll_exit=True)
        self.distro = self.w.add (TitleSelectOne, name="Release:",
          values = ["stable","oldstable","testing","unstable","experimental"], scroll_exit=True)
        self.m_name    = self.w.add (TitleText, name="Maintainer:", value="Max Mustermann")
        self.m_mail    = self.w.add (TitleText, name="Mail:",       value="max@mustermann.org")
        self.gui ()
        self.w.edit ()

    def save (self):
        self.deb['k_name']       = self.p_name.get_value ()
        self.deb['k_debversion'] = self.p_version.get_value ()
        self.deb['k_debarch']    = self.p_arch.get_value ()
        self.deb['m_name']       = self.m_name.get_value ()
        self.deb['m_mail']       = self.m_mail.get_value ()
        self.deb['source_format']= self.source_format.get_value ()
        self.deb['distro']       = self.distro.get_value ()
        self.debianize ()

class Autotools (Debianize):
    def __init__ (self):
        print ('autotools not supported at the moment')
        sys.exit (-2)

class Kernel (Debianize):
    def __init__ (self):
        if os.path.exists ('debian'):
            print 'debian already exists, nothing to do'
            sys.exit (-1)
        Debianize.__init__ (self)

    def gui (self):
        self.loadaddr  = self.w.add (TitleText, name="Loadaddress:", value="0x800800")
        self.defconfig = self.w.add (TitleText, name="defconfig:", value="omap2plus_defconfig")
        self.img_type  = self.w.add (TitleSelectOne, name="Image Format:",
          values = ["zImage","uImage","Image"], scroll_exit=True)
        self.cross     = self.w.add (TitleText, name="CROSS_COMPILE", value="arm-linux-gnueabihf-")
        self.cross     = self.w.add (TitleText, name="Kernel Version", value="4.4")

    def debianize (self):
        if self.deb['k_debarch'] == 'armhf':
            self.deb['k_arch'] = 'arm'
        elif self.deb['k_debarch'] == 'armel':
            self.deb['k_arch'] = 'arm'
        else:
            self.deb['k_arch'] = self.deb['k_debarch']

        self.deb['loadaddr']      = self.loadaddr.get_value ()
        self.deb['defconfig']     = self.defconfig.get_value ()
        self.deb['imgtype']       = self.imgtype.get_value ()
        self.deb['cross_compile'] = self.cross.get_value ()
        self.deb['k_version']     = self.k_version.get_value ()

        os.mkdir ('debian')
        os.mkdir ('debian/source')
        tmpl_dir = os.path.join(mako_template_dir, 'debianize/kernel')
        pkg_name = self.deb['k_name']+'-'+self.deb['k_version']

        for tmpl in ['control', 'rules']:
            with open (os.path.join('debian/', tmpl), 'w') as f:
                mako = os.path.join(tmpl_dir, tmpl+'.mako')
                f.write (template(self.deb, mako))

        with open ('debian/source/format', 'w') as f:
            mako = os.path.join(tmpl_dir, 'format.mako')
            f.write (template(self.deb, mako))

        cmd = 'dch --package linux-' + pkg_name + ' -v ' + self.deb['k_debversion'] + ' --create -M -D ' + self.deb['distro'] + ' "generated by elbe debianize"'
        os.system (cmd)

        copyfile (os.path.join(tmpl_dir, 'copyright'), 'debian/copyright')
        copyfile (os.path.join(tmpl_dir, 'linux-image.install'),
                  'debian/linux-image-'+pkg_name+'.install')
        copyfile (os.path.join(tmpl_dir, 'linux-headers.install'),
                  'debian/linux-headers-'+pkg_name+'.install')

        with open ('debian/compat', 'w') as f:
            f.write ('9')



#TODO before adding another helper, refactor the code to be 'plugin-like',
# see finetuning for example.
debianizer = {'kernel':    Kernel,
              'autotools': Autotools}

files = {'kernel': ['Kbuild', 'Kconfig', 'MAINTAINERS', 'REPORTING-BUGS'],
         'autotools': ['configure.ac'] }

def run_command ( args ):
    for key in files.keys ():
       match = True
       for f in files[key]:
           if not os.path.exists (f):
               match = False
       if match:
           wizzard = debianizer[key] ()
           wizzard.run ()
           wizzard.save ()
           sys.exit (0)

    print ("this creates a debinization of a kernel source")
    print ("please run the command from kernel source dir")
    sys.exit (-2)