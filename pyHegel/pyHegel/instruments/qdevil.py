# -*- coding: utf-8 -*-

########################## Copyrights and license ############################
#                                                                            #
# Copyright 2021-2023  Christian Lupien <christian.lupien@usherbrooke.ca>    #
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

from ..instruments_base import visaInstrument,\
                            scpiDevice, MemoryDevice, ReadvalDev, BaseDevice,\
                            ChoiceBase, ChoiceStrings, ChoiceSimpleMap, _general_check,\
                            decode_float64, locked_calling, visa_wrap, Choice_bool_OnOff,\
                            wait, release_lock_context, mainStatusLine, resource_info,\
                            quoted_string, _repr_or_string

from ..instruments_registry import register_instrument

from ..types import dict_improved

from ..comp2to3 import string_upper, fb, fu, make_str

import numpy as np
import socket
import time

from collections import namedtuple

try:
    socket_timeout = socket.timeout
except NameError:
    socket_timeout = TimeoutError

# python 3 round returns and int but python 2 returns a float
iround = lambda x: int(round(x))

#######################################################
##    QDevil QDAC-II
#######################################################

class float_inf(ChoiceBase):
    def __init__(self, min, max):
        self._min = min
        self._max = max
    def __call__(self, input_str):
        return float(input_str)
    def tostr(self, val):
        return _repr_or_string(val)
    def __repr__(self):
        return 'Limits: %s <= val <= %s or inf'%(self._min, self._max)
    def __contains__(self, val):
        if val == np.inf:
            return True
        else:
            try:
                _general_check(val, min=self._min, max=self._max)
            except ValueError:
                return False
            else:
                return True

# timing for version 5-0.9.26
# using: %timeit get(qd.output_range, ch=1)
#  tcp takes 250 ms, serial takes 16 ms
# also Level and Level:last only return 4 digits after the dot (1e4 resolution)
# like set(qd.level, 1.2345678901), get returned as 1.2346 for both level and level:last
# That is fixed in 7-0.17.5, where they return 1.2345679 (level) and 1.2345655 (level_now)

#@register_instrument('QDevil', 'QDAC-II', '7-0.17.5')
#@register_instrument('QDevil', 'QDAC-II', '5-0.9.26')
@register_instrument('QDevil', 'QDAC-II')
class qdevil_qdac_ii(visaInstrument):
    """
    WARNING: changing range/filters should be done with 0 V output.
    Important devices:
        level
        ramp
        fetch
        output_range
        output_filter
        slew_dc
        measI_range
        measI_nplc
        measI_aperture
    Useful methods:
        level_all
    TCP address format:
        TCPIP::Q310-00012.mshome.net::5025::SOCKET
    """
    def __init__(self, visa_addr, *args, **kwargs):
        kwargs['write_termination'] = '\n'
        kwargs['read_termination'] = '\n'
        rsrc_info = resource_info(visa_addr)
        if rsrc_info.interface_type == visa_wrap.constants.InterfaceType.asrl:
            kwargs['parity'] = visa_wrap.constants.Parity.none
            kwargs['data_bits'] = 8
            kwargs['baud_rate'] = 921600
        # In case keep alive is needed
