# -*- coding: utf-8 -*-
########################## Copyrights and license ############################
#                                                                            #
# Copyright 2025       Christian Lupien <christian.lupien@usherbrooke.ca>    #
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

from weakref import proxy

import ctypes
from ctypes import CDLL, Structure, POINTER, memmove, byref, cast,\
                    sizeof, create_string_buffer, Array, _Pointer,\
                    c_char, c_wchar, create_unicode_buffer,\
                    c_short, c_ushort, c_byte, c_ubyte,\
                    c_int, c_uint, c_long, c_ulong,\
                    c_longlong, c_ulonglong,\
                    c_float, c_double,\
                    c_uint8, c_uint16, c_uint32, c_uint64,\
                    c_int8, c_int16, c_int32, c_int64, c_void_p,\
                    c_char_p as c_null_term_string,\
                    c_wchar_p as c_null_term_wstring,\
                    addressof

import numpy.ctypeslib
from numpy.ctypeslib import as_ctypes, as_array, as_ctypes_type

from .comp2to3 import fu, fb, is_py3, IntEnum as _IntEnum, IntFlag as _IntFlag,\
                    with_metaclass
from .config import Addition_dll_search

from .types import _GeneralImproved

try:
    warnings
    #print("We are reloading this module, no need to add the filter again")
except NameError:
    import warnings
    # The RE are done with match (they have to match from the start of the string)
    # This filters a warning when using ctypeslib as_array on a ctypes array.
    #  http://stackoverflow.com/questions/4964101/pep-3118-warning-when-using-ctypes-array-as-numpy-array
    warnings.filterwarnings('ignore', 'Item size computed from the PEP 3118 buffer format string does not match the actual item size.', RuntimeWarning, r'numpy\.ctypeslib')


# Note that ctypes does have ways to automate converion to ctypes:
#  There is the from_param staticmethod that is used when having a class used in arg_types
# and there is the _as_parameter_ attribute (get be a property) of an object.
# However, these do not help the converion back into python.
# Hence all the work we do here to perform both.

# The return value is returned in these ways (from Modules/_ctypes/callproc.c):
#  - if restype is not given: returns a python integer
#  - if restype is None: returns None
#  - if restype is a simple ctypes, calls the internal equivalent of .value and
#     pass that to the checker and return the checker result.
#  - if restype is another kind of ctype, returns an instance of that, then
#     pass that to the checker and return the checker result.
#  - Otherwise calls restype and returns the result (considering the return to be an integer)
# The checker is something internal. It is not the errcheck function which is run after
# that if it exists. errcheck is executed for any if the above conditions.
# The checker can be specified in the restype type with a _check_retval_ class method.
# That is used in the WinDLL HRESULT type.

class DefaultVal(object):
    """ Use this to have the default initializer behavior for a ctype object """
    pass

class General_CType(object):
    def ctype(self):
        """
        This should return the type that will be used internally for the
        function argtype.
        """
        raise NotImplementedError
    def initialize(self, val=None, cache=None):
        """
        This should return the value to use in the call to the ctype function.
        """
        raise NotImplementedError
    def extract(self, ctype_val, N=None, size=None, cache=None):
        """
        This should take the ctype value after the call and return a proper python value.
        """
        raise NotImplementedError
    def len(self, ctype_val):
        raise NotImplementedError
    def sizeof(self, ctype_val):
        raise NotImplementedError
    # default implementation for use in types StructureImproved
    def encode(self, val):
        return self.initialize(val)
    def decode(self, ctype_val):
        return self.extract(ctype_val)

def get_real_base_type(base_type):
    if isinstance(base_type, General_CType):
        return base_type.ctype()
    return base_type

def get_address(c_obj):
    """ Get the address pointed to for a POINTER type
        otherwise return the address of the object
    """
    # cannot use hasattr because that does a getattr
    # which can fail when pointer address is 0 (None)
#        if hasattr(c_obj, 'contents'):
#        if 'contents' in dir(c_obj):
    if isinstance(c_obj, _Pointer):
        if c_obj: # not NULL
            return cast(c_obj, c_void_p).value
        return None
    if isinstance(c_obj, c_void_p):
        return c_obj.value
    return addressof(c_obj)


