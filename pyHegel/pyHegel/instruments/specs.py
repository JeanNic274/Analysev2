# -*- coding: utf-8 -*-

########################## Copyrights and license ############################
#                                                                            #
# Copyright 2024-2024  Christian Lupien <christian.lupien@usherbrooke.ca>    #
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

from __future__ import absolute_import, print_function, division

import socket
import ctypes
from ctypes import c_char, c_byte, c_int32, c_uint16, c_uint32, c_uint16, c_float, c_double, c_uint8, create_string_buffer,\
                   sizeof
import struct
import numpy as np
import weakref
import time
import re
import select
import time

from ..instruments_base import BaseInstrument,\
                            BaseDevice, Base2Device,\
                            MemoryDevice, dict_improved,\
                            ChoiceIndex, ChoiceBase,\
                            sleep, locked_calling, ProxyMethod,\
                            wait_on_event, release_lock_context, _retry_wait,\
                            _delayed_signal_context_manager
from ..instruments_registry import register_instrument


####################################
# Raw Specs Nanonis Tramea interface
####################################

class ReqHeader(ctypes.BigEndianStructure):
    """
    Request message header to be sent from the client to the server.
    """
    _pack_ = 1 # Disabling optimization of the memory representation of the object (it could change the length of the object)
    _fields_ =  [('name', c_char*24), ('size', c_int32), ('send_response', c_uint16), ('reserved', c_byte*2)]

class RespHeader(ctypes.BigEndianStructure):
    """
    Response message header sent from the server to the client.
    """
    _pack_ = 1
    _fields_ =  [('name', c_char*24), ('size', c_int32), ('reserved', c_byte*4)]

class ErrorResp(ctypes.BigEndianStructure):
    """
    Error message response header.
    """
    _pack_ = 1
    _fields_ =  [('status', c_uint32), ('size', c_int32)]
    # followed by the string data of length size

class Nanonis_TCP(object):
    """
    Call this class to create a connection with the machine. Only one connection should be active at any given time.

    See TCPProtocol_Tramea_2018.pdf for the entire documentation about the TCP protocol for the Nanonos Tramea.
    """
    _connections_time = []
    def __init__(self, server_addr='localhost', server_port=6501, timeout=3, quiet_delete=False, quiet_load=True):
        self._quiet_delete = quiet_delete
        self._quiet_load = quiet_load
        address = (server_addr, server_port)
        self.sk = socket.create_connection(address, timeout)
        self._create()
        self._init_time = time.time()
        self._connections_time.append(self._init_time)
        self._quiet_load = False
    def close(self):
        self.sk.close()
    def __del__(self):
        if not (self._quiet_delete or self._quiet_load):
            datetime = time.strftime('%Y-%m-%d %H:%M:%S',  time.localtime(self._init_time))
            print('Closing connection created on {}'.format(datetime)) # Python creates a new instance before deleting the last one (when both have the same name)
        self.close()
    def send(self, str_orig):
        """
        Send a command to the machine and in case the message hasn't been sent entirely, send the part of the message that's left to be sent.
        """
        str = memoryview(str_orig)
        sent = 0
        to_send = len(str_orig)
        while sent < to_send: # while the entire message hasn't been sent, send what's left to be sent
            # could produce the socket.timeout exception
            #print(str[sent:].tobytes())
            n = self.sk.send(str[sent:]) # send the message and return the size of the sent message
            sent += n
    def recv(self, n):
        """
        Receive the response from the machine and in case the response hasn't been received entirely, read the part of the message that's left to be received.
        """
        buf = bytearray(n)
        to_read = 4096 if n > 4096 else n
        received = 0
        while received < n: # while the entire message hasn't been received, receive what's left to be received
            m = memoryview(buf)[received:]
            read_cnt = self.sk.recv_into(m, to_read) # receive the message and return the size of the received message
            if read_cnt == 0: # and no timeout, connection is closed
                raise RuntimeError('Connection closed')
            received += read_cnt
            if n-received < to_read:
                to_read = n-received
        return buf

    def recv_empty(self):
        """
        Empties the read buffer. Use this after a break or an error.
        """
        if not self.wait_recv(0):
            # no data waiting
            return 0
        N = 0
        try:
            # read as long as recv returns >0 data
            while True:
                ret_s = self.sk.recv(1024)
                n = len(ret_s)
                N += n
                if n == 0:
                    break
                if not self.wait_recv(0):
                    break
        except socket.timeout:
            pass
        return N

    def wait_recv(self, wait=None):
        """
        wait when None, the function will wait for as long as necessary.
        if given, it will wait at most that.
        It can be zero to just check if there is data.
        returns True when there is data. False when there is None.
        """
        read_list = [self.sk]
        def wait_func(timeout):
            r, _, _ = select.select(read_list, [], [], timeout)
            return bool(r)
        if wait == 0:
            return wait_func(0)
        return wait_on_event(wait_func, max_time=wait)

    def do_response(self, name):
        """
        Read the response header to get the size of the message to read then read it.
        """
        name = name.encode('utf-8')
        hdr = self.recv(sizeof(RespHeader))
        resp = RespHeader.from_buffer_copy(hdr)
        if resp.name != name:
            raise RuntimeError('Unexpected response. Was waiting for "%s" but got "%s"'%(name, resp.name))
        if resp.size > 2**20: # 1 Mb
            raise RuntimeError('Returned data too large (%i)'%resp.size)
        return self.recv(resp.size)

    def do_request(self, name, args_str=None, get_response=True):
        """
        Create the header for a given command then send it.
        """
        r = ReqHeader()
        if len(name) > 23:
            raise RuntimeError('Func name too long')
        #r.name = name.encode('utf-8')
        r.name = name.encode('latin1')
        r.send_response = get_response
        #if args_struct is not None:
            #r.size = sizeof(args_struct)
            #extra = bytearray(args_struct)
        if args_str is not None:
            extra = bytearray(args_str)
            r.size = len(extra)
        else:
            extra = b''
        #print(r, r.name, r.size, r.send_response, r.reserved[:])
        rb = bytearray(r)
        #print(rb, '====', extra)
        self.send(rb+extra)
        #self.sk.sendall(rb+extra)

    def do_both(self, name, args_struct=None, get_response=True):
        """
        Create the header for a given command, send the command and receive the response.
        """
        with _delayed_signal_context_manager():
            self.do_request(name, args_struct, get_response)
            if get_response:
                return self.do_response(name)

    _data_types = ['string', 'int', 'uint16', 'uint32', 'float32', 'float64', '1Dstring', '1Dint', '1Duint8', '1Duint32', '1Dfloat32', '1Dfloat64', '2Dfloat32']
    _data_types_simple = {'int':'i', 'uint16':'H', 'uint32':'I', 'float32':'f', 'float64':'d'}
    _data_types_array = {'1Dint':'i', '1Duint8':'B', '1Duint32':'I', '1Dfloat32':'f', '1Dfloat64':'d', '2Dfloat32':'f'}
    _type_elem_size_cache = {}
    def _get_type_elem_size(self, type_fmt):
        """
        Return the size in bytes of an element given it's type.
        """
        length = self._type_elem_size_cache.get(type_fmt)
        if length is not None:
            return length
        if type_fmt in self._data_types_simple:
            type_fmt = self._data_types_simple[type_fmt]
        elif type_fmt in self._data_types_array:
            type_fmt = self._data_types_array[type_fmt]
        elif type_fmt in ['string', '1Dstring']:
            type_fmt = 'c'
        length = struct.calcsize(type_fmt)
        self._type_elem_size_cache[type_fmt] = length
        return length

    def _ret_parser_helper(self, val, dtype):
        """
        Convert a return argument from bytes to strings.
        """
        if dtype == 'string':
            r, n = self._ret_parser_helper(val, 'int') # read int before string to get string length
            res = struct.unpack('>%is'%r, val[n:r+n])[0] # read string starting after the int
            return res.decode('latin1'), r+n

        elif dtype not in self._data_types_simple:
            raise RuntimeError('Unknow data simple type')
        conv_fmt = '>'+self._data_types_simple[dtype] # '>' is Big-endian
        length = self._get_type_elem_size(conv_fmt)
        result = struct.unpack(conv_fmt, val[:length])[0]
        return result, length

    def _debug_parser(self, byte_array, n_types, dtypes):
        """
        Manual parser that converts bytes to string.

        Arguments:
            n_types : number of bytes to parse (array for many types)

            dtypes : type of the bytes to parse (array for many types)
        """
        if not isinstance(n_types,list):
            n_types = [n_types]
            dtypes = [dtypes]
        result = []
        prev_length = 0
        for n in n_types:
            dtype = dtypes[n_types.index(n)]
            if dtype not in self._data_types_simple and dtype != "string":
                raise RuntimeError('Unknow data simple type and is not a string')
            if dtype != "string":
                conv_fmt = '>{}'.format(n)+self._data_types_simple[dtype]
            else:
                conv_fmt = '>{}s'.format(n)

            length = self._get_type_elem_size(conv_fmt)
            result.append(struct.unpack(conv_fmt, byte_array[prev_length:prev_length+length]))
            prev_length += length
        return result

    def _find_other(self, results, defs, index, extension, do_exc=True):
        """
        Find the variable linked to another variable with a similar name in the arguments.
        Usually used to find the size of an array in the arguments.
        """
        try:
            name = defs[index]
        except IndexError:
            name = defs[0]+extension
            if name not in results:
                name = '_'+name
        if name not in results:
            if do_exc:
                raise RuntimeError('Could not find the variable name: %s'%name)
            else:
                return None
        return results[name]

    def ret_parser(self, val_str, definitions=['error'], add_error=True):
        """
        Convert all the return arguments from bytes to strings.

        definition is a list of tuples or the string 'error'
            The tuples are (name, type) or (name, dtype, Nelem_name, Nelem_name_2D_col)
            where dtype is one of
                string, int, uint16, uint32, float32, float64, 1Dstring, 1Dint, 1Duint8, 1Duint32, 1Dfloat32, 1Dfloat64, 2Dfloat32
            and size_name is a previous name entry that specifies the size
            if not given, Nelem_name is name_N (or _name_N) and Nelem_name_2D_col is name_Ncol (or _name_Ncol)
            For dtype of 1Dstring use
               (name, string, Nelem_name, size_name)
            if not given, Nelem_name is name_N (or _name_N) and size_name is name_size (or _name_size)
            at least one of  Nelem_name or size_name needs to be given (the other can be None)
        """
        if definitions is None:
            definitions = []
        if add_error and 'error' not in definitions:
            definitions.append('error')
        if 'error' in definitions: # add error arguments to the list of arguments
            definitions = definitions[:] # make a copy of list
            i = definitions.index('error')
            del definitions[i]
            definitions.insert(i, ('error_desc', 'string'))
            definitions.insert(i, ('error_status', 'uint32'))
        val = memoryview(val_str)
        results = dict_improved()
        for d in definitions:
            name = d[0]
            dtype = d[1]
            if dtype not in self._data_types:
                raise RuntimeError('Unknow data type')
            if dtype in self._data_types_simple or dtype == 'string':
                res, length = self._ret_parser_helper(val, dtype)
            elif dtype.startswith('1D'):
                if "_arrays_size" in results:
                    #print("arrays_size" in results)
                    N = results["_arrays_size"] # 3DSSwChSegValuesGet has one int to specify the size of all next 1D arrays in args
                else:
                    N = self._find_other(results, d, 2, '_N', do_exc=(dtype != '1Dstring'))
                if dtype == '1Dstring':
                    size = self._find_other(results, d, 3, '_size', do_exc=False)
                    res = []
                    length = 0
                    cnt = 0
                    if size is None and N is None:
                        raise RuntimeError('Both size and N are None which is not allowed')
                    elif size is not None and N is not None:
                        check = lambda length, cnt: length < size and cnt < N
                    elif size is not None:
                        check = lambda length, cnt: length < size
                    else: # N is not None
                        check = lambda length, cnt: cnt < N
                    while check(length, cnt):
                        r, l = self._ret_parser_helper(val[length:], 'string')
                        res.append(r)
                        length += l
                        cnt += 1
                    if size is not None and length != size:
                        raise RuntimeError('1Dstring length(%i) of data parsed is not the expexted %i'%(length, size))
                    if N is not None and cnt != N:
                        raise RuntimeError('1Dstring count(%i) of data parsed is not the expexted %i'%(cnt, N))
                else:
                    conv = '>'+self._data_types_array[dtype]
                    elem_size = self._get_type_elem_size(conv)
                    length = elem_size*N