#        if  rsrc_info.interface_type == visa_wrap.constants.InterfaceType.tcpip:
#            kwargs['keep_alive'] = 'auto'
#            kwargs['keep_alive_time'] = 15*60 # 15 min.
        super(qdevil_qdac_ii, self).__init__(visa_addr, *args, **kwargs)

    def level_all(self, level=0.):
        self.write('SOURce:VOLTage %s,(@1:24)'%level)

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        #orig_ch = self.current_channel.get()
        levels = []
        ranges = []
        filters = []
        dc_modes = []
        slews = []
        enhs = []
        measI_ranges = []
        measI_apertures = []
        def get_append(quest_base, conv):
            vals_str = self.ask(quest_base+' (@1:24)')
            vals = list(map(conv, vals_str.split(',')))
            return vals
        levels = get_append('SOURce:VOLTage:LAST?', float)
        ranges = get_append('SOURce:RANGe?', self.output_range.choices)
        filters = get_append('SOURce:FILTer?', self.output_filter.choices)
        #enhs = get_append('SOURce:RENHancement?', self.output_resolution_enhencement_en.choices)
        enhs = get_append('SOURce:RENHancement?', bool)
        dc_modes =get_append('SOURce:VOLTage:MODE?', self.dc_mode.choices)
        slews = get_append('SOURce:VOLTage:SLEW?', float)
        measI_ranges = get_append('SENSe:RANGe?', self.measI_range.choices)
        measI_apertures = get_append('SENSe:APERture?', float)
        base = ['level=%r'%levels,
                'output_range=%r'%ranges,
                'output_filter=%r'%filters,
                'output_resolution_enhencement_en=%r'%enhs,
                'dc_mode=%r'%dc_modes,
                'slew_dc=%r'%slews,
                'measI_range=%r'%measI_ranges,
                'measI_aperture=%r'%measI_apertures]
        #self.current_channel.set(orig_ch)
        return base + self._conf_helper('line_freq', 'current_channel', options)

    def _ramp_wait(self):
        # can only do polling
        ch = self.current_channel.get()
        target = self.level.getcache() # level uses setget=True
        with release_lock_context(self):
            with mainStatusLine.new(priority=10, timed=True) as progress:
                while True:
                    now_val = self.level_now.get(ch=ch)
                    #if target == now_val:
                    # firmware 7-0.17.5 dpes not return exactly the same value for level and level_now
                    if abs(round(target - now_val, 4)) < 2e-4:
                        break
                    wait(.05)
                    progress('ramp progress: %s -> %s'%(now_val, target))

    def _ramp_setdev(self, val, ch=None):
        prev_val = self.level.get(ch=ch)
        self.level.set(val)
        if prev_val != val:
            self._ramp_wait()
    def _ramp_getdev(self, ch=None):
        return self.level.get(ch=ch)
    def _ramp_checkdev(self, val, ch=None):
        self.level.check(val, ch=ch)

    def _fetch_getformat(self, chs=None, **kwarg):
        chs = self._fetch_ch_helper(chs)
        headers = ['ch_%i'%ch for ch in chs]
        d = self.fetch._format
        d.update(multi=headers, graph=list(range(len(chs))))
        return BaseDevice.getformat(self.fetch, **kwarg)
    def _fetch_ch_helper_check(self, ch):
        if ch not in range(1, 24+1):
            raise ValueError(self.perror('fetch chs not in [1, 24] range'))
    def _fetch_ch_helper(self, chs=None):
        if chs is None:
            chs = [self.current_channel.get()]
        elif isinstance(chs, (list, tuple, np.ndarray)):
            for ch in chs:
                self._fetch_ch_helper_check(ch)
        else:
            self._fetch_ch_helper_check(ch)
            chs = [chs]
        chs = sorted(set(chs)) # remove duplicates and sort
        return chs
    def _fetch_getdev(self, chs=None):
        """ Read the current from the list of channels or
            of the current_channel if chs is None.
            repeats in chs are removed and the list is reorder in ascending order.
        """
        #TODO: This will timeout for long request. Eventually handle this better.
        chs = self._fetch_ch_helper(chs)
        chs_str = ','.join(map(str, chs))
        vals_str = self.ask('READ? (@%s)'%chs_str)
        vals = decode_float64(vals_str)
        return vals

    def _read_limits(self):
        conv = lambda s: list(map(float, s.split(',')))
        low_min = conv(self.ask('SOURce:RANGe:LOW:MINimum? (@1:24)'))
        low_max = conv(self.ask('SOURce:RANGe:LOW:MAXimum? (@1:24)'))
        high_min = conv(self.ask('SOURce:RANGe:HIGH:MINimum? (@1:24)'))
        high_max = conv(self.ask('SOURce:RANGe:HIGH:MAXimum? (@1:24)'))
        return dict(low_min=low_min, low_max=low_max, high_min=high_min, high_max=high_max)

    def _level_ch_helper(self, ch=None):
        if ch is not None:
            self.current_channel.set(ch)
        return self.current_channel.get()
    def _level_getdev(self, ch=None):
        ch = self._level_ch_helper(ch)
        valstr = self.ask('SOURce{ch}:VOLTage:LAST?'.format(ch=ch))
        return float(valstr)
    def _level_checkdev(self, val, ch=None):
        ch = self._level_ch_helper(ch)
        rge = self.output_range.getcache()
        if rge == 10:
            max = self._limits['high_max']
            min = self._limits['high_min']
        else:
            max = self._limits['low_max']
            min = self._limits['low_min']
        self.level._general_check(val, min=min[ch-1], max=max[ch-1])
    def _level_setdev(self, val, ch=None):
        # this was set by checkdev.
        ch = self.current_channel.get()
        self.write('SOURce{ch}:VOLTage {val}'.format(ch=ch, val=_repr_or_string(val)))

    @locked_calling
    def temperatures(self):
        """ Returns the 9 temperatures starting with the top row left, then top row middle, ... """
        results = []
        for i in [1, 2, 3]: # upper, middle, lower
            for j in [1, 2, 3]: # left, middle, right
                val_str = self.ask('SYSTem:TEMPerature? %i,%i'%(i, j))
                results.append(float(val_str))
        return results
    def _create_devs(self):
        self._limits = self._read_limits()
        self.current_channel = MemoryDevice(1, choices=list(range(1, 24+1)))
        def devChannelOption(*arg, **kwarg):
            options = kwarg.pop('options', {}).copy()
            options.update(ch=self.current_channel)
            app = kwarg.pop('options_apply', ['ch'])
            kwarg.update(options=options, options_apply=app)
            return scpiDevice(*arg, **kwarg)
        #self.level = devChannelOption('SOURce{ch}:VOLTage', 'SOURce{ch}:VOLTage:LAST?', str_type=float, setget=True)
        self._devwrap('level', setget=True)
        self.level_now = devChannelOption(getstr='SOURce{ch}:VOLTage?', str_type=float)
        range_ch = ChoiceSimpleMap(dict(LOW=2., HIGH=10.), filter=string_upper)
        #TODO we might need to cache all the ranges (not just current_channel) to speed up level check
        self.output_range = devChannelOption('SOURce{ch}:RANGe', choices=range_ch)
        self.output_filter = devChannelOption('SOURce{ch}:FILTer', choices=ChoiceStrings('DC', 'MEDium', 'HIGH'),
                                              doc="""DC is about 10 Hz, medium is about 10 kHz and high is about 230 kHz""")
        # fw 5-0.9.26 does not accept 0/1 for boolean
        # fixed in 7-0.17.5
        #self.output_resolution_enhencement_en = devChannelOption('SOURce{ch}:RENHancement', choices=Choice_bool_OnOff)
        self.output_resolution_enhencement_en = devChannelOption('SOURce{ch}:RENHancement', str_type=bool)
        self.dc_mode = devChannelOption('SOURce{ch}:VOLTage:MODE', choices=ChoiceStrings('FIXed', 'SWEep', 'LIST'))
        self.slew_dc = devChannelOption('SOURce{ch}:VOLTage:SLEW', choices=float_inf(min=0.01, max=2e7), doc='in V/s')

        self.measI_range =  devChannelOption('SENSe{ch}:RANGe', choices=ChoiceStrings('LOW', 'HIGH'), doc="Low=200 nA, high=10 mA")
        # There is an error here. Setting nplc=1/60. at 60 Hz will return an aperture of 0., fw 5-0.9.26
        self.measI_nplc =  devChannelOption('SENSe{ch}:NPLCycles', str_type=float, min=1/60., max=100.)
        self.measI_aperture =  devChannelOption('SENSe{ch}:APERture', str_type=float, min=0.0003, max=1.)

        # This does now work for fw 5-0.9.26
        #self.ref_source = scpiDevice('SYSTem:CLOCk:SOURce', choices=ChoiceStrings('INTernal', 'INTernal'))
        self.line_freq = scpiDevice('SYSTem:LFRequency', choices=[50, 60])

        self._devwrap('ramp')
        self._devwrap('fetch', autoinit=False)
        #TODO: handle sine, triangle, square, awg and the various triggers
        #self._devwrap('level')
        self.alias = self.level
        super(qdevil_qdac_ii, self)._create_devs()