class Buffer(General_CType):
    """ This is a fancier Array like type.
        It allows more flexibility for the generated wrappers.
    """
    def __init__(self, size=None, base_type=c_char, adjust_return=True,
                 allow_any_size=False, raw=False, encoding='utf-8', null_string_len=False,
                 null_terminated_array=False, use_ndarray=False):
        """
        When size is None, it will generate an object of the size given during initialize.
        adjust_return makes it crop the returned object to the correct length.
        allow_any_size makes the internal ctypes argtype be a pointer, so it accepts any array size.
             This also occurs when size=None.
        raw applies to c_char arrays. it is used to return the raw values instead of the null-terminated string interpreted one.
            When false the string is conv from/to unicode. if 'byte', the null-terminated string is kept as byte for input and output.
        With size=None and base_type=c_char, the object is generated with the correct length.
        With base_type=c_char (or c_wchar), null_string_len=True returns the python string len +1.
        if null_terminated_array is True, it both sets a null value as the last one and gets until it sees a null value.
                                This will only apply for size=None
                                This can be a function taking a ctype value (could be a structure) and returning
                                something interpreted as a boolean. For a structure you could just return an item
                                for example:
                                  lambda incoming_stuct: incoming_struct.some_element
        use_ndarray, when True, will reuse the numpy buffer on call and use the ctypes buffer for an ndarray on return.
        """
        self.size = size
        self.base_type = base_type
        base_type = get_real_base_type(base_type)
        self.base_ptr = POINTER(base_type)
        if size is not None:
            self.base_N = base_type*size
        if size is None or allow_any_size:
            self.base = self.base_ptr
        else:
            self.base = self.base_N
        self.adjust_return = adjust_return
        self.raw = raw
        self.encoding = encoding
        self.null_string_len = null_string_len
        self.null_terminated_array = null_terminated_array
        self.use_ndarray = use_ndarray

    def ctype(self):
        return self.base

    def initialize(self, val=DefaultVal, cache=None):
        """ val=None sends a Null pointer. The Buffer needs size=None or allow_any_size=True """
        if val is None:
            return self.base_ptr()
        base_type = self.base_type
        real_base_type = get_real_base_type(base_type)
        if self.size is not None:
            v = self.base_N()
            if cache is not None:
                cache[get_address(v)] = v
        elif base_type == c_char:
            # size is None here
            if val is DefaultVal:
                raise ValueError('A value is required in this configuration.')
            val = fb(val, self.encoding)
            v = create_string_buffer(val)
            if cache is not None:
                cache[get_address(v)] = v
            return v
        elif base_type == c_wchar:
            # size is None here
            if val is DefaultVal:
                raise ValueError('A value is required in this configuration.')
            val = fu(val, self.encoding)
            v = create_unicode_buffer(val)
            if cache is not None:
                cache[get_address(v)] = v
            return v
        if val is not DefaultVal:
            if self.size is not None:
                if self.raw is False and base_type == c_char:
                    val = fb(val, self.encoding)
                if self.raw is False and base_type == c_wchar:
                    val = fu(val, self.encoding)
                if hasattr(v, 'value'):
                    # for things like c_char*N, w_char*N
                    v.value = val
                else:
                    # for other arrays
                    N = len(val)
                    if N > self.size:
                        raise ValueError('too many values to fit in array (%i > %i)'%(N, self.size))
                    if isinstance(base_type, General_CType):
                        for i in range(N):
                            v[i] = base_type.initialize(val[i], cache=cache)
                    elif self.use_ndarray and isinstance(val, numpy.ndarray) and val.flags.c_contiguous and \
                             as_ctypes_type(val.dtype) == real_base_type and N == self.size:
                        v = as_ctypes(val)
                        # numpy array saved as v.__keep internaly
                    else:
                        v[:N] = val[:N]
            else:
                # size is None
                init_done = False
                if self.use_ndarray and isinstance(val, numpy.ndarray) and val.flags.c_contiguous and \
                        as_ctypes_type(val.dtype) == real_base_type:
                    v = as_ctypes(val)
                    # numpy array saved as v.__keep internaly
                    init_done = True
                else:
                    N = len(val)
                    if self.null_terminated_array:
                        N += 1
                    size = sizeof(real_base_type)
                    v = (real_base_type*N)()
                if cache is not None:
                    cache[get_address(v)] = v
                if not init_done:
                    for i, vv in enumerate(val):
                        if isinstance(vv, real_base_type) and sizeof(vv) == size:
                            memmove(byref(v[i]), byref(vv), size)
                        elif isinstance(base_type, General_CType):
                            v[i] = self.base_type.initialize(vv, cache=cache)
                        else:
                            v[i] = vv
        else:
            if self.size is None:
                raise ValueError('Cannot handle DefaultVal when not given any size. Either give it a size or some initial values')
            # val is DefaultVal and there is a size. v exists
            if isinstance(base_type, General_CType):
                for i in range(self.size):
                    v[i] = self.base_type.initialize(cache=cache)
        return v

    def extract(self, ctype_val, N=None, size=None, cache=None):
        base_type = self.base_type
        real_base_type = get_real_base_type(base_type)
        if N is None and size is not None:
            # If N exist, do not overwrite it.
            N = size/sizeof(real_base_type)
        if isinstance(ctype_val, _Pointer):
            # This is a pointer type, check for NULL before dereferencing
            address = get_address(ctype_val)
            #address = cast(ctype_val, c_void_p).value
            # could also check the truth value of ctype_val. It is False
            # when address is None.
            if address is None:
                return None
            # ok so recast to correct size/type
            # But from_address makes it loose access to the reserverd memory
            # so if possible instead prefer to use the cached value.
            if cache is not None and address in cache:
                ctype_val = cache[address]
            elif self.size is not None:
                ctype_val = self.base_N.from_address(address)
            elif N is not None:
                ctype_val = (real_base_type*N).from_address(address)
            elif real_base_type == c_char:
                ctype_val = cast(ctype_val, c_null_term_string)
            elif real_base_type == c_wchar:
                ctype_val = cast(ctype_val, c_null_term_wstring)
            elif self.null_terminated_array:
                if self.null_terminated_array is True and issubclass(real_base_type, _Pointer):
                    # This works for real_base_type a subclass of _Pointer
                    # It returns False when the pointer is to Null
                    detect = lambda x: bool(x)
                elif self.null_terminated_array is True:
                    raise ValueError("""null_terminated_array needs to be a function to identify the end of array.""")
                else:
                    detect = self.null_terminated_array
                i = 0
                while detect(ctype_val[i]):
                    i += 1
                N = i
                ctype_val = (real_base_type*N).from_address(address)
            else:
                raise ValueError('Can not handle pointer to unknown size')
        if self.base_type == c_char:
            if self.raw is True:
                v = ctype_val.raw
            else:
                v = ctype_val.value
                if self.raw != 'byte':
                    v = fu(v, self.encoding)
        elif self.base_type == c_wchar:
            v = ctype_val.value
        else:
            if self.use_ndarray:
                v = as_array(ctype_val)
                # ctype_val saved as v.base (memory view of v.base.obj)
            else:
                v = list(ctype_val)
                if isinstance(base_type, General_CType):
                    v = [base_type.extract(vv, cache=cache) for vv in v]
        if N is not None:
            if not self.adjust_return and len(v) != N:
                raise RuntimeError('Unexpected length to data')
            return v[:N]
        return v

    def len(self, ctype_val):
        if ctype_val:
            if self.base_type in [c_char, c_wchar] and self.null_string_len:
                lf = len(ctype_val)
                ls = len(ctype_val.value)
                if ls+1 > lf:
                    raise ValueError('The current string does not contain the null.')
                return ls+1
            return len(ctype_val)
        return 0

    def sizeof(self, ctype_val):
        if ctype_val:
            return sizeof(ctype_val)
        return 0