#                    res = np.fromstring(val[:length].tobytes(), np.dtype(conv)) # deprecation warning
                    res = np.frombuffer(val[:length].tobytes(), np.dtype(conv))
            else: # dtype.startswith('2D')
                N = self._find_other(results, d, 2, '_N')
                Ncol = self._find_other(results, d, 3, '_Ncol')
                conv = '>'+self._data_types_array[dtype]
                length = N*Ncol* self._get_type_elem_size(conv)
#                res = np.fromstring(np.dtype(conv), val[:length]) # deprecation warning
                res = np.frombuffer(val[:length].tobytes(), np.dtype(conv))
                res.shape = (N, Ncol)
            results[name] = res
            val = val[length:]
        if len(val) != 0:
            raise RuntimeError('There are leftovers in the result parsing.')
        return results

    def _arg_parser_helper(self, arg_val, dtype):
        """
        Convert an argument from bytes to strings.
        """
        # This test is already done (in arg_parser) so should not fail here
        if dtype not in self._data_types:
            raise RuntimeError('Unknow data type')
        if dtype in self._data_types_simple:
            val_str = struct.pack('>'+self._data_types_simple[dtype], arg_val)
        elif dtype == 'string':
            arg_val = arg_val.encode('latin1')
            val_str = self._arg_parser_helper(len(arg_val), 'int')
            val_str += arg_val
        elif dtype in self._data_types_array:
            arg_val = np.ascontiguousarray(arg_val, dtype='>'+self._data_types_array[dtype])
            val_str = arg_val.tobytes()
        else: # dtype == '1Dstring':
            val_str = b''
            for a in arg_val:
                val_str += self._arg_parser_helper(a, 'string')
        return val_str

    def arg_parser(self, args, args_def):
        """
        Convert all the arguments from bytes to strings.

        args_def is a list of tuples (name, dtype) (similar to ret_parser)
           the user args are matched to all args_def with names that do not start with "_"
           Those should be calculated automatically:
            for example name=foo   will have name=_foo_N being the number of elements of foo
                                   and name=_foo_size being the number of bytes of foo
                                   (there is also _Ncol)
        """
        Nargs = len(args)
        if args_def is None:
            if Nargs != 0:
                raise RuntimeError('Unexpected arguments present. Should be none.')
            return None
        args_dict = {}
        base_args = [arg for arg in args_def if arg[0][0] != '_']
        extra_args = [arg for arg in args_def if arg[0][0] == '_']
        string_hdr_size = self._get_type_elem_size('int')
        if len(args) != len(base_args):
            raise RuntimeError('Invalid number of arguments')
        for arg, arg_def in zip(args, base_args):
            name, dtype = arg_def
            if name in args_dict:
                raise RuntimeError('Repeated arg name')
            if dtype not in self._data_types:
                raise RuntimeError('Unknow data type')
            args_dict[name] = arg
            elem_size = self._get_type_elem_size(dtype)
            if dtype == 'string':
                N = len(arg)
                args_dict['_'+name+'_N'] = N
                args_dict['_'+name+'_size'] = N + string_hdr_size
            elif dtype.startswith('1D'):
                N = len(arg)
                args_dict['_'+name+'_N'] = N
                if dtype == '1Dstring':
                    size = 0
                    for a in arg:
                        size += len(a) + string_hdr_size
                else:
                    size = N*elem_size
                args_dict['_'+name+'_size'] = size
            elif dtype == '2Dfloat32':
                N = len(arg)
                Ncol = len(arg[0])
                args_dict['_'+name+'_N'] = N
                args_dict['_'+name+'_Ncol'] = Ncol
                args_dict['_'+name+'_size'] = N*Ncol*elem_size
        for arg_def in extra_args:
            name, dtype = arg_def
            if name == '_arrays_size':
                # Check all lengths are the same
                length = None
                for k, v in args_dict.items():
                    if k.endswith('_N'):
                        if length is None:
                            length = v
                        if length != v:
                            raise ValueError('Some of the arrays do not have the same length')
                args_dict['_arrays_size'] = length
            if name not in args_dict:
                raise RuntimeError('Missing arg name')
            if dtype not in self._data_types:
                raise RuntimeError('Unknow data type')
        args_str = bytearray()
        for arg_def in args_def:
            name, dtype = arg_def
            arg_str = self._arg_parser_helper(args_dict[name], dtype)
            name_size = '_'+name+'_size'
            if name_size in args_dict and len(arg_str) != args_dict[name_size]:
                raise RuntimeError('Calculated size and real size different for arg: %s'%name)
            args_str.extend(arg_str)
        return args_str

    #def TDS_Open(self):
    #    ret = self.do_both('3DSOpen')
    #    return self.ret_parser(ret)

    #def TDS_SwChSignalGet(self):
    #    ret = self.do_both('3DSSwChSignalGet')
    #    return self.ret_parser(ret, [('sweep_channel', 'int'), ('channel_names_N', 'int'), ('Nch', 'int'), ('channel_names', '1Dstring')])

    def do_both_wait(self, name, args_def, rets_def, args, state='all'):
        if state not in ['all', 'wait', 'request', 'reply']:
            raise ValueError("state needs to be one of 'all', 'wait', 'request', 'reply'")
        if state in ['all', 'request']:
            ret = self.do_request(name, self.arg_parser(args, args_def))
        if state in ['all', 'wait']:
            ret = self.wait_recv()
        if state in ['all', 'reply']:
            ret = self.ret_parser(self.do_response(name), rets_def)
        return ret

    def _create_helper(self, name, args_def=None, rets_def=None, add_error=True, get_response=True):
        """
        Create the functions of the class given the arguments (and their type) of the function.
        get_response can be False, True or 'state'
        """
        func_name = name
        self = weakref.proxy(self)
        if name.startswith('3DS'): # Python's function can't start with a number
            func_name = 'TDS_'+name[3:]
        elif name.startswith('1DS'):
            func_name = 'ODS_'+name[3:]
        doc = "function arguments:\n"
        if args_def is None:
            doc += '    No arguments\n'
        else:
            for a in args_def:
                a_name = a[0]
                if a_name[0] != '_':
                    doc += '    %15s : %s\n'%(a_name, a[1])
        if get_response == 'state':
            doc += '    %15s : %s\n'%('state', "specified only as keyword argument and one of 'all' (default), 'wait', 'request', 'reply'")
        if get_response:
            if get_response is True:
                func = lambda *args: self.ret_parser(self.do_both(name, self.arg_parser(args, args_def)), rets_def, add_error)
            elif get_response == 'state':
                func = lambda *args, **kwargs: self.do_both_wait(name, args_def, rets_def, args, kwargs.pop('state', 'all'))
            else:
                raise ValueError("get_response can only be True, False, 'state'")
            doc += 'Return Values:\n'
            if rets_def is not None:
                for r in rets_def:
                    doc += '    %15s : %s\n'%(r[0], r[1])
            if add_error:
                doc += '    %15s : %s\n'%('error_desc', 'string')
                doc += '    %15s : %s\n'%('error_status', 'uint32')
        else:
            func = lambda *args: self.do_both(name, self.arg_parser(args, args_def), get_response=False)
            doc += 'No return values'
        func.__doc__ = doc
        setattr(self, func_name, func)

    def _create(self):
        """
        List of the functions to create.
        The available functions are listed in TCPProtocol_Tramea_2018.pdf.

        Note : The parser handles string sizes. Do not include an argument before a string to indicate it's size.
                However, arrays need to have their size specified.
        """
        self._create_helper('3DSChannelsSet', args_def=[('_ch_indexes_N', 'int'), ('ch_indexes', '1Dint')])
        self._create_helper('3DSChannelsGet', rets_def=[('_ch_indexes_N', 'int'), ('ch_indexes', '1Dint'), ('_ch_names_size', 'int'), ('_ch_names_N', 'int'), ('ch_names', '1Dstring')]) # missing 1Dstring argument in the documentation Nanonis
        self._create_helper('3DSSaveOptionsSet', args_def=[('series_name', 'string'), ('create_date_time_folder', 'uint32')])
        self._create_helper('3DSSaveOptionsGet', rets_def=[('series_name', 'string'), ('create_date_time_folder', 'uint32'), ('_fixed_params_size', 'int'), ('_fixed_params_N', 'int'), ('fixed_params', '1Dstring')])
        self._create_helper('3DSStart')
        self._create_helper('3DSStop')
        self._create_helper('3DSOpen')
        self._create_helper('3DSStatusGet', rets_def=[('status', 'uint32')]) # new in version R8066 (status of the 3D Sweep : 0=Stopped, 1=Running, 2=Paused)
        self._create_helper('3DSSwChSignalSet', args_def=[('sweep_channel_index', 'int')])
        self._create_helper('3DSSwChSignalGet', rets_def=[('sweep_channel_index', 'int'), ('_channel_names_size', 'int'), ('_channel_names_N', 'int'), ('channel_names', '1Dstring')])
        self._create_helper('3DSSwChLimitsGet', rets_def=[('start', 'float32'), ('stop', 'float32')])
        self._create_helper('3DSSwChLimitsSet', args_def=[('start', 'float32'), ('stop', 'float32')])
        self._create_helper('3DSSwChPropsSet', args_def=[('npoints', 'int'), ('nsweeps', 'int'), ('backward_sweep', 'int'), ('end_sweep_action', 'int'), ('end_sweep_value', 'float32'), ('save_all', 'int')])
        self._create_helper('3DSSwChPropsGet', rets_def=[('npoints', 'int'), ('nsweeps', 'int'), ('backward_sweep', 'int'), ('end_sweep_action', 'int'), ('end_sweep_value', 'float32'), ('save_all', 'int')])
        self._create_helper('3DSSwChTmngSet', args_def=[('initial_settling_time', 'float32'), ('settling_time', 'float32'), ('integration_time', 'float32'), ('end_settling_time', 'float32'), ('max_slew_rate', 'float32')])
        self._create_helper('3DSSwChTmngGet', rets_def=[('initial_settling_time', 'float32'), ('settling_time', 'float32'), ('integration_time', 'float32'), ('end_settling_time', 'float32'), ('max_slew_rate', 'float32')])
        self._create_helper('3DSSwChSegModeSet', args_def=[('segments_mode', 'int')])
        self._create_helper('3DSSwChSegModeGet', rets_def=[('segments_mode', 'int')])
        # Note that _arrays_size is handle specially.
        self._create_helper('3DSSwChSegValuesSet', args_def=[('_arrays_size', 'int'), ('start_values', '1Dfloat32'), ('stop_values', '1Dfloat32'), ('settling_times', '1Dfloat32'), ('integration_times', '1Dfloat32'), ('n_steps', '1Dint'), ('is_last_segment', '1Duint32')]) # This module must be in multi segment mode.  This must be explicitly set before calling this command'
        self._create_helper('3DSSwChSegValuesGet', rets_def=[('_arrays_size', 'int'), ('start_values', '1Dfloat32'), ('stop_values', '1Dfloat32'), ('settling_times', '1Dfloat32'), ('integration_times', '1Dfloat32'), ('n_steps', '1Dint'), ('is_last_segment', '1Duint32')])
        self._create_helper('3DSStCh1SignalSet', args_def=[('step_ch1_index', 'int')])
        self._create_helper('3DSStCh2SignalSet', args_def=[('step_ch2_index', 'int')])
        self._create_helper('3DSStCh1SignalGet', rets_def=[('step_ch1_index', 'int'), ('_ch_names_size','int'), ('_ch_names_N','int'), ('ch_names','1Dstring')])
        self._create_helper('3DSStCh2SignalGet', rets_def=[('step_ch2_index', 'int'), ('_ch_names_size','int'), ('_ch_names_N','int'), ('ch_names','1Dstring')])
        self._create_helper('3DSStCh1LimitsSet', args_def=[('start', 'float32'), ('stop', 'float32')])
        self._create_helper('3DSStCh2LimitsSet', args_def=[('start', 'float32'), ('stop', 'float32')])
        self._create_helper('3DSStCh1LimitsGet', rets_def=[('start', 'float32'), ('stop', 'float32')])
        self._create_helper('3DSStCh2LimitsGet', rets_def=[('start', 'float32'), ('stop', 'float32')])
        self._create_helper('3DSStCh1PropsSet', args_def=[('npoints', 'int'), ('backward_sweep', 'int'), ('end_sweep_action', 'int'), ('end_sweep_value', 'float32')])
        self._create_helper('3DSStCh2PropsSet', args_def=[('npoints', 'int'), ('backward_sweep', 'int'), ('end_sweep_action', 'int'), ('end_sweep_value', 'float32')])
        self._create_helper('3DSStCh1PropsGet', rets_def=[('npoints', 'int'), ('backward_sweep', 'int'), ('end_sweep_action', 'int'), ('end_sweep_value', 'float32')])
        self._create_helper('3DSStCh2PropsGet', rets_def=[('npoints', 'int'), ('backward_sweep', 'int'), ('end_sweep_action', 'int'), ('end_sweep_value', 'float32')])
        self._create_helper('3DSStCh1TmngSet', args_def=[('initial_settling_time', 'float32'), ('end_settling_time', 'float32'), ('max_slew_rate', 'float32')])
        self._create_helper('3DSStCh2TmngSet', args_def=[('initial_settling_time', 'float32'), ('end_settling_time', 'float32'), ('max_slew_rate', 'float32')])
        self._create_helper('3DSStCh1TmngGet', rets_def=[('initial_settling_time', 'float32'), ('end_settling_time', 'float32'), ('max_slew_rate', 'float32')])
        self._create_helper('3DSStCh2TmngGet', rets_def=[('initial_settling_time', 'float32'), ('end_settling_time', 'float32'), ('max_slew_rate', 'float32')])
        # The maximum_time is set incorrectly. The nanonis internal interface seems to be using int instead of float32
        #self._create_helper('3DSAdvTmngRowLimitSet', args_def=[('row_index', 'int'), ('maximum_time_time', 'float32'), ('channel_index', 'int')])
        self._create_helper('3DSAdvTmngRowLimitSet', args_def=[('row_index', 'int'), ('maximum_time_time', 'int'), ('channel_index', 'int')])
        self._create_helper('3DSAdvTmngRowLimitGet', args_def=[('row_index', 'int')], rets_def=[('maximum_time_time', 'float32'), ('channel_index', 'int'), ('_channels_name_size', 'int'), ('_channels_name_N', 'int'), ('channels_name', '1Dstring')])
        self._create_helper('3DSAdvTmngRowMethodsSet', args_def=[('row_index', 'int'), ('method_lower', 'int'), ('method_middle', 'int'), ('method_upper', 'int'), ('method_alternative', 'int')])
        self._create_helper('3DSAdvTmngRowMethodsGet', args_def=[('row_index', 'int')], rets_def=[('method_lower', 'int'), ('method_middle', 'int'), ('method_upper', 'int'), ('method_alternative', 'int')])
        # The next 2 have a wrong description in document (it uses float32, but the interface seems to require float64)
        #self._create_helper('3DSAdvTmngRowValsSet', args_def=[('row_index', 'int'), ('middle_range_from', 'float32'), ('lower_range_value', 'float32'), ('middle_range_value', 'float32'), ('middle_range_to', 'float32'), ('upper_range_value', 'float32'), ('alternative_range_value', 'float32')])
        #self._create_helper('3DSAdvTmngRowValsGet', args_def=[('row_index', 'int')], rets_def=[('middle_range_from', 'float32'), ('lower_range_value', 'float32'), ('middle_range_value', 'float32'), ('middle_range_to', 'float32'), ('upper_range_value', 'float32'), ('alternative_range_value', 'float32')])
        self._create_helper('3DSAdvTmngRowValsSet', args_def=[('row_index', 'int'), ('middle_range_from', 'float64'), ('lower_range_value', 'float64'), ('middle_range_value', 'float64'), ('middle_range_to', 'float64'), ('upper_range_value', 'float64'), ('alternative_range_value', 'float64')])
        self._create_helper('3DSAdvTmngRowValsGet', args_def=[('row_index', 'int')], rets_def=[('middle_range_from', 'float64'), ('lower_range_value', 'float64'), ('middle_range_value', 'float64'), ('middle_range_to', 'float64'), ('upper_range_value', 'float64'), ('alternative_range_value', 'float64')])
        self._create_helper('3DSAdvTmngEnable', args_def=[('enable', 'uint32')])
        self._create_helper('3DSAdvTmngSend')
        self._create_helper('1DSChannelsSet', args_def=[('_ch_indexes_N', 'int'), ('ch_indexes', '1Dint')])
        self._create_helper('1DSChannelsGet', rets_def=[('_ch_indexes_N', 'int'), ('ch_indexes', '1Dint')])
        self._create_helper('1DSSweepSignalSet', args_def=[('ch_index', 'int')])
        self._create_helper('1DSSweepSignalGet', rets_def=[('ch_index', 'int'), ('_ch_names_size','int'), ('_ch_names_N','int'), ('ch_names','1Dstring')])
        # for next 2: document says float64 for but it seems to be using float32
        self._create_helper('1DSLimitsSet', args_def=[('lower_limit', 'float32'), ('upper_limit', 'float32')])
        self._create_helper('1DSLimitsGet', rets_def=[('lower_limit', 'float32'), ('upper_limit', 'float32')])
        self._create_helper('1DSPropsSet', args_def=[('initial_settling_ms', 'float32'), ('max_slew_rate', 'float32'), ('nsteps', 'int'), ('period_ms', 'uint16'), ('autosave', 'int'), ('show_save_dialog', 'int'), ('settling_time_ms', 'float32')])
        self._create_helper('1DSPropsGet', rets_def=[('initial_settling_ms', 'float32'), ('max_slew_rate', 'float32'), ('nsteps', 'int'), ('period_ms', 'uint16'), ('autosave', 'int'), ('show_save_dialog', 'int'), ('settling_time_ms', 'float32')])
        self._create_helper('1DSStart', args_def=[('get_data', 'uint32'), ('sweep_dir_from_lower', 'uint32'), ('save_base_name', 'string'), ('reset_signal', 'uint32')], rets_def=[ ('_ch_names_size','int'), ('_ch_names_N','int'), ('ch_names','1Dstring'), ('_data_N', 'int'), ('_data_Ncol', 'int'), ('data', '2Dfloat32')], get_response='state')
        self._create_helper('1DSStop')
        self._create_helper('1DSOpen')
        self._create_helper('UOModeSet', args_def=[('output_index', 'int'), ('output_mode', 'uint16')])
        self._create_helper('UOModeGet', args_def=[('output_index', 'int')], rets_def=[('output_mode', 'uint16')])
        self._create_helper('UOMonChannelSet', args_def=[('output_index', 'int'), ('monitor_channel_index', 'int')])
        self._create_helper('UOMonChannelGet', args_def=[('output_index', 'int')], rets_def=[('monitor_channel_index', 'int')])
        self._create_helper('UOValSet', args_def=[('output_index', 'int'), ('output_value', 'float32')])
        self._create_helper('UOCalibrSet', args_def=[('output_index', 'int'), ('calibration_per_volt', 'float32'), ('offset_in physical_units', 'float32')])
        self._create_helper('UOCalcSignalNameSet', args_def=[('output_index', 'int'), ('signal_name', 'string')])
        self._create_helper('UOCalcSignalNameGet', args_def=[('output_index', 'int')], rets_def=[('signal_name', 'string')])
        self._create_helper('UOLimitsSet', args_def=[('output_index', 'int'), ('upper_limit', 'float32'), ('lower_limit', 'float32')])
        self._create_helper('UOLimitsGet', args_def=[('output_index', 'int')], rets_def=[('upper_limit', 'float32'), ('lower_limit', 'float32')])
        self._create_helper('DigLinePropsSet', args_def=[('line_index', 'uint32'), ('port_sel', 'uint32'), ('direction', 'uint32'), ('polarity', 'uint32')])
        self._create_helper('DigLineOutStatusSet', args_def=[('port_sel', 'uint32'), ('line_index', 'uint32'), ('status', 'uint32')])
        self._create_helper('DigLinesTTLValsGet', args_def=[('port_sel', 'uint16')], rets_def=[('_ttl_voltages_N', 'int'), ('ttl_voltages', '1Duint32')])
        self._create_helper('DigLinesPulse', args_def=[('port_sel', 'uint16'), ('_lines_index_N', 'int'), ('lines_index', '1Duint8'), ('pulse_width_s', 'float32'), ('pulse_pause_s', 'float32'), ('number_pulses', 'int'), ('wait_until_finished', 'uint32')], get_response='state')
        self._create_helper('UICalibrSet', args_def=[('signal_index', 'int'), ('calibration_per_volt', 'float32'), ('offset_in_physical_units', 'float32')])
        self._create_helper('SignalsNamesGet', rets_def=[('_signal_names_size', 'int'), ('_signal_names_N', 'int'), ('signal_names', '1Dstring')])
        self._create_helper('SignalsInSlotsGet', rets_def=[('_signal_names_size', 'int'), ('_signal_names_N', 'int'), ('signal_names', '1Dstring'), ('_signal_indexes_N', 'int'), ('signal_indexes', '1Dint')])
        self._create_helper('SignalCalibrGet', args_def=[('signal_index', 'int')], rets_def=[('calibration_per_volt', 'float32'), ('offset_in_physical_units', 'float32')])
        self._create_helper('SignalInSlotSet', args_def=[('slot', 'int'), ('RT_signal_index', 'int')])
        self._create_helper('SignalRangeGet', args_def=[('signal_index', 'int')], rets_def=[('max_lim', 'float32'), ('min_lim', 'float32')])
        self._create_helper('SignalValGet', args_def=[('signal_index', 'int'), ('wait_for_newest_data','uint32')], rets_def=[('signal_value', 'float32')])
        self._create_helper('SignalsValGet', args_def=[('_signal_indexes_N', 'int'), ('signal_indexes', '1Dint'), ('wait_for_newest_data','uint32')], rets_def=[('_signals_values_N', 'int'), ('signals_values', '1Dfloat32')])
        self._create_helper('SignalsMeasNamesGet', rets_def=[('meas_channels_size', 'int'), ('_meas_channels_N','int'), ('meas_channels', '1Dstring')])
        self._create_helper('SignalsAddRTGet', rets_def=[('_signal_names_size', 'int'), ('_signal_names_N','int'), ('signal_names', '1Dstring'), ('name_23', 'string'), ('name_24', 'string')])
        self._create_helper('SignalsAddRTSet', args_def=[('name_23', 'int'), ('name_24', 'int')])
        self._create_helper('UtilSessionPathGet', rets_def=[('path', 'string')])
        # from_to session when 1 will skip the path and use the session file instead
        # paths can be full. If it does not include the .ini extension, it will create a dir containing Nanonis-Session.ini
        # with just a filename it creates something in C:\ProgramData\Nanonis\Certificate ...\Settings
        self._create_helper('UtilSettingsLoad', args_def=[('path', 'string'), ('load_from_session', 'uint32')])
        self._create_helper('UtilSettingsSave', args_def=[('path', 'string'), ('save_to_session', 'uint32')])
        self._create_helper('UtilLayoutLoad', args_def=[('path', 'string'), ('load_from_session', 'uint32')])
        self._create_helper('UtilLayoutSave', args_def=[('path', 'string'), ('save_to_session', 'uint32')])
        self._create_helper('UtilLock')
        self._create_helper('UtilUnLock')
        self._create_helper('UtilRTFrqSet', args_def=[('rt_freq_hz', 'float32')])
        self._create_helper('UtilRTFrqGet', rets_def=[('rt_freq_hz', 'float32')])
        self._create_helper('UtilAnimSet', args_def=[('animation_period_s', 'float32')])
        self._create_helper('UtilAnimGet', rets_def=[('animation_period_s', 'float32')])
        self._create_helper('UtilRTOversSet', args_def=[('rt_oversampling', 'int')])
        self._create_helper('UtilRTOversGet', rets_def=[('rt_oversampling', 'int')])
        ##   The Oscilloscope/PSD functions do not seem to work
        # self._create_helper('OHRChannelSet', args_def=[('channel_index', 'int')])
        # self._create_helper('OHRChannelGet', rets_def=[('channel_index', 'int')])
        # self._create_helper('OHROversSet', args_def=[('oversamplng_index', 'int')])
        # self._create_helper('OHROversGet', rets_def=[('oversamplng_index', 'int')])
        # self._create_helper('OHRCalibrModeSet', args_def=[('calib_mode', 'uint16')]) # 0=raw, 1=calibrated
        # self._create_helper('OHRCalibrModeGet', rets_def=[('calib_mode', 'uint16')])
        # self._create_helper('OHRSamplesSet', args_def=[('num_samples', 'int')])
        # self._create_helper('OHRSamplesGet', rets_def=[('num_samples', 'int')])
        # self._create_helper('OHRPreTriggerSet', args_def=[('pretrig_samples', 'uint32'), ('pretrig_s', 'float64')])
        # self._create_helper('OHRPreTriggerGet', rets_def=[('pretrig_samples', 'int')])
        # self._create_helper('OHRRun')
        # self._create_helper('OHROsciDataGet', args_def=[('wait_for_next_trig', 'uint16'), ('timeout_s', 'float64')], rets_def=[('t0','string'), ('dt', 'float64'), ('_Y_N', 'int'), ('Y', '1Dfloat32'), ('is_timeout', 'uint32')])
        # self._create_helper('OHRTriggerModeSet', args_def=[('trig_mode', 'uint16')]) # 0=immediate, 1=level, 2=digital
        # self._create_helper('OHRTriggerModeGet', rets_def=[('trig_mode', 'uint16')])
        # self._create_helper('OHRTriggerLevChannelSet', args_def=[('level_trig_ch_index', 'int')])
        # self._create_helper('OHRTriggerLevChannelGet', rets_def=[('level_trig_ch_index', 'int')])
        # self._create_helper('OHRTriggerLevValSet', args_def=[('trigger_level', 'float64')])
        # self._create_helper('OHRTriggerLevValGet', rets_def=[('trigger_level', 'float64')])
        # self._create_helper('OHRTriggerLevHystSet', args_def=[('trigger_level_hysteresis', 'float64')])
        # self._create_helper('OHRTriggerLevHystGet', rets_def=[('trigger_level_hysteresis', 'float64')])
        # self._create_helper('OHRTriggerLevSlopeSet', args_def=[('triger_slope_falling', 'unit16')])
        # self._create_helper('OHRTriggerLevSlopeGet', rets_def=[('triger_slope_falling', 'unit16')])
        # self._create_helper('OHRTriggerDigChannelSet', args_def=[('channel_index', 'int')])
        # self._create_helper('OHRTriggerDigChannelGet', rets_def=[('channel_index', 'int')])
        # self._create_helper('OHRTriggerArmModeSet', args_def=[('trigger_arming_mode', 'uint16')]) # 0=single, 1=continuous
        # self._create_helper('OHRTriggerArmModeGet', rets_def=[('trigger_arming_mode', 'uint16')])
        # self._create_helper('OHRTriggerDigSlopeSet', args_def=[('digital_slope_falling', 'uint16')])
        # self._create_helper('OHRTriggerDigSlopeGet', rets_def=[('digital_slope_falling', 'uint16')])
        # self._create_helper('OHRTriggerRearm')
        # self._create_helper('OHRPSDShow', args_def=[('show_psd', 'uint32')])
        # self._create_helper('OHRPSDWeightSet', args_def=[('psd_weighting', 'uint16')]) # 0=linear, 1=exponential
        # self._create_helper('OHRPSDWeightGet', rets_def=[('psd_weighting', 'uint16')])
        # self._create_helper('OHRPSDWindowSet', args_def=[('psd_window_type', 'uint16')]) # 0=None, 1=Hanning, 2=Hamming
        # self._create_helper('OHRPSDWindowGet', rets_def=[('psd_window_type', 'uint16')])
        # self._create_helper('OHRPSDAvrgTypeSet', args_def=[('psd_averaging_type', 'uint16')]) # 0=None, 1=Vector, 2=RMS, 3=Peak hold
        # self._create_helper('OHRPSDAvrgTypeGet', rets_def=[('psd_averaging_type', 'uint16')])
        # self._create_helper('OHRPSDAvrgCountSet', args_def=[('psd_averaging_count', 'int')])
        # self._create_helper('OHRPSDAvrgCountGet', rets_def=[('psd_averaging_count', 'int')])
        # self._create_helper('OHRPSDAvrgRestart')
        # self._create_helper('OHRPSDDataGet', args_def=[('wait_for_next_trig', 'uint16'), ('timeout_s', 'float64')], rets_def=[('f0','float64'), ('df', 'float64'), ('_Y_N', 'int'), ('Y', '1Dfloat32'), ('is_timeout', 'uint32')])
        self._create_helper('LIModOnOffSet',args_def=[('modulator_number','int'), ('lockin_on_off','uint32')])
        self._create_helper('LIModOnOffGet',args_def=[('modulator_number','int')], rets_def =[('lockin_on_off','uint32')])
        self._create_helper('LIModSignalSet',args_def=[('modulator_number','int'), ('modulator_signal_index','int')])
        self._create_helper('LIModSignalGet',args_def=[('modulator_number','int')], rets_def=[('modulator_signal_index','int')])
        self._create_helper('LIModPhaseRegIndexSet',args_def=[('modulator_number','int'), ('phase_register_index','int')])
        self._create_helper('LIModPhaseRegIndexGet',args_def=[('modulator_number','int')], rets_def=[('phase_register_index','int')])
        self._create_helper('LIModHarmonicSet',args_def=[('modulator_number','int'), ('harmonic','int')])
        self._create_helper('LIModHarmonicGet',args_def=[('modulator_number','int')], rets_def=[('harmonic','int')])
        self._create_helper('LIModPhaseSet',args_def=[('modulator_number','int'), ('phase','float32')])
        self._create_helper('LIModPhaseGet',args_def=[('modulator_number','int')], rets_def=[('phase','float32')])
        self._create_helper('LIModAmplitudeSet',args_def=[('modulator_number','int'), ('amplitude','float32')])
        self._create_helper('LIModAmplitudeGet',args_def=[('modulator_number','int')], rets_def=[('amplitude','float32')])
        self._create_helper('LIModPhaseRegFreqSet',args_def=[('modulator_number','int'), ('freq','float64')])
        self._create_helper('LIModPhaseRegFreqGet',args_def=[('modulator_number','int')], rets_def=[('freq','float64')])
        self._create_helper('LIDemodSignalSet',args_def=[('demodulator_number','int'), ('demodulator_signal_index','int')])
        self._create_helper('LIDemodSignalGet',args_def=[('demodulator_number','int')], rets_def=[('demodulator_signal_index','int')])
        self._create_helper('LIDemodHPFilterSet',args_def=[('demodulator_number','int'), ('HP_filter_order','int'), ('HP_filter_cutoff_freq','float32')])
        self._create_helper('LIDemodHPFilterGet',args_def=[('demodulator_number','int')], rets_def=[('HP_filter_order','int'), ('HP_filter_cutoff_freq','float32')])
        # The Script modules commands are untested
        self._create_helper('ScriptLoad', args_def=[('path', 'string'), ('load_from_session', 'uint32')])
        self._create_helper('ScriptSave', args_def=[('path', 'string'), ('save_to_session', 'uint32')])
        self._create_helper('ScriptDeploy', args_def=[('script_index', 'int')])
        self._create_helper('ScriptUndeploy', args_def=[('script_index', 'int')])
        self._create_helper('ScriptRun', args_def=[('script_index', 'int'), ('wait_until_finished', 'uint32')])
        self._create_helper('ScriptStop')

