# -*- coding: utf-8 -*-
########################## Copyrights and license ############################
#                                                                            #
# Copyright 2024       Christian Lupien <christian.lupien@usherbrooke.ca>    #
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

from collections import OrderedDict
import numpy as np
import time
import threading
import weakref
import json
import datetime

from ..ctypes_helper import DLL_Wrapper, Buffer, General_POINTER, General_Conv,\
                            c_uint32, c_int32, c_int8, c_double, c_byte,\
                            c_uint32_p, c_int32_p, c_int8_p, c_double_p,\
                            c_void_p, c_void_p_p, IntEnumC, IntFlagC, sizeof

from ..types import StructureImproved, UnionImproved, StructureImproved_extend, dict_improved

from ..instruments_base import visaInstrument, BaseInstrument, scpiDevice, MemoryDevice,\
                                visa_wrap, locked_calling, resource_info, wait,\
                                ChoiceStrings, Choice_bool_OnOff, ChoiceSimpleMap,\
                                ChoiceDevDep, ProxyMethod, decode_int32, _retry_wait,\
                                wait_on_event, MemoryDevice_update, BaseDevice, Base2Device,\
                                _general_check, _sleep_signal_context_manager, ChoiceBase
from ..instruments_registry import register_instrument
from . import ScalingDevice
from ..dll_load_helper import delayed_libusb_import as _delayed_libusb_import

from ..comp2to3 import fu, string_types, is_py2

if is_py2:
    import Queue as queue
else:
    import queue

#######################################################
##    ANC300 piezo controller
#######################################################