#######################################################
##    Quantum Machine/QDevil QSwitch
#######################################################

# by using this class, the VisaInstrument write/read with delays will work properly
class UDP_Visa_replacement(object):
    def __init__(self, socket, name):
        self.socket = socket
        # This is needed for recording timing between process (_Shared_Structure)
        self.instr = namedtuple('UDP_Instr', ['resource_name'])
        self.instr.resource_name = name
    def write_raw(self, message):
        self.socket.send(message)
    def write(self, message, termination='default', encoding = None):
        encoding = 'utf-8' if encoding is None else encoding
        term = fb('\n' if termination=='default' else termination)
        self.write_raw(fb(message, encoding=encoding) + term)
    def read_raw(self, size=None):
        if size is None:
            size = 1024
        return self.socket.recv(size)
    def read(self, termination='default', encoding=None, chunk_size=None):
        encoding = 'utf-8' if encoding is None else encoding
        data = self.read_raw()
        term = fu('\n' if termination=='default' else termination)
        data_str = make_str(data, encoding=encoding)
        if data_str.endswith(term):
            if len(term) > 0:
                data_str = data_str[:-len(term)]
        else:
            raise RuntimeError(self.perror('Missing expected newline'))
        return data_str
    def read_raw_n_all(self, count, chunk_size=None):
        return self.read_raw(count)