#######################################################
##    Nanonis Tramea
#######################################################

class nanonis_dev(Base2Device):
    def __init__(self, get_func_name=None, set_func_name=None, return_func=None, params_option_map=[], get_params_option_map='auto', **kwargs):
        """
        func_name is the function name in Nanonis_TCP object
        return_func is either the string of the paramter to return, None for no return or a function that generates the correct
         return out of the dict
        params_option_map is a list of the pyHegel options names in the order they most be presented to the nanonis call
        """
        super(nanonis_dev, self).__init__(**kwargs)
        self._getdev_p = get_func_name
        self._setdev_p = set_func_name
        self._params_map = params_option_map
        if get_params_option_map == 'auto':
            # make a copy
            get_params_option_map = params_option_map[:]
            if '_val' in get_params_option_map:
                get_params_option_map.remove('_val')
        self._params_map_get = get_params_option_map
        if isinstance(return_func, str):
            return_func = lambda x, f=return_func: x[f]
        self._return_func = return_func
    def _conv_params(self, options, params_map):
        return [options[k] for k in params_map]
    def _handle_error(self, ret_val):
        if ret_val.error_status:
            raise RuntimeError(self.perror(ret_val.error_desc))
    def _set_write(self, val, options):
        options = options.copy()
        if isinstance(self.choices, ChoiceBase):
            val = self.choices.tostr(val)
        options['_val'] = val
        params = self._conv_params(options, self._params_map)
        ret = getattr(self.instr._nanonis, self._setdev_p)(*params)
        self._handle_error(ret)
    def _get_ask(self, options):
        params = self._conv_params(options, self._params_map_get)
        ret = getattr(self.instr._nanonis, self._getdev_p)(*params)
        self._handle_error(ret)
        val = self._return_func(ret)
        if isinstance(self.choices, ChoiceBase):
            val = self.choices(val)
        return val

