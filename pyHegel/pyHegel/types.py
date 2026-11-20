# -*- coding: utf-8 -*-

########################## Copyrights and license ############################
#                                                                            #
# Copyright 2011-2023  Christian Lupien <christian.lupien@usherbrooke.ca>    #
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

"""
This module contains some improved types:
 StructureImproved (ctypes Structure improvement)
 dict_improved  (OrderedDict improvement)
"""
from __future__ import absolute_import, print_function, division

from collections import OrderedDict
from ctypes import Structure, Union, memmove, byref, sizeof, c_uint8, c_ubyte, c_char,\
                    resize, addressof, Array
import keyword
from numpy.ctypeslib import as_array

from .comp2to3 import string_types, string_bytes_types, Iterator, isidentifier, with_metaclass


def _filter_fields_helper(name, value):
    fields_conv = None
    if name == '_fields_':
        fields_conv = {}
        # make a list copy of input value, we don't want to change the original one
        value = list(value)
        for i, entry in enumerate(value):
            c_type = entry[1]
            # Check if it is a usable ctype
            # could try to do issubclass of _CData but that is not available
            # _SimpleCData does not include Structures Unions...
            try:
                _ = sizeof(c_type)
            except TypeError:
                new_entry = list(entry)
                # This should handle ctypes_helper General_CType
                new_entry[1] = c_type.ctype()
                value[i] = tuple(new_entry)
                fields_conv[entry[0]] = c_type
    return value, fields_conv

def _improved_array_setitem(self, idx, val):
    if isinstance(self[0], _GeneralImproved):
        objs = self[idx]
        if isinstance(objs, list):
            # here for slices
            if len(objs) != len(val):
                raise ValueError('Need to have the same number of elements on both side of assignment.')
            for o, v in zip(objs, val):
                o.update(v)
        else:
            # here for single element
            objs.update(val)
        return
    super(type(self), self).__setitem__(idx, val)

def Generate_Array(t, N):
    t._in_mul = True
    try:
        base = t*N
    finally:
        t._in_mul = False
    base.__setitem__orig = base.__setitem__
    base.__setitem__ = _improved_array_setitem
    return base

class _StructureImprovedMeta(Structure.__class__):
    # Using this metaclass will add a separate cache to each new subclass
    def __init__(cls, name, bases, d):
        super(_StructureImprovedMeta, cls).__init__(name, bases, d)
        cls._names_cache = [] # every sub class needs to have its own cache
        cls._in_mul = False
    def __setattr__(cls, name, value):
        value, fields_conv = _filter_fields_helper(name, value)
        super(_StructureImprovedMeta, cls).__setattr__(name, value)
        if fields_conv is not None:
        #if name == '_fields_':
            # Need to make sure that every subclass has its own version of _fields_conv
            # We need to generate it here because _fields_ is set before __init__ is called.
            # And since _fields is only set once (it errors our on subsequent calls),
            # it will not be overwritten
            cls._fields_conv = fields_conv
    def __mul__(cls, multiplier):
        if cls._in_mul:
            return super(_StructureImprovedMeta, cls).__mul__(multiplier)
        else:
            return Generate_Array(cls, multiplier)
    def __rmul__(cls, multiplier):
        return cls.__mul__(multiplier)

class _UnionImprovedMeta(Union.__class__):
    # Using this metaclass will add a separate cache to each new subclass
    def __init__(cls, name, bases, d):
        super(_UnionImprovedMeta, cls).__init__(name, bases, d)
        cls._names_cache = [] # every sub class needs to have its own cache
        cls._in_mul = False
    def __setattr__(cls, name, value):
        value, fields_conv = _filter_fields_helper(name, value)
        super(_UnionImprovedMeta, cls).__setattr__(name, value)
        if name == '_fields_':
            # Need to make sure that every subclass has its own version of _fields_conv
            # We need to generate it here because _fields_ is set before __init__ is called.
            # And since _fields is only set once (it errors our on subsequent calls),
            # it will not be overwritten
            cls._fields_conv = fields_conv
    def __mul__(cls, multiplier):
        if cls._in_mul:
            return super(_UnionImprovedMeta, cls).__mul__(multiplier)
        else:
            return Generate_Array(cls, multiplier)
    def __rmul__(cls, multiplier):
        return cls.__mul__(multiplier)

