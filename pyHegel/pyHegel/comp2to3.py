# -*- coding: utf-8 -*-

########################## Copyrights and license ############################
#                                                                            #
# Copyright 2023-2023  Christian Lupien <christian.lupien@usherbrooke.ca>    #
#                                                                            #
# This file is part of pyHegel.  http://github.com/lupien/pyHegel            #
#                                                                            #
# pyHegel is free software: you can redistribute it and/or modify it under   #
# the terms of the GNU Lesser General Public License as published by the     #
# Free Software Foundation, either version 3 of the License, or (at your     #
# option) any later version.                                                 #
#                                                                            #
# pyHegel is distributed in the hope that it will be useful, but WITHOUT     #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or      #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public        #
# License for more details.                                                  #
#                                                                            #
# You should have received a copy of the GNU Lesser General Public License   #
# along with pyHegel.  If not, see <http://www.gnu.org/licenses/>.           #
#                                                                            #
##############################################################################

# some of this codes comes for the module six
#   https://github.com/benjaminp/six

from __future__ import absolute_import, print_function, division
import sys
import warnings
import inspect
import types

is_py2 = sys.version_info[0] == 2
is_py3 = sys.version_info[0] == 3

def warn_deprecation(mess):
    # DeprecationWarning are not displayed by default, so use UserWarning instead
    #warnings.warn(mess, DeprecationWarning)
    warnings.warn(mess, UserWarning, 2)

def comp_execfile(filename, *args):
    if is_py2:
        execfile(filename, *args)
    else:
        # this break out of *args is prevent a syntax error when reading this module in python2
        # python3 accepts:
        #  exec(compile(open(filename, "rb").read(), filename, 'exec'), *args)
        N = len(args)
        if N == 0:
            exec(compile(open(filename, "rb").read(), filename, 'exec'))
        elif N == 1:
            exec(compile(open(filename, "rb").read(), filename, 'exec'), args[0])
        elif N == 2:
            exec(compile(open(filename, "rb").read(), filename, 'exec'), args[0], args[1])
        else:
            raise TypeError('Too many arguments')

if is_py2:
    import re
    _identifier_re = re.compile(r'[a-zA-Z_][a-zA-Z_0-9]*\Z')
    def isidentifier(s):
        """ python 2 identifier are ascii letters or _, and digits after the first character """
        res = _identifier_re.match(s)
        if res is None:
            return False
        return True
    def open_universal(name, mode, *args):
        mode += 'U'
        return open(name, mode, *args)
    #
    # Do the equivalent of  shutil.get_terminal_size
    #
    class Term_Size(object):
        def __init__(self, cols=80, rows=24):
            self.columns = cols
            self.lines = rows
        def __repr__(self):
            return "Term_Size(columns=%d, lines=%i)"%(self.columns, self.lines)
    import os
    import ctypes
    if os.name == 'nt':
        import ctypes.wintypes as wt
        import msvcrt
        class COORD(ctypes.Structure):
            _fields_ = [('X', wt.SHORT), ('Y', wt.SHORT)]
        class CONSOLE_SCREEN_BUFFER(ctypes.Structure):
            _fields_ = [('dwSize', COORD), ('dwCursorPosition', COORD),
                        ('wAttributes', wt.WORD), ('srWindow', wt.SMALL_RECT),
                        ('dwMaximumWindowSize', COORD)]
        GetConsoleScreenBufferInfo = ctypes.windll.kernel32.GetConsoleScreenBufferInfo
        GetConsoleScreenBufferInfo.restype = wt.BOOL
        GetConsoleScreenBufferInfo.argstype = [wt.HANDLE, ctypes.POINTER(CONSOLE_SCREEN_BUFFER)]
        def _get_terminal_size(fd):
            # This could genere IOError
            hndl = msvcrt.get_osfhandle(fd)
            csb = CONSOLE_SCREEN_BUFFER()
            if not GetConsoleScreenBufferInfo(hndl, ctypes.byref(csb)):
                return 0, 0
            #return csb.dwSize.X, csb.dwSize.Y # The Y size is the size of the buffer not the screen
            return csb.srWindow.Right - csb.srWindow.Left + 1, csb.srWindow.Bottom - csb.srWindow.Top + 1
    else:
        try:
            from termios import TIOCGWINSZ
            from fcntl import ioctl
        except ImportError:
            _get_terminal_size = lambda fd: (0, 0)
        else:
            class Term_ioctl_size(ctypes.Structure):
                _fields_ = [('ws_row', ctypes.c_ushort), ('ws_col', ctypes.c_ushort),
                            ('ws_xpixel', ctypes.c_ushort), ('ws_ypixel', ctypes.c_ushort)]
            def _get_terminal_size(fd):
                size = Term_ioctl_size()
                # this could generate an IOError
                ioctl(fd, TIOCGWINSZ, size, True)
                return size.ws_col, size.ws_row
    # this is based on the python 3 version of shutil.get_terminal_size
    def get_terminal_size(fallback=(80, 24)):
        try:
            columns = int(os.environ['COLUMNS'])
        except (KeyError, ValueError):
            columns = 0
        try:
            lines = int(os.environ['LINES'])
        except (KeyError, ValueError):
            lines = 0
        if columns <= 0 or lines <= 0:
            try:
                fd = sys.__stdout__.fileno()
                term_size = _get_terminal_size(fd)
            except (IOError, AttributeError):
                term_size = 0, 0
            if columns <= 0:
                columns = term_size[0] or fallback[0]
            if lines <= 0:
                lines = term_size[1] or fallback[1]
        return Term_Size(columns, lines)