@register_instrument('SPECS', 'Nanonis Tramea')
class nanonis_tramea(BaseInstrument):
    """
    This instrument controls a SPECS Nanonis Tramea system.
    To use this instrument, the most useful devices are probably:
        out_level
        in_level
        fetch
        out_level_now
        ramp_out_level
    Important methods are:
        reset_all_output_cache
        print_signals
        settings_load
        settings_save
        conf_output_calibration
        conf_input_calibration
        clear_input_buffer
    """
    # For the pyHegel interface signals are numbered starting at 1. For the raw interface it starts at 0.
    def __init__(self, server_addr='localhost', server_port=6501, timeout=3, quiet_delete=False, quiet_load=True, **kwargs):
        """
        server_addr is the address of the nanonis application. The application needs to have enabled tcp and the same port
             as set in server_port.
        """
        self._nanonis = Nanonis_TCP(server_addr, server_port, timeout, quiet_delete, quiet_load)
        super(nanonis_tramea, self).__init__(**kwargs)

    def idn(self):
        return "SPECS,Nanonis Tramea,NoSerial,v0"

    def __del__(self):
        del self._nanonis
        super(nanonis_tramea, self).__del__()

    def init(self, full=False):
        if full:
            self.reset_all_output_cache()

    def clear_input_buffer(self):
        """ Empties the input buffer in case of error.
        """
        self._nanonis.recv_empty()

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        orig = self.current_out_channel.get()
        chs = self._fetch_ch_helper(out_num=True)
        levels = []
        confs = []
        modes = []
        for c in chs:
            levels.append(self.out_level.get(ch=c-24))
            confs.append(self.conf_output_calibration())
            mode = self.out_mode.get()
            if mode == 'monitor':
                extra = self.out_monitor_ch.get()
            elif mode == 'calc':
                extra = self.out_calc_name.get()
            else:
                extra = None
            modes.append((mode, extra))
        self.current_out_channel.set(orig)
        headers = []
        # verify chs is continous and add it in header if it is not continuous
        if chs != list(range(25, 25+len(chs))):
            headers += ['out_channels={}'.format([c-24 for c in chs])]
        headers += ['levels=%s'%levels,
                    'confs=%s'%confs,
                    'modes=%s'%modes]
        return headers + self._conf_helper(options)

    def _handle_error(self, ret_val):
        if ret_val.error_status:
            raise RuntimeError(self.perror(ret_val.error_desc))

    def threeD_swepper_start(self):
        self._nanonis.TDS_Start()
    def threeD_swepper_stop(self):
        self._nanonis.TDS_Stop()
    def threeD_swepper_open(self):
        self._nanonis.TDS_Open()

    def settings_load(self, path=None):
        """
        provide the path where to load the settings from.
        It can be a directory name which will use a file named Nanonis-Session.ini
        within that directory.
        It can be a full path name with a file with .ini as extension.
        Or it can be None, in which case it loads the session settings.
        """
        if path is None:
            ret = self._nanonis.UtilSettingsLoad('', 1)
        else:
            ret = self._nanonis.UtilSettingsLoad(path, 0)
        self._handle_error(ret)

    def settings_save(self, path=None):
        """
        provide the path where to save the settings to.
        It can be a directory name which will use a file named Nanonis-Session.ini
        within that directory. It will create the necessary directory.
        It can be a full path name with a file with .ini as extension.
        Or it can be None, in which case it loads the session settings.
        """
        if path is None:
            ret = self._nanonis.UtilSettingsSave('', 1)
        else:
            ret = self._nanonis.UtilSettingsSave(path, 0)
        self._handle_error(ret)

    def conf_output_calibration(self, cal_per_volt=None, offset_in_physical_units=None, lower_limit=None, upper_limit=None, ch=None):
        """
        when no value is given, returns a tuple (cal_per_volt, offset_in_physical_units, lower_limit, upper_limit) for the selected ch
        Otherwise modifies only the given values.
        They are all in physical units.
        """
        if ch is not None:
            self.current_out_channel.set(ch)
        ch = self.current_out_channel.get()
        if cal_per_volt is None and offset_in_physical_units is None and lower_limit is None and  upper_limit is None:
            # we read
            ret1 = self._nanonis.SignalCalibrGet(ch-1+24)
            self._handle_error(ret1)
            # This functions starts ch at 1 instead of 0.
            ret2 = self._nanonis.UOLimitsGet(ch)
            self._handle_error(ret2)
            return ret1.calibration_per_volt, ret1.offset_in_physical_units, ret2.lower_limit, ret2.upper_limit
        if cal_per_volt is not None or offset_in_physical_units is not None:
            if cal_per_volt is None or offset_in_physical_units is None:
                ret = self._nanonis.SignalCalibrGet(ch-1+24)
                self._handle_error(ret)
                if cal_per_volt is None:
                    cal_per_volt = ret.calibration_per_volt
                else:
                    offset_in_physical_units = ret.offset_in_physical_units
            # This functions starts ch at 1 instead of 0.
            ret = self._nanonis.UOCalibrSet(ch, cal_per_volt, offset_in_physical_units)
            self._handle_error(ret)
        if lower_limit is not None or upper_limit is not None:
            if lower_limit is None or upper_limit is None:
                # This functions starts ch at 1 instead of 0.
                ret = self._nanonis.UOLimitsGet(ch)
                self._handle_error(ret)
                if upper_limit is None:
                    upper_limit = ret.upper_limit
                else:
                    lower_limit = ret.lower_limit
            # This functions starts ch at 1 instead of 0.
            ret = self._nanonis.UOLimitsSet(ch, upper_limit, lower_limit)
            self._handle_error(ret)

    def conf_input_calibration(self, cal_per_volt=None, offset_in_physical_units=None, ch=None):
        """
        when no value is given, returns a tuple (cal_per_volt, offset_in_physical_units) for the selected ch
        Otherwise modifies only the given values.
        """
        if ch is not None:
            self.current_in_channel.set(ch)
        ch = self.current_in_channel.get()
        if cal_per_volt is None and offset_in_physical_units is None:
            # we read
            ret = self._nanonis.SignalCalibrGet(ch-1)
            self._handle_error(ret)
            return ret.calibration_per_volt, ret.offset_in_physical_units
        if cal_per_volt is None or offset_in_physical_units is None:
            ret = self._nanonis.SignalCalibrGet(ch-1)
            self._handle_error(ret)
            if cal_per_volt is None:
                cal_per_volt = ret.calibration_per_volt
            else:
                offset_in_physical_units = ret.offset_in_physical_units
        # This functions starts ch at 1 instead of 0.
        ret = self._nanonis.UICalibrSet(ch, cal_per_volt, offset_in_physical_units)
        self._handle_error(ret)

    def _fetch_ch_helper(self, ch=None, out_num=False):
        if ch is None:
            installed = self.signals_installed
            if out_num:
                ch = [i for i, name in installed if i>24 and name.lower().startswith('output')]
            else:
                ch = [i for i, name in installed if i<=24] # 24 should be the last input channel in the list
        if not isinstance(ch, (list)):
            ch = [ch]
        return ch

    def _fetch_getformat(self, **kwarg):
        ch = kwarg.get('ch', None)
        out_num = kwarg.get('out_num', False)
        ch = self._fetch_ch_helper(ch)
        multi = []
        title = 'ch%02i'
        off = 0
        if out_num:
            title = 'outch%02i'
            off = 24
        for c in ch:
            multi.append(title%(c-off))
        fmt = self.fetch._format
        fmt.update(multi=multi)
        return BaseDevice.getformat(self.fetch, **kwarg)

    def _fetch_getdev(self, ch=None, wait=True, out_num=False):
        """ ch is the single of list of multiple channels to read. It defaults to all the input channels.
            wait is like in_level. When True (default) it waits for the next new point
             otherwise it returns the current point
            out_num when True will use the output numbers instead and will get all the installed output channels
            when ch is None.
        """
        ch = self._fetch_ch_helper(ch, out_num)
        ch = [c-1 for c in ch]
        ret = self._nanonis.SignalsValGet(ch, wait)
        self._handle_error(ret)
        return ret.signals_values

    def _out_ch_helper(self, ch=None):
        if ch is not None:
            self.current_out_channel.set(ch)
        ch = self.current_out_channel.get()
        return ch

    def _ramp_out_level_getdev(self, ch=None):
        return self.out_level_now.get(ch=ch)
    def _ramp_out_level_checkdev(self, val, ch=None, detect_not_moving=False):
        self.out_level.check(val, ch=ch)
    def _ramp_out_level_setdev(self, val, ch=None, detect_not_moving=False):
        """
        parameters:
            ch: to select channel
            detect_not_moving: False by default. When True, it will stop ramping if it detects
                            the voltage stopped moving
            It also always tries to stop if we are close enough to the target.
            detect_not_moving does not work well when a large offset is used
            in the calibration (because of limited float resolution it will stop
            before the ramping is completed). I have seen it fail sometimes even with no offset.
        """
        # ch was set in check
        ch = self.current_out_channel.get()
        cal_per_volt, offset_in_physical_units, lower_limit, upper_limit = self.conf_output_calibration()
        # Since calculations are done in float (24 bit of resolution), the smallest change possible is limited by the offset
        offset_raw = abs(offset_in_physical_units/cal_per_volt)
        def raw(v):
            return (v-offset_in_physical_units)/cal_per_volt
        target = max(min(raw(val), 10), -10) # limit to +-10V
        # we need to do the calculations in raw units otherwise it is too hard to obtain a valid eps
        # 22 bits resolution is 4.2e6 levels on +-10V
        # 20 bits is 1.05e6.
        # Nanonis for output does not seem to care there is a limited hardware resolution.
        # It just uses the full float. so instead we have 24 bits which is 16.8e6
        # So to be certain about ending detection, use 1e-7
        eps = (20+offset_raw)*1e-7
        # use a list so it can be modified from check_state
        last_v = [np.inf] # inf to make sure it is different than the next value
        self.out_level.set(val)
        def check_state():
            #   It seems that when reading out_level_now (with wait=False) faster than animation time,
            # you can get up to 3 repeats of the same data. New data only comes once in 4.
            # The repeat reading usually are returned within 2 ms. The real reading takes animation time.
            # So when using timeit on out_level_now (with wait=False), you get an average time which is 1/4
            # of animation time.
            # But unless you always try 4 reading (something could change in the future) it is hard to detect that
            # it took only 2 ms, it is easy to get delays because of other sources (garbage collection, the computer busy somewhere else.)
            # So instead of try to find long reading, we take 4 unless we already detect a change.
            for i in range(4):
                v = raw(self.out_level_now.get(ch=ch, wait=False))
                if v != last_v[0]:
                    # if i != 3:
                    #     print('shorter read')
                    break
            is_done = abs(v-target) < eps
            if detect_not_moving:
                is_done = is_done or last_v[0] == v
            #print(abs(v-target) < eps, last_v[0] == v, v, target, eps)
            last_v[0] = v
            return is_done
        with release_lock_context(self):
            _retry_wait(check_state, -np.inf, delay=0.05)

    def reset_all_output_cache(self):
        """ The out_level does not read back the values from the instrument.
            Instead it maintains a cache with the last set value.
            This method will update the cache with the current out channel reading.
            It will update correctly unless a channel is currently ramping to a target value.
        """
        chs = self._fetch_ch_helper(out_num=True)
        vals = self.fetch.get(out_num=True)
        for c, v in zip(chs, vals):
            self.out_level._getdev_cache[(c-24,)] = v

    def print_signals(self, measured=False):
        self._read_signals_name()
        sigs, offset = (self.signals_meas_list, 0) if measured else (self.signals_list, 1)
        for c, n in enumerate(sigs):
            print("%3d:  %s"%(c+1,n))

    def _read_signals_name(self):
        ret = self._nanonis.SignalsMeasNamesGet()
        self._handle_error(ret)
        self.signals_meas_list = ret.meas_channels
        ret = self._nanonis.SignalsNamesGet()
        self._handle_error(ret)
        self.signals_list = ret.signal_names

    def _create_devs(self):
        try:
            self._read_signals_name()
        except socket.timeout:
            raise RuntimeError('Received a timeout. There is probably another active connection to the Nanonis server. Only the first one works.')
        # find out which channels are installed
        installed = [False]*len(self.signals_list)
        for name in self.signals_meas_list:
            if name not in self.signals_list:
                # to skip 'Timestamp (ms)', 'SC5 #1 Temp. (degC)', 'SC5 #2 Temp. (degC)'
                continue
            installed[self.signals_list.index(name)] = True
        self.signals_installed = [(i+1, nm) for i, (nm, is_installed) in enumerate(zip(self.signals_list, installed)) if is_installed]
        def check_output_name(name):
            n = name.lower()
            return n.startswith('output') or re.match(r'[cm]\d*:', n)
        states = [n.lower().startswith('input') for n in self.signals_list[:24]] + \
                 [check_output_name(n) for n in self.signals_list[24:24+50]]
        if not all(states):
            raise RuntimeError('Unexpected input/output names in signals_list')
        Ns = len(self.signals_list)
        Nm = len(self.signals_meas_list)
        Nin = Ns
        Nout = 48 # That would be the maximum with 3 TSO modules (Each with 16 out). TSC modules only have 8 out channels. The max is 3 modules.
        self.current_out_channel = MemoryDevice(1, choices=list(range(1, Nout+1)), no_type_conv=True)
        self.current_in_channel = MemoryDevice(1, choices=list(range(1, Nin+1)), no_type_conv=True)
        def In_dev(*args, **kwargs):
            options = kwargs.pop('options', {}).copy()
            options['ch'] = self.current_in_channel
            app = kwargs.pop('options_apply', ['ch'])
            options_conv = kwargs.pop('options_conv', {}).copy()
            options_conv.update(ch=lambda base_val, conv_val: base_val-1)
            p = kwargs.pop('params_option_map', None)
            if p is None:
                params_option_map = ['ch']
            else:
                params_option_map = p
            kwargs.update(options=options, options_apply=app, options_conv=options_conv, params_option_map=params_option_map)
            return nanonis_dev(*args, **kwargs)
        self.in_level = In_dev('SignalValGet', return_func='signal_value',
                                    doc="wait parameter when True (default) makes sure to obtain a completely new data point (takes longer)",
                                    params_option_map=['ch', 'wait'],
                                    options=dict(wait=True),
                                    options_lim=dict(wait=[True, False]),
                                    options_conv=dict(wait=lambda val, val_str: val))
        self.in_range = In_dev('SignalRangeGet', return_func=lambda x: (x.min_lim, x.max_lim),
                               multi=['min', 'max'],
                               doc='returns a min, max tuple')
        def Out_dev(*args, **kwargs):
            options = kwargs.pop('options', {}).copy()
            options['ch'] = self.current_out_channel
            app = kwargs.pop('options_apply', ['ch'])
            options_conv = kwargs.pop('options_conv', {}).copy()
            options_conv.update(ch=lambda base_val, conv_val: base_val)
            params_option_map=['ch', '_val']
            kwargs.update(options=options, options_apply=app, options_conv=options_conv, params_option_map=params_option_map)
            return nanonis_dev(*args, **kwargs)

        self.out_mode = Out_dev('UOModeGet', 'UOModeSet', return_func='output_mode',
                                    choices=ChoiceIndex(['user', 'monitor', 'calc', 'override'], noconv=True))
        out_choices = ChoiceIndex(self.current_in_channel.choices, noconv=True)
        self.out_monitor_ch = Out_dev('UOMonChannelGet' , 'UOMonChannelSet', return_func='monitor_channel_index',
                                      choices=out_choices, doc='see print_signals for the names. You need to provide the index.')
        self.out_calc_name = Out_dev('UOCalcSignalNameGet' , 'UOCalcSignalNameSet', return_func='signal_name')
        self.out_level = Out_dev('UOCalcSignalNameGet' , 'UOValSet', return_func='signal_name', cache_as_get=(['ch'],),
                                 doc="Note that there is no internal function to read back the out level so we use a cached value here. See the reset_all_output_cache methode.")
        self.out_level_now = nanonis_dev('SignalValGet', return_func='signal_value',
                                    doc="wait parameter when True (default) makes sure to obtain a completely new data point (takes longer)",
                                    params_option_map=['ch', 'wait'],
                                    options=dict(ch=self.current_out_channel, wait=True),
                                    options_lim=dict(wait=[True, False]),
                                    options_conv=dict(wait=lambda val, val_str: val,
                                                      ch=lambda val, val_str: val+23),
                                    options_apply=['ch'])
        self.animation_period = nanonis_dev('UtilAnimGet', 'UtilAnimSet', return_func='animation_period_s', params_option_map=['_val'])
        self._devwrap('fetch', autoinit=False)
        self._devwrap('ramp_out_level', autoinit=False)

        # This needs to be last to complete creation
        super(nanonis_tramea, self)._create_devs()

    @locked_calling
    def _test_ramp_algo(self, ch):
        """
        This code will test the what is used in the ramp algo by changing the
        setting of the specified ch. So be warned the the voltages there
        will be affected. Set the ramping speed for the full range to something that takes
        at least 10s.
        It returns max_rep, rep_avg
        max_rep should be less than or equal to 3 (and mostly 3 upon repeat).
        rep_avg should be close (could be a little smaller) to max_rep
        """
        # The algo requires that the data is read as float32 (and is float32 inside the application)
        # and that reading back takes sometimes 4 iteration (which we check here)
        anim_orig = self.animation_period.get()
        cal_orig = self.conf_output_calibration(ch=ch)
        self.animation_period.set(.1)
        self.conf_output_calibration(1,0)
        self.ramp_out_level.set(-10.)
        self.out_level.set(+10)
        last_v = self.out_level_now.get(wait=False)
        # wait until first change:
        for i in range(4):
            v = self.out_level_now.get(wait=False)
            is_diff = v != last_v
            last_v = v
            if is_diff:
                break
        max_rep = 0
        rep_count = 0
        data = []
        end_rep = []
        warned = False
        for i in range(200):
            t0 = time.time()
            v = self.out_level_now.get(wait=False)
            dt = time.time() - t0
            if v == 10 and not warned:
                print('Ramp speed to low, the ramp stopped before the end of the test. Please slow the ramp.')
                warned = True
            same_v = v == last_v
            fast = dt < 0.05
            last_v = v
            if not same_v:
                end_rep.append(rep_count)
                rep_count = 0
            else:
                rep_count += 1
                max_rep = max(max_rep, rep_count)
            data.append([v, same_v, fast, rep_count])
        self._test_ramp_algo_data = data
        self.ramp_out_level.set(0.)
        self.animation_period.set(anim_orig)
        self.conf_output_calibration(*cal_orig[:2])
        return max_rep, np.mean(end_rep)

# To start and wait for a 1D sweep:
#  nn = instruments.nanonis_tramea()
# Done in 3 parts
#  nn._nanonis.ODS_Start(1, 1, '', 0, state='request')
#  nn._nanonis.ODS_Start(1, 1, '', 0, state='wait')
#  nn._nanonis.ODS_Start(1, 1, '', 0, state='reply')
# Done all together. here state='all' is optional (it is the default)
#  nn._nanonis.ODS_Start(1, 1, '', 0, state='all')

# Ramp failure with detect_not_moving was detected with the following code:
# # with animation at 0.1 s and ramping rate at 1V/s get a glitch about every 5 iteration (random)
# i=0
# while True:
#     i += 1
#     t0 = time.time()
#     set(nn.ramp_out_level,-1, ch=2, detect_not_moving=True)
#     set(nn.ramp_out_level,1, ch=2, detect_not_moving=True)
#     dt = time.time() - t0
#     if dt < 4:
#         print('Glitch at', i, time.ctime())
#     wait(0.3)