#@register_instrument('Quantum Machines', 'QSwitch', '1.3')
@register_instrument('Quantum Machines', 'QSwitch')
class qdevil_qswitch(visaInstrument):
    """
    Important devices:
        ground_en (soft ground though 1M on output)
        through_en (connects the input or not)
        out_sel
        autosave
    Useful methods:
        conf_relays
        restart_firmware
        reset_lan_connection
        reset_poweron
        show
        ground_en_all
        through_en_all
        ch_set
        clear_buffer
    USB address format example:
        ASRL6
    TCP address format example (for firmware <2.0):
        TCPIP::qswitch-73.mshome.net::5025::SOCKET
    Newer firmware (>=2.0)  use udp, so the address is like
        'qswitch-73.mshome.net'
    """
    # Commands need to be <127 characters long
    def __init__(self, visa_addr, *args, **kwargs):
        """
        optional kwargs:
            repeat_en: when True and when using udp, will repeat the get attempts for
                       the duration of set_timeout
        """
        self._udp_repeat_en = kwargs.pop('repeat_en', True)
        self._udp_max_repeat = 0
        self._udp_basic_repeat_n = 2
        kwargs['write_termination'] = '\n'
        kwargs['read_termination'] = '\n'
        self._udp_mode = False
        try:
            rsrc_info = resource_info(visa_addr)
        except visa_wrap.VisaIOError as exc:
            if exc.error_code == visa_wrap.constants.VI_ERROR_INV_RSRC_NAME:
                # lets try udp instead
                self._udp_mode = True
                self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._udp_address = (visa_addr, 5025)
                self._udp_socket.connect(self._udp_address)
                kwargs['bypass_open'] = True
                self.visa = UDP_Visa_replacement(self._udp_socket, 'UDP::'+visa_addr)
            else:
                raise
        if not self._udp_mode and rsrc_info.interface_type == visa_wrap.constants.InterfaceType.asrl:
            baud_rate = kwargs.pop('baud_rate', 9600)
            parity = kwargs.pop('parity', visa_wrap.constants.Parity.none)
            data_bits = kwargs.pop('data_bits', 8)
            stop_bits = kwargs.pop('stop_bits', visa_wrap.constants.StopBits.one)
            kwargs['baud_rate'] = baud_rate
            kwargs['parity'] = parity
            kwargs['data_bits'] = data_bits
            kwargs['stop_bits'] = stop_bits
        # In case keep alive is needed