if is_py3:
    from collections import namedtuple
    ArgSpec = namedtuple('ArgSpec', 'args varargs keywords defaults')
    def py3_inspect_getargspec(func):
        s = inspect.signature(func)
        args = []
        varargs = None
        keywords = None
        defaults = []
        for para in s.parameters.values():
            if para.kind not in [para.VAR_KEYWORD, para.VAR_POSITIONAL]:
                args.append(para.name)
            elif para.kind == para.VAR_POSITIONAL:
                varargs = para.name
            elif para.kind == para.VAR_KEYWORD:
                keywords = para.name
            elif para.default != para.empty:
                defaults.append(para.defaults)
        return ArgSpec(args, varargs, keywords, tuple(defaults))


if is_py3:
    import importlib
    import io
    from _thread import get_ident, error as thread_error
    import builtins
    reload = importlib.reload
    string_types = (str,)
    string_bytes_types = (str,bytes)
    bytes_type = bytes
    def StringIO(init=''):
        # Disable newline conversion
        return io.StringIO(init, newline='')
    unicode_type = str
    xrange = range
    string_upper = lambda s: s.upper()
    builtins_set = builtins.set
    from collections.abc import Iterator
    isidentifier = lambda s: s.isidentifier()
    inspect_getargspec = py3_inspect_getargspec
    open_universal = open
    from shutil import get_terminal_size
    int2byte = lambda x: bytes([x])

else:
    from StringIO import StringIO
    from thread import get_ident, error as thread_error
    import string
    import __builtin__
    reload = reload
    string_types = (basestring,)
    string_bytes_types = (basestring,)
    bytes_type = str
    unicode_type = unicode
    xrange = xrange
    string_upper = string.upper
    builtins_set = __builtin__.set
    from collections import Iterator
    inspect_getargspec = inspect.getargspec
    # This replaces the python 2 with the equivalent from python 3.
    # Note that for text this forces unicode strings
    # For text it turns on by default universal newlines mode
    # But it also handles line buffering correctly also in windows (which the
    # default open does not because windows does not do line buffering).
    # It also allows using a encoding.
    import io
    open = io.open
    int2byte = lambda x: chr(x)