class Buffer_as_Byte(General_CType):
    """
    This class does the same as Buffer. The internal handling is done by Buffer,
    so it has the same options, but it modifies the type to another one.
    This is useful in Stuctures for example where arrays of char are automatically converted
    to null terminated strings. To avoid that and have the full Buffer options and conversions,
    this class tells the structure that we use bytes but the internal handling is done with char.
    """
    def __init__(self, size=None, base_type=c_char, other_type='auto', *args, **kwargs):
        """
        Uses all the same parameters as Buffer. See it for full documentation.
        The only different parameter is other_type.
        It can be some type or auto where it will by byte for char and something of the correct
        length for wchar.
        """
        self.buf = Buffer(size=size, base_type=base_type, *args, **kwargs)
        if other_type == 'auto':
            N = sizeof(base_type)
            if base_type == c_char or N == 1:
                other_type = c_byte
            else:
                d = {2: c_uint16, 4: c_uint32, 8: c_uint64}
                if N not in d:
                    raise ValueError('Unexpexted value size.')
                other_type = d[N]
        self.base_type = base_type
        self.other_type = other_type

    def change_type(self, incoming, to):
        # incoming can be a type or an instance
        if isinstance(incoming, type):
            if issubclass(incoming, _Pointer):
                return POINTER(to)
        elif isinstance(incoming, _Pointer):
            return POINTER(to)
        # array
        N = incoming._length_
        return to*N

    def do_conv(self, incoming, to):
        new_type = self.change_type(incoming, to)
        if issubclass(new_type, _Pointer):
            return cast(incoming, new_type)
        # array
        return new_type.from_buffer(incoming)

    def ctype(self):
        t = self.buf.ctype()
        new_type = self.change_type(t, self.other_type)
        return new_type

    def initialize(self, val=None, cache=None):
        ret = self.buf.initialize(val, cache)
        return self.do_conv(ret, self.other_type)

    def extract(self, ctype_val, N=None, size=None, cache=None):
        ctype_val = self.do_conv(ctype_val, self.base_type)
        return self.buf.extract(ctype_val, N, size, cache)

    def len(self, ctype_val):
        ctype_val = self.do_conv(ctype_val, self.base_type)
        return self.buf.len(ctype_val)

    def sizeof(self, ctype_val):
        ctype_val = self.do_conv(ctype_val, self.base_type)
        return self.buf.sizeof(ctype_val)