class _GeneralImproved(object):
    # TODO fix the problem of not being able to subclass (_fields_ does not have all names)
    _names_cache = [] # This gets overwritten by metaclass so that all subclass have their own list
    _fields_conv = {} # This gets overwritten by metaclass so that all subclass have their own dict
    def _get_names(self):
        if self._names_cache == []:
            # fields can containt 2 or 3 elements tuples.
            self._names_cache.extend([t[0] for t in self._fields_])
        return self._names_cache
    _names_ = property(_get_names)
    def __getattribute__(self, name):
        value = super(_GeneralImproved, self).__getattribute__(name)
        if name == '_fields_conv':
            # This is to prevent an infinte loop on the next lines.
            return value
        # prevent wrapper defining __getattribute__ from causing loops
        fields_conv = super(_GeneralImproved, self).__getattribute__('_fields_conv')
        if name in fields_conv:
            t = fields_conv[name]
            if hasattr(t, 'decode'):
                value = t.decode(value)
        return value
    def __setattr__(self, name, value):
        if name in self._fields_conv:
            t = self._fields_conv[name]
            if hasattr(t, 'encode'):
                value = t.encode(value)
        if isinstance(self[name], _GeneralImproved):
            self[name]._update(value)
        else:
            super(_GeneralImproved, self).__setattr__(name, value)
    def __getitem__(self, key):
        if not isinstance(key, string_bytes_types):
            key = self._names_[key]
        return getattr(self, key)
    def __setitem__(self, key, value):
        if not isinstance(key, string_bytes_types):
            key = self._names_[key]
        setattr(self, key, value)
    def __len__(self):
        return len(self._fields_)
    def _assign_helper(self, k, v):
        if isinstance(self[k], _GeneralImproved):
            self[k].update(v)
        else:
            self[k] = v
    def _update(self, *args, **kwargs):
        """
        updates the structure data.
        You can provide the same type of object as a first argument,
        or positional arguments to change the values in order
        or named keyword aguments to change the named item.
        Named changes can also be done by providing a single dict as arguments.
        or by a list as a single argument.
        Note that because of the 2 aboves you cannot have a dict or list to
        assing only the first element (surround the item in a list in this case.)
        """
        only_one = False
        if len(args)==1:
            if type(args[0]) == type(self):
                memmove(byref(self), byref(args[0]), sizeof(self))
                only_one = True
            elif isinstance(args[0], dict):
                kwargs.update(args[0])
                only_one = True
            elif isinstance(args[0], (list, tuple)):
                args = args[0]
        if not only_one:
            for i,v in enumerate(args):
                self._assign_helper(i, v)
        for k,v in kwargs.items():
            self._assign_helper(k, v)
    def update(self, *args, **kwargs):
        self._update(*args, **kwargs)
    update.__doc__ = _update.__doc__
    def as_dict(self):
        return OrderedDict(self.items())
    def items(self):
        return [(k,self[k]) for k in self._names_]
    def keys(self):
        return self._names_
    def values(self):
        return [self[k] for k in self._names_]
    def __repr__(self):
        return self.show_all(multiline=False, show=False)
    def show_all(self, multiline=True, show=True):
        strs = ['%s=%r'%(k, v) for k,v in self.items()]
        if multiline:
            ret = '%s(\n  %s\n)'%(self.__class__.__name__, '\n  '.join(strs))
        else:
            ret = '%s(%s)'%(self.__class__.__name__, ', '.join(strs))
        if show:
            print(ret)
        else:
            return ret

class StructureImproved(with_metaclass(_StructureImprovedMeta, _GeneralImproved, Structure)):
    """
    This adds to the way Structure works (structure elements are
    class attribute).
    -can also access (RW) elements with numerical ([1]) and name indexing (['key1'])
    -can get and OrderedDict from the data (as_dict method)
    -can get the number of elements (len)
    -can get a list of items, keys or values like for a dict
    -can print a more readable version of the structure
    -elements can have converters.
    Note that it can be initialized with positional arguments or keyword arguments.
    And changed later with update.
    You probably cannot subclass this structure (self._fields_ then only contains
    a fraction of the names.)
    
    To use converters, the ctype needs to be replaced in the _fields_ attribute by
    another class that is not a ctypes. That class needs to have a method ctypes
    that returns the proper ctypes to use and can also have decode and encode
    method that takes the Structure value and returns what you want (for decode) and
    the opposite for encode.
    """
    pass

