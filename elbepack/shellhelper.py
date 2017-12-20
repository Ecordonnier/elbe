# ELBE - Debian Based Embedded Rootfilesystem Builder
# Copyright (c) 2014-2015 Torben Hohn <torbenh@linutronix.de>
# Copyright (c) 2014 Ferdinand Schwenk <ferdinand.schwenk@emtrion.de>
# Copyright (c) 2016-2017 Manuel Traut <manut@linutronix.de>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from subprocess import Popen, PIPE, STDOUT


class CommandError(Exception):
    def __init__(self, cmd, returncode):
        Exception.__init__(self)
        self.returncode = returncode
        self.cmd = cmd

    def __repr__(self):
        return "Error: %d returned from Command %s" % (
            self.returncode, self.cmd)


def system(cmd, allow_fail=False):
    ret = os.system(cmd)

    if ret != 0:
        if not allow_fail:
            raise CommandError(cmd, ret)


def command_out(cmd, input=None, output=PIPE):
    if input is None:
        p = Popen(cmd, shell=True, stdout=output, stderr=STDOUT)
        out, stderr = p.communicate()
    else:
        p = Popen(cmd, shell=True, stdout=output, stderr=STDOUT, stdin=PIPE)
        out, stderr = p.communicate(input=input)

    return p.returncode, out


def system_out(cmd, input=None, allow_fail=False):
    code, out = command_out(cmd, input)

    if code != 0:
        if not allow_fail:
            raise CommandError(cmd, code)

    return out


def command_out_stderr(cmd, input=None):
    if input is None:
        p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
        output, stderr = p.communicate()
    else:
        p = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE, stdin=PIPE)
        output, stderr = p.communicate(input=input)

    return p.returncode, output, stderr


def system_out_stderr(cmd, input=None, allow_fail=False):
    code, out, err = command_out(cmd, input)

    if code != 0:
        if not allow_fail:
            raise CommandError(cmd, code)

    return out, err