class General_Conv(General_CType):
    """
    This class allows changing the return of a base ctypes into some more general python python.
    For example it is used in the IntEnumC and IntFlagC types
    """
    def __init__(self, base, ptype=None, decoder=None, encoder=None, force_check=False):
        """
        base is the ctype base value.
        ptype is the python type (could be enum, bool), when given can provide automatic conversion.
        force_check will raise ValueError if the input is not an instance of ptype (if provided)
        for decoder either provide a decoder function in init or
        overwrite the decode mehtod.
        It is the same for encoder.
        functions signature: encoder(val, basetype)
                             decoder(ctype_val, N, size)
        """
        self.base = base
        self._decoder = decoder
        self._encoder = encoder
        self._ptype = ptype
        self._force_check = force_check
    def ctype(self):
        return self.base
    def encoder(self, val):
        if self._ptype is not None and self._force_check:
            if not isinstance(val, self._ptype):
                raise ValueError('The value is not of the correct type. Expecting "%s"'%self._ptype)
        if self._encoder is not None:
            return self._encoder(val, self.base)
        return self.base(val)
    def decoder(self, ctype_val, N, size):
        if self._decoder is not None:
            return self._decoder(ctype_val, N, size)
        if self._ptype is not None:
            return self._ptype(ctype_val)
        return ctype_val
    def initialize(self, val=DefaultVal, cache=None):
        if val is DefaultVal:
            v = self.base()
        else:
            v = self.encoder(val)
        return v
    def extract(self, ctype_val, N=None, size=None, cache=None):
        return self.decoder(ctype_val, N, size)
    def len(self, ctype_val):
        return len(ctype_val)
    def sizeof(self, ctype_val):
        return sizeof(ctype_val)