open_utf8 = lambda *args, **kwargs: open(*args, encoding='utf-8')

def fu(s, encoding='utf-8'):
    """ Make sure string is unicode """
    if isinstance(s, bytes_type):
        return s.decode(encoding)
    else:
        return s

def fb(b, encoding='utf-8'):
    """ Make sure string is byte """
    if isinstance(b, unicode_type):
        return b.encode(encoding)
    else:
        return b

def write_unicode_byte(f, s):
    f.write(fu(s))

def make_str(s, encoding='utf-8'):
    """ returns str in python2 (bytes) and str in python3 (unicode) """
    if is_py2:
        return fb(s, encoding=encoding)
    else:
        return fu(s, encoding=encoding)

# This is taken from the module six
#  https://github.com/benjaminp/six/
# Copyright (c) 2010-2020 Benjamin Peterson
def with_metaclass(meta, *bases):
    """Create a base class with a metaclass."""
    # This requires a bit of explanation: the basic idea is to make a dummy
    # metaclass for one level of class instantiation that replaces itself with
    # the actual metaclass.
    class metaclass(type):

        def __new__(cls, name, this_bases, d):
            if sys.version_info[:2] >= (3, 7):
                # This version introduced PEP 560 that requires a bit
                # of extra care (we mimic what is done by __build_class__).
                resolved_bases = types.resolve_bases(bases)
                if resolved_bases is not bases:
                    d['__orig_bases__'] = bases
            else:
                resolved_bases = bases
            return meta(name, resolved_bases, d)

        @classmethod
        def __prepare__(cls, name, this_bases):
            return meta.__prepare__(name, bases)
    return type.__new__(metaclass, 'temporary_class', (), {})

if is_py3:
    from enum import IntEnum, IntFlag, EnumMeta
else:
    from enum import IntEnum, EnumMeta

    def _IntFlag__new__(cls, value):
        try:
            return IntEnum.__new__(cls, value)
        except ValueError:
            nv = int.__new__(cls, value)
            # now lets calculate the correct name
            if value == 0:
                name = ''
            else:
                names = []
                values = []
                val = 0
                for elem in cls:
                    elval = elem.value
                    if (value & elval) == elval:
                        names.append(elem.name)
                        values.append(elval)
                        val |= elval
                # now simplify. This is not done in python 3 enum.
                # not that if you have a=7, b=8 and c=9
                # it will use a|c for 15 instead of a|b
                keep = []
                N = len(names)
                for i in range(N):
                    vi = values[i]
                    if vi == 0:
                        continue
                    i_ok = True
                    for j in range(i+1, N):
                        vj = values[j]
                        if vi & vj == vi:
                            # vj contains at least vi
                            # so we do not need to keep it.
                            i_ok = False
                            break
                    if i_ok:
                        keep.append(i)
                # deal with missing flag names
                unnamed = value ^ val
                if unnamed:
                    if len(keep):
                        names.append(str(unnamed))
                        keep.append(N)
                    else:
                        names = []
                name = '|'.join(names[i] for i in keep)
            nv._name_ = name
            nv._value_ = value
            nv.__objclass__ = cls
            nv.__init__(value)
            cls._value2member_map_[value] = nv
            return nv

    class EnumFlagMeta(EnumMeta):
        def __new__(metacls, cls, bases, classdict):
            cls = super(EnumFlagMeta, metacls).__new__(metacls, cls, bases, classdict)
            # Need staticmethod here. It it not needed when __new__ is defined inside
            # a class definition. Be here we change it afterwards so it is required.
            # It needs to be done here, because the Meta class overwrites the
            # class __new__ with the Enum.__new__.
            cls.__new__ = staticmethod(_IntFlag__new__)
            return cls
        def __contains__(cls, value):
            if isinstance(value, cls):
                return True
            return value in cls._value2member_map_

    class IntFlag(IntEnum):
        __metaclass__ = EnumFlagMeta
        def _get_value(self, flag):
            if isinstance(flag, self.__class__):
                other_val = flag._value_
            elif isinstance(flag, int):
                other_val = flag
            else:
                 return NotImplemented
            if other_val is None or self._value_ is None:
                raise TypeError("None cannot be combined")
            return other_val
        def __or__(self, other):
            other_val = self._get_value(other)
            if other_val is NotImplemented:
                return NotImplemented
            return self.__class__(self._value_ | other_val)
        __ror__ = __or__
        def __and__(self, other):
            other_val = self._get_value(other)
            if other_val is NotImplemented:
                return NotImplemented
            return self.__class__(self._value_ & other_val)
        __rand__= __and__
        def __xor__(self, other):
            other_val = self._get_value(other)
            if other_val is NotImplemented:
                return NotImplemented
            return self.__class__(self._value_ ^ other_val)
        __rxor__= __xor__
        def __invert__(self):
            if self._value_ is None:
                raise TypeError("None cannot be inverted")
            return self.__class__(~self._value_)
        # already have __nonzero__ from int
        def __contains__(self, other):
            """ Returns True if self has at least the same flags as other """
            if not isinstance(other, self.__class__):
                raise TypeError("unsupported operand type")
            return other._value_ & self._value_ == other._value_
        def __repr__(self):
            cls_name = self.__class__.__name__
            if self.name == "":
                return "<%s: %s>" % (cls_name, repr(self._value_))
            else:
                return super(IntFlag, self).__repr__()