#        if  rsrc_info.interface_type == visa_wrap.constants.InterfaceType.tcpip:
#            kwargs['keep_alive'] = 'auto'
#            kwargs['keep_alive_time'] = 15*60 # 15 min.
        super(qdevil_qswitch, self).__init__(visa_addr, *args, **kwargs)

    def __del__(self):
        if self._udp_mode:
            self._udp_socket.close()
        super(qdevil_qswitch, self).__del__()

    @property
    def set_timeout(self):
        if self._udp_mode:
            return self._udp_socket.gettimeout()
        else:
            return super(qdevil_qswitch, self).set_timeout
    @set_timeout.setter
    def set_timeout(self, val):
        if self._udp_mode:
            self._udp_socket.settimeout(val)
        else:
            visaInstrument.set_timeout.__set__(self, val)
            #super(qdevil_qswitch, self).set_timeout = val

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        base = ['conf_relays=%r'%self.conf_relays() ]
        #return base + self._conf_helper('autosave_en', 'beeper_led_en', 'lan_mac', options)
        return base + self._conf_helper('autosave_en', 'lan_mac_addr', options)

    def _udp_write_repeat(self, val):
        cmd = make_str(val)
        cmd = val.lower().strip().split(' ')[0].split(':')[-1]
        do_repeat = '?' not in val
        do_fancy_repeat = do_repeat and cmd in ['clos', 'close', 'open', '*rst']
        if do_fancy_repeat:
            if cmd == '*rst':
                query = "clos:stat?"
                check_reply = lambda r: r == "(@1!0:24!0)"
            else:
                split_cmd = val.lstrip().split(' ', 1)
                query = split_cmd[0] + '? ' + split_cmd[1]
                def check_reply(r):
                    # check that it is a sequence 1,1,1,1,1,1
                    if len(r) == 0:
                        return False
                    return all(x=='1' for x in r.strip().split(','))
            prev_timeout = self.set_timeout
            now = time.time()
            try:
                self.set_timeout = 0.5
                rep = 0
                while True:
                    try:
                        self.write(val, repeat_en=False)
                        reply = self.ask(query, repeat_en=False)
                        if check_reply(reply):
                            break
                        raise socket_timeout
                    except socket_timeout:
                        if time.time() > now + prev_timeout:
                            raise
                        rep += 1
                        if rep > self._udp_max_repeat:
                            self._udp_max_repeat = rep
            finally:
                self.set_timeout = prev_timeout
        elif do_repeat:
            # we just send it twice. It will wait the necessary time
            for i in range(self._udp_basic_repeat_n):
                self.write(val, repeat_en=False)
        else:
            self.write(val, repeat_en=False)

    @locked_calling
    def write(self, val, termination='default', encoding=None, repeat_en=None):
        if len(val) > 127:
            raise ValueError(self.perror('Command is too long. Needs to be <127.'))
        if repeat_en is None:
            repeat_en = self._udp_repeat_en
        if self._udp_mode and repeat_en:
            self._udp_write_repeat(val)
        else:
            super(qdevil_qswitch, self).write(val, termination=termination, encoding=encoding)

    @locked_calling
    def ask(self, question, raw=False, encoding=None, chunk_size=None, repeat_en=None):
        if repeat_en is None:
            repeat_en = self._udp_repeat_en
        if self._udp_mode and repeat_en:
            prev_timeout = self.set_timeout
            now = time.time()
            try:
                self.set_timeout = 0.5
                rep = 0
                while True:
                    try:
                        return super(qdevil_qswitch, self).ask(question, raw=raw, encoding=encoding, chunk_size=chunk_size)
                    except socket_timeout:
                        if time.time() > now + prev_timeout:
                            raise
                        rep += 1
                        if rep > self._udp_max_repeat:
                            self._udp_max_repeat = rep
            finally:
                self.set_timeout = prev_timeout
        else:
            return super(qdevil_qswitch, self).ask(question, raw=raw, encoding=encoding, chunk_size=chunk_size)

    def clear_buffer(self):
        """ This empties the read buffer """
        if self._udp_mode:
            prev_timeout = self.set_timeout
            try:
                self.set_timeout = 0.001
                while True:
                    self.read()
            except socket_timeout:
                pass
            finally:
                self.set_timeout = prev_timeout
        else:
            self.visa.instr.clear()

    def clear(self):
        raise NotImplementedError('clear does not work on this device. You might want to use clear_buffer.')

    def _opc(self):
        # opc does not need the wait.
        try:
            prev_wait = self._write_write_wait
            self._write_write_wait = 0.
            self.ask('*opc?')
        finally:
            self._write_write_wait = prev_wait

    def _split_route(self, val):
        """ Splits a route like 1!2 or 1!2:12!2.
            returns start, stop, output
        """
        start_end = val.split(':')
        if len(start_end) not in [1, 2]:
            raise RuntimeError('Unexpected syntax, incorrect :')
        if len(start_end) == 2:
            start, end = start_end
        else:
            start = end = start_end[0]
        start1, start2 = start.split('!')
        end1, end2 = end.split('!')
        if start2 != end2:
            raise RuntimeError('Unexpected syntax, invalid !')
        s = int(start1)
        e = int(end1)
        o = int(start2)
        if s < 1 or s > 24 or e < 1 or e > 24 or o < 0 or o > 9:
            raise RuntimeError('Unexpected syntax, incorrect value.')
        return s, e, o

    def _find_list(self, val):
        if val is None:
            return [], []
        invalid_range = lambda x: x<1 or x>24
        if hasattr(val, 'items'):
            # we have a dict, could have entries 'open' or 'close'
            val = val.copy()
            open = val.pop('open', [])
            close = val.pop('close', [])
            if not isinstance(open, (list, tuple, np.ndarray)):
                open = [open]
            if not isinstance(close, (list, tuple, np.ndarray)):
                close = [close]
            if len(val) != 0:
                raise ValueError("Invalid key in dictionnary (only 'open' and 'close' allowed)")
            # clean up the lists
            open = list(set(iround(v) for v in open))
            close = list(set(iround(v) for v in close))
            if any(invalid_range(v) for v in open):
                raise ValueError("Invalid values. They need to be between 1 and 24")
            if any(invalid_range(v) for v in close):
                raise ValueError("Invalid values. They need to be between 1 and 24")
        else:
            if len(val) == 24 and all(v in [True, False] for v in val):
                open = [i+1 for i, v in enumerate(val) if not v]
                close = [i+1 for i, v in enumerate(val) if v]
            else:
                # list of index to close
                close = [iround(v) for v in val]
                if any(invalid_range(v) for v in close):
                    raise ValueError("Invalid values. They need to be between 1 and 24")
                close = set(close)
                open = set(range(1, 24+1)).difference(close)
                close = list(close)
                open = list(open)
        return sorted(open), sorted(close)

    def _gen_expr(self, index_list, ch, contract=True, clean=False):
        if clean:
            # if clean is False we assume the values are already sorted ints and unique.
            index_list = sorted(set([iround(v) for v in index_list]))
        if not contract:
            expr_list = ['%d!%d'%(i, ch) for i in index_list]
        else:
            expr_list = []
            start = index_list[0]
            stop = start
            def add_expr():
                if stop == start:
                    expr_list.append('%d!%d'%(start, ch))
                else:
                    expr_list.append('%d!%d:%d!%d'%(start, ch, stop, ch))
            for i in index_list[1:]:
                if i-stop == 1:
                    stop = i
                    continue
                # jump by more than one so record previous range and start the new one
                add_expr()
                start = stop = i
            add_expr()
        expr = ','.join(expr_list)
        return expr

    def _apply_conf(self, open_close_list, ch, do_open=False, contract=True):
        # assumes open_close_list is sorted.
        if len(open_close_list) == 0:
            return
        expr = self._gen_expr(open_close_list, ch)
        if do_open:
            self.write('OPEN (@%s)'%expr)
        else:
            self.write('CLOSe (@%s)'%expr)
        self._opc()

    @locked_calling
    def conf_lan(self, dhcp_en=None, hostname=None, ipaddr=None, gateway=None, smask=None, query='current'):
        """
        When None of the parameters are given, returns them as a dictionnary.
        It will return either the 'current' (default) or 'static' values according to query.
        'static' are the values that will be apply at the next restart_firmware.
        To see the mac address, use the lan_mac_addr device
        To enable dhcp you might need to set the ipaddr to 0.0.0.0 (it is documented in 2.0 but
        seens to work without it.)
        """
        if dhcp_en is None and hostname is None and ipaddr is None and gateway is None and smask is None:
            get = lambda x: x.get(query=query)
            return dict_improved(dhcp_en = get(self.lan_dhcp_en),
                                 hostname = get(self.lan_hostname),
                                 ipaddr = get(self.lan_ip_addr),
                                 gateway = get(self.lan_gateway),
                                 smask = get(self.lan_subnet_mask))
        if ipaddr is not None:
            self.lan_ip_addr.set(ipaddr)
        if dhcp_en is not None:
            self.lan_dhcp_en.set(dhcp_en)
        if hostname is not None:
            self.lan_hostname.set(hostname)
        if gateway is not None:
            self.lan_gateway.set(gateway)
        if smask is not None:
            self.lan_subnet_mask.set(smask)

    @locked_calling
    def conf_relays(self, ground=None, through=None, out=None, raw=False):
        """
        without any of the parameters, returns the string (raw=True) or dictionnary
        of the relay state.
        Otherwise you can provide a value for ground, through or out to change
        the state of the ground, through or out relays.
        For ground or through, you can give a list of 24 True/False (True=close) or
        a list of the channel number to be closed or a dict with keys open and close and
        the values the list of channels to change. The first 2 will change all the settings.
        The dict way only changes some.
        For out, give a list of 8 elements. Each element is the channel to connect or a list of channels
        to connect. It can be None so the out channel is unchanged (it can also be a dict or a list of 24 True/False)
        It can be 0 to turn the outch off (the same as [])
        The order is first closes ground, then does out, then through and finishes by opening ground.
        """
        if ground is None and through is None and out is None:
            ret = self.ask('CLOSe:STATe?')
            if raw:
                return ret
            if ret[:2] != '(@' or ret[-1] != ')':
                raise RuntimeError(self.perror('Unexpected returned string for state'))
            groups = ret[2:-1].split(',')
            ground = [False]*24
            through = [False]*24
            out = [0]*8
            data = dict(ground=ground, through=through, out=out)
            for g in groups:
                s, e, o = self._split_route(g)
                if o == 0:
                    ground[slice(s-1, e)] = [True]*(e-s+1)
                elif o == 9:
                    through[slice(s-1, e)] = [True]*(e-s+1)
                else:
                    v = out[o-1]
                    new = list(range(s, e+1))
                    if v == 0:
                        v = new
                    elif isinstance(v, list):
                        v.extend(new)
                    else: # not a list but a single value != 0
                        v = [v] + new
                    if len(v) == 1:
                        v = v[0]
                    out[o-1] = v
            return data
        if ground is not None:
            g_open, g_close = self._find_list(ground)
        else:
            g_open = g_close = []
        if through is not None:
            t_open, t_close = self._find_list(through)
        else:
            t_open = t_close = []
        if out is not None:
            if len(out) != 8:
                raise ValueError('Invalid length for out. It needs to have 8 elements')
            o_opens = []
            o_closes = []
            for o in out:
                if not isinstance(o, (list, tuple, np.ndarray, type(None))):
                    o = [o]
                if o == [0]:
                    o = []
                o_open, o_close = self._find_list(o)
                o_opens.append(o_open)
                o_closes.append(o_close)
        else:
            o_opens = o_closes = [[]]*8
        self._apply_conf(g_close, 0, False)
        self._apply_conf(t_close, 9, False)
        for i, o in enumerate(o_closes):
            self._apply_conf(o, i+1, False)
        for i, o in enumerate(o_opens):
            self._apply_conf(o, i+1, True)
        self._apply_conf(t_open, 9, True)
        self._apply_conf(g_open, 0, True)

    @locked_calling
    def reset_lan_connection(self):
        """ This forcebly closes a stuck lan connection. It does not reset the dhcp. Use restart_firmware for that. """
        if self._isfw_2:
            # For 2.0 it does not produce error but it probably does nothing.
            raise RuntimeError('This is not functionnal for firmware >=2.0')
        self.write('LAN:CLOSe')
        self._opc()
        self.write('LAN:RESTart')
        self._opc()

    def restart_firmware(self):
        """
        Restart the firmware. When autosave is enable all the state of the relays is unaltered.
        Compare to reset_poweron method which returns the relays to factory default and
                disables autosave. It does not restart the firmware.
        """
        self.write('RESTart')

    def get_error_all(self):
        return self.ask('SYSTem:ERRor:ALL?')

    def _ch_helper(self, ch=None):
        if ch is not None:
            self.current_ch.set(ch)
        ch = self.current_ch.get()
        return ch

    def _ground_en_checkdev(self, state, ch=None):
        ch = self._ch_helper(ch)
        BaseDevice._checkdev(self.ground_en, state)
    def _ground_en_setdev(self, state, ch=None):
        ch = self._ch_helper(ch)
        ch_list = '(@%d!0)'%ch
        if state:
            self.write('CLOSe '+ch_list)
        else:
            self.write('OPEN '+ch_list)
        self._opc()
    def _ground_en_getdev(self, ch=None):
        ch = self._ch_helper(ch)
        ch_list = '(@%d!0)'%ch
        ret = self.ask('CLOSe? '+ch_list)
        return bool(int(ret))

    def _through_en_checkdev(self, state, ch=None):
        ch = self._ch_helper(ch)
        BaseDevice._checkdev(self.through_en, state)
    def _through_en_setdev(self, state, ch=None):
        ch = self._ch_helper(ch)
        ch_list = '(@%d!9)'%ch
        if state:
            self.write('CLOSe '+ch_list)
        else:
            self.write('OPEN '+ch_list)
        self._opc()
    def _through_en_getdev(self, ch=None):
        ch = self._ch_helper(ch)
        ch_list = '(@%d!9)'%ch
        ret = self.ask('CLOSe? '+ch_list)
        return bool(int(ret))

    def _outch_helper(self, ch=None):
        if ch is not None:
            self.current_outch.set(ch)
        ch = self.current_outch.get()
        return ch

    def _out_sel_checkdev(self, sel, outch=None):
        outch = self._outch_helper(outch)
        BaseDevice._checkdev(self.out_sel, sel)
    def _out_sel_setdev(self, sel, outch=None):
        ch = self._outch_helper(outch)
        ch_list = '(@1!%d:24!%d)'%(ch, ch)
        ch_list2 = '(@%d!%d)'%(sel, ch)
        self.write('OPEN '+ch_list)
        if sel != 0:
            self.write('CLOSe '+ch_list2)
        self._opc()
    def _out_sel_getdev(self, outch=None):
        ch = self._outch_helper(outch)
        ch_list = '(@1!%d:24!%d)'%(ch, ch)
        ret = self.ask('CLOSe? '+ch_list)
        state = [bool(int(v)) for v in ret.split(',')]
        if True in state:
            if len([s for s in state if s is True]) > 1:
                print("----WARNING: multiple outputs channels are connected to output %d"%ch)
            return state.index(True)
        return 0

    def show(self):
        """ Display the state of the qswitch relays """
        config = self._build_switch_array()
        print(self._format_switch_array(config))

    def _build_switch_array(self):
        """ Build and return the array defining the current state """
        state = self.conf_relays()
        config = np.zeros((10, 24), dtype=bool)
        config[0] = state['ground']
        config[9] = state['through']
        for i, ch in enumerate(state['out']):
            if ch == 0:
                continue
            if isinstance(ch, (list, tuple)):
                for c in ch:
                    config[i+1, c-1] = True
            else:
                config[i+1, ch-1] = True
        return config.T

    def _format_switch_array(self, arr):
        """ arr is the array constructed by _build_switch_array """
        ports = u"Ch Gd {}  Th\n".format(
                    '  '.join([u'%d'%i for i in range(1, 9)]))
        res = ports
        symbol = {False:u"_", True:u"\u22A5"} # ⟘ (uptack)
        symbol_th = {False:u"\\", True:u"_"}
        symbol_gd = {False:u"_", True:u"\u22A5"}
        for ch, conf in enumerate(arr):
            format_line = u"{}__".format(symbol_gd[conf[0]])
            format_line += u"__".join(symbol[i] for i in conf[1:-1])
            format_line += u"__{}__".format(symbol_th[conf[-1]])
            res += u"{:2} {}\n".format(ch+1, format_line)
        return res
    
    def ch_set(self, ch, ground, through):
        self.ground_en.set(ground, ch=ch)
        self.through_en.set(through, ch=ch)

    def ground_en_all(self, val=True):
        self.conf_relays(ground=[val]*24)

    def through_en_all(self, val=True):
        self.conf_relays(through=[val]*24)

    def _create_devs(self):
        # we need to set this before any writes.
        # otherwise some write request are lost.
        # except for *opc command
        fw_version = self.idn_split()['firmware']
        if int(fw_version.split('.')[0]) >= 2:
            self._isfw_2 = True
        else:
            self._isfw_2 = False
        self._write_write_wait = 0.075
        self.current_ch = MemoryDevice(1, choices=list(range(1, 24+1)))
        self.current_outch = MemoryDevice(1, choices=list(range(1, 8+1)))
        self.autosave_en = scpiDevice('AUTosave', str_type=bool)
        # Documention 2.0 as removed beeper:state?, the write worked buffer and still does.
        # The read did not work and is now removed from the documentation.
        #self.beeper_led_en = scpiDevice('BEEPer:STATe', str_type=bool)
        self.beeper_led_en = scpiDevice('BEEPer:STATe', str_type=bool, autoget=False, cache_as_get=True)
        if not self._isfw_2:
            # This does not produce an error but useless in 2.0
            self.lan_timeout = scpiDevice('LAN:TIMeout', str_type=int, min=0,
                                      doc="in seconds. Can be zero to disable it.")
        ch_query = ChoiceStrings('CURRent', 'STATic')
        def devLanOption(*arg, **kwarg):
            options = kwarg.pop('options', {}).copy()
            options.update(query='CURRent')
            options_lim = kwarg.pop('options_lim', {}).copy()
            options_lim.update(query=ch_query)
            kwarg.update(options=options, options_lim=options_lim)
            return scpiDevice(*arg, **kwarg)
        self.lan_dhcp_en = devLanOption('LAN:DHCP', 'LAN:DHCP? {query}', str_type=bool)
        # Documentions 2.0 still shows hostname accept current, static but it does not work
        # and I was told (by email) it was not supposed to use them.
        #self.lan_hostname = devLanOption('LAN:HOSTname', 'LAN:HOSTname? {query}', str_type=quoted_string())
        # keep use devLanOption anyway in case in changes and so it works like the others in conf_lan
        self.lan_hostname = devLanOption('LAN:HOSTname', 'LAN:HOSTname?', str_type=quoted_string())
        self.lan_ip_addr = devLanOption('LAN:IPADdress', 'LAN:IPADdress? {query}', str_type=quoted_string())
        self.lan_gateway = devLanOption('LAN:GATeway', 'LAN:GATeway? {query}', str_type=quoted_string())
        self.lan_subnet_mask = devLanOption('LAN:SMASk', 'LAN:SMASk? {query}', str_type=int, min=0, max=32)
        self.lan_mac_addr = scpiDevice(getstr='LAN:MAC?', str_type=quoted_string())
        self._devwrap('ground_en', doc='optional paramter: ch')
        self._devwrap('through_en', doc='optional paramter: ch')
        self._devwrap('out_sel', choices=list(range(24+1)),
                      doc="""select the unique channel to connect to outch (optional parameter).
                      To disconnect, select channel 0.
                      It always opens all the connections the outch first.
                      Therefore, with this device, only 1 ch connects to the outch.
                      """)
        # This needs to be last to complete creation
        super(qdevil_qswitch, self)._create_devs()