class General_POINTER(General_CType):
    def __init__(self, base, accept_None=True):
        self.base = base
        if isinstance(base, General_CType):
            self.param = POINTER(base.base)
        else:
            self.param = POINTER(base)
        self.accept_None = accept_None
    def ctype(self):
        return self.param
    def initialize(self, val=DefaultVal, cache=None):
        if self.accept_None and val is None:
            # calling the POINTER type without a parameter generates a null pointer.
            return self.param()
        else:
            if isinstance(self.base, General_CType):
                base = self.base.initialize
            else:
                base = self.base
            if val is DefaultVal:
                v = base()
            else:
                if isinstance(val, self.param):
                    return val
                elif isinstance(val, self.base):
                    v = val
                elif issubclass(self.base, _GeneralImproved):
                    v = base()
                    v.update(val)
                else:
                    v = base(val)
            return self.param(v)
    def extract(self, ctype_val, N=None, size=None, cache=None):
        if ctype_val:
            # the pointer ctypes_val is True when not a null pointer.
            val = ctype_val.contents
            if isinstance(self.base, General_CType):
                return self.base.extract(val, N, size)
            if isinstance(val, Structure):
                return val
            return val.value
        return None
    def sizeof(self, obj):
        if isinstance(self.base, General_CType):
            return self.base.sizeof(obj)
        return sizeof(obj.contents)
    def len(self, obj):
        if isinstance(self.base, General_CType):
            return self.base.len(obj)
        return len(obj.contents)

class EnumFlag_Ctype(General_Conv):
    def __init__(self, ptype, force_check=True, c_type=c_int32):
        super(EnumFlag_Ctype, self).__init__(c_type, ptype, force_check=force_check)
        #self.p = General_POINTER(self)
    def decode(self, val): # this is called by ImprovedStructure
        try:
            v = self._ptype(val)
        except ValueError:
            # We come here if the value is not part of the enum
            # In this case we return the val instead of generating an error.
            v = val
        return v
    def decoder(self, ctype_val, N, size):
        # accept both ctype (which as .value) and python int (whic
        #  might be the case for a function return value)
        try:
            v = ctype_val.value
        except AttributeError:
            v = ctype_val
        return self.decode(v)

class EnumMeta_CType(type(_IntEnum)):
    def __new__(metacls, cls, bases, classdict):
        c_type = classdict.pop('__ctype__', c_int32)
        force_check = classdict.pop('__force_check__', True)
        newcls = super(EnumMeta_CType, metacls).__new__(metacls, cls, bases, classdict)
        newcls.ctype = EnumFlag_Ctype(newcls, c_type=c_type, force_check=force_check)
        newcls.pointer = General_POINTER(newcls.ctype)
        return newcls

class FlagMeta_CType(type(_IntFlag)):
    def __new__(metacls, cls, bases, classdict):
        c_type = classdict.pop('__ctype__', c_int32)
        force_check = classdict.pop('__force_check__', True)
        newcls = super(FlagMeta_CType, metacls).__new__(metacls, cls, bases, classdict)
        newcls.ctype = EnumFlag_Ctype(newcls, c_type=c_type, force_check=force_check)
        newcls.pointer = General_POINTER(newcls.ctype)
        return newcls

class IntEnumC(with_metaclass(EnumMeta_CType, _IntEnum)):
    """
    This enum contains members .ctype and .pointer that can be used for wrappers.
    To overwrite the internal ctype of c_int32 add a __ctype__ attribute with the correct
    type.
    To overwrite the force_check of General_Conv, provide a __force_check__ attribute.
    """

class IntFlagC(with_metaclass(FlagMeta_CType, _IntFlag)):
    """
    This enum contains members .ctype and .pointer that can be used for wrappers.
    To overwrite the internal ctype of c_int32 add a __ctype__ attribute with the correct
    type.
    To overwrite the force_check of General_Conv, provide a __force_check__ attribute.
    """

# Note that ctypes.c_char_p is not the same as ctypes.POINTER(c_char)
# ctypes.c_char_p only handles nul terminating strings, it does not handle access raw strings
# Here c_char_p is a pointer to a single char.
# To handle char *, use Buffer instead.
c_char_p = General_POINTER(c_char)
c_byte_p = General_POINTER(c_byte)
c_ubyte_p = General_POINTER(c_ubyte)
c_short_p = General_POINTER(c_short)
c_ushort_p = General_POINTER(c_ushort)
c_int_p = General_POINTER(c_int)
c_uint_p = General_POINTER(c_uint)
c_long_p = General_POINTER(c_long)
c_ulong_p = General_POINTER(c_ulong)
c_longlong_p = General_POINTER(c_longlong)
c_ulonglong_p = General_POINTER(c_ulonglong)