# Differences between python2 and 3
# in python 3 both IntEnum and IntFlag return str of the int for __str__
#                 in ptyhon 2 instead it returns representation of the item
#                 This has to do with pickling which is not taken care of here.
# in python 3 for IntFlag you can iterate on the instances to get names of bits
#                and len returns the bit_count if the instance
#                it also keeps track of mask of all the flags
#                and a mask of all the single bit flags.
#                for the list _member_names_ that is used in __iter__ it only
#                  includes single_bit values

if is_py3:
    def reraise(tp, value, tb=None):
        try:
            if isinstance(tp, BaseException):
                if value is not None:
                    raise ValueError('Invalid call to reraise')
                value = tp
            elif value is None:
                value = tp()
            elif isinstance(value, tuple):
                value = tp(*value)
            else:
                value = tp(value)
            if value.__traceback__ is not tb:
                raise value.with_traceback(tb)
            raise value
        finally:
            value = None
            tb = None

else:
    def exec_(_code_, _globs_=None, _locs_=None):
        """Execute code in a namespace."""
        if _globs_ is None:
            frame = sys._getframe(1)
            _globs_ = frame.f_globals
            if _locs_ is None:
                _locs_ = frame.f_locals
            del frame
        elif _locs_ is None:
            _locs_ = _globs_
        exec("""exec _code_ in _globs_, _locs_""")

    exec_("""def reraise(tp, value, tb=None):
    try:
        raise tp, value, tb
    finally:
        tb = None
""")


def repr_number(val):
    ret = repr(val)
    if is_py3:
        # handle newer numpy which returns np.float64(1.0) like values
        # with repr. Can than use str instead but I cannot check for the
        # version since np.set_printoptions(legacy='1.13') can change the behavior.
        # Also that old version, and str on python 2.7 for floats, do not return
        # enough digit so those require repr
        # np.generic is the root of the scalar values in numpy
        import numpy as np
        if isinstance(val, np.generic) and ret.startswith('np.'):
            ret = str(val)
    # clean up long int (python 2)
    if is_py2:
        if isinstance(val, long):
            ret = ret.rstrip('L')
    return ret

def repr_or_string(val):
    if isinstance(val, string_bytes_types):
        return val
    return repr_number(val)

def str_or_repr(s):
    """ Always returns a str type (use repr if needed) """
    if not isinstance(s, str):
        return repr(s)
    else:
        return s

def repr_or_string_unicode(val):
    return fu(repr_or_string(val))