class UnionImproved(with_metaclass(_UnionImprovedMeta, _GeneralImproved, Union)):
    """
    This adds to the way Structure works (structure elements are
    class attribute).
    -can also access (RW) elements with numerical ([1]) and name indexing (['key1'])
    -can get and OrderedDict from the data (as_dict method)
    -can get the number of elements (len)
    -can get a list of items, keys or values like for a dict
    -can print a more readable version of the structure
    -elements can have converters.
    Note that it can be initialized with positional arguments or keyword arguments.
    And changed later with update.
    You probably cannot subclass this structure (self._fields_ then only contains
    a fraction of the names.)
    
    To use converters, the ctype needs to be replaced in the _fields_ attribute by
    another class that is not a ctypes. That class needs to have a method ctypes
    that returns the proper ctypes to use and can also have decode and encode
    method that takes the Structure value and returns what you want (for decode) and
    the opposite for encode.
    """
    pass


# ctypes in Python 2.6.2 at least has a bug that prevents
# subclassing arrays unless _length_ and _type_ are redefined
# create a metaclass to automatically do that transformation
# I think this problem was fixed in 3.3 but not in 2.7
_ctypes_array_metabase = (c_uint8*4).__class__
class _ctypes_array_metabase_fix(_ctypes_array_metabase):
    def __new__(mcls, name, bases, d):
        d['_length_'] = bases[0]._length_
        d['_type_'] = bases[0]._type_
        return super(_ctypes_array_metabase_fix, mcls).__new__(mcls, name, bases, d)

# TODO Fix the ctypes.sizeof instruction which returns the base size, not the
# augmented size of the structure. I am not sure if it is possible
class StructureImproved_extend(StructureImproved):
    """
    Adds to StructImproved a way to extend the last entry.
    a _mask_ variable containing (src, dst), both strings
    while replace access to src with calls to _dst_get, and assignment to src
    with calls to _dst_set. This can be useful for structure that have a last
    of variable length.
    If _mask_ is just a string, it replaces that entry with
    _mask_default_set, _mask_default_get.
    They both use the string in _mask_lengthvar to access a size variable for
    the mask attribute.
    They also use the type in _mask_basetype as the base type of the array.
    And the use the _mask_get_conv to convert from the new proper ctype structure
    to something else. By default the function tries to return a numpy array,
    unless the basetype is c_char, in which case it returns the type as is.
    By default c_char arrays are return with .value (zero terminated string), to have them
    return .raw, set attribute _mask_char_raw to True
    It will also make the set_data_size method work (assuming the variable to replace is the last one)
    You can return the unmasked variable as _maskname_raw for a masked variable called maskname
    """
    _mask_ = (None, '')
    _mask_lengthvar = ''
    _mask_basetype = c_ubyte
    _mask_char_raw = False
    @staticmethod
    def _normalize_mask(mask):
        if isinstance(mask, string_bytes_types):
            mask = (mask, 'mask_default')
        return mask
    def __setattr__(self, name, value):
        mask = self._normalize_mask(self._mask_)
        if name == mask[0]:
            getattr(self, '_'+mask[1]+'_set')(value)
        else:
            super(StructureImproved_extend, self).__setattr__(name, value)
    def __getattribute__(self, name):
        mask = super(StructureImproved_extend, self).__getattribute__('_mask_')
        normalize = super(StructureImproved_extend, self).__getattribute__('_normalize_mask')
        mask = normalize(mask)
        if name == mask[0]:
            name = '_'+mask[1]+'_get'
            return super(StructureImproved_extend, self).__getattribute__(name)()
        elif name == '_'+mask[0]+'_raw':
            return super(StructureImproved_extend, self).__getattribute__(mask[0])
        else:
            return super(StructureImproved_extend, self).__getattribute__(name)
    def _mask_get_offset(self):
        mask = self._normalize_mask(self._mask_)
        return getattr(self.__class__, mask[0]).offset
    def _mask_get_count(self):
        # returns the number of elements, used for resize and newtype
        length = getattr(self, self._mask_lengthvar)
        return length
    def _mask_set_count(self, n):
        setattr(self, self._mask_lengthvar, n)
    def _mask_get_conv(self, cdata):
        # This should return an object that can be assigned to
        cnt = self._mask_get_count()
        if self._mask_basetype == c_char:
            return cdata
        if cnt > 0:
            # this can produce the warning we filter above (about PEP 3118)
            return as_array(cdata)
        else:
            return cdata
    def set_data_size(self, n):
        """
        Use this instead of changing the count directly. It will properly resize
        the structure.
        It assumes the variable to mask is the last element of the structure.
        """
        mask = self._normalize_mask(self._mask_)
        if mask[1] != 'mask_default':
            raise NotImplementedError('This function is only implemented when using the default mask. Subclasses should overwrite this.')
        self._mask_set_count(n)
        offset = self._mask_get_offset()
        cnt = self._mask_get_count()
        t = self._mask_basetype
        newsize = offset + cnt * sizeof(t)
        minsize = sizeof(self)
        newsize = max(minsize, newsize)
        resize(self, newsize)
    def _mask_default_get(self):
        #print)'Get called')
        cnt = self._mask_get_count()
        #cnt = min(cnt, 1024*1024)
        newtype = self._mask_basetype * cnt
        if self._mask_basetype == c_char:
            # we now deal with character arrays.
            if self._mask_char_raw:
                # define a new class that shows the raw data when displayed with repr
                newtype = _ctypes_array_metabase_fix('tmp_array_class', (newtype,), dict(__repr__= lambda s: repr(s.raw)))
            else:
                # define a new class that shows the value data when displayed with repr
                newtype = _ctypes_array_metabase_fix('tmp_array_class', (newtype,), dict(__repr__= lambda s: repr(s.value)))
        offset = self._mask_get_offset()
        cdata = newtype.from_address(addressof(self) + offset)
        #print(addressof(self), offset, cdata, list(cdata))
        return self._mask_get_conv(cdata)
    def _mask_default_set(self, val):
        #print('set called')
        self._mask_default_get()[:] = val