c_float_p = General_POINTER(c_float)
c_double_p = General_POINTER(c_double)

c_int8_p = General_POINTER(c_int8)
c_int16_p = General_POINTER(c_int16)
c_int32_p = General_POINTER(c_int32)
c_int64_p = General_POINTER(c_int64)
c_uint8_p = General_POINTER(c_uint8)
c_uint16_p = General_POINTER(c_uint16)
c_uint32_p = General_POINTER(c_uint32)
c_uint64_p = General_POINTER(c_uint64)

c_void_p_p = General_POINTER(c_void_p)

class DLL_Wrapper(object):
    # add _quiet_delete here in case we call __del__ before __init__ because of problem in subclass
    _quiet_delete = False
    _quiet_load = True
    def __init__(self, dll_name=None, extra_paths=None, quiet_delete=False, quiet_load=True, loader=CDLL, **kwargs):
        self._quiet_load = quiet_load
        self._quiet_delete = quiet_delete
        self._load_dll(dll_name, extra_paths, loader, **kwargs)
        self._create_funcs()
        self._quiet_load = False

    def _load_dll(self, dll_name=None, extra_paths=None, loader=CDLL):
        if extra_paths is not None:
            if not isinstance(extra_paths, (list, tuple)):
                extra_paths = [extra_paths]
            self._additional_paths = Addition_dll_search()
            for p in extra_paths:
                self._additional_paths.add(p, quiet=True)
        else:
            self._additional_paths = None
        self._dll = loader(dll_name)
        return self._dll

    def __del__(self):
        if not (self._quiet_delete or self._quiet_load):
            print('Destroying '+repr(self))

    def _init_arg(self, types, init_val=None, cache=None):
        arg = ()
        if init_val is not DefaultVal:
            arg = (init_val,)
            if not isinstance(types, General_CType) and isinstance(init_val, types):
                return init_val
        if isinstance(types, General_CType):
            return types.initialize(*arg, cache=cache)
        if issubclass(types, _GeneralImproved):
            t = types()
            t.update(*arg)
            return t
        if issubclass(types, Array) and len(arg):
            arg = arg[0]
        return types(*arg)

    def _add_ret(self, name, t, c_val, sizes, cache=None):
        name = name.rstrip('_+')
        size = sizes.get(name +'_size', None)
        N = sizes.get(name +'_N', None)
        if isinstance(t, General_CType):
            return t.extract(c_val, N, size, cache=cache)
        elif isinstance(t, Structure):
            return c_val
        elif isinstance(t, Array):
            if N is not None:
                return c_val[:N]
            if size is not None:
                return c_val[:size/sizeof(t._type_)]
            return c_val[:]
        elif hasattr(c_val, 'value'):
            return c_val.value
        # we get here for some function return values
        return c_val

    def _generate_wrapper(self, dll_func, names, types, defaults, return_res):
        names_clean = [n.strip('_+') for n in names]
        params = [n.strip('_+') for n in names if not n.endswith('_') and not n.startswith('_')]
        rets = [n.strip('_+') for n in names if n[-1] in ['_', '+'] and n[0] != '_']
        if return_res is not None:
            name = return_res[0]
            if name is True:
                name = 'XXXXunknown_nameXXXX_'
            else:
                if name in ['', '_']:
                    raise ValueError('Invalid return name. It needs to contain some text string.')
                if name[-1] != '_':
                    name = name + '_'
            names_out = names + [name]
            types_out = types + [return_res[1]]
        else:
            names_out = names
            types_out = types
        doc = """
        The parameter list is:
            %s
        The return tuple is:
            %s
        """%(params, rets)
        pself = proxy(self)
        def wrap(*args):
            # prepare arguments
            dll_args = []
            args = list(args)
            cache = {}
            def pop_arg():
                if len(args) == 0:
                    raise ValueError('Missing argument')
                return args.pop(0)
            for n, t, d in zip(names, types, defaults):
                last = n[-1]
                first = n[0]
                # possibilities
                #  name    input param only
                #  name_   output param only
                #  name+   input/output
                #  _name   input only but hidden
                #  _name_  output only but hidden
                #  _name+  input/output but hidden
                if last in '_+':
                    # name_, name+, _name_, _name+
                    if last == '+' and first != '_':
                        # name+
                        dll_args.append(pself._init_arg(t, pop_arg(), cache=cache))
                    else:
                        # name_, _name_, _name+
                        # i.e. return values only or hidden
                        dll_args.append(pself._init_arg(t, d, cache=cache))
                else:
                    # name, _name
                    if first != '_':
                        # name
                        dll_args.append(pself._init_arg(t, pop_arg(), cache=cache))
                    else:
                        # _name
                        dll_args.append(pself._init_arg(t, d, cache=cache))
            # now calc size or lengths for hidden input names (start with _)
            for n, t, d in zip(names, types, dll_args):
                if n[0] != '_' or n[-1] == '_':
                    continue
                n = n.rstrip('+')
                if n.endswith('_N'):
                    i = names_clean.index(n[1:-2])
                    t2 = types[i]
                    argi = dll_args[i]
                    if isinstance(t2, General_CType):
                        v = t2.len(argi)
                    else:
                        v = len(argi)
                elif n.endswith('_size'):
                    i = names_clean.index(n[1:-5])
                    t2 = types[i]
                    argi = dll_args[i]
                    if isinstance(t2, General_CType):
                        v = t2.sizeof(argi)
                    else:
                        v = sizeof(argi)
                else:
                    # This isa hidden argument. It has probably already been initialized.
                    continue
                try:
                    d.contents.value = v
                except AttributeError:
                    d.value = v
            if len(args) != 0:
                raise ValueError('Invalid number of arguments')
            # call dll func
            global _dll_args_last
            ret_val = dll_func(*dll_args)
            if return_res is not None:
                dll_args = dll_args + [ret_val]
            _dll_args_last = dll_args
            # prepare return values
            ret = []
            sizes = {}
            for n, t, a in zip(names_out, types_out, dll_args):
                if n[0] == '_':
                    n = n[1:].strip('_+')
                    if not (n.endswith('_N') or n.endswith('_size')):
                        continue
                    try:
                        v = a.contents.value
                    except AttributeError:
                        v = a.value
                    sizes[n] = v
            for n, t, a in zip(names_out, types_out, dll_args):
                last = n[-1]
                if last not in '_+' or n[0] == '_':
                    continue
                ret.append(pself._add_ret(n, t, a, sizes, cache=cache))
            if len(ret) == 1:
                return ret[0]
            elif len(ret) == 0:
                return None
            return tuple(ret)
        wrap.__doc__ = doc
        wrap._return_names = rets
        return wrap

    def _create_helper(self, funcname, argdefs, restype=c_int, othername=None, errcheck=None, name_prefix='', return_res=False):
        """
        funcname is the function name without the name_prefix start
        It will result in the ctypes def as _funcname and
        the python version as funcname
        argdefs is a list of tuple of (name, ctype) or (name, ctype, initializer)
         names that end in '_' are return only parameters
         names that end in '+' are both input and output parameter
         names that start with '_' are not displayed (could be use for automatic length, or number of elements)
         other names are only control parameters.
        restype is the return type.
        othername can be used to define the function with another name (defines a function with different defaults for example
                        The types need to be the same if the ctype function is already defined.)
        return_res, when True or a string, will return the function result as the last returned value (it could have been
                        changed by errcheck). When the string starts with a '_', it will not be returned
                        but could be used for length conversions.
                        An ending '_' should not be added. It is implicit.
        """
        names =[x[0] for x in argdefs]
        def conv_t(t):
            if isinstance(t, General_CType):
                t = t.ctype()
            return t
        type_defs = [x[1] for x in argdefs]
        types = [conv_t(x) for x in type_defs]
        res_type = conv_t(restype)
        defaults = [x[2] if len(x)==3 else DefaultVal for x in argdefs]
        dll_func_name = name_prefix + funcname
        ctype_name = '_'+funcname
        dll_func_obj = getattr(self._dll, dll_func_name, None)
        if dll_func_obj is None:
            raise ValueError('The name "%s" is not present in the dll.'%dll_func_name)
        if hasattr(self, ctype_name):
            # Already defined, check we are calling it the same way
            if dll_func_obj.argtypes != types or dll_func_obj.restype != res_type:
                raise ValueError('Already defined. It should have the same configuration')
        else:
            dll_func_obj.restype = res_type
            dll_func_obj.argtypes = types
            if errcheck is not None:
                dll_func_obj.errcheck = errcheck
            dll_func_obj.__doc__ = """
            The parameter list are:
                %s
            """%' '.join(names)
            #"""%' '.join(['%s(%s)'%(n, t) for n, t in argdefs])
            setattr(self, ctype_name, dll_func_obj)
        fn = funcname if othername is None else othername
        res_type = None
        if return_res:
            res_type = (return_res, restype)
        setattr(self, fn, self._generate_wrapper(dll_func_obj, names, type_defs, defaults, res_type))

    def _create_funcs(self):
        raise NotImplementedError('This needs to be overriden in subclass')