#@register_instrument('attocube', 'ANC300', '1.2.2-3 2019-01-25 11:02')
@register_instrument('attocube', 'ANC300')
class attocube_anc300(visaInstrument):
    """
    This controls the attocube ANC300 piezo controller
    Useful devices:
        step_rel
        step_abs
        ax_freq
        ax_amp
        ax_mode
    Useful methods:
        reset_absolute_coords
        step
        stop
        wait_stepping
        empty_buf
    If you want to bypass the auto detection of the modules for the commands that accept ax='all'
    (stop, wait_stepping), you can modify the attribute enabled_ax_list

    Possible addresses:
        ASRL
        TCPIP::something.local::7230::socket

    IMPORTANT: You should always remeasure the capacitances when changing piezo
               temperature otherwise the internal limits are not calculated
               properly.
    """
    def __init__(self, visa_addr, ax_names=None, output_trig_feature_en=False, password='123456', quiet_empty=True, **kwargs):
        """
        ax_names is either a list of names to use for the axis (in the axis order,
                i.e. 1, 2, 3 ...) or a dictionnary of names with keys the axis
                number. For the list, you can skip entries by using None as a name.
                the names need to be different. Not all axes need to have a name
                These names will be usable as when selecting and axis.
                Only names attached to axis that have a module installed will
                be kept.
        output_trig_feature_en when True allow the use of the output trig (needs to
                have been enabled by a feature code)
        password is the password used when connecting with the ethernet connection.
        """
        self._doing_ask = False
        self._quiet_empty = quiet_empty
        self._output_trig_feature_en = output_trig_feature_en
        self._password = password
        self._wait_check_socket_read = None
        self._wait_check_socket_kwargs = {}
        cnsts = visa_wrap.constants
        rsrc_info = resource_info(visa_addr)
        if ax_names is None:
            ax_names = {}
        elif isinstance(ax_names, (list, tuple)):
            ax_names = {i+1:n for i, n in enumerate(ax_names) if n is not None}
        else:
            ax_names = {k:v for k, v in ax_names.items() if k is not None}
        # Check names are different
        if len(set(ax_names.values())) != len(ax_names):
            raise ValueError('Multiname ax_names with same name')
        self._ax_names = ax_names
        self._password = None
        if rsrc_info.interface_type == cnsts.InterfaceType.asrl:
            baud_rate = kwargs.pop('baud_rate', 38400)
            parity = kwargs.pop('parity', cnsts.Parity.none)
            data_bits = kwargs.pop('data_bits', 8)
            stop_bits = kwargs.pop('stop_bits', cnsts.StopBits.one)
            kwargs['baud_rate'] = baud_rate
            kwargs['parity'] = parity
            kwargs['data_bits'] = data_bits
            kwargs['stop_bits'] = stop_bits
        elif rsrc_info.interface_type == cnsts.InterfaceType.tcpip:
            self._password = password
        super(attocube_anc300, self).__init__(visa_addr, write_termination='\r\n',
                                            read_termination='\r\n', **kwargs)

    def init(self, full=False):
        self.ask('echo off')

    def get_error(self):
        raise NotImplementedError(self.perror('get_error is not implemented for this instrument'))
    def clear(self):
        self.empty_buf()
    def reset_poweron(self):
        raise NotImplementedError(self.perror('reset_poweron is not implemented for this instrument'))

    def reset_absolute_coords(self, coord=None, ax='all'):
        """
        if coord is None, returns the selected axis coordinates.
        coord can be a single value (for the current or single ax selection)
        or a list of coordinates for the list of selected axis ('all' by default).
        """
        prev_ax = self.current_ax.get()
        ax, single = self._multi_ax_helper(ax)
        if coord is None:
            ret = []
            for a in ax:
                ret.append(self.absolute_coord.get(ax=a))
            if single:
                ret = ret[0]
        else:
            ret = None
            if not isinstance(coord, (list, tuple, np.ndarray)):
                coord = [coord]
            if len(coord) != len(ax):
                raise ValueError(self.perror('incorrect number of values. Was expecting %d'%len(ax)))
            for c, a in zip(coord, ax):
                self.absolute_coord.set(c, ax=a)
        if not single:
            self.current_ax.set(prev_ax)
        return ret

    def idn(self):
        # ver like 'attocube ANC300 controller version 1.2.2-3 2019-01-25 11:02'
        ver = self.ask('ver')[0]
        # serial like 'ANC300B-C-2133-4009021'
        serial = self.ask('getcser')
        pre = 'attocube ANC300 controller version '
        if not ver.startswith(pre):
            raise RuntimeError('Unexpected version number')
        fw_ver = ver[len(pre):]
        return 'attocube,ANC300,%s,%s'%(serial, fw_ver)

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        orig_ax = self.current_ax.get()
        base = self._conf_helper('current_ax')
        base += ['enabled_list=%r'%self.enabled_ax_list]
        axes = self.enabled_ax_list
        base += ['ax_names=%r'%[self._ax_names.get(a, None) for a in axes]]
        base += ['serial_nums=%r'%[self.serial_nums[a-1] for a in axes]]
        data = OrderedDict(zip(['absolute_coord', 'ax_freq', 'ax_amp', 'ax_mode', 'ax_capacitance_nF', 'ax_ac_in_en',
                                'ax_dc_in_en', 'ax_offset', 'ax_filter', 'ax_trigger_up', 'ax_trigger_down'],
                               [[] for i in range(11)]))
        for a in axes:
            self.current_ax.set(a)
            for k, v in data.items():
                v.append(getattr(self, k).get())
        for k, v in data.items():
            base.append('%s=%r'%(k, v))
        self.current_ax.set(orig_ax)
        return base + self._conf_helper('default_return_gnd', 'default_step_mode', 'default_wait', options)

    @locked_calling
    def write(self, val, termination='default', encoding=None, skip_read=False):
        if self._doing_ask or skip_read:
            super(attocube_anc300, self).write(val, termination=termination, encoding=encoding)
        else:
            ret = self.ask(val, encoding=encoding)
            if ret != []:
                raise RuntimeError(self.perror('The device returned unexpected extra information: %s'%ret))

    def _wait_check_socket(self, wait):
        prev_timeout = self.set_timeout
        self.set_timeout = wait
        try:
            ret = self.read(**self._wait_check_socket_kwargs)
            self._wait_check_socket_read = ret
            return True
        except visa_wrap.VisaIOError as exc:
            if exc.error_code == visa_wrap.constants.VI_ERROR_TMO:
                pass
        finally:
            self.set_timeout = prev_timeout
        return False

    def _wait_read_helper(self, raw=False, encoding=None, chunk_size=None):
        # Note that this will not work properly when echo is enabled because
        # the \r\n of the echoed line is not sent immediately.
        # It could be fixed by reading a characeter at a time, but should be uncessary.
        if self.visa.is_serial():
            _retry_wait(lambda : self.visa.bytes_in_buffer != 0, -np.inf)
            ret = self.read(raw=raw, encoding=encoding, chunk_size=chunk_size)
        else:
            self._wait_check_socket_read = None
            self._wait_check_socket_kwargs = dict(raw=raw, encoding=encoding, chunk_size=chunk_size)
            wait_on_event(self._wait_check_socket)
            ret = self._wait_check_socket_read
        return ret

    def _read_helper(self, question, ret=None, raw=False, encoding=None, chunk_size=None, do_wait=False):
        ret_list = []
        echo_count = 0
        first = True
        error_msg = 'ERROR'
        ok_msg = 'OK'
        while ret not in [error_msg, ok_msg]:
            if ret is None:
                pass
            elif (first and fu(ret) == fu(question)) or ret.startswith('> '):
                # skip echo
                # print('skipping: %s'%ret)
                echo_count += 1
                if echo_count > 1:
                    raise RuntimeError(self.perror('Received more than one echo prompt which was unexpected'))
                first = False
            else:
                ret_list.append(ret)
            if do_wait:
                ret = self._wait_read_helper(raw=raw, encoding=encoding, chunk_size=chunk_size)
            else:
                ret = self.read(raw=raw, encoding=encoding, chunk_size=chunk_size)
        if ret.startswith(error_msg):
            if len(ret_list):
                raise RuntimeError(self.perror('Received Error: %s'%ret_list[-1]))
            else:
                raise RuntimeError(self.perror('Received Error.'))
        return ret_list

    @locked_calling
    def ask(self, question, raw=False, encoding=None, chunk_size=None, remove=None):
        try:
            self._doing_ask = True
            # ret_list = []
            ret = super(attocube_anc300, self).ask(question, raw=raw, encoding=encoding, chunk_size=chunk_size)
            ret_list = self._read_helper(question, ret, raw=raw, encoding=encoding, chunk_size=chunk_size)
            if len(ret_list) == 1:
                retv = ret_list[0]
                if remove is not None:
                    if isinstance(remove, tuple):
                        pre = remove[0]
                        post = ' ' + remove[1]
                        end = -len(post)
                    else:
                        pre = remove
                        post = ''
                        end = None
                    pre += ' = '
                    if retv.startswith(pre) and retv.endswith(post):
                        return retv[len(pre):end]
                    else:
                        raise RuntimeError(self.perror('Unexpected return value. Was expecting something starting with %r but got %r'%(remove, retv)))
                return retv
            return ret_list
        finally:
            self._doing_ask = False

    def empty_buf(self, quiet=True, ret=False):
        prev_timeout = self.set_timeout
        rets = []
        try:
            self.set_timeout = 0.1
            while True:
                r = self.read()
                rets.append(r)
                if not quiet:
                    print(r)
        except visa_wrap.VisaIOError:
            pass
        finally:
            self.set_timeout = prev_timeout
        if ret:
            return rets

    def send_feature_code(self, code):
        self.write('setfc ' + code)

    def _ax_helper(self, ax=None):
        if ax is not None:
            ax = self.current_ax.set(ax)
        ax = self.current_ax.get()
        # need to convert ax which could be any names to the real ax integer
        ax = int(self.current_ax.choices.tostr(ax))
        return ax

    def conf_pattern(self, ax=None, pattern_up=None, pattern_down=None):
        """ either sets (when given a pattern) or reads the
            voltage pattern when no pattern are given (returned as a tuple
            up, down). The patterns needs to be a sequence of 256 integer values (0-255).
            All for a particular ax.
        """
        ax = self._ax_helper(ax)
        if pattern_up is None and pattern_down is None:
            up = decode_int32(','.join(self.ask('getpu %d'%ax)))
            dn = decode_int32(','.join(self.ask('getpd %d'%ax)))
            return up, dn
        if pattern_up is not None:
            if len(pattern_up) != 256 or min(pattern_up) < 0 or max(pattern_up) > 255:
                raise ValueError('invalid pattern_up')
            self.write('setpu %d %s'%(ax, ' '.join(['%d'%v for v in pattern_up])))
        if pattern_down is not None:
            if len(pattern_down) != 256 or min(pattern_down) < 0 or max(pattern_down) > 255:
                raise ValueError('invalid pattern_down')
            self.write('setpd %d %s'%(ax, ' '.join(['%d'%v for v in pattern_down])))

    def _multi_ax_helper(self, ax=None):
        single = False
        if ax == 'all':
            ax = self.enabled_ax_list
        else:
            if not isinstance(ax, (list, tuple, np.ndarray)):
                ax = [ax]
                single = True
            # go trough _ax_helper to make sure we have the numbered ax names instead
            # of the named ones.
            prev_ax = self.current_ax.get()
            ax = [self._ax_helper(a) for a in ax]
            if not single:
                self.current_ax.set(prev_ax)
        return ax, single

    @locked_calling
    def stop(self, ax=None):
        """
        stop the motion along axis ax. ax can be None (use the current_ax),
            any valid axis or 'all' to stop motion along all axes, or a list
            of axes to use.
        """
        ax, single = self._multi_ax_helper(ax)
        for a in ax:
            self.write('stop %d'%a)

    @locked_calling
    def step(self, count, ax=None, step_mode='stp', return_gnd='auto', wait=True):
        """ moves axis ax by count steps.
        when count is positive moves up,
        when count is negative moves down.
        if count is +- inf, moves continuously (until stopped)
        step_mode when not None, will set that move before moving.
        return_gnd will return the mode to 'gnd' when True, or
                     to the state before stepping when 'auto' (default)
                     otherwise it is not changed.
                     This only works if wait is True
        wait, when True (default) will wait until the motion is stopped
              but only if count is not inf.
        Note that this function does not keep track of absolute_coord.
             For that use the step_abs or step_rel devices.
        """
        if step_mode not in [None, 'stp', 'stp+', 'stp-']:
            raise ValueError(self.perror("invalid step_mode should be one of [None, 'stp', 'stp+', 'stp-'"))
        ax = self._ax_helper(ax)
        prev_mode = None
        if return_gnd == 'auto':
            prev_mode = self.ax_mode.get()
        elif return_gnd is True:
            prev_mode = 'gnd'
        if step_mode is not None:
            self.ax_mode.set(step_mode)
        if abs(count) == np.inf:
            if count > 0:
                self.write('stepu %d c'%ax)
            else:
                self.write('stepd %d c'%ax)
        else:
            count = int(count)
            if count == 0:
                raise ValueError(self.perror('can not move 0 count steps'))
            if count > 0:
                self.write('stepu %d %d'%(ax, count))
            else:
                self.write('stepd %d %d'%(ax, -count))
            if wait:
                self.wait_stepping()
        if wait and prev_mode is not None:
            self.ax_mode.set(prev_mode)

    @locked_calling
    def wait_stepping(self, ax=None):
        ax = self._ax_helper(ax)
        question = 'stepw %d'%ax
        self.write(question, skip_read=True)
        # This seems to always return [], so the return value is useless.
        # But return it just in case
        return self._read_helper(question, do_wait=True)

    @locked_calling
    def wait_capacitance(self, ax=None):
        ax = self._ax_helper(ax)
        question = 'capw %d'%ax
        self.write(question, skip_read=True)
        # This seems to always return ['capacitance = 0.000000 nF'], so the return value is useless.
        # But return it just in case
        return self._read_helper(question, do_wait=True)

    @locked_calling
    def measure_capacitances(self, ax='all'):
        ax, single = self._multi_ax_helper(ax)
        meas = []
        prev_ax = self.current_ax.get()
        for a in ax:
            prev_mode = self.ax_mode.get(ax=a)
            self.ax_mode.set('cap')
            self.wait_capacitance()
            self.ax_mode.set(prev_mode)
            meas.append(self.ax_capacitance_nF.get())
        if single:
            return meas[0]
        else:
            self.current_ax.set(prev_ax)
        return meas

    def _step_kwargs_parser(self, step_mode, return_gnd, wait):
        if step_mode == 'default':
            step_mode = self.default_step_mode.get()
        if return_gnd == 'default':
            return_gnd = self.default_return_gnd.get()
        if wait == 'default':
            wait = self.default_wait.get()
        return dict(step_mode=step_mode, return_gnd=return_gnd, wait=wait)

    def _step_rel_checkdev(self, count, ax=None, step_mode='default', return_gnd='default', wait='default'):
        ax = self._ax_helper(ax)

    def _step_rel_setdev(self, count, ax=None, step_mode='default', return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(step_mode, return_gnd, wait)
        xo = self.absolute_coord.get()
        count = int(count)
        if count == 0:
            return
        self.step(count, ax=ax, **kwargs)
        if abs(count) != np.inf:
            self.absolute_coord.set(xo + count)

    def _step_rel_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.absolute_coord.get()

    def _step_abs_checkdev(self, new_pos, ax=None, step_mode='default', return_gnd='default', wait='default'):
        ax = self._ax_helper(ax)

    def _step_abs_setdev(self, new_pos, ax=None, step_mode='default', return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(step_mode, return_gnd, wait)
        xo = self.absolute_coord.get()
        count = new_pos - xo
        count = int(count)
        if count == 0:
            return
        self.step(count, ax=ax, **kwargs)
        self.absolute_coord.set(new_pos)

    def _step_abs_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.absolute_coord.get()

    def _ax_model_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self._model_list[ax-1]

    def _create_devs(self):
        if self._password is not None:
            self.write(self._password, skip_read=True)
            ret = self.empty_buf(quiet=True, ret=True)
            if ret[-1] != 'Authorization success':
                raise RuntimeError('Invalid password')
        else:
            self.empty_buf(quiet=self._quiet_empty)
        serial_list = []
        model_list = []
        enabled_ax_list = []
        ax_choices_dict = {}
        ax_choices_k = []
        ax_choices_v = []
        for i in range(1, 7+1):
            try:
                ret = self.ask('getser %d'%i)
            except:
                ret = None
            else:
                enabled_ax_list.append(i)
                i_str = '%d'%i
                ax_choices_k.append(i_str)
                ax_choices_v.append(i)
                if i in self._ax_names:
                    n = self._ax_names[i]
                    ax_choices_k.append(i_str)
                    ax_choices_v.append(n)
                    ax_choices_dict[i_str] = n
                else:
                    ax_choices_dict[i_str] = i
            serial_list.append(ret)
            model_list.append(ret.split('-', 1)[0] if ret is not None else None)
        self.serial_nums = serial_list
        self._model_list = model_list
        self.enabled_ax_list = enabled_ax_list
        self.current_ax = MemoryDevice(1, choices=ChoiceSimpleMap(ax_choices_dict, keys_values_lists=(ax_choices_k, ax_choices_v)))
        self.default_step_mode = MemoryDevice('stp', choices=[None, 'stp', 'stp+', 'stp-'])
        self.default_wait = MemoryDevice(True, choices=[True, False])
        self.default_return_gnd = MemoryDevice('auto', choices=[True, False, 'auto'])
        # ProxyMethod is to allow del to delete this self object
        pask = ProxyMethod(self.ask)
        def scpiDevice_anc300(*args, **kwargs):
            remove = kwargs.pop('remove', None)
            if remove is not None:
                kwargs['ask_func'] = lambda *args, **kwargs: pask(*args, remove=remove, **kwargs)
            return scpiDevice(*args, **kwargs)
        def devAxOption(*arg, **kwarg):
            options = kwarg.pop('options', {}).copy()
            options.update(ax=self.current_ax)
            app = kwarg.pop('options_apply', ['ax'])
            kwarg.update(options=options, options_apply=app)
            return scpiDevice_anc300(*arg, **kwarg)
        self.ax_mode = devAxOption('setm {ax} {val}', 'getm {ax}',
                                   choices=ChoiceStrings('gnd', 'inp', 'cap', 'stp', 'off', 'stp+', 'stp-'),
                                   remove='mode')
        self.ax_freq = devAxOption('setf {ax} {val}', 'getf {ax}', str_type=float, remove=('frequency', 'Hz'), min=1, max=10000)
        self.ax_amp = devAxOption('setv {ax} {val}', 'getv {ax}', str_type=float, remove=('voltage', 'V'), min=0, max=150)
        self.ax_offset = devAxOption('seta {ax} {val}', 'geta {ax}', str_type=float, remove=('voltage', 'V'), min=0, max=150)
        self.ax_ac_in_en = devAxOption('setaci {ax} {val}', 'getaci {ax}', choices=Choice_bool_OnOff, remove='acin')
        self.ax_dc_in_en = devAxOption('setdci {ax} {val}', 'getdci {ax}', choices=Choice_bool_OnOff, remove='dcin')
        self._devwrap('ax_model')
        # Note that I have not tested ANM200A, ANM300A if that is what is returned by the instrument.
        filter_choices = ChoiceDevDep(self.ax_model, {None: ChoiceSimpleMap({'N/A':-1}),
                                                 'ANM150A': ChoiceSimpleMap({'N/A':-1}),
                                                 'ANM200A': ChoiceSimpleMap({'1.6':1.6, '16':16, '160':160, '1600':1600}),
                                                 'ANM300A': ChoiceSimpleMap({'16':16, '160':160, 'off':0})},
                                      force_get=True)
        self.ax_filter = devAxOption('setfil {ax} {val}', 'getfil {ax}',
                                     choices=filter_choices,
                                     remove='filter')
        self.ax_capacitance_nF = devAxOption(getstr='getc {ax}', str_type=float, remove=('capacitance', 'nF'))
        self.ax_output_voltage = devAxOption(getstr='geto {ax}', str_type=float, remove=('voltage', 'V'))

        d = {'%d'%i: i for i in range(1, 16+1)}
        d['off'] = 0
        trig_ch = ChoiceSimpleMap(d)
        self.ax_trigger_up = devAxOption('settu {ax} {val}', 'gettu {ax}', choices=trig_ch,
                                         remove = 'trigger', doc='doc 0 means off')
        self.ax_trigger_down = devAxOption('settd {ax} {val}', 'gettd {ax}',  choices=trig_ch,
                                         remove = 'trigger', doc='doc 0 means off')
        if self._output_trig_feature_en:
            self.current_ch = MemoryDevice(1, options=[1, 2, 3, 4])
            # TODO find out what something should be.
            self.output_trigger = scpiDevice_anc300('setto {ch} {val}', 'getto {ch}', remove='something',
                                                    options=dict(ch=self.current_ch), options_apply=['ch'])
        self.absolute_coord = MemoryDevice_update(0, nch=7, first_ch=1, ch_name='ax', ch_helper_func=ProxyMethod(self._ax_helper))
        self._devwrap('step_rel', doc="""Moves the requested number of step for set. returns the absolute_coord for get.
                                          Accepts parameters ax, step_mode, return_gnd, wait which are set to 'default' by
                                          which means they use the value set in devices default_*.
                                          For the other values, see the step method documentation.""")
        self._devwrap('step_abs', doc="""Moves the count of step between the requested new position and the previous absolute_coord.
                                          Accepts parameters ax, step_mode, return_gnd, wait which are set to 'default' by
                                          which means they use the value set in devices default_*.
                                          For the other values, see the step method documentation.""")

        # This needs to be last to complete creation
        super(attocube_anc300, self)._create_devs()


#######################################################
##    ANC350 piezo controller
#######################################################
# C header files are in C:\Program Files (x86)\N-Hands\Daisy@ANC350\userlib\inc
# windows dll in C:\Program Files (x86)\N-Hands\Daisy@ANC350\userlib\lib
#  for anc350v4.dll
# and C:\Program Files (x86)\N-Hands\Daisy@ANC350
#  for dependent libusb0.dll
# but that is probably present in C:\Windows\System32

class ANC350_Exception(Exception):
    def __init__(self, msg, errno):
        self.errno = errno
        super(ANC350_Exception, self).__init__(msg)

_ANC350_Error_string = {
        -1: "Unspecified Error",
        0: "Success",
        1: "Timeout",
        2: "Not connected",
        3: "Already Connected",
        7: "Device Locked",
        8: "Unknown Error",
        9: "Invalid Device",
        10: "Invalid Axis",
        11: "Parameter out of range",
        12: "Function not available for device",
        13: "File error upon opening or interpreting"}

class ANC_DeviceType(IntEnumC):
    Anc350Res = 0
    Anc350Num = 1
    Anc350Fps = 2
    Anc350None = 3

class ANC_ActuatorType(IntEnumC):
    ActLinear = 0
    ActGonio = 1
    ActRot = 2


class ANC_InterfaceType(IntEnumC):
    IfNone = 0
    IfUsb = 1
    IfTcp = 2
    IfAll = 3

class ANC_MovingStatus(IntEnumC):
    MoveIdle = 0
    MoveMove = 1
    MovePending = 2

class ANC_Features(IntFlagC):
    Sync = 0x01 # ethernet enabled
    Lockin = 0x02 # low power measurement enabled
    Duty = 0x04 # duty cycle enabled
    App = 0x08 # cnontrol by IOS app enabled

ANC_Handle = c_void_p
ANC_Handle_p = c_void_p_p
Bln32 = General_Conv(c_int32, bool, force_check=True)
Bln32_p = General_POINTER(Bln32)

_ANCSTR_BUF = Buffer(16) # needs at least 16 char
_ANCADDR_BUF = Buffer()
_ANCNAME_BUF = Buffer(20)

ANC_DLL_Default_Path = r'C:\Codes\Attocube'

class ANC350_Lib_dll(DLL_Wrapper):
    _dll_cache = None
    def __init__(self, dll_name='anc350v4', extra_paths=ANC_DLL_Default_Path, **kwargs):
        super(ANC350_Lib_dll, self).__init__(dll_name, extra_paths=extra_paths, **kwargs)

    def _errcheck(self, result, func, args):
        if result != 0:
            if result in _ANC350_Error_string:
                msg = _ANC350_Error_string[result]
            else:
                msg = 'Unexpected error'
            raise ANC350_Exception('ANC350 Error(%i): %s'%(result, msg), result)

    def _create_funcs(self):
        errcheck = ProxyMethod(self._errcheck)
        create_helper = lambda name, *args, **kwargs:\
            self._create_helper(name, *args, errcheck=errcheck, restype=c_int32, name_prefix='ANC_', **kwargs)
        create_helper('discover', [('ifaces', ANC_InterfaceType.ctype), ('devCount_', c_uint32_p)])
        create_helper('getDeviceInfo', [('devNo', c_uint32), ('devType_', ANC_DeviceType.pointer),
                                        ('id_', c_int32_p), ('serialNo_', _ANCSTR_BUF), ('address_', _ANCSTR_BUF),
                                        ('connected_', Bln32_p)])
        create_helper('registerExternalIp', [('hostname', _ANCADDR_BUF)])
        create_helper('connect', [('devNo', c_uint32), ('device_', ANC_Handle_p)])
        create_helper_dev = lambda name, argdefs=[], **kwargs: create_helper(name, [('device', ANC_Handle)]+argdefs, **kwargs)
        create_helper_dev('disconnect')
        create_helper_dev('getDeviceConfig', [('features_', ANC_Features.pointer)])
        create_helper_ax = lambda name, argdefs=[], **kwargs: create_helper_dev(name, [('axisNo', c_uint32)]+argdefs, **kwargs)
        create_helper_ax('getAxisStatus', [('connected_', Bln32_p), ('enabled_', Bln32_p),
#                                            ('moving_', Bln32_p), ('target_', Bln32_p), ('eotFwd_', Bln32_p),
                                            ('moving_', ANC_MovingStatus.pointer), ('target_', Bln32_p), ('eotFwd_', Bln32_p),
                                            ('eotBwd_', Bln32_p), ('error_', Bln32_p)])
        create_helper_ax('setAxisOutput', [('enable', Bln32), ('autoDisable', Bln32)])
        create_helper_ax('setAmplitude', [('amplitude', c_double)])
        create_helper_ax('setFrequency', [('frequency', c_double)])
        create_helper_ax('setDcVoltage', [('voltage', c_double)])
        create_helper_ax('getAmplitude', [('amplitude_', c_double_p)])
        create_helper_ax('getFrequency', [('frequency_', c_double_p)])
        create_helper_ax('getDcVoltage', [('voltage_', c_double_p)])
        create_helper_ax('startSingleStep', [('backward', Bln32)])
        create_helper_ax('startContinousMove', [('start', Bln32), ('backward', Bln32)])
        create_helper_ax('startAutoMove', [('enable', Bln32), ('relative', Bln32)])
        create_helper_ax('setTargetPosition', [('target', c_double)])
        create_helper_ax('setTargetRange', [('targetRg', c_double)])
        create_helper_ax('setTargetGround', [('targetGnd', Bln32)])
        create_helper_ax('getPosition', [('position_', c_double_p)])
        create_helper_dev('getFirmwareVersion', [('version_', c_int32_p)])
        create_helper_ax('configureExtTrigger', [('mode', c_uint32)])
        create_helper_ax('configureAQuadBIn', [('enable', Bln32), ('resolution', c_double)])
        create_helper_ax('configureAQuadBOut', [('enable', Bln32), ('resolution', c_double), ('clock', c_double)])
        create_helper_ax('configureRngTriggerPol', [('polarity', c_uint32)])
        create_helper_ax('configureRngTrigger', [('lower', c_uint32), ('upper', c_uint32)])
        create_helper_ax('configureRngTriggerEps', [('epsilon', c_uint32)])
        create_helper_dev('configureNslTrigger', [('enable', Bln32)])
        create_helper_ax('configureNslTriggerAxis')
        create_helper_ax('selectActuator', [('actuator', c_uint32)])
        create_helper_ax('getActuatorName', [('name_', _ANCNAME_BUF)])
        create_helper_ax('getActuatorType', [('type_', ANC_ActuatorType.pointer)])
        create_helper_ax('getLutName', [('name_', _ANCNAME_BUF)])
        create_helper_ax('measureCapacitance', [('cap_', c_double_p)])
        create_helper_ax('loadLutFile', [('fileName', _ANCADDR_BUF)])
        create_helper_dev('saveParams')
        create_helper_ax('resetPosition')
        create_helper_ax('moveReference')
        create_helper_ax('getRefPosition', [('position_', c_double_p), ('valid_', Bln32_p)])
        create_helper_dev('configureDutyCycle', [('enable', Bln32), ('period', c_double), ('offTime', c_double)])
        create_helper_dev('enableSensor', [('enable', Bln32)])
        create_helper_ax('enableRefAutoUpdate', [('enable', Bln32)])
        create_helper_ax('enableRefAutoReset', [('enable', Bln32)])


class Val_Arg:
    pass

class AttoDev(Base2Device):
    def __init__(self, getname=None, setname=None, dev_type=None, use_axis=False, get_arg=(), set_arg=(Val_Arg,), **kwargs):
        super(AttoDev, self).__init__(**kwargs)
        if getname is not None:
            self._getdev_p = getname
        if setname is not None:
            self._setdev_p = setname
        self._use_axis = use_axis
        self._get_arg = get_arg
        self._set_arg = set_arg
        self._dev_type = dev_type
        if dev_type is None:
            self._dev_type = self.choices

    def _set_write(self, val, options):
        instr = self.instr
        device = instr._ancdev
        func = getattr(instr._sdk, self._setdev_p)
        val = self._todev_conv_helper(val)
        args = (device,)
        if 'ax' in options:
            args += (options['ax'],)
        args += tuple(val if a is Val_Arg else options[a] for a in self._set_arg)
        func(*args)

    def _get_ask(self, options):
        instr = self.instr
        device = instr._ancdev
        #ax = self._ax_helper(ax)
        func = getattr(instr._sdk, self._getdev_p)
        args = (device,)
        if 'ax' in options:
            args += (options['ax'],)
        args += self._get_arg
        val = func(*args)
        return self._fromdev_conv_helper(val)

    def _todev_conv_helper(self, val):
        t = self._dev_type
        if t == int:
            return int(val)
        elif t == bool:
            return int(val)
        elif t is None:
            return val
        return t.tostr(val)

    def _fromdev_conv_helper(self, val):
        if isinstance(val, tuple):
            names = getattr(self.instr._sdk, self._getdev_p)._return_names
            return dict_improved([(k, v) for k, v in zip(names, val)])
        t = self._dev_type
        if t == int:
            return val
        elif t == bool:
            return bool(val)
        elif t is None:
            return val
        return t(val)


_ANC350_DLL_CACHE = None

class ANC_Stepping_Timeout(RuntimeError):
    pass

class ANC_Stepping_Stuck(RuntimeError):
    pass

@register_instrument('attocube', 'ANC350v4')
class attocube_anc350v4(BaseInstrument):
    """
    This controls the attocube ANC350 piezo controller
    Useful devices:
        step_rel, step_rel_um
        step_abs, step_abs_um
        move_rel, move_rel_um
        move_abs, move_abs_um
        ax_output_en
        ax_stop_on_eot
        ax_freq
        ax_amp
        ax_dc_volt
        ax_measure_cap
        ax_status
        ax_position
        ax_position_um
        ax_target_pos
        ax_target_pos_um
        ax_target_reached_range
        ax_target_reached_range_um
        ax_target_ground_en

    Useful methods:
        reset_step_absolute_coords
        move_auto
        step
        stop
        wait_stepping
        conf_ax
        set_limits
    """
    def __init__(self, dev_num=0, ax_names=['x', 'y', 'z'], dll_path=ANC_DLL_Default_Path,
                 search=ANC_InterfaceType.IfAll, limits=[(None, None), (None,None), (None, None)],
                 register_ip=[], **kwargs):
        """
        dev_num can be a number, which selects that device discovered.
                It can also be a serial number string to select one.
                You can use the static method discover to list devices.

        ax_names is list of names to use for the axis (in the axis order,
                i.e. 0, 1, 2). A name can be left as None. It defaults to ['x', 'y', 'z']
        limits are a list of 3 tuples of (min, max) values for each axis. A value
               of None disables the limit handling.
        register_ip is a list of ip addresses or hostnames to preregister for the discovery.
             It is necessary if the ip address is not on the local network.
        stuck_recovery is the option for trying to get the motion unblocked.
               It is a list of tuples (recover_type, amplitude, repeats)
               They are tried in sequence. If it is still stuck at the end,
               it will raise ANC_Stepping_Stuck exception.
        """
        self._sdk = None
        self._ancdev = None
        limits = np.array(limits)
        self._xyz_limits = limits
        if limits.shape != (3, 2):
            raise ValueError('limits is not of the correct shape')
        if len(ax_names) != 3:
            raise ValueError('ax_names needs to be a list of 3 strings')
        self._ax_names = ax_names
        self._sdk = self._load_dll(dll_path)
        dev_info = self.discover(_sdk=self._sdk, search=search, only_serial=False, register_ip=register_ip)
        if isinstance(dev_num, string_types):
            for i, di in enumerate(dev_info):
                if di['serial'] == dev_num:
                    dev_num = i
                    break
            else:
                dev_num = None
        if dev_num is None or dev_num >= len(dev_info):
            raise RuntimeError('Unable to find requested dev_num')
        self._dev_info = dev_info[dev_num]
        self._ancdev = self._sdk.connect(dev_num)
        super(attocube_anc350v4, self).__init__()
        self._extra_create_dev()

    @staticmethod
    def _load_dll(dll_path=ANC_DLL_Default_Path):
        # keeping a global value for the sdk prevents it from being deleted in the wrong order.
        # So we should be able to close the device in our __del__ (the sdk should still work.)
        global _ANC350_DLL_CACHE
        if _ANC350_DLL_CACHE is None:
            sdk = ANC350_Lib_dll(extra_paths=dll_path, quiet_delete=True)
            _ANC350_DLL_CACHE = sdk
        else:
            sdk = _ANC350_DLL_CACHE
        return sdk

    def __del__(self):
        if self._sdk is not None and self._ancdev is not None:
            self._sdk.disconnect(self._ancdev)
            self._sdk = None
            self._ancdev = None
        super(attocube_anc350v4, self).__del__()

    @locked_calling
    def idn(self):
        fw_ver = self._sdk.getFirmwareVersion(self._ancdev)
        serial = self._dev_info['serial']
        # serial like 'L 01 0950'
        return 'attocube,ANC350v4,%s,%s'%(serial, fw_ver)

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        base = ['conf_ax=%s'%self.conf_ax()]
        base.append('devtype=%s'%self._dev_info['devtype'])
        base.append('features=%s'%(self.options,))
        return base + self._conf_helper(options)

    @staticmethod
    def discover(dll_path=ANC_DLL_Default_Path, only_serial=True, search=ANC_InterfaceType.IfAll,
                 _sdk=None, register_ip=[]):
        """
        list all devices. Every devices is represented by a dict or the serial number
           depending on the value of only_serial.
        The device number is the index of of the list (and also the num element of the dict)
        addr shows 'USB' when the device connected by USB.
        To get a numbered list, you can use:
            list(enumerate(attocube_anc350.discover()))
        register_ip is a list of ip addresses or hostnames to preregister for the discovery.
             It is necessary if the ip address is not on the local network.
        """
        if _sdk is not None:
            sdk = _sdk
        else:
            sdk = attocube_anc350v4._load_dll(dll_path)
        for ip in register_ip:
            sdk.registerExternalIp(ip)
        n = sdk.discover(search)
        ret = []
        for i in range(n):
            devtype, id, serial, addr, connected = sdk.getDeviceInfo(i)
            if only_serial:
                d = serial
            else:
                d = dict(devtype=devtype, id=id, serial=serial, addr=addr, connected=connected, num=i)
            ret.append(d)
        return ret

    @locked_calling
    def conf_ax(self):
        ax_orig = self.current_ax.get()
        ret = []
        for ax in range(3):
            name = self._sdk.getActuatorName(self._ancdev, ax)
            type = self._sdk.getActuatorType(self._ancdev, ax)
            lutname = self.ax_lut_name.get(ax=ax)
            freq = self.ax_freq.get()
            amp = self.ax_amp.get()
            dc_volt = self.ax_dc_volt.get()
            out_en = self.ax_output_en.get()
            stop_on_eot = self.ax_stop_on_eot.get()
            target = self.ax_target_pos.get()
            target_ground_en = self.ax_target_ground_en.get()
            target_reached_range = self.ax_target_reached_range.get()
            d = dict(name=name, type=type, lutname=lutname, freq=freq, amp=amp, dc_volt=dc_volt,
                     out_en=out_en, stop_on_eot=stop_on_eot, target=target,
                     target_ground_en=target_ground_en, target_reached_range=target_reached_range)
            ret.append(d)
        self.current_ax.set(ax_orig)
        return ret

    @locked_calling
    def save_parameters(self):
        """
        Saves parameters to persistent flash memory in the device.
        They will be present as defaults after the next power-on.
        Affected paramters: ax_amp, ax_freq, ax_target_reached_range,
                            ax_target_ground
                            actuator selection, triggers and quadrature
        """
        self._sdk.saveParams(self._ancdev)

    def _ax_helper(self, ax=None):
        if ax is not None:
            ax = self.current_ax.set(ax)
        ax = self.current_ax.get()
        # need to convert ax which could be any names to the real ax integer
        ax = self.current_ax._tostr(ax)
        return ax

    def _multi_ax_helper(self, ax=None):
        single = False
        if ax == 'all':
            ax =[0, 1, 2]
        else:
            if not isinstance(ax, (list, tuple, np.ndarray)):
                ax = [ax]
                single = True
            # go trough _ax_helper to make sure we have the numbered ax names instead
            # of the named ones.
            prev_ax = self.current_ax.get()
            ax = [self._ax_helper(a) for a in ax]
            if not single:
                self.current_ax.set(prev_ax)
        return ax, single

    @locked_calling
    def stop(self, ax=None):
        """
        stop the motion along axis ax. ax can be None (use the current_ax),
            any valid axis or 'all' to stop motion along all axes, or a list
            of axes to use.
        """
        ax, single = self._multi_ax_helper(ax)
        for a in ax:
            # param are device, axisNo, start, backward
            self._sdk.startContinousMove(self._ancdev, a, False, False)
            # param are device, axisNo, enable, relative
            # This is unecessary
            #self._sdk.startAutoMove(self._ancdev, a, False, False)

    def _is_it_moving(self, ax=None, auto=False):
        """ This will possibly change the current axis """
        stat = self.ax_status.get(ax=ax)
        if stat.enabled:
            moving = stat.moving != ANC_MovingStatus.MoveIdle
            if (auto and moving and not stat.target) or (not auto and moving):
                return True, stat
        return False, stat

    @locked_calling
    def wait_stepping(self, axs=[0, 1, 2], periods=None, auto=False, timeout=None):
        orig_ax = self.current_ax.get()
        axs, single = self._multi_ax_helper(axs)
        if periods is None:
            periods = [1./self.ax_freq.get(ax=ax) for ax in axs]
        min_wait = 5e-3 # minimum wait set to 5 ms, or 200 Hz
        start_time = time.time()
        while True:
            wait_time = 0.
            moving = False
            last_stat = []
            for ax, p in zip(axs, periods):
                is_moving, last_st = self._is_it_moving(ax, auto)
                last_stat.append(last_st)
                if is_moving:
                    moving = True
                    wait_time = max(wait_time, p)
            if not moving:
                break
            # if the wait just started after the start of a step that takes
            # x, then waiting for 4 * (x+delta)/4 should be enough (thanks to the delta)
            # At most we will wiat ~x/4
            wait_time = max(min_wait, (wait_time + min_wait)/4)
            if timeout is not None:
                delta = time.time() - start_time
                if delta > timeout:
                    raise ANC_Stepping_Timeout
                timeout_wait = max(timeout - delta, min_wait)
                wait_time = min(wait_time, timeout_wait)
            wait(wait_time)
        self.current_ax.set(orig_ax)
        return last_stat

    def _step_move_prep(self, ax=None, auto_enable=True, return_gnd='auto', stop_on_eot=None, wait=True):
        if return_gnd not in ['auto', True, False]:
            raise ValueError("return_gnd needs to be one of 'auto', True, False")
        ax = self._ax_helper(ax)
        if stop_on_eot is not None:
            self.ax_stop_on_eot.set(stop_on_eot)
        if self.ax_amp.get() == 0:
            raise ValueError('You need an amplitude different that 0 for steps to work.')
        orig_status = self.ax_status.get()
        is_enabled = orig_status.enabled
        if return_gnd == 'auto':
            orig_enable = is_enabled
        elif return_gnd is True:
            orig_enable = False
        else:
            orig_enable = True
        base_args = (self._ancdev, ax)
        if auto_enable and is_enabled is False:
            self.ax_output_en.set(True)
        elif is_enabled is False:
            raise RuntimeError(self.perror("ax output is not enabled. So can't move"))
        return orig_enable, base_args, wait

    @locked_calling
    def step(self, count, ax=None, auto_enable=True, return_gnd='auto', stop_on_eot=None, wait=True, timeout=None):
        """ moves axis ax by count steps.
        when count is positive moves up,
        when count is negative moves down.
        if count is +- inf, moves continuously (until stopped, or timeout runs out)
        auto_enable is to turn on the output if True and is not already enabled
        step_mode when not None, will set that move before moving.
        return_gnd will disable the output when True, or
                     to the state before stepping when 'auto' (default)
                     otherwise it is not changed.
                     This only works if wait is True
        stop_on_eot when True, will stop the motion if an eot (end of travel)
              condition is detected. If None, which is the default,
              it uses the ax_stop_on_eot device value.
              When specified, the value of the ax_stop_on_eot device is changed.
        wait, when True (default) will wait until the motion is stopped,
              but only if count is not inf. It will also wait until timeout.
              When set to False, the function still waits most of the steps.
              This is a final wait for the last step (or the only wait for a
              single step)
        Note that this function does not keep track of absolute_coord.
             For that use the step_abs or step_rel devices.
        Pressing CTRL-C will call the stop method.
        """
        if not abs(count) == np.inf and int(count) == 0:
            raise ValueError(self.perror('can not move 0 count steps'))
        orig_enable, base_args, wait = self._step_move_prep(ax, auto_enable, return_gnd, stop_on_eot, wait)
        ax = base_args[1]
        try:
            periods = [1./self.ax_freq.get()]
            if abs(count) == np.inf:
                if count > 0:
                    direction_back = False
                else:
                    direction_back = True
                args = base_args + (True, direction_back)
                self._sdk.startContinousMove(*args)
                if wait and timeout is not None:
                    try:
                        self.wait_stepping([ax], periods, timeout=timeout)
                    except ANC_Stepping_Timeout:
                        pass
                    self.stop()
            else:
                count = int(count)
                if count > 0:
                    direction_back = False
                else:
                    direction_back = True
                    count = -count
                args = base_args + (direction_back,)
                start_time = time.time()
                for i in range(count):
                    if timeout is not None:
                        to = timeout - (time.time() - start_time)
                        to = max(to, 0.)
                    else:
                        to = None
                    self.wait_stepping([ax], periods, timeout=to)
                    self._sdk.startSingleStep(*args)
                if wait:
                    self.wait_stepping([ax], periods)
        except KeyboardInterrupt:
            self.stop()
            if wait and not orig_enable:
                self.ax_output_en.set(orig_enable)
            raise
        if wait and not orig_enable:
            self.ax_output_en.set(orig_enable)

    def _ax_check_limits(self, ax, target, relative):
        ax = self._ax_helper(ax)
        mn, mx = self._xyz_limits[ax]
        if relative:
            target = target + self.ax_position.get()
        _general_check(target, min=mn, max=mx, msg_src=self)

# TODO handle retries when motion is stuck
    @locked_calling
    def move_auto(self, target, ax=None, relative=False, auto_enable=True, return_gnd='auto', stop_on_eot=None, wait=True, timeout=None):
        """ moves axis ax automatically to target.
        relative, when True, will displace by target amount. When False (Default)
              moves to target value.
              Note that when relative, the displacement is with respect to the currently measured pos.
        auto_enable is to turn on the output if True and is not already enabled
        step_mode when not None, will set that move before moving.
        return_gnd will disable the output when True, or
                     to the state before stepping when 'auto' (default)
                     otherwise it is not changed.
                     This only works if wait is True
        stop_on_eot when True, will stop the motion if an eot (end of travel)
              condition is detected. If None, which is the default,
              it uses the ax_stop_on_eot device value.
              When specified, the value of the ax_stop_on_eot device is changed.
        wait, when True (default) will wait until the motion is stopped
        See also ax_target_reached_range and ax_target_ground_en
        Pressing CTRL-C will call the stop method.
        """
        orig_enable, base_args, wait = self._step_move_prep(ax, auto_enable, return_gnd, stop_on_eot, wait)
        ax = base_args[1]
        self._ax_check_limits(ax, target, relative)
        args = base_args + (True, relative)
        self.ax_target_pos.set(target)
        self._sdk.startAutoMove(*args)
        if wait:
            try:
                last_status = self.wait_stepping([ax], auto=True)
                if not orig_enable:
                    self.ax_output_en.set(orig_enable)
            except KeyboardInterrupt:
                self.stop()
                if not orig_enable:
                    self.ax_output_en.set(orig_enable)
                raise

    def set_limits(self, min='keep', max='keep', ax=None):
        """
        When both min and max are 'keep', lists all the limits (returns a 3x2 array
                        for the min, max of the 3 directions)
        change the limits (like the limits option of the instrument initialization).
        by default when the value is 'keep' nothing is changed.
        Otherwise the value can be None to disable the limit or a number in m or deg.
        It only changes the limits for the axis ax (current_ax if not given)
        """
        if min == 'keep' and max == 'keep':
            return self._xyz_limits
        if isinstance(min, string_types) and min != 'keep':
            raise ValueError("The only string allowed is 'keep', otherwise use None or a number")
        if isinstance(max, string_types) and max != 'keep':
            raise ValueError("The only string allowed is 'keep', otherwise use None or a number")
        ax = self._ax_helper(ax)
        if min != 'keep':
            self._xyz_limits[ax, 0] = min
        if max != 'keep':
            self._xyz_limits[ax, 1] = max

    def reset_step_absolute_coords(self, coord=None, ax='all'):
        """
        if coord is None, returns the selected axis step coordinates.
        coord can be a single value (for the current or single ax selection)
        or a list of coordinates for the list of selected axis ('all' by default).
        """
        prev_ax = self.current_ax.get()
        ax, single = self._multi_ax_helper(ax)
        if coord is None:
            ret = []
            for a in ax:
                ret.append(self.step_absolute_coord.get(ax=a))
            if single:
                ret = ret[0]
        else:
            ret = None
            if not isinstance(coord, (list, tuple, np.ndarray)):
                coord = [coord]
            if len(coord) != len(ax):
                raise ValueError(self.perror('incorrect number of values. Was expecting %d'%len(ax)))
            for c, a in zip(coord, ax):
                self.step_absolute_coord.set(c, ax=a)
        if not single:
            self.current_ax.set(prev_ax)
        return ret

    def _step_kwargs_parser(self, return_gnd, wait):
        if return_gnd == 'default':
            return_gnd = self.default_return_gnd.get()
        if wait == 'default':
            wait = self.default_wait.get()
        return dict(return_gnd=return_gnd, wait=wait)

    def _step_rel_checkdev(self, count, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper(ax)

    def _step_rel_setdev(self, count, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(return_gnd, wait)
        xo = self.step_absolute_coord.get()
        count = int(count)
        if count == 0:
            return
        self.step(count, ax=ax, **kwargs)
        if abs(count) != np.inf:
            self.step_absolute_coord.set(xo + count)

    def _step_rel_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.step_absolute_coord.get()

    def _step_abs_checkdev(self, new_pos, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper(ax)

    def _step_abs_setdev(self, new_pos, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(return_gnd, wait)
        xo = self.step_absolute_coord.get()
        count = new_pos - xo
        count = int(count)
        if count == 0:
            return
        self.step(count, ax=ax, **kwargs)
        self.step_absolute_coord.set(new_pos)

    def _step_abs_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.step_absolute_coord.get()

    def _move_abs_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.ax_position.get()

    def _move_rel_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.ax_position.get()

    def _move_abs_checkdev(self, target, ax=None, return_gnd='default', wait='default'):
        self._ax_check_limits(ax, target, relative=False)

    def _move_rel_checkdev(self, target, ax=None, return_gnd='default', wait='default'):
        self._ax_check_limits(ax, target, relative=True)

    def _move_abs_setdev(self, target, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(return_gnd, wait)
        self.move_auto(target, ax, relative=False, **kwargs)

    def _move_rel_setdev(self, target, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(return_gnd, wait)
        self.move_auto(target, ax, relative=True, **kwargs)


    def _update_output(self, ax, dev):
        # ax is already set, and eot as been set
        out_en = self.ax_output_en.get()
        self.ax_output_en.set(out_en)

    def _create_devs(self):
        self.current_ax = MemoryDevice(0, choices=
                                       ChoiceSimpleMap({k: v for k, v in enumerate(self._ax_names)}, allow_keys=True))

        features = self._sdk.getDeviceConfig(self._ancdev)
        self.options = features

        def AttoDevAx(*arg, **kwarg):
            options = kwarg.pop('options', {}).copy()
            options.update(ax=self.current_ax)
            app = kwarg.pop('options_apply', ['ax'])
            kwarg.update(options=options, options_apply=app)
            return AttoDev(*arg, **kwarg)

        self.ax_freq = AttoDevAx('getFrequency', 'setFrequency', setget=True)
        self.ax_amp = AttoDevAx('getAmplitude', 'setAmplitude', setget=True)
        self.ax_dc_volt = AttoDevAx('getDcVoltage', 'setDcVoltage', setget=True)
        self.ax_measure_cap = AttoDevAx('measureCapacitance', autoinit=False)
        self.ax_position = AttoDevAx('getPosition', doc='Units are meter or degree')
        self.ax_lut_name = AttoDevAx('getLutName', 'loadLutFile', autoinit=False)
        self.ax_status = AttoDevAx('getAxisStatus')

        tostr = ProxyMethod(self.current_ax._tostr)
        AttoDevAx_CacheGet = lambda setname, inits=None, **kwargs: AttoDevAx(setname=setname,
                                        cache_as_get=(['ax'], inits, None,
                                        dict(ax=lambda name, val: tostr(val)) ), **kwargs)
        self._AttoDevAx_CacheGet = AttoDevAx_CacheGet
        self.ax_target_pos = AttoDevAx_CacheGet('setTargetPosition', doc='Units are meter or degree')
        self.ax_target_reached_range = AttoDevAx_CacheGet('setTargetRange', doc='Units are meter or degree')
        self.ax_target_ground_en = AttoDevAx_CacheGet('setTargetGround', doc="This makes the output go to zero volt after a target move.")

        MemDev_Ax = lambda val, **kwargs:  MemoryDevice_update(val, nch=3, first_ch=0, ch_name='ax', ch_helper_func=self._ax_helper,
                                                               no_type_conv=True, **kwargs)
        self.ax_stop_on_eot = MemDev_Ax(True, update_func=self._update_output)
        self.step_absolute_coord = MemDev_Ax(0)
        self.default_wait = MemoryDevice(True, choices=[True, False])
        self.default_return_gnd = MemoryDevice('auto', choices=[True, False, 'auto'])
        self._devwrap('step_rel', doc="""Moves the requested number of step for set. returns the absolute_coord for get.
                                          Accepts parameters ax, return_gnd, wait which are set to 'default' by
                                          which means they use the value set in devices default_*.
                                          For the other values, see the step method documentation.""")
        self._devwrap('step_abs', doc="""Moves the count of step between the requested new position and the previous absolute_coord.
                                          Accepts parameters ax, return_gnd, wait which are set to 'default' by
                                          which means they use the value set in devices default_*.
                                          For the other values, see the step method documentation.""")

        self._devwrap('move_abs', doc="""Moves to the requested position.
                                          Accepts parameters ax, return_gnd, wait which are set to 'default' by
                                          which means they use the value set in devices default_*.
                                          For the other values, see the move_auto method documentation.""")
        self._devwrap('move_rel', doc="""Moves to the request displacement away from the current position.
                                          Accepts parameters ax, return_gnd, wait which are set to 'default' by
                                          which means they use the value set in devices default_*.
                                          For the other values, see the move_auto method documentation.""")


        # TODO: selectActuator
        #devtype = self._dev_info['devtype']
        #if devtype in [ANC_DeviceType.Anc350Num, ANC_DeviceType.Anc350Fps]:
            # resetPosition
        #if devtype == ANC_DeviceType.Anc350Num:
            # moveReference
            # getRefPosition
            # configureDutyCycle
            # enableSensor
            # enableRefAutoUpdate
            # enableRefAutoReset

        # This needs to be last to complete creation
        super(attocube_anc350v4, self)._create_devs()

    @locked_calling
    def _extra_create_dev(self):
        orig_ax = self.current_ax.get()
        out_en = {(ax,):self.ax_status.get(ax=ax).enabled for ax in range(3)}
        self.current_ax.set(orig_ax)
        self.ax_output_en = self._AttoDevAx_CacheGet('setAxisOutput', inits=out_en,
                                                set_arg=(Val_Arg, 'stop_on_eot'),
                                                options_apply=['ax', 'stop_on_eot'],
                                                options=dict(stop_on_eot=self.ax_stop_on_eot))
        del self._AttoDevAx_CacheGet
        m2um = 1e6
        Scale_um = lambda x, doc='In µm.\n':  ScalingDevice(x, m2um, only_val=True, quiet_del=True, doc=doc)
        self.ax_position_um = Scale_um(self.ax_position)
        self.ax_target_pos_um = Scale_um(self.ax_target_pos)
        self.ax_target_reached_range_um = Scale_um(self.ax_target_reached_range)
        Scale_um2 = lambda x: Scale_um(x, doc='In µm.\n'+x._doc)
        self.move_abs_um = Scale_um2(self.move_abs)
        self.move_rel_um = Scale_um2(self.move_rel)
        self._create_devs_helper()


class Step_Move_Interface(object):
    def _create_step_move(self, move_en=False, ax_names=['x', 'y', 'z'],
                          limits=[(None, None), (None,None), (None, None)]):
        """
        This method requires the existence of methods:
            _ax_helper
            step
            if move_en is True:
                move_auto
                _ax_check_limits
        and devices:
            _step_kwargs_parser
            if move_en is True:
                ax_position
        """
        limits = np.array(limits)
        self._xyz_limits = limits
        if limits.shape != (3, 2):
            raise ValueError('limits is not of the correct shape')
        if len(ax_names) != 3:
            raise ValueError('ax_names needs to be a list of 3 strings')
        self._ax_names = ax_names

        MemDev_Ax = lambda val, **kwargs:  MemoryDevice_update(val, nch=3, first_ch=0, ch_name='ax', ch_helper_func=self._ax_helper,
                                                               no_type_conv=True, **kwargs)
        Scale_um = lambda x, doc='In µm.\n':  ScalingDevice(x, m2um, only_val=True, quiet_del=True, doc=doc)
        Scale_um2 = lambda x: Scale_um(x, doc='In µm.\n'+x._doc)
        self.step_absolute_coord = MemDev_Ax(0)
        self.default_wait = MemoryDevice(True, choices=[True, False])
        self.default_return_gnd = MemoryDevice('auto', choices=[True, False, 'auto'])
        self._devwrap('step_rel', doc="""Moves the requested number of step for set. returns the absolute_coord for get.
                                          Accepts parameters ax, return_gnd, wait which are set to 'default' by
                                          which means they use the value set in devices default_*.
                                          For the other values, see the step method documentation.""")
        self._devwrap('step_abs', doc="""Moves the count of step between the requested new position and the previous absolute_coord.
                                          Accepts parameters ax, return_gnd, wait which are set to 'default' by
                                          which means they use the value set in devices default_*.
                                          For the other values, see the step method documentation.""")

        if move_en:
            self._devwrap('move_abs', doc="""Moves to the requested position.
                                              Accepts parameters ax, return_gnd, wait which are set to 'default' by
                                              which means they use the value set in devices default_*.
                                              For the other values, see the move_auto method documentation.""")
            self._devwrap('move_rel', doc="""Moves to the request displacement away from the current position.
                                              Accepts parameters ax, return_gnd, wait which are set to 'default' by
                                              which means they use the value set in devices default_*.
                                              For the other values, see the move_auto method documentation.""")
            m2um = 1e6
            self.ax_position_um = Scale_um(self.ax_position)
            self.ax_target_pos_um = Scale_um(self.ax_target_pos)
            self.ax_target_reached_range_um = Scale_um(self.ax_target_reached_range)
            self.move_abs_um = Scale_um2(self.move_abs)
            self.move_rel_um = Scale_um2(self.move_rel)

    def _ax_check_limits(self, ax, target, relative):
        ax = self._ax_helper(ax)
        mn, mx = self._xyz_limits[ax]
        if relative:
            target = target + self.ax_position.get()
        _general_check(target, min=mn, max=mx, msg_src=self)

    def set_limits(self, min='keep', max='keep', ax=None):
        """
        When both min and max are 'keep', lists all the limits (returns a 3x2 array
                        for the min, max of the 3 directions)
        change the limits (like the limits option of the instrument initialization).
        by default when the value is 'keep' nothing is changed.
        Otherwise the value can be None to disable the limit or a number in m or deg.
        It only changes the limits for the axis ax (current_ax if not given)
        """
        if min == 'keep' and max == 'keep':
            return self._xyz_limits
        if isinstance(min, string_types) and min != 'keep':
            raise ValueError("The only string allowed is 'keep', otherwise use None or a number")
        if isinstance(max, string_types) and max != 'keep':
            raise ValueError("The only string allowed is 'keep', otherwise use None or a number")
        ax = self._ax_helper(ax)
        if min != 'keep':
            self._xyz_limits[ax, 0] = min
        if max != 'keep':
            self._xyz_limits[ax, 1] = max

    def _step_rel_checkdev(self, count, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper(ax)

    def _step_rel_setdev(self, count, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(return_gnd, wait)
        xo = self.step_absolute_coord.get()
        count = int(count)
        if count == 0:
            return
        self.step(count, ax=ax, **kwargs)
        if abs(count) != np.inf:
            self.step_absolute_coord.set(xo + count)

    def _step_rel_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.step_absolute_coord.get()

    def _step_abs_checkdev(self, new_pos, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper(ax)

    def _step_abs_setdev(self, new_pos, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(return_gnd, wait)
        xo = self.step_absolute_coord.get()
        count = new_pos - xo
        count = int(count)
        if count == 0:
            return
        self.step(count, ax=ax, **kwargs)
        self.step_absolute_coord.set(new_pos)

    def _step_abs_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.step_absolute_coord.get()

    def _move_abs_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.ax_position.get()

    def _move_rel_getdev(self, ax=None):
        ax = self._ax_helper(ax)
        return self.ax_position.get()

    def _move_abs_checkdev(self, target, ax=None, return_gnd='default', wait='default'):
        self._ax_check_limits(ax, target, relative=False)

    def _move_rel_checkdev(self, target, ax=None, return_gnd='default', wait='default'):
        self._ax_check_limits(ax, target, relative=True)

    def _move_abs_setdev(self, target, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(return_gnd, wait)
        self.move_auto(target, ax, relative=False, **kwargs)

    def _move_rel_setdev(self, target, ax=None, return_gnd='default', wait='default'):
        ax = self._ax_helper() # axis already set by checkdev
        kwargs = self._step_kwargs_parser(return_gnd, wait)
        self.move_auto(target, ax, relative=True, **kwargs)


    def _fix_stuck_pre_helper(self, param, allowed, check_only=False):
        param = param.copy()
        allowed_names = [k for k, v in allowed]
        orig = dict_improved({k:None} for k in ['amp', 'freq'])
        ret = dict_improved(allowed)
        for k, v in param.items():
            if k not in allowed_names:
                raise ValueError('Invalid parameter')
            ret[k] = v
            if k == 'amp' and v is not None:
                orig['amp'] = self.ax_amp.get()
                if not check_only:
                    self.ax_amp.set(v)
            if k == 'freq' and v is not None:
                orig['freq'] = self.ax_amp.get()
                if not check_only:
                    self.ax_freq.set(v)
            ret[k] = v
        return ret, orig

    def _fix_stuck_post_helper(self, orig):
        for k, v in orig:
            if v is None:
                return
            dev = dict(amp=self.ax_amp, freq=self.ax_freq)[k]
            dev.set(v)

    def _fix_stuck(self, i, ax, direction, check_only=False):
        fixes = self._fix_stuck_list[ax]
        try:
            fix = fixes[i]
        except IndexError:
            return False
        name, param = fix
        self._fix_stuck_internal(name, param, direction, check_only=check_only)
        return True

    def _fix_stuck_iter(self, ax, direction, check_only=False):
        fixes = self._fix_stuck_list[ax]
        for fix in fixes:
            name, param = fix
            self._fix_stuck_internal(name, param, direction, check_only=check_only)
            yield

    def _fix_stuck_internal(self, name, param, direction, check_only=False):
        if name == 'wiggle':
            param, orig = self._fix_stuck_pre_helper(param,  [('amp', None), ('freq', None), ('n_steps', 5), ('n_repeats', 10)], check_only)
            if check_only:
                return True
            for _ in param.n_repeats:
                self.step(param.n_steps)
                self.step(-param.n_steps)
        elif name == 'force':
            # force in one direction
            #  dir can be 0 for auto, 1 for fwd et -1 for reverse
            param, orig = self._fix_stuck_pre_helper(param,  [('amp', None), ('freq', None), ('n_steps', 5), ('dir', 0)], check_only)
            if check_only:
                return True
            n_steps = param.n_steps
            dir = param.dir
            if dir == 0:
                dir = direction
            if dir < 0:
                n_steps *= -1
            self.step(n_steps)
        elif name == 'move':
            # move without stopping at different amp, freq
            param, orig = self._fix_stuck_pre_helper(param,  [('amp', None), ('freq', None), ('timeout', 1.)], check_only)
            if check_only:
                return True
            target = self.ax_target.get()
            self.move(target, timeout=param.timeout)
        elif name == 'restart':
            param, orig = self._fix_stuck_pre_helper(param, [], check_only)
            if check_only:
                return True
        else:
            raise ValueError('Invalid fix_stuck name')
        self._fix_stuck_post_helper(orig)

#######################################################
##    ANC350 piezo controller, libusb direct access
#######################################################

class UcOpcode(IntEnumC):
    set = 0
    get = 1
    ack = 3
    tell = 4

class UcReason(IntEnumC):
    OK = 0
    Addr = 1
    Range = 2
    Ignored = 3
    Verify = 4
    Type = 5
    Unknown = 99

class ANC_addresses(IntEnumC):
    ID_GET_HW_ID = 0x0168
    ID_SET_HW_ID = 0x016A
    ID_PROGRAM_ID = 0x016F
    ID_SYNC_REQUEST = 0x000A
    ID_ASYNC_EN = 0x0145
    ID_FIRMWARE_RETR = 0x016C
    ID_VER_DSP1 = 0x0111
    ID_VER_FPGA1 = 0x0117
    ID_VER_FL_DSP1 = 0x0240
    ID_VER_FL_FPGA1 = 0x0246
    ID_PRD_DSP1 = 0x0112
    ID_PRD_FPGA1 = 0x0118
    ID_PRD_FL_DSP1 = 0x0241
    ID_PRD_FL_FPGA1 = 0x0247
    ID_FIRMWARE_VER = 0x3038
    ID_ANC_CONNECTED = 0x3002
    ID_ANC_MOVING = 0x302E
    ID_ANC_HUMP_FWD = 0x3039
    ID_ANC_HUMP_BKWD = 0x303A
    ID_ANC_SENSOR_ERROR = 0x3031
    ID_ANC_IMAX_STATUS = 0x3150
    ID_ANC_STATUS = 0x0404
    ANC_STATUS_RUNNING = 0x0001
    ANC_STATUS_HUMP = 0x0002
    ANC_STATUS_SENS_ERR = 0x0100
    ANC_STATUS_DISCONN = 0x0400
    ANC_STATUS_REF_VALID = 0x0800
    ID_ANC_IMAX_RESET = 0x3151
    ID_ANC_POSITION = 0x0415
    ID_ANC_COUNTER = 0x0415
    ID_ANC_REF_POSITION = 0x0407
    ID_ANC_POS_RESET = 0x044F
    ID_ANC_AUTO_RESET = 0x3035
    ID_ANC_REF_UPDATE = 0x3034
    ID_ANC_SGL_FWD = 0x0410
    ID_ANC_SGL_BKWD = 0x0411
    ID_ANC_CONT_FWD = 0x040E
    ID_ANC_CONT_BKWD = 0x040F
    ID_ANC_ACT_AMPL = 0x0514
    ID_ANC_TARGET = 0x0408
    ID_ANC_TARGET_RANGE = 0x3036
    ID_ANC_RUN_TARGET = 0x040D
    ID_ANC_MOVE_REF = 0x0444
    ID_ANC_RUN_RELATIVE = 0x0418
    ID_ANC_TARGET_STATUS = 0x3037
    ID_ANC_OUTPUT_EN = 0x3030
    ID_ANC_STOP_EN = 0x0450
    ID_ANC_AMPL = 0x0400
    ID_ANC_FAST_FREQ = 0x0401
    ID_ANC_STOP_ZERO = 0x0451
    ID_ANC_TRG_MODE = 0x3042
    ID_ANC_QUAD_IN_MODE = 0x3044
    ID_ANC_QUAD_IN_PERIOD = 0x3045
    ID_ANC_QUAD_OUT_MODE = 0x3046
    ID_ANC_QUAD_OUT_PERIOD = 0x3047
    ID_ANC_QUAD_OUT_CLOCK = 0x3048
    ID_ANC_CAP_START = 0x051E
    ID_ANC_CAP_VALUE = 0x0569
    ID_ANC_SENSOR_VOLT = 0x0526
    ID_ANC_SENSOR_EN = 0x058D
    ID_ANC_CYCLE_EN = 0x0588
    ID_ANC_CYCLE_PERIOD = 0x0589
    ID_ANC_CYCLE_OFFTIME = 0x058A
    ID_ANC_ACTORPS_SAVE = 0x050C
    # This seesm to always be broadcast even if ID_ASYNC_EN is off
    # It is not listed in anc350v4_protocol.h
    ID_ANC_ALL_POS_TELL = 0x303B

class UcTelegram(StructureImproved):
    _fields_ = [('length', c_int32),
                ('opcode', UcOpcode.ctype),
                ('address', ANC_addresses.ctype),
                ('index', c_int32),
                ('correlationNumber', c_int32)]

class UcStruct_extend(StructureImproved_extend):
    _mask_ = 'data'
    _mask_basetype = c_int32
    def _mask_get_count(self):
        size_int32 = sizeof(c_int32)
        length = self.hdr.length + size_int32
        offset = self._mask_get_offset()
        diff = length - offset
        if diff % size_int32 != 0:
            raise ValueError('size not a multiple of of int32')
        return diff // size_int32
    def _mask_set_count(self, n):
        size_int32 = sizeof(c_int32)
        offset = self._mask_get_offset()
        self.hdr.length = (offset - size_int32) + n*size_int32

class UcSetTelegram(UcStruct_extend):
    _fields_ = [('hdr', UcTelegram),
                ('data', c_int32*0)]
    _mask_ = 'data'
    _mask_basetype = c_int32

class UcGetTelegram(StructureImproved):
    _fields_ = [('hdr', UcTelegram)]

class UcAckTelegram(UcStruct_extend):
    _fields_ = [('hdr', UcTelegram),
                ('reason', UcReason.ctype),
                ('data', c_int32*0)]

class UcTellTelegram(UcStruct_extend):
    _fields_ = [('hdr', UcTelegram),
                ('data', c_int32*0)]

class Int2char(UnionImproved):
    _fields_ = [('val', c_int32), ('str', c_byte*4)]
    def get_bytes(self):
        return bytes(self.str)

UcRecvTimeout = 1 #s
Uc_Anc_Tcp_port = 2101
UC_MAXSIZE = 512
UC_MAXDATA = (UC_MAXSIZE - sizeof(UcTelegram))//sizeof(c_int32)

# udp discovery: a packet containing "N-Hands discovery\0" to 239.255.170.171, port 7071
# the anc version of it sends it 3 times
#   For usb
# Vendor ID: 0x16C0
# Product ID: 0x055B
# Interface Number: 0x00
# Endpoint for Sending: 0x02
# Endpoint for Receiving: 0x86



"""
# pip install pyusb
# pyusb needs python >=3.9
import usb.core
import usb.util
from ctypes import sizeof
devs = usb.core.find(idVendor=0x16C0, idProduct=0x055B, find_all=True)
dev = list(devs)[0]
dev.set_configuration()
cfg = dev.get_active_configuration()
intf = cfg[(0,0)]
ep_in = usb.util.find_descriptor(intf, bEndpointAddress=0x86)
ep_out = usb.util.find_descriptor(intf, bEndpointAddress=0x02)
gt = instruments.attocube.UcGetTelegram((0, instruments.attocube.UcOpcode.get, instruments.attocube.ANC_addresses.ID_ANC_TARGET, 0, 55))
gt2 = instruments.attocube.gen_telegram(instruments.attocube.UcOpcode.get, instruments.attocube.ANC_addresses.ID_FIRMWARE_VER, 0, 66)
gt3 = instruments.attocube.gen_telegram(instruments.attocube.UcOpcode.get, instruments.attocube.ANC_addresses.ID_ANC_TARGET_RANGE, 2, 66)

gt.hdr.length = sizeof(gt)
timeout = 1000 #ms
def read_until(t=None, printit=False, timeout=timeout):
    i = 0
    res = []
    while True:
        try:
            r = ep_in.read(512, timeout)
        except usb.USBError as exc:
            print('skipped', i, exc)
            break
        rc = instruments.attocube.read_telegram(r)
        if rc.hdr.address != instruments.attocube.ANC_addresses.ID_ANC_ALL_POS_TELL:
            res.append(rc)
        if t is not None:
            if rc.hdr.opcode == t:
                print('skipped', i)
                return rc, r, res
        if printit:
            print(rc)
        i += 1
    return None, None, res

_, _, res0 = read_until()
ep_out.write(bytes(gt), timeout)
ac, a, res = read_until(instruments.attocube.UcOpcode.ack); ac

# to free device so it can be opened somewhere else:
usb.util.release_interface(dev, intf)
# That seems to be enough. however could also use:
usb.util.dispose_resources(dev)
# with either, there is no need the recreate dev, intf, ep* they will all still work
# if the device is still available.

# To show the full configuration, including string names when available
# print(str(dev)) or just
print(dev)
"""

# should check correlation number
def read_telegram(data):
    N = sizeof(UcTelegram)
    t = UcTelegram.from_buffer(data[:N])
    if len(data) != t.length+4:
        raise RuntimeError('Wrong length')
    if t.opcode == UcOpcode.ack:
        return UcAckTelegram.from_buffer(data)
    elif t.opcode == UcOpcode.tell:
        return UcTellTelegram.from_buffer(data)
    elif t.opcode == UcOpcode.set:
        return UcSetTelegram.from_buffer(data)
    elif t.opcode == UcOpcode.get:
        return UcGetTelegram.from_buffer(data)
    else:
        raise RuntimeError('Unknow opcode')

def gen_telegram(opcode, address, index, correlationNum, data=None, reason=None):
    arg = (0, opcode, address, index, correlationNum)
    if opcode == UcOpcode.ack:
        t = UcAckTelegram(hdr=arg)
    elif opcode == UcOpcode.tell:
        t = UcTellTelegram(hdr=arg)
    elif opcode == UcOpcode.set:
        t = UcSetTelegram(hdr=arg)
    elif opcode == UcOpcode.get:
        t = UcGetTelegram(hdr=arg)
        t.hdr.length = sizeof(UcGetTelegram) - sizeof(c_int32)
    else:
        raise RuntimeError('Unknow opcode')
    if data is not None:
        if isinstance(data, (np.ndarray, list, tuple)):
            n = len(data)
        else:
            n = 1
        t.set_data_size(n)
        t.data = data
    if reason is not None:
        t.reason = reason
    return t

usb_core = None
usb_util = None

class ANC_libusb_listen_thread(threading.Thread):
    def __init__(self, control):
        super(ANC_libusb_listen_thread, self).__init__()
        self.control = control
        self.__stop = False
        self._regular_cache = queue.Queue() # infinite size
        self._lock = threading.Lock()
        self._listen_cache = {}
        self._last_ping = dict()
        self.daemon = True # This will allow python to exit

    def cancel(self):
        self.__stop = True

    def run(self):
        # This print is needed on anaconda 2019.10 on windows 10 to prevent
        #  a windows error exeption when later trying to print in the thread (status_line)
        # Doing a print at the beginning of the thread fixes that problem.
        #print('Listen Thread started')
        control = self.control
        timeout = 1000 #ms
        max_size = 512
        ep_in = control._ep_in
        #ep_out = control._ep_out
        while True:
            if self.__stop:
                return
            try:
                r = ep_in.read(max_size, timeout)
#            except usb_core.USBTimeoutError:
            except usb_core.USBError:
                continue
            t = read_telegram(r)
            h = t.hdr
            if h.opcode == UcOpcode.ack:
                self._regular_cache.put((t, time.time()))
            elif h.opcode == UcOpcode.tell:
                if h.address == ANC_addresses.ID_ANC_ALL_POS_TELL:
                    # This one as an ever increasing index
                    self.put_cache(h.address, h.correlationNumber, t.data.copy(), h.index)
                else:
                    self.put_cache(h.address, h.index, t.data.copy(), h.correlationNumber)
            else:
                raise RuntimeError('Unexpected telegram type.')

    def put_cache(self, addr, index, value, correl):
        with self._lock:
            self._listen_cache[((addr), index)] = (value, correl, time.time())

    def get_cache(self, addr, index=0):
        with self._lock:
            ret = self._listen_cache.get((addr, index), None)
        return ret

    def del_cache(self,  addr, index, recursion=False):
        with self._lock:
            try:
                del self._listen_cache[(addr, index)]
            except KeyError:
                pass

    def get_last_regular(self):
        return self._regular_cache.get(timeout=self.control._timeout)

    def clear_buffer(self):
        while True:
            try:
                self._regular_cache.get_nowait()
            except queue.Empty:
                break

    def wait(self, timeout=None):
        # we use a the context manager because join uses sleep.
        with _sleep_signal_context_manager():
            self.join(timeout)
        return not self.is_alive()


class AttoDev2(Base2Device):
    def __init__(self, addr, settable=False, dev_type=None, scale=None, **kwargs):
        super(AttoDev2, self).__init__(**kwargs)
        self._addr = addr
        self._getdev_p = True
        if settable:
            self._setdev_p = True
        self._dev_type = dev_type
        if dev_type is None:
            self._dev_type = self.choices
        self._scale = scale

    def _set_write(self, val, options):
        kwargs = {}
        if 'ax' in options:
            ax = options['ax']
            kwargs['index'] = ax
        else:
            ax = None
        val = self._todev_conv_helper(val, ax)
        self.instr.write(self._addr, val, **kwargs)

    def _get_ask(self, options):
        kwargs = {}
        if 'ax' in options:
            ax = options['ax']
            kwargs['index'] = ax
        else:
            ax = None
        val = self.instr.ask(self._addr, **kwargs)
        return self._fromdev_conv_helper(val, ax)

    def _todev_conv_helper(self, val, ax):
        t = self._dev_type
        if t == int:
            return int(val)
        elif t == bool:
            return int(val)
        elif t is None:
            return val
        elif t is float:
            if self._scale is True:
                val = val/self.instr._ax_scale[ax]
            elif self._scale is not None:
                val = val/self._scale
            return int(round(val))
        return t.tostr(val)

    def _fromdev_conv_helper(self, val, ax):
        t = self._dev_type
        if t == int:
            return val
        elif t == bool:
            return bool(val)
        elif t is None:
            return val
        elif t is float:
            val = float(val)
            if self._scale is True:
                return val*self.instr._ax_scale[ax]
            elif self._scale is not None:
                return val*self._scale
            return val
        return t(val)

# TODO deal with proper init (device selection), timeout setting
@register_instrument('attocube', 'ANC350')
class attocube_anc350(BaseInstrument):
    """
    This controls the attocube ANC350 piezo controller
    Useful devices:
        step_rel, step_rel_um
        ax_target_ground_en

    Useful methods:
        reset_step_absolute_coords
        move_auto
        step
        stop
        wait_stepping
        conf_ax
        set_limits
    """
    def __init__(self, dev_num=0, ax_names=['x', 'y', 'z'], dll_path=ANC_DLL_Default_Path,
                 search=ANC_InterfaceType.IfAll, limits=[(None, None), (None,None), (None, None)],
                 register_ip=[], **kwargs):
        """
        dev_num can be a number, which selects that device discovered.
                It can also be a serial number string to select one.
                You can use the static method discover to list devices.

        ax_names is list of names to use for the axis (in the axis order,
                i.e. 0, 1, 2). A name can be left as None. It defaults to ['x', 'y', 'z']
        limits are a list of 3 tuples of (min, max) values for each axis. A value
               of None disables the limit handling.
        register_ip is a list of ip addresses or hostnames to preregister for the discovery.
             It is necessary if the ip address is not on the local network.
        """
        global usb_core, usb_util
        usb_core, usb_util = _delayed_libusb_import()
        devs = usb_core.find(idVendor=0x16C0, idProduct=0x055B, find_all=True)
        dev = list(devs)[0]
        dev.set_configuration()
        cfg = dev.get_active_configuration()
        intf = cfg[(0,0)]
        ep_in = usb_util.find_descriptor(intf, bEndpointAddress=0x86)
        ep_out = usb_util.find_descriptor(intf, bEndpointAddress=0x02)
        self._usb_dev = dev
        self._usb_cfg = cfg
        self._usb_intf = intf
        self._ep_in = ep_in
        self._ep_out = ep_out
        self._correlation_num = 10
        s = weakref.proxy(self)
        self._timeout = 1.
        self._last_tell = (0, 0)
        self._helper_thread = ANC_libusb_listen_thread(s)
        self._helper_thread.start()
        limits = np.array(limits)
        self._xyz_limits = limits
        if limits.shape != (3, 2):
            raise ValueError('limits is not of the correct shape')
        if len(ax_names) != 3:
            raise ValueError('ax_names needs to be a list of 3 strings')
        self._ax_names = ax_names
        super(attocube_anc350, self).__init__()


    def __del__(self):
        self._helper_thread.cancel()
        self._helper_thread.wait(1.5)
        # to free device so it can be opened somewhere else:
        usb_util.release_interface(self._usb_dev, self._usb_intf)
        # That seems to be enough. however could also use:
        #usb_util.dispose_resources(self._usb_dev)
        # with either, there is no need the recreate dev, intf, ep* they will all still work
        # if the device is still available.
        super(attocube_anc350, self).__del__()

    @locked_calling
    def write(self, address, val, index=0, timeout=1., correl=None):
        if correl is None:
            self._correlation_num += 1
            correl = self._correlation_num
        t = gen_telegram(UcOpcode.set, address, index, correl, data=val)
        timeout = int(timeout/1000.)
        self._ep_out.write(bytes(t), timeout)

    def clear(self):
        self._helper_thread.clear_buffer()

    @locked_calling
    def ask(self, address=None, index=0, tell_addr=None, check_correl=True, timeout=1., correl=None):
        time_before_send = time.time()
        if address is not None:
            if correl is None:
                self._correlation_num += 1
                correl = self._correlation_num
            t = gen_telegram(UcOpcode.get, address, index, correl)
            timeout = int(timeout/1000.)
            self._ep_out.write(bytes(t), timeout)
        if tell_addr is None and address is not None:
            while True:
                ret = self._helper_thread.get_last_regular()
                if ret is None:
                    return None
                t, time_recv = ret
                if time_before_send <= time_recv:
                    # it is a new value
                    break
            h = t.hdr
            if h.address != address or h.index != index:
                raise RuntimeError(self.perror('Received unexpected telegram, %r'%t))
            if check_correl and h.correlationNumber != correl:
                raise RuntimeError(self.perror('Incorrect correlationNumber for telegram: %r'%t))
            if t.reason != UcReason.OK:
                raise RuntimeError(self.perror('There was an error of type %s with telegram: %r'%(t.reason, t)))
            data = t.data
        else:
            ret = self._helper_thread.get_cache(tell_addr, index)
            if ret is None:
                return None
            data, correl, time_recv = ret
            self._last_tell = (correl, time_recv)
        if len(data) == 1:
            return data[0]
        return data

    def _read_string_base(self, base_address, count, incr='addr', index=0, reverse=True):
        if incr not in ['addr', 'index']:
            raise RuntimeError('Invalid incr value')
        ret = []
        addr = base_address
        base_index = index
        for i in range(5):
            if incr == 'addr':
                addr = base_address + i
            else:
                index = base_index + i
            r = self.ask(addr, index)
            d = Int2char(val=r)
            s = d.get_bytes()
            if reverse:
                s = s[::-1]
            s = s.replace(b'\0', b' ')
            ret.append(s)
        return fu(b''.join(ret)).rstrip(' ')

    def _read_string(self, base_address, index=0):
        return self._read_string_base(base_address, count=5, incr='addr', index=index)

    def _read_string2(self, address):
        return self._read_string_base(address, count=7, incr='index', reverse=False)

    def read_actuator_name(self, ax=0):
        return self._read_string(0x3003, ax)

    def read_actuator_lut_name(self, ax=0):
        return self._read_string(0x0596, ax)

    def read_serial(self):
        val = self.ask(0x066f)
        letter = chr(val>>16)
        n1 = (val&0xffff)>>12
        n2 = val&0x0fff
        return "%s %02d %04d"%(letter, n1, n2)

    def read_fw(self):
        dsp_version = self._read_string2(ANC_addresses.ID_VER_DSP1)
        fpga_version = self._read_string2(ANC_addresses.ID_VER_FPGA1)
        dsp_product_id = self._read_string2(ANC_addresses.ID_PRD_DSP1)
        fpga_product_id = self._read_string2(ANC_addresses.ID_PRD_FPGA1)
        extra1 = self._read_string2(0x0119)
        extra2 = self._read_string2(0x011a)
        old = self.ask(ANC_addresses.ID_FIRMWARE_VER)
        return dict(dsp_version=dsp_version, fpga_version=fpga_version,
                    dsp_product_id=dsp_product_id, fpga_product_id=fpga_product_id,
                    extra1=extra1, extra2=extra2, old=old)

    def _ax_helper(self, ax=None):
        if ax is not None:
            ax = self.current_ax.set(ax)
        ax = self.current_ax.get()
        # need to convert ax which could be any names to the real ax integer
        ax = self.current_ax._tostr(ax)
        return ax

    def _multi_ax_helper(self, ax=None):
        single = False
        if ax == 'all':
            ax =[0, 1, 2]
        else:
            if not isinstance(ax, (list, tuple, np.ndarray)):
                ax = [ax]
                single = True
            # go trough _ax_helper to make sure we have the numbered ax names instead
            # of the named ones.
            prev_ax = self.current_ax.get()
            ax = [self._ax_helper(a) for a in ax]
            if not single:
                self.current_ax.set(prev_ax)
        return ax, single

    @locked_calling
    def clear_overccurent_error(self, ax=None):
        ax = self._ax_helper(ax)
        self.write(ANC_addresses.ID_ANC_IMAX_RESET, ax, 1)

    def _get_HW_id(self):
        return self.ask(ANC_addresses.ID_GET_HW_ID)
    def _set_HW_id(self, id_val, save_permanent=False):
        self.write(ANC_addresses.ID_SET_HW_ID, id_val)
        if save_permanent:
            self.write(ANC_addresses.ID_PROGRAM_ID, 0x1234)
    def _set_asynchronous_en(self, en):
        self.write(ANC_addresses.ID_ASYNC_EN, en)

    def _move_to_target_en(self, en):
        self.write(ANC_addresses.ID_ANC_RUN_TARGET, en)
    def _move_to_target_abs_en(self, en):
        self.write(ANC_addresses.ID_ANC_RUN_TARGET, en)
    def _move_to_target_rel_en(self, en):
        self.write(ANC_addresses.ID_ANC_RUN_RELATIVE, en)
    def _step_single_fwd(self):
        self.write(ANC_addresses.ID_ANC_SGL_FWD, 1)
    def _step_single_bkwd(self):
        self.write(ANC_addresses.ID_ANC_SGL_BKWD, 1)
    def _step_continuous_fwd_en(self, en):
        self.write(ANC_addresses.ID_ANC_CONT_FWD, en)
    def _step_continuous_bkwd_en(self, en):
        self.write(ANC_addresses.ID_ANC_CONT_BKWD, en)

    def _create_devs(self):
        self.current_ax = MemoryDevice(0, choices=
                                       ChoiceSimpleMap({k: v for k, v in enumerate(self._ax_names)}, allow_keys=True))
        #features = self.ask()
        #self.options = features

        # I have not seen gonio or rot type, so I cannot confirm that this will work.
        ax_type = [self.ask(0x3033, ax) for ax in range(3)]
        # 3 types are possible 0=linear, 1,2 are gonio.rot
        # linear as scale of nm, the other two are 100 uDeg
        self._ax_scale = [100e-6 if t else 1e-9 for t in ax_type]

        def AttoDevAx(*arg, **kwarg):
            options = kwarg.pop('options', {}).copy()
            options.update(ax=self.current_ax)
            app = kwarg.pop('options_apply', ['ax'])
            kwarg.update(options=options, options_apply=app)
            return AttoDev2(*arg, **kwarg)

        self.ax_output_en = AttoDevAx(ANC_addresses.ID_ANC_OUTPUT_EN, True, dev_type=bool)
        self.ax_freq = AttoDevAx(ANC_addresses.ID_ANC_FAST_FREQ, True, dev_type=float)
        self.ax_amp = AttoDevAx(ANC_addresses.ID_ANC_AMPL, True, dev_type=float, scale=1e-3)
        self.ax_dc_volt = AttoDevAx(ANC_addresses.ID_ANC_ACT_AMPL, True, dev_type=float, scale=1e-3)
        #self.ax_measure_cap = AttoDevAx('measureCapacitance', autoinit=False)
        self.ax_position = AttoDevAx(ANC_addresses.ID_ANC_POSITION, dev_type=float, scale=True)
        #self.ax_lut_name = AttoDevAx('getLutName', 'loadLutFile', autoinit=False)
        self.ax_status = AttoDevAx(ANC_addresses.ID_ANC_STATUS)
        # status bit field
        #  ANC_STATUS_RUNNING    0x0001 /**< ANC_STATUS Bitmask: axis is moving. */
        #  ANC_STATUS_HUMP       0x0002 /**< ANC_STATUS Bitmask: EOT detected.   */
        #  ANC_STATUS_SENS_ERR   0x0100 /**< ANC_STATUS Bitmask: sensor error.   */
        #  ANC_STATUS_DISCONN    0x0400 /**< ANC_STATUS Bitmask: sensor disconn. */
        #  ANC_STATUS_REF_VALID  0x0800 /**< ANC_STATUS Bitmask: reference valid.*/
        self.ax_status_target = AttoDevAx(ANC_addresses.ID_ANC_TARGET_STATUS, dev_type=bool)
        self.ax_status_moving = AttoDevAx(ANC_addresses.ID_ANC_MOVING, dev_type=bool)
        self.ax_status_eot_fwd = AttoDevAx(ANC_addresses.ID_ANC_HUMP_FWD, dev_type=bool)
        self.ax_status_eot_bkwd = AttoDevAx(ANC_addresses.ID_ANC_HUMP_BKWD, dev_type=bool)
        self.ax_status_sensor_error = AttoDevAx(ANC_addresses.ID_ANC_SENSOR_ERROR, dev_type=bool)
        self.ax_status_overcurrent = AttoDevAx(ANC_addresses.ID_ANC_IMAX_STATUS, dev_type=bool)
        self.ax_status_connected = AttoDevAx(ANC_addresses.ID_ANC_CONNECTED, dev_type=bool)
        self.ax_target_pos = AttoDevAx(ANC_addresses.ID_ANC_TARGET, True, dev_type=float, scale=True)
        self.ax_target_reached_range = AttoDevAx(ANC_addresses.ID_ANC_TARGET_RANGE, True, dev_type=float, scale=True)
        self.ax_target_ground_en = AttoDevAx(ANC_addresses.ID_ANC_STOP_ZERO, True, dev_type=bool,
                                             doc="This makes the output go to zero volt after a target move.")
        self.ax_stop_on_eot = AttoDevAx(ANC_addresses.ID_ANC_STOP_EN, True, dev_type=bool)
        self.ax_use_lut_en = AttoDevAx(0x058e, True, dev_type=bool)
        self.lockin_en = AttoDev2(0x05a0, True, dev_type=bool)
        self.meas_voltage = AttoDev2(0x0526, True, dev_type=float, scale=1e-3)
        MemDev_Ax = lambda val, **kwargs:  MemoryDevice_update(val, nch=3, first_ch=0, ch_name='ax', ch_helper_func=self._ax_helper,
                                                               no_type_conv=True, **kwargs)
        self.step_absolute_coord = MemDev_Ax(0)

        # This needs to be last to complete creation
        super(attocube_anc350, self)._create_devs()



# get ID_VER_DSP1(0x0111) ID_PRD_DSP1(0x0112) with index 0-6
# same with ID_VER_FPGA1(0x0117), ID_PRD_FPGA1(0x0118)
# same with 0x119 0x11a
#   anc2.read_string2(instruments.attocube.ANC_addresses.ID_VER_DSP1)
#     '2019/02/12 09:50:00'
#   anc2.read_string2(instruments.attocube.ANC_addresses.ID_PRD_DSP1)
#      'ANC350V3         DspVersion'
#   anc2.read_string2(instruments.attocube.ANC_addresses.ID_VER_FPGA1)
#     '2015/10/05,06:41:23'
#   anc2.read_string2(instruments.attocube.ANC_addresses.ID_PRD_FPGA1)
#      'anc3res_core.ncd 23'
#   anc2.read_string2(0x119)
#      '2019/02/05,11:59:00'
#   anc2.read_string2(0x11a)
#      'anc3res_appl.ncd 23'
#
# 0x58e pour activer ou pas Use LUT
# 0x5a0 pour activer/desactiver lockin
# 0x526 pour choisir voltage en mV
# 0x300. c'est pour le actuator name ANPx341
# Note that they all have a reason of 0
# 0x3003 index1 = 'xPNA'
# 0x3004 index1 = ' 143'
# 0x3005 index1 = '    '
# 0x3006 index1 = '    '
# 0x3007 index1 = '    '
#    anc2.read_string(0x3003, 0)
#  here index selects axis, for 1 we read ANPx341-02112
# 0x0596 index1 = 'xPNA'
# 0x0597 index1 = '-143'
# 0x0598 index1 = '1120'
# 0x0599 index1 = '   2'
# 0x059a index1 = '    '
#    anc2.read_string(0x0596, 0)
# capacitance result comes in a tell 0x569
#   anc2.write(instruments.attocube.ANC_addresses.ID_ANC_CAP_START, 0, 1)
#   anc2.ask(None, 0, tell_addr=instruments.attocube.ANC_addresses.ID_ANC_CAP_VALUE), anc2._last_tell

# 0x3033 to get actuator type (linear, gonion rot)
# getDeviceConfig (Features): requests: 0x3053 (-1)
#                                       0x315d (0)
#                                       0x3055 (-1)
#                                       0x3058 (1) # maybe lockin feature
# other possible flags: Duty cycle, App control (IOS), Sync (ethernet)
# discover request 0x167 (0x9100) (also hw id and serial number)
#    is 0x9100 saying ANC_DeviceType.Anc350Res?

# 0x3014 to select actuator type (anpx141...)
#    anc2.ask(0x3014, 0)
# 0x66f returns 0000 b6:13:4c:00 which is the serial number L 01 0950
#  since 4c is 'L' 13b6 is broken into 01 et 0x3b6 = 950

# Because ID_ANC_ALL_POS_TELL is being sent continuously (or placed in the instrumnent out put buffer)
# if it is not read, eventually the instruments stop sending it. (There seems to be about 1879 entries)
# Since it seems to send them every 1.5 ms that is about 2.82s. Empirically, I get that
# the ID_ANC_ALL_POS_TELL sending stops after 3s of not reading.
# Sending a request (either set or get) restarts the sending of the ID_ANC_ALL_POS_TELL



#######################################################
##    AMC300 piezo controller, jsonrpc
#######################################################

class AttoAMC_Device(Base2Device):
    def __init__(self, getstr=None, setstr=None,
                 val_type=None, choices=None, add_axis=False, scale=None,
                 ask_opt={}, **kwarg):
        """
           val_type can be float, int, bool, str, None
           If choices is a subclass of ChoiceBase, then val_type will be
           set to that object if unset.
        """
        if setstr is None and getstr is None:
            raise ValueError('At least one of setstr or getstr needs to be specified')
        if isinstance(choices, ChoiceBase) and val_type is None:
            val_type = choices
        super(AttoAMC_Device, self).__init__(choices=choices, get_has_check=True, **kwarg)
        self._setdev_p = setstr
        if getstr is not None:
            self._getdev_p = getstr
        self._ask_opt = ask_opt
        self.type = val_type
        self.add_axis = add_axis
        self.scale = scale
    def _tostr(self, val):
        # This function converts from val to a str for the command
        if self.scale is not None:
            val /= self.scale
        t = self.type
        if t == int:
            return int(val)
        if t == bool:
            return bool(val)
        if isinstance(t, ChoiceBase):
            return t.tostr(val)
        return val
    def _fromstr(self, valstr):
        # This function converts from the query result to a value
        if self.scale is not None:
            valstr *= self.scale
        t = self.type
        if isinstance(t, ChoiceBase):
            return t(valstr)
        return valstr
    def _set_write(self, val, options):
        # This is called with val already in instrument format.
        command = self._setdev_p
        if self.add_axis:
            ax = options['ax']
            params = [ax, val]
        else:
            params = val
        self.instr.do_request(command, params=params, **self._ask_opt)
    def _get_ask(self, options):
        # you should have self._get_para_checked() before the actual operation
        # this returns a value in instrument format
        command = self._getdev_p
        self._get_para_checked()
        if self.add_axis:
            ax = options['ax']
            params = ax
        else:
            params = None
        ret = self.instr.do_request(command, params=params, **self._ask_opt)
        return ret

@register_instrument('attocube', 'AMC300')
class attocube_amc300(visaInstrument):
    """
    This is the driver of Attocube AMC300 piezo controller.
    address in the form:
       tcpip::AMC300RES-A01-0547.local::9090::socket
    """
    def __init__(self, visa_addr, ax_names=['x', 'y', 'z'], **kwargs):
        self._request_id = 0
        self._error_cache = {}
        self._ax_names = ax_names
        kwargs['write_termination'] = '\r\n'
        kwargs['read_termination'] = '\r\n'
        rsrc_info = resource_info(visa_addr)
        if int(rsrc_info.resource_name.split('::')[2]) != 9090:
                self.perror('Invalid port number in visa_addr. It should be 9090.')
        super(attocube_amc300, self).__init__(visa_addr, **kwargs)

    def idn(self):
        fw = self.do_request('system.getFirmwareVersion')
        flux = self.do_request('system.getFluxCode')
        serial = self.do_request('system.getSerialNumber')
        return "attocube,AMC300,%s,%s"%(serial, 'fw:%s_flux:%s'%(fw, flux))

    def _get_error_helper(self, err_code, lang):
        key = (lang, err_code)
        if key in self._error_cache:
            return self._error_cache[key]
        val = self.do_request('system.errorNumberToString', list(key))
        self._error_cache[key] = val
        return val

    def _get_error(self, err_code, lang=-1):
        """ lang = 0 for error name,
            lang = 1 for more user friendly error message
            lang = -1 combines both
        """
        if lang == -1:
            err1 = self._get_error_helper(err_code, 0)
            err2 = self._get_error_helper(err_code, 1)
            if err1 == err2:
                return err1
            return "(%s) %s"%(err1, err2)
        return self._get_error_helper(err_code, lang)

    def _get_error_recommendation(self, err_code, lang=0):
        return self.do_request('system.errorNumberToRecommendation', [lang, err_code])

    @locked_calling
    def do_request(self, method_name, params=None, prefix='com.attocube.', skip_error=False):
        rid = self._request_id
        self._request_id += 1
        req_dict = dict(jsonrpc="2.0", method=prefix+method_name, id=rid, api=2)
        if params is not None:
            if not isinstance(params, list):
                params = [params]
            req_dict['params'] = params
        ret_json = self.ask(json.dumps(req_dict))
        ret = json.loads(ret_json)
        if 'jsonrpc' not in ret or ret['jsonrpc'] != '2.0':
            raise RuntimeError("Invalid response.")
        if ret['id'] != rid and ret['id'] != None:
            raise RuntimeError("Invalid request id")
        if 'error' in ret:
            err = ret['error']
            raise RuntimeError('Problem doing "%s" call. Error is (%i) %s'%(method_name, err['code'], err['message']))
        elif 'result' in ret:
            result = ret['result']
        else:
            raise RuntimeError('Unexpected response: %r'%ret)
        errCode = result[0]
        if errCode != 0 and not skip_error:
            raise RuntimeError("Error %d in request: %s"%(errCode, self._get_error(errCode)))
        if not skip_error:
            result = result[1:]
        if len(result) == 0:
            result = None
        elif len(result) == 1:
            result = result[0]
        return result

    def reboot_system(self):
        self.do_request('system.rebootSystem')
        print("!!! You will need to re-establish the connection !!!")

    @locked_calling
    def reset_soft(self):
        """ This will perform a reboot after the reset """
        self.do_request('system.system.softReset')
        self.reboot_system()

    def update_time(self, dt):
        """ datetime can be 'now' to use the current time, it can be 'internet' to ask
        the device to get it from attocube.com (if it has access to it) or a datetime object
        """
        if dt == 'internet':
            self.do_request('system.updateTimeFromInternet')
            return
        if dt == 'now':
            dt = datetime.datetime.utcnow()
        self.do_request('system.setTime', params=[dt.day, dt.month, dt.year, dt.hour, dt.minute, dt.second])

    def _ax_helper(self, ax=None):
        if ax is not None:
            ax = self.current_ax.set(ax)
        ax = self.current_ax.get()
        # need to convert ax which could be any names to the real ax integer
        ax = self.current_ax._tostr(ax)
        return ax

    def _create_devs(self):
        self.current_ax = MemoryDevice(0, choices=
                                       ChoiceSimpleMap({k: v for k, v in enumerate(self._ax_names)}, allow_keys=True))
        def AttoAMCDevAx(*arg, **kwarg):
            options = kwarg.pop('options', {}).copy()
            options.update(ax=self.current_ax)
            app = kwarg.pop('options_apply', ['ax'])
            kwarg.update(options=options, options_apply=app, add_axis=True)
            return AttoAMC_Device(*arg, **kwarg)

        self.actor_name = AttoAMCDevAx('amc.control.getActorName')
        self.ax_frequency = AttoAMCDevAx('amc.control.getControlFrequency', 'amc.control.setControlFrequency', scale=1e-3, val_type=int, setget=True)
        self.ax_amp = AttoAMCDevAx('amc.control.getControlAmplitude', 'amc.control.setControlAmplitude', scale=1e-3, val_type=int, setget=True)
        self.ax_dc_volt = AttoAMCDevAx('amc.control.getControlFixOutputVoltage', 'amc.control.setControlFixOutputVoltage', scale=1e-3, val_type=int, setget=True)
        self.ax_position = AttoAMCDevAx('amc.move.getPosition', scale=1e-9, val_type=int, setget=True)
        #self.ax_lut_name = AttoAMCDevAx('amc.res.getLutSn', autoinit=False)
        self.ax_status = AttoAMCDevAx('amc.status.getFullCombinedStatus')
        self.ax_automeasure_en = AttoAMCDevAx('amc.control.getAutoMeasure', 'amc.control.setAutoMeasure', val_type=bool)
        self.ax_sensor_en = AttoAMCDevAx('amc.control.getSensorEnabled', 'amc.control.setSensorEnabled', val_type=bool)
        #self.ax_sensor_dir_inverted_en = AttoAMCDevAx('amc.control.getSensorDirection', 'amc.control.setSensorDirection', val_type=bool)

        self.get_pos = AttoAMC_Device(getstr='amc.control.getPositionsAndVoltages')

        # This needs to be last to complete creation
        super(attocube_amc300, self)._create_devs()


# Possible parameters:
#  int, string, errCode, bool, double

# amc.amcids.getLowerSoftLimit
# amc.amcids.getSoftLimitEnabled
# amc.amcids.getSoftLimitReached
# amc.amcids.getUpperSoftLimit
# amc.amcids.resetIdsAxis
# amc.amcids.setLowerSoftLimit
# amc.amcids.setSoftLimitEnabled
# amc.amcids.setUpperSoftLimit
# amc.control.MultiAxisPositioning
# amc.control.MultiAxisPositioningWithTime
# amc.control.getActorName
# amc.control.getActorParametersActorName
# amc.control.getActorSensitivity
# amc.control.getActorType
# amc.control.getAutoMeasure
# amc.control.getControlAmplitude
# amc.control.getControlAutoReset
# amc.control.getControlFixOutputVoltage
# amc.control.getControlFrequency
# amc.control.getControlMove
# amc.control.getControlOutput
# amc.control.getControlReferenceAutoUpdate
# amc.control.getControlTargetRange
# amc.control.getCrosstalkThreshold
# amc.control.getCurrentOutputVoltage
# amc.control.getEoTParameters
# amc.control.getExternalSensor
# amc.control.getFinePositioningRange
# amc.control.getFinePositioningSlewRate
# amc.control.getMotionControlThreshold
# amc.control.getPositionsAndVoltages
# amc.control.getReferencePosition
# amc.control.getSensorDirection
# amc.control.getSensorEnabled
# amc.control.getStatusMovingAllAxes
# amc.control.searchReferencePosition
# amc.control.setActorParametersByName
# amc.control.setActorParametersJson
# amc.control.setActorSensitivity
# amc.control.setAutoMeasure
# amc.control.setControlAmplitude
# amc.control.setControlAutoReset
# amc.control.setControlFixOutputVoltage
# amc.control.setControlFrequency
# amc.control.setControlMove
# amc.control.setControlOutput
# amc.control.setControlReferenceAutoUpdate
# amc.control.setControlTargetRange
# amc.control.setCrosstalkThreshold
# amc.control.setEoTParameters
# amc.control.setExternalSensor
# amc.control.setFinePositioningRange
# amc.control.setFinePositioningSlewRate
# amc.control.setMotionControlThreshold
# amc.control.setReset
# amc.control.setSensorDirection
# amc.control.setSensorEnabled
# amc.description.checkChassisNbr
# amc.description.getDeviceType
# amc.description.getFeaturesActivated
# amc.description.getPositionersList
# amc.diagnostic.getDiagnosticPower
# amc.diagnostic.getDiagnosticResults
# amc.diagnostic.getDiagnosticStepSize
# amc.diagnostic.getDiagnosticTemperature
# amc.diagnostic.startDiagnostic
# amc.move.getControlContinuousBkwd
# amc.move.getControlContinuousFwd
# amc.move.getControlEotOutputDeactive
# amc.move.getControlTargetPosition
# amc.move.getGroundAxis
# amc.move.getGroundAxisAutoOnTarget
# amc.move.getGroundTargetRange
# amc.move.getNSteps
# amc.move.getPosition
# amc.move.getPositionWithTime
# amc.move.getPositionWithTime_32Bit
# amc.move.moveReference
# amc.move.performNSteps
# amc.move.setControlContinuousBkwd
# amc.move.setControlContinuousFwd
# amc.move.setControlEotOutputDeactive
# amc.move.setControlTargetPosition
# amc.move.setGroundAxis
# amc.move.setGroundAxisAutoOnTarget
# amc.move.setGroundTargetRange
# amc.move.setNSteps
# amc.move.setSingleStep
# amc.move.writeNSteps
# amc.res.getChainGain
# amc.res.getLinearization
# amc.res.getLutSn
# amc.res.getMode
# amc.res.getSensorStatus
# amc.res.setChainGain
# amc.res.setConfigurationFile
# amc.res.setLinearization
# amc.res.setMode
# amc.rotcomp.getControlTargetRanges
# amc.rotcomp.getEnabled
# amc.rotcomp.getLUT
# amc.rotcomp.setEnabled
# amc.rotcomp.setLUT
# amc.rotcomp.updateOffsets
# amc.rtin.apply
# amc.rtin.discard
# amc.rtin.getControlAQuadBInResolution
# amc.rtin.getControlMoveGPIO
# amc.rtin.getGpioMode
# amc.rtin.getNslMux
# amc.rtin.getRealTimeInChangePerPulse
# amc.rtin.getRealTimeInFeedbackLoopMode
# amc.rtin.getRealTimeInMode
# amc.rtin.getRealTimeInStepsPerPulse
# amc.rtin.setControlAQuadBInResolution
# amc.rtin.setControlMoveGPIO
# amc.rtin.setGpioMode
# amc.rtin.setNslMux
# amc.rtin.setRealTimeInChangePerPulse
# amc.rtin.setRealTimeInFeedbackLoopMode
# amc.rtin.setRealTimeInMode
# amc.rtin.setRealTimeInStepsPerPulse
# amc.rtout.apply
# amc.rtout.applyAxis
# amc.rtout.discard
# amc.rtout.discardAxis
# amc.rtout.discardSignalMode
# amc.rtout.getControlAQuadBOut
# amc.rtout.getControlAQuadBOutClock
# amc.rtout.getControlAQuadBOutResolution
# amc.rtout.getMode
# amc.rtout.getSignalMode
# amc.rtout.getTriggerConfig
# amc.rtout.setControlAQuadBOutClock
# amc.rtout.setControlAQuadBOutResolution
# amc.rtout.setMode
# amc.rtout.setSignalMode
# amc.rtout.setTriggerConfig
# amc.status.getFullCombinedStatus
# amc.status.getOlStatus
# amc.status.getStatusConnected
# amc.status.getStatusEot
# amc.status.getStatusEotBkwd
# amc.status.getStatusEotFwd
# amc.status.getStatusMoving
# amc.status.getStatusReference
# amc.status.getStatusTargetRange
# system.about.getInstalledPackages
# system.about.getPackageLicense
# system.apply
# system.errorNumberToRecommendation
# system.errorNumberToString
# system.factoryReset
# system.getDeviceName
# system.getFirmwareVersion
# system.getFluxCode
# system.getHostname
# system.getMacAddress
# system.getSerialNumber
# system.network.apply
# system.network.configureWifi
# system.network.discard
# system.network.getDefaultGateway
# system.network.getDnsResolver
# system.network.getEnableDhcpClient
# system.network.getEnableDhcpServer
# system.network.getIpAddress
# system.network.getProxyServer
# system.network.getRealIpAddress
# system.network.getSubnetMask
# system.network.getWifiMode
# system.network.getWifiPassphrase
# system.network.getWifiPresent
# system.network.getWifiSSID
# system.network.setDefaultGateway
# system.network.setDnsResolver
# system.network.setEnableDhcpClient
# system.network.setEnableDhcpServer
# system.network.setIpAddress
# system.network.setProxyServer
# system.network.setSubnetMask
# system.network.setWifiMode
# system.network.setWifiPassphrase
# system.network.setWifiSSID
# system.network.verify
# system.rebootSystem
# system.setDeviceName
# system.setTime
# system.softReset
# system.updateTimeFromInternet
# system.update.getLicenseUpdateProgress
# system.update.getSwUpdateProgress
# system.update.licenseUpdateBase64
# system.update.softwareUpdateBase64
# system.update.uploadLicenseBase64
# system.update.uploadSoftwareImageBase64