class dict_improved(OrderedDict):
    """
    This adds to the basic dict/OrderedDict syntax:
        -getting/setting/deleting with numerical indexing (obj[0])
                or with slices obj[1:3] or with list of index
                obj[[2,1,3]]. can also use list of keys (obj[['key1', 'key2']])
        -getting a regular dict/OrderedDict copy (as_dict)
        -getting/setting/deleting as attributes (obj.key)
        -adding new elements to the dict as attribute (obj.newkey=val)
         (could already do obj['newkey']=val)
    Note that it can be initialized like dict(a=1, b=2) but the order is not
    conserved: dict_improved(a=1, b=2) is the same as dict_improved(b=2, a=1) but is not the same
    as dict_improved([('b', 2), ('a', 1)]). So to recreate a dict, use the output from repr_raw
    not from str.
    show_all method shows all the entry, one per line by default.
    the option _freeze=True prevents adding/removing elements to the dict (defaults to False).
    the option _allow_overwrite=True (the default) allows overwritting existing attributes
      (the original attribute is saved as oldname_orig)
    """
    def __init__(self, *arg, **kwarg):
        freeze = kwarg.pop('_freeze', False)
        allow_overwrite = kwarg.pop('_allow_overwrite', True)
        #self._known_keys = []
        super(dict_improved, self).__setattr__('_known_keys', [])
        super(dict_improved, self).__setattr__('_dict_improved__init_complete', False)
        super(dict_improved, self).__setattr__('_freeze', freeze)
        super(dict_improved, self).__setattr__('_allow_overwrite', allow_overwrite)
        # Since we can only go through an iterator once, convert it to a list now
        if len(arg)>=1 and isinstance(arg[0], Iterator):
            arg = (list(arg[0]),) + arg[1:]
        # Now check the entries
        tmp = OrderedDict(*arg, **kwarg)
        for key in tmp.keys():
            self._check_valid_key(key)
        # input is ok so create the object
        super(dict_improved, self).__init__(*arg, **kwarg)
        self._dict_improved__init_complete = True
    def _check_valid_key(self, key):
        if not isinstance(key, string_bytes_types):
            raise TypeError("You can only use strings as keys.")
        if not isidentifier(key):
            raise TypeError("You can only use valid string identifiers as keys.")
        if keyword.iskeyword(key):
            raise TypeError("You can only use strings that are not python keywords as keys.")
    def _set_freeze(self, val):
        """
        Change the freeze state. val is True or False
        This works even when _allow_overwrite is True
        """
        super(dict_improved, self).__setattr__('_freeze', val)
    def __getattribute__(self, name):
        known = super(dict_improved, self).__getattribute__("_known_keys")
        if name in known:
            return self[name]
        else:
            return super(dict_improved, self).__getattribute__(name)
    def _setattribute_helper(self, name):
        # Check to see if use indexing (returns True) or the parent call (returns False)
        if not self._dict_improved__init_complete:
            # during init, we use parent call
            return False
        if name in self._known_keys:
            return True
        if hasattr(self, name):
            # not in known but already exists
            if self._freeze:
                # This allows changing the value directly
                return False
            if self._allow_overwrite:
                return True
        # not known and does not exist
        return True # should add it or raise an exception
    def __setattr__(self, name, value):
        if self._setattribute_helper(name):
            self[name] = value
        else:
            super(dict_improved, self).__setattr__(name, value)
    def __delattr__(self, name):
        if name in self._known_keys:
            del self[name]
        else:
            super(dict_improved, self).__delattr__(name)
    def __getitem__(self, key):
        if isinstance(key, list):
            return [self[k] for k in key]
        if not isinstance(key, string_bytes_types):
            # assume we are using an integer index
            key = list(self.keys())[key]
            if isinstance(key, list): # it was a slice
                return self[key]
        return super(dict_improved, self).__getitem__(key)
    def __delitem__(self, key):
        if isinstance(key, list):
            for k in key:
                del self[k]
            return
        if not isinstance(key, string_bytes_types):
            # assume we are using an integer index
            key = self.keys()[key]
            if isinstance(key, list): # it was a slice
                del self[key]
                return
        if self._freeze and key in self._known_keys:
            raise RuntimeError("Modifying keys of dictionnary not allowed for this object.")
        super(dict_improved, self).__delitem__(key)
        self._known_keys.remove(key)
        delattr(self, key)
    def __setitem__(self, key, value):
        if isinstance(key, list):
            if len(key) != len(value):
                raise RuntimeError('keys and values are not the same length.')
            for k,v in zip(key, value):
                self[k] = v
            return
        if not isinstance(key, string_bytes_types):
            # assume we are using an integer index
            key = self.keys()[key]
            if isinstance(key, list): # it was a slice
                self[key] = value
                return
        if self._dict_improved__init_complete and self._freeze and key not in self._known_keys:
            raise RuntimeError("Modifying keys of dictionnary not allowed for this object.")
        if key not in self._known_keys:
            self._check_valid_key(key)
            if hasattr(self, key):
                if not self._allow_overwrite:
                    raise RuntimeError("Replacing existing attributes not allowed for this object.")
                super(dict_improved, self).__setattr__(key+'_orig', getattr(self, key))
            # add entry so tab completion sees it
            super(dict_improved, self).__setattr__(key, 'Should never see this')
            self._known_keys.append(key)
        super(dict_improved, self).__setitem__(key, value)
    def clear(self):
        if self._freeze:
            raise RuntimeError("Modifying keys of dictionnary not allowed for this object.")
        keys = self._known_keys
        del self._known_keys[:]
        for k in keys:
            delattr(self, k)
        super(dict_improved, self).clear()
    def as_dict(self, order=False):
        """
        Returns a copy in a regular dict (order=False)
        or an ordered dict copy (order=True, same as copy method).
        """
        if order:
            return OrderedDict(self)
        else:
            return dict(self)
    def show_all(self, multiline=True, show=True):
        strs = ['%s=%r'%(k, v) for k,v in self.items()]
        if multiline:
            ret = '%s(\n  %s\n)'%(self.__class__.__name__, '\n  '.join(strs))
        else:
            ret = '%s(%s)'%(self.__class__.__name__, ', '.join(strs))
        if show:
            print(ret)
        else:
            return ret
    def __repr__(self):
        # could use numpy.get_printoptions()['threshold']
        """ This is a simplified view of the data. Using it to recreate
            the structure would necessarily keep the order.
            Use the repr_raw method output for that."""
        return self.show_all(multiline=False, show=False)
    def repr_raw(self):
        return super(dict_improved, self).__repr__()