"""
Examples:
    x = Buffer() #  pointer to chars; in c: char *
    xx = x.initialize() # This is an error
    xx = x.initialize('hello') # this works
    xx = x.initialize(None) # pointer to char but pointing to NULL
    y = Buffer(10, x) # pointer to pointer of chars; in c: char **
    # The next 3 produce the same result; all the pointers are to NULL
    yy = y.initialize([])
    yy = y.initialize([None])
    yy = y.initialize([None]*10)
    # The next one has the first item initialize to a string, the others point to NULL:
    yy = y.initialize(['test'])
    list(map(bool, yy)) # boolean value of pointer says if it is not NULL
    yy[0][:4]
    y.extract(yy)

    # To handle null terminated strings:
    x = Buffer(10, c_null_term_string)
    xx = x.initialize([b'test'])
    x.extract(xx)

    x = Buffer(10) # array of 10 chars; in c: char [10]
    y = Buffer(5, x) # array of 5 arrays of 10 chars
    yy = y.initialize()
    y.extract(yy)
    x = Buffer(10, allow_any_size=True)) # array of 10 chars represented as pointers to char; in c: char *
    y = Buffer(5, x) # array of 5 of pointers to chars (10 of them); in c: char * [5]
    yy = y.initialize()
    y.extract(yy)

    y = Buffer(None, ctypes.c_double, use_ndarray=True)
    y2 = Buffer(100, ctypes.c_double, use_ndarray=True)
    y3 = Buffer(200, ctypes.c_double, use_ndarray=True)
    v = linspace(0, 1, 100)
    yy = y.initialize(v)
    y.extract(yy)
    yy = y2.initialize(v)
    y2.extract(yy)
    yy = y3.initialize(v)
    y3.extract(yy)

It is essential to keep the data objects alive. Asigning object which just an address
is not sufficient.
Example that show the requirement of the cache attribute:
import ctypes
import pyHegel.ctypes_helper as ct
from pyHegel.ctypes_helper import Buffer, General_POINTER, Buffer_as_Byte
from pyHegel.types import StructureImproved
class S(StructureImproved):
    _fields_ = [('x', ctypes.c_double), ('x', ctypes.c_int64)]
class S2(StructureImproved):
    _fields_ = [('x', ctypes.c_double), ('y', ctypes.c_int64), ('z', S)]
B1 = Buffer(5, S2, allow_any_size=True)
B2 = Buffer(10, B1)
x = B2.initialize([[dict(x=55)], [dict(z=dict(x=11))]], cache=None)
y = B2.extract(x, cache=None)
del x
z = randn(1000); del z
clear_state()
z = [randn(10) for i in range(100)]; del z
clear_state()
print(y) # shows random values
d = {}
x = B2.initialize([[dict(x=55)], [dict(z=dict(x=11))]], cache=d)
y = B2.extract(x, cache=d)
del d
del x
z = randn(1000); del z
clear_state()
z = [randn(10) for i in range(100)]; del z
clear_state()
print(y) # Shows correct values

class S(StructureImproved):
    _fields_ = [('type', ct.c_int), ('test', ct.Buffer_as_Byte(10))]
s = S(1, 'hello')
print(s)
"""