# -*- coding: utf-8 -*-
########################## Copyrights and license ############################
#                                                                            #
# Copyright 2026       Christian Lupien <christian.lupien@usherbrooke.ca>    #
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

import struct

from weakref import proxy

from ..ctypes_helper import DLL_Wrapper, Buffer, General_POINTER, General_Conv,\
                            c_uint32, c_int32, c_double, c_float, c_long,\
                            c_uint32_p, c_float_p, c_void_p, IntEnumC, \
                            c_uint16, c_uint8, c_uint64, c_uint64_p, c_uint16_p, c_uint8_p

from .. import instruments_base
from ..instruments_base import visaInstrument, BaseInstrument,\
                                visa_wrap, locked_calling, resource_info,\
                                ProxyMethod, Base2Device


from ..instruments_registry import register_instrument, add_to_instruments
from ..dll_load_helper import delayed_libusb_import

from ..types import StructureImproved, dict_improved

from ..comp2to3 import string_bytes_types

# wether it is a write or a read of a register, the communication starts with a
# device write, followed by a device read
#
# information extracted from dll
# libusb_bulk_transfer are all 8 bytes long (on write to 0x81 and on read on endpoint 0x02)
# read on register 0x20 0x0b is signal phase
# read on register 0x26 is alc dac
# write on 0x47 data=0 (one byte): synth_self_cal
#
# For rs232 interface, the write are the required length only: 2, 3, 5 or 7.
#  The write and read are the same length
# For rs232 read, the device write length is only the required one: 2, 3, 4
#  The read is always 6 in length
# For usb on device read, only the first 6 byte are meaningful. They are the data.

# For PXI: 0x4a picks MCU syncs to the LO or from the PXI 10 MHz

#
#######################################################
##    Signal Core SC551B, libusb direct access
#######################################################

class SC_dev(Base2Device):
    def __init__(self, read_param, write_param=None, **kwargs):
        """
        read_param and write param are the parameters to ask and write in
        the form (register, dict())
        """
        super(SC_dev, self).__init__(**kwargs)
        self.read_param = read_param
        self._getdev_p = True
        if write_param is not None:
            self._setdev_p = True
        self.write_param = write_param
    def _set_write(self, val, options):
        register, kwargs_orig = self.write_param
        kwargs = kwargs_orig.copy()
        if 'data1' in kwargs:
            kwargs['data2'] = val
        else:
            kwargs['data1'] = val
        self.instr.write(register, **kwargs)
    def _get_ask(self, options):
        register, kwargs_orig = self.read_param
        kwargs = kwargs_orig.copy()
        bit_offset = kwargs.pop('bit_offset', None)
        bit_mask = kwargs.pop('bit_mask', 1)
        inv = kwargs.pop('inv', False)
        val = self.instr.ask(register, **kwargs)
        if bit_offset is not None:
            val >>= bit_offset
            val &= bit_mask
            if bit_mask == 1:
                val = bool(val)
                if inv:
                    val = not val
        return val


def bitw(val, bitn, val0=False, val1=True):
    if val not in [val0, val1]:
        raise ValueError('Invalid value. Use either %r or %r'%(val0, val1))
    if val == val1:
        return 1<<bitn
    return 0

def bitr(val, bitn, val0=False, val1=True):
    sel = (val>>bitn)&1
    if sel == 1:
        return val1
    return val0

@register_instrument('SignalCore', 'SC5511')
class signalcore_SC5511_libusb(BaseInstrument):
    """
    This controls the Signal Core SC5511 (A or B) rf generator using the libusb
    interface or visa rs232.
    Useful devices:
        freq1
        level_dBm
        out_en
        standby1_en
        freq2
        standby2_en
        temperature
    Useful methods:
        discover (static method)
        status
        conf_reference
        conf_synth_mode
        conf_sweep_list
        conf_sweep
        conf_list
    """
    def __init__(self, dev_num=0, visa_addr=None, timeout=1,  **kwargs):
        """
        dev_num can be a number, which selects that device discovered.
                It can also be a serial number string to select one.
                You can use the static method discover to list devices.
                This is for usb connected devices.
        visa_addr if given, will instead connect using the rs232 interface using
                 visa. The address should probably look like 'ASRL4'
        """
        global usb_core, usb_util
        self._visa = None
        self._dev_info_cache = None
        if visa_addr is not None:
            rsrc_info = resource_info(visa_addr)
            cnsts = visa_wrap.constants
            if rsrc_info.interface_type == cnsts.InterfaceType.asrl:
                baud_rate = kwargs.pop('baud_rate', 115200)
                kwargs2 = kwargs.copy()
                quiet_del = kwargs2.pop('quiet_delete', True)
                kwargs2['baud_rate'] = baud_rate
                kwargs2['parity'] = cnsts.Parity.none
                kwargs2['data_bits'] = 8
                kwargs2['stop_bits'] = cnsts.StopBits.one
                kwargs2['quiet_delete'] = quiet_del
            else:
                raise ValueError('Only accept serial interface visa addresses.')
            self._visa = visaInstrument(visa_addr, skip_id_test=True, **kwargs2)
            self._visa.set_timeout = timeout
        else:
            usb_core, usb_util = delayed_libusb_import()
            self._usb_timeout = timeout
            devs = self.discover(return_dev=True)
            if len(devs) == 0:
                raise RuntimeError('Did not find any signal core devices')
            try:
                dev = devs[dev_num][-1]
            except IndexError:
                dev_sel = [d for i, m, s, d in devs if s == dev_num]
                if len(dev_sel) != 1:
                    raise RuntimeError('Unable to find unique signal core device')
                dev = dev_sel[0]
            dev.set_configuration()
            # Note that cfg, intf, ep_in and ep_out keep a reference to dev
            cfg = dev.get_active_configuration()
            intf = cfg[(0,1)]
            ep_in = usb_util.find_descriptor(intf, bEndpointAddress=0x81)
            ep_out = usb_util.find_descriptor(intf, bEndpointAddress=0x02)
            intf.set_altsetting()
            self._usb_dev = dev
            self._usb_cfg = cfg
            self._usb_intf = intf
            self._ep_in = ep_in
            self._ep_out = ep_out
        self._system_active_led_en(True)
        super(signalcore_SC5511_libusb, self).__init__(**kwargs)


    @staticmethod
    def discover(return_dev=False):
        """
        returns a list of tuples containing (device_number, model_name, serial_number)
        The serial number might be 'no_serial' if the device is already opened.
        This only list usb connected devices.
        """
        global usb_core, usb_util
        usb_core, usb_util = delayed_libusb_import()
        # idProduct 0x0026 is for SC5511B Signal Source".
        # idProduct 0x001E is for SC5511A Signal Source".
        def find_helper(dev):
            return dev.idProduct in [0x001E, 0x0026]
        #devs = usb_core.find(idVendor=0x277C, idProduct=0x0026, find_all=True)
        devs = usb_core.find(idVendor=0x277C, custom_match=find_helper, find_all=True)
        def read_serial(dev):
            try:
                return dev.serial_number
            except:
                return "no_serial"
        models = {0x001E:"SC5511A", 0x0026:"SC5511B"}
        if return_dev:
            result = [(i, models[d.idProduct], read_serial(d), d) for i, d in enumerate(devs)]
        else:
            result = [(i, models[d.idProduct], read_serial(d)) for i, d in enumerate(devs)]
        return result

    def close(self):
        if hasattr(self, '_usb_dev'):
            self._system_active_led_en(False)
            usb_util.dispose_resources(self._usb_dev)
        elif self._visa is not None:
            self._system_active_led_en(False)
            del self._visa

    def __del__(self):
        self.close()
        # to free device so it can be opened somewhere else:
        # del self._usb_dev
        # this should call
        #   self._usb_dev._finalize_object()
        # which, through self._usb_dev._ctx.dispose()
        # should release all interfaces and close the device
        # The release internally looks like
        #   usb_util.release_interface(self._usb_dev, self._usb_intf)
        super(signalcore_SC5511_libusb, self).__del__()

    def idn(self):
        res = self.get_device_info()
        if self._visa:
            product = 'SC5511B'
            sn = res.sn
        else:
            dev = self._usb_dev
            sn = dev.serial_number
            product = dev.product
        version = 'hw:%r-fw:%r-date:%s'%(res.hw_rev, res.fw_rev, res.manuf_date)
        return "SignalCore,%s,%s,%s"%(product, sn, version)

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        base = self._conf_helper('freq1', 'level_dBm', 'out_en', 'standby1_en', 'freq2', 'standby2_en',
                                 'alc_auto_level_en', 'alc_close_loop_mode_en', 'temperature')
        opts = ['status=%s'%self.status(),
                'conf_regerence=%s'%self.conf_reference(),
                'conf_synth_mode=%s'%self.conf_synth_mode(),
                'conf_hardware_trigger=%s'%self.conf_hardware_trigger(),
                'conf_pulse=%s'%self.conf_pulse()]
        sl = self.conf_sweep_list()
        opts += ['conf_sweep_list=%s'%sl]
        if sl.sweep_mode_en:
            opts += ['conf_sweep=%s'%self.conf_sweep()]
        else:
            opts += ['conf_list=%s'%self.conf_list()]
        return base + opts + self._conf_helper(options)

    def _conv(self, data, t):
        if t in ['byte', 'bool', bool, 'ibool']:
            if t == 'ibool':
                data = not data
            return struct.pack('>B', data)
        elif t == 'ushort':
            return struct.pack('>H', data)
        elif t == 'uint':
            return struct.pack('>I', data)
        elif t == 'ulong':
            return struct.pack('>Q', data)[2:]
        elif t in ['freq', 'freq_list']:
            d_mHz = int(data*1e3)
            if t == 'freq_list':
                d_mHz &= 0x3fffffffffff
            d = struct.pack('>Q', d_mHz)[2:]
            return d
        elif t == 'freq2':
            d_MHz = round(data*4/100e6)*25
            d = struct.pack('>H', d_MHz)
            return d
        elif t in ['level', 'level_list', 'phase']:
            if t == 'phase':
                cdB = int(abs(data)*10)
            else:
                cdB = int(abs(data)*100)
            sign = 0x8000 if data<0 else 0
            cdB |= sign
            if t == 'level_list':
                cdB &= 0xffff
                cdB |= 0x2<<46
                d = struct.pack('>Q', cdB)[2:]
            else:
                d = struct.pack('>H', cdB)
            return d
        elif t in ['dwell', 'dwell_list']:
            dwell = int(data/0.5e-3)
            if t == 'dwell_list':
                dwell &= 0xffffffff
                dwell |= 0x01<<46
                d = struct.pack('>Q', dwell)[2:]
            else:
                d = struct.pack('>I', dwell)
            return d
        else:
            raise ValueError('unknown type: %r'%t)

    def _internal_cmd(self, register, data1=None, type1=None, data2=None, type2=None, read_length=1):
        data = bytearray(8)
        data[0] = register
        if type1 is not None:
            d = self._conv(data1, type1)
            n = len(d)
            data[1:1+n] = d
        else:
            n = 0
        if type2 is not None:
            d = self._conv(data2, type2)
            n2 = len(d)
            data[1+n:1+n+n2] = d
            N = 1+n+n2
        else:
            N = 1+n
        if self._visa is not None:
            if N == 1:
                N = 2
            self._visa.write(bytes(data[:N]), termination=None)
            res = self._visa.read(raw=True, count=read_length)
            return res + b'\0'*(8-len(res))
        else:
            timeout = int(self._usb_timeout*1000)
            w_res = self._ep_out.write(data, timeout)
            if w_res != 8:
                raise RuntimeError(self.perror('Write was not the correct length'))
            res = self._ep_in.read(8, timeout)
        return res

    def write(self, register, data1=None, type1=None, data2=None, type2=None, read_length=1):
        self._internal_cmd(register, data1, type1, data2, type2)

    def ask(self, register, res_type, data1=None, type1=None, data2=None, type2=None):
        read_length = 6
        res = self._internal_cmd(register, data1, type1, data2, type2, read_length)
        r = res[:6] # only the first 6 values are valid
        if res_type == 'bool':
            return bool(r[0])
        elif res_type == 'byte':
            return r[0]
        elif res_type == 'ushort':
            return struct.unpack('>H', r[:2])[0]
        elif res_type == 'uint':
            return struct.unpack('>I', r[:4])[0]
        elif res_type == 'ulong':
            d = bytearray(8)
            d[2:] = r
            return struct.unpack('>Q', d)[0]
        elif res_type == 'float':
            return struct.unpack('>f', r[:4])[0]
        elif res_type in ['freq', 'freq_list']:
            # in mHz
            z = struct.unpack('>HI', r)
            return float(z[0]*2**32+z[1])/1e3
        elif res_type == 'freq2':
            # in mHz
            z = struct.unpack('>H', r[:2])
            return float(z[0])*1e6
        elif res_type == 'level':
            z = struct.unpack('>f', r[:4])
            return z[0]
        elif res_type in ['level_list']:
            if res_type == 'level_list':
                scale = 100.
                d = r[4:]
            else:
                scale = 10.
                d = r[:2]
            z = struct.unpack('>H', d)
            sign = -1 if z[0]&0x8000 else 1
            # in 0.01 dB or 0.1 deg
            return float(z[0]&0x7fff)/scale*sign
        elif res_type in ['dwell', 'dwell_list']:
            if res_type == 'dwell':
                d = r[:4]
            else:
                d = r[2:]
            z = struct.unpack('>I', d)
            return float(z[0])*.5e-3
        elif res_type in ['temp', 'phase']:
            z = struct.unpack('>f', r[:4])
            return z[0]
        elif res_type == 'date':
            z = struct.unpack('>bbbb', r[:4])
            return '20%02d-%02d-%02d %02d:00'%z
        else:
            raise ValueError('unknown res_type: %r'%res_type)

    @property
    def set_timeout(self):
        if self._visa is not None:
            return self._visa.set_timeout
        else:
            return self._usb_timeout
    @set_timeout.setter
    def set_timeout(self, seconds):
        if self._visa is not None:
            self._visa.set_timeout = seconds
        else:
            self._usb_timeout = seconds

    def _system_active_led_en(self, enable):
        self.write(0x02, enable, 'byte')

    def get_device_info(self):
        if self._dev_info_cache is not None:
            return self._dev_info_cache
        sn ='%08X'%(self.ask(0x23, 'uint', 0, 'byte'))
        hw_rev = self.ask(0x23, 'float', 1, 'byte')
        fw_rev = self.ask(0x23, 'float', 2, 'byte')
        manuf_date = self.ask(0x23, 'date', 3, 'byte')
        if self._visa is None:
            sn2 = self._usb_dev.serial_number
        else:
            sn2 = sn
        d = locals()
        d.pop('self')
        d.pop('sn2')
        d = dict_improved(d)
        if sn != sn2:
            print('Serial Numbers are not matching (%s != %s)'%(sn, sn2))
        self._dev_info_cache = d
        return d

    def trig_software(self):
        self.write(0x0f)

    def perform_self_calibration(self):
        self.write(0x47)

    def reinitialize(self, power_up_state=False):
        self.write(0x01, data1=power_up_state, type1=bool)

    def store_default_state_eeprom(self):
        self.write(0x1b, data1=0, type1=bool)

    _spur_sup_sel = dict(val0=True, val1=False)
    def conf_synth_mode(self, fracN_en=None, low_loop_gain_en=None, spur_supression_en=None):
        """
        When called with not parameters, returns the current configuration.
        fracN_en when False means harmonic offset mode instead of fracN PLL offset
        low_loop_gain_en when False, means normal loop gain
        spur_supression_en when True it will activate FracN. Only applies when fracN_en is False.
        """
        lcls = locals().copy()
        lcls.pop('self')
        status = self.status()
        d = {'fracN_en': 'lock_mode_fracN_en',
             'low_loop_gain_en': 'loop_gain_low_en',
             'spur_supression_en': 'spur_suppresion_en'
             }
        conf = dict_improved([(k, status[v]) for k, v in d.items()])
        if all([v is None for v in lcls.values()]):
            return conf
        for k, v in lcls.items():
            if v is None:
                lcls[k] = conf[k]
        bw = lambda name, i, **kwargs: bitw(lcls[name], i, **kwargs)
        new_val = bw('fracN_en', 0) | \
                  bw('low_loop_gain_en', 1) | \
                  bw('spur_supression_en', 2, **self._spur_sup_sel)
        self.write(0x03, data1=new_val, type1='byte')

    _waveform_sel = dict(val0='sawtooth', val1='triangular')
    def conf_sweep_list(self, sweep_list_en=None, sweep_mode_en=None, reverse_en=None,
                        sweep_wf=None, return_start_en=None, cycle_count=None,
                        hardware_trig_en=None, step_on_trig_en=None,
                        trig_out_en=None, trig_out_on_completion_en=None):
        """
        When called with no parameters, returns the current configuration.
        sweep_list_en enables or disables both sweep or list which is selected
                   with the sweep_mode_en option.
        sweep_mode_en when False means the list mode is active
        sweep_wf is either 'sawtooth' or 'triangular'
        A cycle_count of 0 means cycle forever.
        step_on_trig_en can only be set to True for hardware_trig
                        when False, the trig starts or stops the sweep/list
        trig_out_on_completion_en when False, produces trig on every frequency change.
        """
        lcls = locals().copy()
        lcls.pop('self')
        status = self.status()
        d = {'sweep_list_en': 'sweep_list_mode_en',
             'sweep_mode_en': 'sweep_mode_en',
             'reverse_en': 'reverse_direction_en',
             'sweep_wf': 'sweep_waveform_sel',
             'hardware_trig_en': 'hardware_trig_en',
             'step_on_trig_en': 'step_on_trig_in_en',
             'return_start_en': 'list_return_to_start_en',
             'trig_out_en': 'trig_out_en',
             'trig_out_on_completion_en': 'trig_out_on_cycles_en'
             }
        dict_data = [(k, status[v]) for k, v in d.items()]
        conf = dict_improved([(k, status[v]) for k, v in d.items()])
        if all([v is None for v in lcls.values()]):
            cycle_count = self.cycle_count.get()
            dict_data.append(('cycle_count', cycle_count))
            return dict_improved(dict_data)
        lcls.pop('cycle_count')
        for k, v in lcls.items():
            if v is None:
                lcls[k] = conf[k]
        bw = lambda name, i, **kwargs: bitw(lcls[name], i, **kwargs)
        new_val = bw('sweep_mode_en', 0) | \
                  bw('reverse_en', 1) | \
                  bw('sweep_wf', 2, **self._waveform_sel) | \
                  bw('hardware_trig_en', 3) | \
                  bw('step_on_trig_en', 4) | \
                  bw('return_start_en', 5) | \
                  bw('trig_out_en', 6) | \
                  bw('trig_out_on_completion_en', 7)
        self.write(0x04, data1=lcls['sweep_list_en'], type1='bool')
        self.write(0x05, data1=new_val, type1='byte')
        if cycle_count is not None:
            self.cycle_count.set(cycle_count)

    def transfer_list(self, direction=None):
        """ Transfers the list either "to" or "from" the eeprom depending on the choise of direction.
            Only list_nbpoints values are transferred.
        """
        if direction not in ['to', 'from']:
            raise ValueError("You need to select the direction between 'to' or 'from'.")
        val = 0
        if direction == 'from':
            val = 1
        self.write(0x0e, data1=val, type1='byte')

    def conf_list(self, freqs=None, levels=None, dwells=None):
        """When called with not parameters, returns the current configuration.
           All freqs, levels and dwells need to be of the same length.
        """
        lcls = locals().copy()
        lcls.pop('self')
        if all([v is None for v in lcls.values()]):
            n = self.list_nbpoints.get()
            freqs = []
            levels = []
            dwells = []
            for i in range(n):
                freqs.append(self.ask(0x24, 'freq_list', data1=i, type1='ushort'))
                levels.append(self.ask(0x24, 'level_list', data1=i | (2<<14), type1='ushort'))
                dwells.append(self.ask(0x24, 'dwell_list', data1=i | (1<<14), type1='ushort'))
            return dict_improved(freqs=freqs, levels=levels, dwells=dwells)
        lists = [freqs, levels, dwells]
        vals_not_None = list([v is not None for v in lists])
        if any(vals_not_None):
            if not all(vals_not_None):
                raise ValueError('You need to provide all freqs, levels and dwells at the same time')
            if not (len(freqs) == len(levels) == len(dwells)):
                raise ValueError('The length of freqs, levels and dwells need to be the same.')
            if len(freqs) > 2048:
                raise ValueError('There is a maximum length of 2048 for the lists.')
            self.write(0x0d, data1=0, type1='ulong')
            for f, l, d in zip(freqs, levels, dwells):
                self.write(0x0d, data1=f, type1='freq_list')
                self.write(0x0d, data1=l, type1='level_list')
                self.write(0x0d, data1=d, type1='dwell_list')
            self.write(0x0d, data1=0xffffffffffff, type1='ulong')

    def conf_sweep(self, start=None, stop=None, step=None, dwell=None):
        """When called with not parameters, returns the current configuration.
        """
        lcls = locals().copy()
        lcls.pop('self')
        data_list = [('start', self.sweep_freq_start),
                ('stop', self.sweep_freq_stop),
                ('step', self.sweep_freq_step),
                ('dwell', self.sweep_dwell)]
        data_dict = dict(data_list)
        data = dict_improved([(k, v.get()) for k, v in data_list])
        if all([v is None for v in lcls.values()]):
            return data
        for k, v in lcls.items():
            if v is not None:
                data_dict[k].set(v)

    _ref_freq_sel = dict(val0='10MHz', val1='100MHz')
    def conf_reference(self, lock_external_en=None, ref_out_freq_sel=None,
                       front_pxi_10MHz_en=None, direct_clocking_en=None, ref_in_freq_sel=None):
        """
        ref_out_freq_sel can be '10MHz' or '100MHz'
        ref_in_freq_sel can be '10MHz' or '100MHz'
        front_pxi_10MHz_en only for pxi hardware.
        direct_clocking_en and ref_in_freq_sel only for firmware>=3.0
        """
        lcls = locals().copy()
        lcls.pop('self')
        status = self.status()
        d = {'lock_external_en': 'extref_in_lock_en',
             'ref_out_freq_sel': 'ref_out_freq_sel',
             'front_pxi_10MHz_en': 'pxi10_front_export_en',
             'direct_clocking_en': 'extref_in_100MHz_direct_en',
             'ref_in_freq_sel': 'extref_in_freq_sel',
             }
        conf = dict_improved([(k, status[v]) for k, v in d.items()])
        if all([v is None for v in lcls.values()]):
            return conf
        for k, v in lcls.items():
            if v is None:
                lcls[k] = conf[k]
        bw = lambda name, i, **kwargs: bitw(lcls[name], i, **kwargs)
        new_val = bw('lock_external_en', 0) | \
                  bw('ref_out_freq_sel', 1, **self._ref_freq_sel) | \
                  bw('front_pxi_10MHz_en', 2) | \
                  bw('direct_clocking_en', 3) | \
                  bw('ref_in_freq_sel', 4, **self._ref_freq_sel)
        self.write(0x17, data1=new_val, type1='byte')

    def conf_pulse(self, pulse_en=None, pulse_trig_src=None):
        """
        pulse_trig_src can be "front" or "pxi" and is only for SC5510B models.
         "pxi" means to use the pxi trigger line configured with conf_hardware_trigger.
        """
        lcls = locals().copy()
        lcls.pop('self')
        #status = self.status()
        pulse = self.ask(0x20, 'byte', data1=10, type1='byte')
        br = lambda i, **kwarg: bitr(pulse, i, **kwarg)
        trig_src = dict(val0='front', val1='pxi')
        status = dict_improved([('pulse_en', br(0)), ('pulse_trig_src', br(1, **trig_src))])
        if all([v is None for v in lcls.values()]):
            return status
        # Change one of the parameters
        for k, v in lcls.items():
            if v is None:
                lcls[k] = status[k]
        bw = lambda name, i, **kwargs: bitw(lcls[name], i, **kwargs)
        new_val = bw('pulse_en', 0) | bw('pulse_trig_src', 1, **trig_src)
        self.write(0x1c, data1=new_val, type1='byte')

    def conf_hardware_trigger(self, edge=None, pxi_en=None, trigger_line=None):
        """
        Only valid for pxi hardware.
        edge can be 'fall', 'rise'
        trigger_lines can be 0-7.
        """
        lcls = locals().copy()
        lcls.pop('self')
        conf_edge = self.ask(0x20, 'byte', data1=9, type1='byte')
        edge_type= dict(val0='fall', val1='rise')
        br = lambda i, **kwarg: bitr(conf_edge, i, **kwarg)
        status = dict_improved([('edge', br(0, **edge_type)), ('pxi_en', br(1)), ('trigger_line', (conf_edge>>2)&0x7)])
        if all([v is None for v in lcls.values()]):
            return status
        # Change one of the parameters
        for k, v in lcls.items():
            if v is None:
                lcls[k] = status[k]
        bw = lambda name, i, **kwargs: bitw(lcls[name], i, **kwargs)
        new_val = bw('edge', 0, **edge_type) | bw('pxi_en', 1) | ((lcls['trigger_line']&0x7)<<2)
        self.write(0x0b, data1=new_val, type1='byte')


    def status(self):
        s1 = self.status1_raw.get()
        if hasattr(self, 'status2_raw'):
            s2 = self.status2_raw.get()
            old_fw = False
        else:
            s2 = 0
            old_fw = True
        #print(hex(s2))
        b = lambda n, s=s1, **kwarg: bitr(s, n, **kwarg)
        d = [('trig_out_on_cycles_en', b(47)),
            ('trig_out_en', b(46)),
            ('list_return_to_start_en', b(45)),
            ('step_on_trig_in_en', b(44)),
            ('hardware_trig_en', b(43)),
            ('sweep_waveform_sel', b(42, **self._waveform_sel)),
            ('reverse_direction_en', b(41)),
            ('sweep_mode_en', b(40)),
            ('spur_suppresion_en', b(38, **self._spur_sup_sel)),
            ('over_temp_error', b(37)),
            ('sweep_list_mode_en', b(36)),
            ('sweep_list_running', b(35)),
            ('ref_out_freq_sel', b(34, **self._ref_freq_sel)),
            ('ref_out_freq_sel2', b(9-8, s2, **self._ref_freq_sel)),
            ('extref_in_detected', b(33)),
            ('extref_in_lock_en', b(32)),
            ('extref_in_lock_en2', b(8-8, s2)),
            ('extref_in_freq_sel', b(12-8, s2, **self._ref_freq_sel)),
            ('extref_in_100MHz_direct_en', b(11-8, s2)),
            ('pxi10_front_export_en', b(10-8, s2)),
            ('rf1_out_en', b(31)),
            ('alc_disabled', b(30)),
            ('auto_level_disabled', b(29)),
            ('rf1_standby_en', b(28)),
            ('rf2_standby_en', b(27)),
            ('system_active_led_en', b(26)),
            ('loop_gain_low_en', b(25)),
            ('lock_mode_fracN_en', b(24)),
            ('pll_rf2_locked', b(23)),
            ('pll_TCXO_10MHz_locked', b(22)),
            ('pll_VCXO_100MHz_locked', b(21)),
            ('pll_crs_aux_locked', b(20)),
            ('pll_crs_ref_locked', b(19)),
            ('pll_dds_fine_locked', b(18)),
            ('pll_crs_locked', b(17)),
            ('pll_main_locked', b(16))]
        if old_fw:
            d = [(k,v) for k, v in d if k not in ['ref_out_freq_sel2',
                                              'extref_in_lock_en2']]
                                              #'extref_in_freq_sel',
                                              #'extref_in_100MHz_direct_en',
                                              #'pxi10_front_export_en']]
        return dict_improved(d)

    def _create_devs(self):
        fw_rev = self.get_device_info().fw_rev
        old_fw = False
        if fw_rev < 2:
            old_fw = True
            # raise RuntimeError('Only firmware >=3 work with this driver')
        minF = 100e6
        maxF = 20e9
        minP = -40
        maxP = 30
        self.freq1 = SC_dev((0x20, dict(data1=0, type1='byte', res_type='freq')),
                            (0x10, dict(type1='freq')), setget=True, min=minF, max=maxF)
        self.freq2 = SC_dev((0x20, dict(data1=8, type1='byte', res_type='freq2')),
                            (0x1f, dict(type1='freq2')), setget=True, min=25e6, max=3e9,
                            doc="Garanteed frequency resolution is 25 MHz. At 200 MHz it is ~3 MHz, at 1GHz it is 13 MHz.")
        self.level_dBm = SC_dev((0x20, dict(data1=7, type1='byte', res_type='level')),
                                 (0x11, dict(type1='level')), min=minP, max=maxP, setget=True)
        self.phase_deg = SC_dev((0x20, dict(data1=11, type1='byte', res_type='phase')),
                                 (0x13, dict(type1='phase')), setget=True)
        self.temperature = SC_dev((0x21, dict(res_type='temp')))
        self.sweep_freq_start = SC_dev((0x20, dict(data1=1, type1='byte', res_type='freq')),
                                       (0x06, dict(type1='freq')), setget=True)
        self.sweep_freq_stop = SC_dev((0x20, dict(data1=2, type1='byte', res_type='freq')),
                                       (0x07, dict(type1='freq')), setget=True)
        self.sweep_freq_step = SC_dev((0x20, dict(data1=3, type1='byte', res_type='freq')),
                                       (0x08, dict(type1='freq')), setget=True)
        self.sweep_dwell = SC_dev((0x20, dict(data1=4, type1='byte', res_type='dwell')),
                                       (0x09, dict(type1='dwell')), setget=True)
        self.cycle_count = SC_dev((0x20, dict(data1=5, type1='byte', res_type='uint')),
                                       (0x0a, dict(type1='uint')), setget=True, min=0, max=2**32-1,
                                       doc="A cycle_count of 0 means cycle forever.")
        self.list_nbpoints = SC_dev((0x20, dict(data1=6, type1='byte', res_type='uint')),
                                       (0x0c, dict(type1='uint')), setget=True, min=0, max=2048)
        self.status1_raw = SC_dev((0x22, dict(res_type='ulong')))
        if not old_fw:
            self.status2_raw = SC_dev((0x22, dict(data1=1, type1='byte', res_type='uint')))

        self.out_en = SC_dev((0x22, dict(res_type='ulong', bit_offset=31)),
                                       (0x12, dict(type1='bool')))
        self.standby1_en = SC_dev((0x22, dict(res_type='ulong', bit_offset=28)),
                                       (0x16, dict(type1='bool')))
        self.standby2_en = SC_dev((0x22, dict(res_type='ulong', bit_offset=27)),
                                       (0x1e, dict(type1='bool')))

        self.system_active_led_en = SC_dev((0x22, dict(res_type='ulong', bit_offset=26)),
                                       (0x02, dict(type1='bool')))
        # TODO: There is not read of the reference_dac
        # self.reference_dac_val = SC_dev((0x25, dict(res_type='ushort')),
        #                                (0x18, dict(type1='ushort')), min=0, max=2**14-1)
        self.alc_dac_val = SC_dev((0x25, dict(res_type='ushort')),
                                       (0x19, dict(type1='ushort')), min=0, max=2**14-1, setget=True)
        self.alc_auto_level_en = SC_dev((0x22, dict(res_type='ulong', bit_offset=29, inv=True)),
                                       (0x14, dict(type1='ibool')))
        self.alc_close_loop_mode_en = SC_dev((0x22, dict(res_type='ulong', bit_offset=30, inv=True)),
                                       (0x15, dict(type1='ibool')))

        # This needs to be last to complete creation
        super(signalcore_SC5511_libusb, self)._create_devs()


#######################################################
##    Signal Core SC551B, dll access
#######################################################

class SC_Result(IntEnumC):
#    __force_check__ = False
    Success = 0
    Error_Invalid_Device_Handle = -1
    Error_No_Device = -2
    Error_Invalid_Device = -3
    Error_Mem_Unalocated = -4
    Error_Mem_Exceeded = -5
    Error_Invalid_Reg = -6
    Error_Invalid_Argument = -7
    Error_Comm_Fail = -8
    Error_Out_of_Range = -9
    Error_PLL_Lock = -10
    Error_Timed_Out = -11
    Error_Comm_Init = -12
    Error_Timed_Out_Read = -13
    Error_Invalid_Interface = -14

SC_DLL_Default_Path = r'C:\Program Files\SignalCore\SC5510B_11B\api\c\x64'

_SCI_HANDLE = c_void_p
_SCI_HANDLE_p = General_POINTER(_SCI_HANDLE)
SCISTATUS = c_long

class SC_waveformtype(IntEnumC):
    __ctype__ = c_uint8
    sawtooth = 0
    triangular = 1
SC_ref_freq = General_Conv(c_uint8, SC_waveformtype)

class SC_baudrate(IntEnumC):
    __ctype__ = c_uint8
    rate_57600 = 0
    rate_115200 = 1

class SC_clk_src(IntEnumC):
    __ctype__ = c_uint8
    rf_base_clock = 0
    pxi_10MHz = 1

class SC_pxi_pulse_src(IntEnumC):
    __ctype__ = c_uint8
    front_MCX = 0
    pxi_backplane = 1


class SC_date(StructureImproved):
    _fields_ = [('year', c_uint8),
                ('month', c_uint8),
                ('day', c_uint8),
                ('hour', c_uint8)]

class SC_device_info(StructureImproved):
    _fields_ = [('product_serial_number', c_uint32),
                ('hardware_revision', c_float),
                ('firmware_revision', c_float),
                ('man_date', SC_date)]

class SC_list_mode(StructureImproved):
    _fields_ = [('sss_mode', c_uint8),
                ('sweep_dir', c_uint8),
               # ('tri_waveform', c_uint8),
                ('waveform', SC_waveformtype.ctype),
                ('hw_trigger', c_uint8),
                ('step_on_hw_trig', c_uint8),
                ('return_to_start', c_uint8),
                ('trig_out_enable', c_uint8),
                ('trig_out_on_cycle', c_uint8)]

class SC_pll_status(StructureImproved):
    _fields_ = [('sum_pll_ld', c_uint8),
                ('crs_pll_ld', c_uint8),
                ('fine_pll_ld', c_uint8),
                ('crs_ref_pll_ld', c_uint8),
                ('crs_aux_pll_ld', c_uint8),
                ('ref_100_pll_ld', c_uint8),
                ('ref_10_pll_ld', c_uint8),
                ('rf2_pll_ld', c_uint8)]

class SC_operate_status(StructureImproved):
    _fields_ = [('rf1_lock_mode', c_uint8),
                ('rf1_loop_gain', c_uint8),
                ('device_access', c_uint8),
                ('rf2_standby', c_uint8),
                ('rf1_standby', c_uint8),
                ('auto_pwr_disable', c_uint8),
                ('alc_mode', c_uint8),
                ('rf1_out_enable', c_uint8),
                ('ext_ref_lock_enable', c_uint8),
                ('ext_ref_detect', c_uint8),
                ('ref_out_select', c_uint8),
                ('list_mode_running', c_uint8),
                ('rf1_mode', c_uint8),
                ('over_temp', c_uint8),
                ('harmonic_ss', c_uint8)]

class SC_operate_status_pxi(StructureImproved):
    _fields_ = [('rf1_lock_mode', c_uint8),
                ('rf1_loop_gain', c_uint8),
                ('device_access', c_uint8),
                ('rf2_standby', c_uint8),
                ('rf1_standby', c_uint8),
                ('auto_pwr_disable', c_uint8),
                ('alc_mode', c_uint8),
                ('rf1_out_enable', c_uint8),
                ('ext_ref_lock_enable', c_uint8),
                ('ext_ref_detect', c_uint8),
                ('ref_out_select', c_uint8),
                ('list_mode_running', c_uint8),
                ('rf1_mode', c_uint8),
                ('over_temp', c_uint8),
                ('pxi_clk_enable', c_uint8),
                ('harmonic_ss', c_uint8)]

class SC_device_status(StructureImproved):
    _fields_ = [('list_mode', SC_list_mode),
                ('operate_status', SC_operate_status),
                ('pll_status', SC_pll_status)]

class SC_device_status_pxi(StructureImproved):
    _fields_ = [('list_mode', SC_list_mode),
                ('operate_status', SC_operate_status_pxi),
                ('pll_status', SC_pll_status)]

class SC_trigger(StructureImproved):
    _fields_ = [('edge', c_uint8),
                ('enable', c_uint8),
                ('line', c_uint8)]

class SC_rf_params(StructureImproved):
#    _pack_ = 4
    _fields_ = [('rf1_freq', c_double),
                ('start_freq', c_double),
                ('stop_freq', c_double),
                ('step_freq', c_double),
                ('sweep_dwell_time', c_uint32),
                ('sweep_cycles', c_uint32),
                ('buffer_points', c_uint32),
                ('rf_level', c_float),
                ('rf2_freq', c_uint16)]

class SC_clock_config(StructureImproved):
    _fields_ = [('ext_ref_lock_enable', c_uint8),
                ('ref_out_select', c_uint8),
                ('ext_direct_clocking', c_uint8),
                ('ext_ref_freq', c_uint8)]

class SC_clock_config_pxi(StructureImproved):
    _fields_ = [('ext_ref_lock_enable', c_uint8),
                ('ref_out_select', c_uint8),
                ('pxi_clock_enable', c_uint8),
                ('ext_direct_clocking', c_uint8),
                ('ext_ref_freq', c_uint8)]

class SC_pxi_trigger(StructureImproved):
    _fields_ = [('edge', c_uint8),
                ('enable', c_uint8),
                ('line', c_uint8)]


SC_rf_params_p = General_POINTER(SC_rf_params)
SC_list_mode_p = General_POINTER(SC_list_mode)
SC_device_info_p = General_POINTER(SC_device_info)
SC_device_status_p = General_POINTER(SC_device_status)
SC_device_status_pxi_p = General_POINTER(SC_device_status_pxi)
SC_clock_config_p = General_POINTER(SC_clock_config)
SC_clock_config_pxi_p = General_POINTER(SC_clock_config_pxi)
SC_pxi_trigger_p = General_POINTER(SC_pxi_trigger)


SC_MAX_list_N = 2048
#SC_list_freqs = Buffer(size=SC_MAX_list_N, base_type=c_double, allow_any_size=True, use_ndarray=True)
SC_list_freqs = Buffer(size=SC_MAX_list_N, base_type=c_double, use_ndarray=True)
SC_list_level_dwell = Buffer(size=SC_MAX_list_N, base_type=c_float, use_ndarray=True)

SC_bool = General_Conv(c_int32, bool, force_check=True)
SC_bool_p = General_POINTER(SC_bool)

SC_MAX_SERIAL_BUFFER_LEN = 8
SC_MAX_DEVICES = 128
SC_MAX_PORT_NAME_LEN = 16
SC_MAX_VISA_LEN = 128
SC_serial_num = Buffer(size=SC_MAX_SERIAL_BUFFER_LEN, allow_any_size=True)
SC_serial_list = Buffer(size=SC_MAX_DEVICES, base_type=SC_serial_num)
SC_port_name = Buffer(size=SC_MAX_PORT_NAME_LEN, allow_any_size=True)
SC_port_list = Buffer(size=SC_MAX_DEVICES, base_type=SC_port_name)
SC_visa_name = Buffer(size=SC_MAX_VISA_LEN, allow_any_size=True)
SC_visa_list = Buffer(size=SC_MAX_DEVICES, base_type=SC_port_name)

# sc5510b_get_pulse_mode not in _visa header but is in the dll.
# comparing usb/rs232: rs232 list_buffer_read does not have the dwell_time param in the header but looks the same in the dll.
#                      rs232 list_buffer_write using int instead of int32 for length (but they are both the same in windows 64 bit)
#                      and rs232 uses open_device(char *dev_serial_num, uint8_t baudrate, SCI_PHANDLE dev_handle)
#                      with baudrate: 0 = 57600 1 = 115200
# pxi vs usb: they have different SC_device_status and SC_clock_config
#            pxi sc5510b_set_clock_reference has extra param uint8_t pxi_clk_enable after ext_direct_clk
#            pxi has extra c5510b_set_pxi_trigger(SCI_HANDLE dev_handle, const pxi_trigger_t *pxi_trigger);
#               instead of usb set_trigger_edge
#            pxi has different set_pulse_mode(SCI_HANDLE dev_handle,u int8_t pxi_pulse_src,	uint8_t mode) extra pxi_pulse_src
#                where pxi_pulse_source: 0 = pulse control via front panel MCX connector, 1 = pulse control from PXI back plane trigger (frequency list mode control disabled
#            pxi has different c5510b_get_pulse_mode(SCI_HANDLE dev_handle,	uint8_t* pxi_pulse_src, uint8_t* mode);
#            pxi has extra sc5510b_set_mcu_clk(SCI_HANDLE dev_handle, uint8_t clk_src)
#               write to 0x4a clk_src has bool
#            pxi has extra sc5510b_get_mcu_clk(SCI_HANDLE dev_handle, uint8_t* clk_src)
#               from 0x20, 0xa bit 2
#              where 0=> RF base clock, 1 => pxi 10 MHz.
#            the usb get_trigger_edge(SCI_HANDLE dev_handle, uint8_t *edge) is replaced by the
#            pxi sc5510b_get_pxi_trigger(SCI_HANDLE dev_handle, pxi_trigger_t *pxi_trigger)
#

class SC_Error(Exception):
    def __init__(self, desc, error_code):
        super(SC_Error, self).__init__(desc)
        self.error_code = error_code

class SC_Lib_dll(DLL_Wrapper):
    def __init__(self, dll_name='sc5511b_usb', extra_paths=SC_DLL_Default_Path, **kwargs):
        """
        Possible dll_name: 'sc5511b_usb'   not pxi, with usb connection
                           'sc5511b_rs232' not pxi, with rs232 connection
                           'sc5510b'       pxi using Signal_Core driver
                           'sc5510b_visa'  pxi using visa driver
        """
        # There is a sc5510b_visa_cq version but it is older and lacks some function.
        #  cq probably stands for the company name ColdQuanta which is now named Infleqtion
        self._dll_name = dll_name
        self._is_usb = False
        self._is_rs232 = False
        self._is_pxi = True
        self._is_visa = False
        if 'usb' in dll_name:
            self._is_usb = True
            self._is_pxi = False
        if 'rs232' in dll_name:
            self._is_rs232 = True
            self._is_pxi = False
        if 'visa' in dll_name:
            self._is_visa = True
        super(SC_Lib_dll, self).__init__(dll_name, extra_paths=extra_paths, **kwargs)

    def _errcheck(self, result, func, args):
        if result != 0:
            if -14 <= result < 0:
                raise SC_Error('SC_Lib Error: %r'%(SC_Result(result)), result)
            else:
                raise SC_Error('SC_Lib Error: Unexpected return value (%i)'%result, result)
        return result

    def _create_funcs(self):
        errcheck = ProxyMethod(self._errcheck)
        name_prefix = 'sc5510b_'
        if self._is_usb:
            name_prefix = 'sc5511b_usb_'
        elif self._is_rs232:
            name_prefix = 'sc5511b_rs232_'
        create_helper = lambda name, *args, **kwargs:\
            self._create_helper(name, *args, errcheck=errcheck, restype=SC_Result.ctype, name_prefix=name_prefix, **kwargs)
#            self._create_helper(name, *args, errcheck=errcheck, restype=SCISTATUS, name_prefix='sc5511b_usb_', **kwargs)
        create_helper_dev = lambda name, argdefs=[], **kwargs: create_helper(name, [('device', _SCI_HANDLE)]+argdefs, **kwargs)
        if self._is_rs232:
            create_helper('search_devices', [('port_list_', SC_port_list), ('_port_list_N_', c_uint32_p)])
            create_helper('open_device', [('serial_num', SC_port_name), ('baudrate', SC_baudrate.ctype), ('dev_', _SCI_HANDLE_p)])
        elif self._is_visa:
            #create_helper('search_devices', [('visa_list_', SC_visa_list), ('visa_list_N_', c_uint32_p)], othername='_search_devices', return_res=True)
            #create_helper('search_devices', [('visa_list_', SC_visa_list), ('_visa_list_N_', c_uint32_p)], othername='_search_devices')
            #self.search_devices = self._search_devices_visa_bad
            self.search_devices = self._search_devices_visa_good
            create_helper('open_device', [('visa_name', SC_visa_name), ('dev_', _SCI_HANDLE_p)])
        else:
            #search_devices(char **serial_number_list, uint32_t *dev_count)
            #create_helper('search_devices', [('serial_number_list_', SC_serial_list), ('dev_count_', c_uint32_p)])
            create_helper('search_devices', [('serial_number_list_', SC_serial_list), ('_serial_number_list_N_', c_uint32_p)])
            create_helper('open_device', [('serial_num', SC_serial_num), ('dev_', _SCI_HANDLE_p)])
        create_helper('close_device', [('dev', _SCI_HANDLE)])

        create_helper_dev('reg_write', [('reg_byte', c_uint8), ('instruct_word', c_uint64)])
        create_helper_dev('reg_read', [('reg_byte', c_uint8), ('instruct_word', c_uint64), ('received_word_', c_uint64_p)])

        create_helper_dev('set_freq', [('freq', c_double)])
        create_helper_dev('set_signal_phase', [('phase', c_float)])
        create_helper_dev('set_synth_mode', [('disable_spur_suppress', c_uint8), ('low_loop_gain', c_uint8), ('lock_mode', c_uint8)])
        create_helper_dev('set_rf_mode', [('rf_mode', c_uint8)])
        create_helper_dev('list_mode_config', [('list_mode', SC_list_mode_p)])
        create_helper_dev('list_start_freq', [('freq', c_double)])
        create_helper_dev('list_stop_freq', [('freq', c_double)])
        create_helper_dev('list_step_freq', [('freq', c_double)])
        create_helper_dev('list_dwell_time', [('dwell_time', c_uint32)])
        create_helper_dev('list_cycle_count', [('cycle_count', c_uint32)])
        create_helper_dev('list_buffer_points', [('list_points', c_uint32)])
        create_helper_dev('list_buffer_write', [('freq', SC_list_freqs), ('level', SC_list_level_dwell), ('dwell', SC_list_level_dwell), ('len', c_int32)],
                          othername='_list_buffer_write')
        create_helper_dev('list_buffer_transfer', [('transfer_mode', c_uint8)])
        create_helper_dev('list_soft_trigger')
        create_helper_dev('set_level', [('power_level', c_float)])
        create_helper_dev('set_output', [('enable', c_uint8)])
        create_helper_dev('set_auto_level_disable', [('disable', c_uint8)])
        create_helper_dev('set_alc_mode', [('mode', c_uint8)])
        create_helper_dev('set_standby', [('enable', c_uint8)])
        if self._is_pxi:
            create_helper_dev('set_clock_reference', [('ext_ref_freq', c_uint8), ('ext_direct_clk', c_uint8),
                                                      ('pxi_clk_enable', c_uint8),
                                                      ('select_high', c_uint8),  ('lock_external', c_uint8)])
            create_helper_dev('get_device_status', [('device_status_', SC_device_status_pxi_p)])
            create_helper_dev('get_clock_config', [('clock_config_', SC_clock_config_pxi_p)])
            create_helper_dev('set_pxi_trigger', [('pxi_trigger', SC_pxi_trigger_p)])
            create_helper_dev('get_pxi_trigger', [('pxi_trigger_', SC_pxi_trigger_p)])
            create_helper_dev('set_pulse_mode', [('pxi_pulse_src', SC_pxi_pulse_src.ctype), ('mode', c_uint8)])
            create_helper_dev('get_pulse_mode', [('pxi_pulse_src_', SC_pxi_pulse_src.pointer), ('mode_', c_uint8_p)])
            create_helper_dev('set_mcu_clk', [('clk_src', SC_clk_src.ctype)])
            create_helper_dev('get_mcu_clk', [('clk_src_', SC_clk_src.pointer)])
        else:
            create_helper_dev('set_clock_reference', [('ext_ref_freq', c_uint8), ('ext_direct_clk', c_uint8),
                                                      ('select_high', c_uint8),  ('lock_external', c_uint8)])
            create_helper_dev('get_device_status', [('device_status_', SC_device_status_p)])
            create_helper_dev('get_clock_config', [('clock_config_', SC_clock_config_p)])
            create_helper_dev('set_trigger_edge', [('edge', c_uint8)])
            create_helper_dev('get_trigger_edge', [('edge_', c_uint8_p)])
            # Documentation mentions pulse_mode but only set_pulse_mode exists.
            #create_helper_dev('pulse_mode', [('mode', c_uint8)])
            create_helper_dev('set_pulse_mode', [('mode', c_uint8)])
            create_helper_dev('get_pulse_mode', [('mode_', c_uint8_p)])
        create_helper_dev('set_reference_dac', [('dac_value', c_uint16)])
        create_helper_dev('set_alc_dac', [('dac_value', c_uint16)])
        create_helper_dev('store_default_state')
        create_helper_dev('set_rf2_standby', [('enable', c_uint8)])
        create_helper_dev('set_rf2_freq', [('freq', c_uint16)])
        create_helper_dev('synth_self_cal')
        create_helper_dev('get_rf_parameters', [('params_', SC_rf_params_p)])
        create_helper_dev('get_temperature', [('temp_', c_float_p)])
        create_helper_dev('get_device_info', [('device_info_', SC_device_info_p)])
        create_helper_dev('list_buffer_read', [('len', c_int32), ('freq_', SC_list_freqs), ('level_', SC_list_level_dwell), ('dwell_', SC_list_level_dwell)],
                        othername='_list_buffer_read')
        # Just a test of using the return value.
        #create_helper_dev('list_buffer_read', [('len', c_int32), ('freq_', SC_list_freqs), ('level_', SC_list_level_dwell), ('dwell_', SC_list_level_dwell)], return_res='test')
        create_helper_dev('get_alc_dac', [('dac_value_', c_uint16_p)])
        create_helper_dev('get_signal_phase', [('phase_', c_float_p)])

    def list_buffer_write(self, dev, freq, level, dwell):
        if len(freq) != len(level) or len(freq) != len(dwell):
            raise ValueError("The lengths of freq, level and dwell needs to be the same")
        self._list_buffer_write(dev, freq, level, dwell, len(freq))

    def list_buffer_read(self, dev, n):
        if n<0 or n>SC_MAX_list_N:
            raise ValueError("n is too large. Should be smaller than %d"%SC_MAX_list_N)
        freq, level, dwell = self._list_buffer_read(dev, n)
        return freq[:n], level[:n], dwell[:n]

    def _search_devices_visa_bad(self):
        # The SC visa search function has errors.
        # When no entry are available it can return a random count
        # It can even access invalid memory.
        try:
            ret = self._search_devices()
        except SC_Error as exc:
            if exc.error_code == visa_wrap.constants.VI_ERROR_RSRC_NFOUND:
                return []
            raise
        return ret

    def _search_devices_visa_good(self):
        rsrc_mngr = instruments_base.rsrc_mngr
        if rsrc_mngr is None:
            raise RuntimeError('No visa library loaded.')
        return rsrc_mngr.list_resources('PXI?*{VI_ATTR_MANF_ID == 0x1BEB && VI_ATTR_MODEL_CODE == 0x0021}')

class SC_dev_dll(Base2Device):
    def __init__(self, read_func, write_func=None, read_name=None, scale=None,
                 force_type=None, read_access_func=None, write_access_func=None,
                 **kwargs):
        super(SC_dev_dll, self).__init__(**kwargs)
        self.read_func = read_func
        if read_access_func is None:
            if read_name is not None:
                if scale is None:
                    read_access_func = lambda v: getattr(v, read_name)
                else:
                    read_access_func = lambda v: getattr(v, read_name) * scale
            elif scale is not None:
                read_access_func = lambda v: v * scale
        if write_access_func is None:
            if force_type is not None:
                if scale is not None:
                    write_access_func = lambda v: force_type(v / scale)
                else:
                    write_access_func = lambda v: force_type(v)
            elif scale is not None:
                write_access_func = lambda v: v / scale
        self.read_access_func = read_access_func
        self.write_access_func = write_access_func
        self._getdev_p = True
        if write_func is not None:
            self._setdev_p = True
        self.write_func = write_func
    def _set_write(self, val, options):
        if self.write_access_func is not None:
            val = self.write_access_func(val)
        self.write_func(val)
    def _get_ask(self, options):
        val = self.read_func()
        if self.read_access_func is not None:
            val = self.read_access_func(val)
        return val

_dll_load_cache = {}
def _load_SC_dll(dll_name='sc5511b_usb', extra_paths=SC_DLL_Default_Path, **kwargs):
    if dll_name in _dll_load_cache:
        return _dll_load_cache[dll_name]
    dll = SC_Lib_dll(dll_name,  extra_paths=extra_paths, **kwargs)
    _dll_load_cache[dll_name] = dll
    return dll

class Dll_Wrap_Dev(object):
    def __init__(self, parent):
        self._parent = proxy(parent)
    def __getattr__(self, name):
        return lambda *args, **kwargs: getattr(self._parent._dll, name)(self._parent._dev, *args, **kwargs)

@add_to_instruments
#@register_instrument('SignalCore', 'SC5511')
class signalcore_SC5511_dll(BaseInstrument):
    """
    This controls the Signal Core SC551xB rf generator using the provided dll
    for usb, rs232 and pxi interfaces.
    Useful devices:
        freq1
        level_dBm
        out_en
        standby1_en
        freq2
        standby2_en
        temperature
    Useful methods:
        discover (static method)
        status
        conf_reference
        conf_synth_mode
        conf_sweep_list
        conf_sweep
        conf_list
    """
    _allowed_type = ['sc5511b_usb', 'sc5511b_rs232', 'sc5510b', 'sc5510b_visa']
    def __init__(self, dev_num=0, model_type='sc5511b_usb', extra_paths=SC_DLL_Default_Path, baud_rate=115200, **kwargs):
        """
        dev_num can be a number, which selects that device discovered.
                It can also be a serial number string to select one (only for usb and pxi not visa or rs232)
                You can use the static method discover to list devices.
        model_type:
                    'sc5511b_usb'   not pxi, with usb connection
                    'sc5511b_rs232' not pxi, with rs232 connection
                    'sc5510b'       pxi using Signal_Core driver
                    'sc5510b_visa'  pxi using visa driver
        baud_rate: allowed only 115200 and 57600
        """
        self._dev = None
        if model_type not in self._allowed_type:
            raise ValueError('model_type not in allowed types. It should be one of %s'%(self._allowed_type))
        self._dll = _load_SC_dll(model_type, extra_paths=extra_paths)
        self._dlldev = Dll_Wrap_Dev(self)
        self.open(dev_num, baud_rate)
        super(signalcore_SC5511_dll, self).__init__(**kwargs)


    @staticmethod
    def discover(model_type='sc5511b_usb', extra_paths=SC_DLL_Default_Path, _dll=None):
        """
        returns a list of names (serial number, com ports or pxi visa addresses)
        model_type:
                    'sc5511b_usb'   not pxi, with usb connection
                    'sc5511b_rs232' not pxi, with rs232 connection
                    'sc5510b'       pxi using Signal_Core driver
                    'sc5510b_visa'  pxi using visa driver
        """
        if _dll is None:
            allowed_type = signalcore_SC5511_dll._allowed_type
            if model_type not in allowed_type:
                raise ValueError('model_type not in allowed types. It should be one of %s'%(allowed_type))
            dll = _load_SC_dll(model_type, extra_paths=extra_paths)
        else:
            dll = _dll
        result = dll.search_devices()
        return result

    def open(self, dev_num_name=0, baud_rate=115200):
        if isinstance(dev_num_name, string_bytes_types):
            name = dev_num_name
        else:
            name = self.discover(_dll=self._dll)[dev_num_name]
        if self._dll._is_rs232:
            if baud_rate not in [57600, 115200]:
                raise ValueError('invalid baud rate')
            rate = SC_baudrate.rate_115200 if baud_rate == 115200 else SC_baudrate.rate_57600
            self._dev = self._dll.open_device(name, rate)
        else:
            self._dev = self._dll.open_device(name)

    def close(self):
        if hasattr(self, '_dev'):
            self._dll.close_device(self._dev)
            self._dev = None

    def __del__(self):
        self.close()
        super(signalcore_SC5511_dll, self).__del__()

    def idn(self):
        product = 'SC551xB'
        res = self._dlldev.get_device_info()
        sn = '%08X'%res.product_serial_number
        hw_rev = res.hardware_revision
        fw_rev = res.firmware_revision
        d = res.man_date
        date = '%04d-%02d-%02d %02d:00'%(d.year+2000, d.month, d.day, d.hour)
        version = 'hw:%r-fw:%r-date:%s'%(hw_rev, fw_rev, date)
        return "SignalCore,%s,%s,%s"%(product, sn, version)

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        base = self._conf_helper('freq1', 'level_dBm', 'out_en', 'standby1_en', 'freq2', 'standby2_en',
                                 'alc_auto_level_en', 'alc_close_loop_mode_en', 'temperature')
        opts = ['status=%s'%self.status(),
                'conf_regerence=%s'%self.conf_reference(),
                'conf_synth_mode=%s'%self.conf_synth_mode(),
                'conf_hardware_trigger=%s'%self.conf_hardware_trigger(),
                'conf_pulse=%s'%self.conf_pulse()]
        sl = self.conf_sweep_list()
        opts += ['conf_sweep_list=%s'%sl]
        if sl.sweep_mode_en:
            opts += ['conf_sweep=%s'%self.conf_sweep()]
        else:
            opts += ['conf_list=%s'%self.conf_list()]
        return base + opts + self._conf_helper(options)

    def trig_software(self):
        self._dlldev.list_soft_trigger()

    def perform_self_calibration(self):
        self._dlldev.synth_self_cal()

    def reinitialize(self, power_up_state=False):
        self._dlldev.reg_write(0x01, power_up_state)

    def store_default_state_eeprom(self):
        self._dlldev.store_default_state()

    _spur_sup_sel = dict(val0=True, val1=False)
    def conf_synth_mode(self, fracN_en=None, low_loop_gain_en=None, spur_supression_en=None):
        """
        When called with not parameters, returns the current configuration.
        fracN_en when False means harmonic offset mode instead of fracN PLL offset
        low_loop_gain_en when False, means normal loop gain
        spur_supression_en when True it will activate FracN. Only applies when fracN_en is False.
        """
        lcls = locals().copy()
        lcls.pop('self')
        status = self.status()
        d = {'fracN_en': 'lock_mode_fracN_en',
             'low_loop_gain_en': 'loop_gain_low_en',
             'spur_supression_en': 'spur_suppresion_en'
             }
        conf = dict_improved([(k, status[v]) for k, v in d.items()])
        if all([v is None for v in lcls.values()]):
            return conf
        for k, v in lcls.items():
            if v is None:
                lcls[k] = conf[k]
        ss = 'spur_supression_en'
        lcls[ss] = not lcls[ss]
        args = [lcls.get(n) for n in ['spur_supression_en', 'low_loop_gain_en', 'fracN_en']]
        self._dlldev.set_synth_mode(*args)

    _waveform_sel = dict(val0='sawtooth', val1='triangular')
    def conf_sweep_list(self, sweep_list_en=None, sweep_mode_en=None, reverse_en=None,
                        sweep_wf=None, return_start_en=None, cycle_count=None,
                        hardware_trig_en=None, step_on_trig_en=None,
                        trig_out_en=None, trig_out_on_completion_en=None):
        """
        When called with no parameters, returns the current configuration.
        sweep_list_en enables or disables both sweep or list which is selected
                   with the sweep_mode_en option.
        sweep_mode_en when False means the list mode is active
        sweep_wf is either 'sawtooth' or 'triangular'
        A cycle_count of 0 means cycle forever.
        step_on_trig_en can only be set to True for hardware_trig
                        when False, the trig starts or stops the sweep/list
        trig_out_on_completion_en when False, produces trig on every frequency change.
        """
        lcls = locals().copy()
        lcls.pop('self')
        status = self.status()
        d = {'sweep_list_en': 'sweep_list_mode_en',
             'sweep_mode_en': 'sweep_mode_en',
             'reverse_en': 'reverse_direction_en',
             'sweep_wf': 'sweep_waveform_sel',
             'hardware_trig_en': 'hardware_trig_en',
             'step_on_trig_en': 'step_on_trig_in_en',
             'return_start_en': 'list_return_to_start_en',
             'trig_out_en': 'trig_out_en',
             'trig_out_on_completion_en': 'trig_out_on_cycles_en'
             }
        dict_data = [(k, status[v]) for k, v in d.items()]
        conf = dict_improved([(k, status[v]) for k, v in d.items()])
        if all([v is None for v in lcls.values()]):
            cycle_count = self.cycle_count.get()
            dict_data.append(('cycle_count', cycle_count))
            return dict_improved(dict_data)
        lcls.pop('cycle_count')
        for k, v in lcls.items():
            if v is None:
                lcls[k] = conf[k]
        param_list = ['sweep_mode_en', 'reverse_en', 'sweep_wf', 'hardware_trig_en', 'step_on_trig_en',
                      'return_start_en', 'trig_out_en', 'trig_out_on_completion_en']
        value_list = [lcls[n] for n in param_list]
        conv = {'sawtooth':SC_waveformtype.sawtooth, 'triangular':SC_waveformtype.triangular}
        value_list[2] = conv[value_list[2]]
        self._dlldev.list_mode_config(value_list)
        self._dlldev.set_rf_mode(lcls['sweep_list_en'])
        if cycle_count is not None:
            self.cycle_count.set(cycle_count)

    def transfer_list(self, direction=None):
        """ Transfers the list either "to" or "from" the eeprom depending on the choise of direction.
            Only list_nbpoints values are transferred.
        """
        if direction not in ['to', 'from']:
            raise ValueError("You need to select the direction between 'to' or 'from'.")
        val = 0
        if direction == 'from':
            val = 1
        self._dlldev.list_buffer_transfer(val)

    def conf_list(self, freqs=None, levels=None, dwells=None):
        """When called with not parameters, returns the current configuration.
           All freqs, levels and dwells need to be of the same length.
        """
        lcls = locals().copy()
        lcls.pop('self')
        if all([v is None for v in lcls.values()]):
            n = self.list_nbpoints.get()
            freqs, levels, dwells = self._dlldev.list_buffer_read(n)
            return dict_improved(freqs=freqs, levels=levels, dwells=dwells)
        lists = [freqs, levels, dwells]
        vals_not_None = list([v is not None for v in lists])
        if any(vals_not_None):
            if not all(vals_not_None):
                raise ValueError('You need to provide all freqs, levels and dwells at the same time')
            if not (len(freqs) == len(levels) == len(dwells)):
                raise ValueError('The length of freqs, levels and dwells need to be the same.')
            if len(freqs) > 2048:
                raise ValueError('There is a maximum length of 2048 for the lists.')
            self._dlldev.list_buffer_write(*lists)

    def conf_sweep(self, start=None, stop=None, step=None, dwell=None):
        """When called with not parameters, returns the current configuration.
        """
        lcls = locals().copy()
        lcls.pop('self')
        data_list = [('start', self.sweep_freq_start),
                ('stop', self.sweep_freq_stop),
                ('step', self.sweep_freq_step),
                ('dwell', self.sweep_dwell)]
        data_dict = dict(data_list)
        data = dict_improved([(k, v.get()) for k, v in data_list])
        if all([v is None for v in lcls.values()]):
            return data
        for k, v in lcls.items():
            if v is not None:
                data_dict[k].set(v)

    _ref_freq_sel = dict(val0='10MHz', val1='100MHz')
    def _map_vals(self, in_dict):
        out_dict = {0:in_dict['val0'], 1:in_dict['val1']}
        return out_dict
    def conf_reference(self, lock_external_en=None, ref_out_freq_sel=None,
                       front_pxi_10MHz_en=None, direct_clocking_en=None, ref_in_freq_sel=None):
        """
        ref_out_freq_sel can be '10MHz' or '100MHz'
        ref_in_freq_sel can be '10MHz' or '100MHz'
        front_pxi_10MHz_en only for pxi hardware.
        direct_clocking_en and ref_in_freq_sel only for firmware>=3.0
        """
        lcls = locals().copy()
        lcls.pop('self')
        d = {'lock_external_en': 'ext_ref_lock_enable',
             'ref_out_freq_sel': 'ref_out_select',
             'front_pxi_10MHz_en': 'pxi_clock_enable',
             'direct_clocking_en': 'ext_direct_clocking',
             'ref_in_freq_sel': 'ext_ref_freq',
             }
        if not self._dll._is_pxi:
            d.pop('front_pxi_10MHz_en')
            lcls.pop('front_pxi_10MHz_en')
        ref_freq_sel = self._map_vals(self._ref_freq_sel)
        conv = {'ref_out_freq_sel': ref_freq_sel,
                'ref_in_freq_sel': ref_freq_sel}
        status = self._dlldev.get_clock_config()
        def do_iconv(name, v):
            if name in conv:
                cc = conv[name]
                i = list(cc.values()).index(v)
                return list(cc.keys())[i]
            return v
        def do_conv(name, v):
            if name in conv:
                return conv[name][v]
            return bool(v)
        conf = dict_improved([(k, do_conv(k, status[v])) for k, v in d.items()])
        if all([v is None for v in lcls.values()]):
            return conf
        for k, v in lcls.items():
            if v is None:
                lcls[k] = conf[k]
        param_list = ['ref_in_freq_sel', 'direct_clocking_en', 'front_pxi_10MHz_en', 'ref_out_freq_sel', 'lock_external_en']
        if not self._dll._is_pxi:
            param_list.pop(2) # remove 'front_pxi_10MHz_en'
        args = [do_iconv(n, lcls[n]) for n in param_list]
        self._dlldev.set_clock_reference(*args)

    def conf_pulse(self, pulse_en=None, pulse_trig_src=None):
        """
        pulse_trig_src can be "front" or "pxi" and is only for SC5510B models.
         "pxi" means to use the pxi trigger line configured with conf_hardware_trigger.
        """
        lcls = locals().copy()
        lcls.pop('self')
        #status = self.status()
        data = self._dlldev.get_pulse_mode()
        conv = {SC_pxi_pulse_src.front_MCX:'front', SC_pxi_pulse_src.pxi_backplane:'pxi'}
        iconv = {v:k for k,v in conv.items()}
        if self._dll._is_pxi:
            d = [('pulse_trig_src', conv[data[0]]), ('pulse_en', bool(data[1]))]
        else:
            d = [('pulse_en', bool(data))]
        conf = dict_improved(d)
        if all([v is None for v in lcls.values()]):
            return conf
        # Change one of the parameters
        for k, v in lcls.items():
            if v is None and k in conf:
                lcls[k] = conf[k]
        if self._dll._is_pxi:
            args = (iconv[lcls['pulse_trig_src']], lcls['pulse_en'])
        else:
            args = (lcls['pulse_en'],)
        self._dlldev.set_pulse_mode(*args)

    def conf_hardware_trigger(self, edge=None, pxi_en=None, trigger_line=None):
        """
        Only valid for pxi hardware.
        edge can be 'fall', 'rise'
        trigger_lines can be 0-7.
        """
        lcls = locals().copy()
        lcls.pop('self')
        edge_type= {0:'fall', 1:'rise'}
        iedge_type = {v:k for k, v in edge_type.items()}
        if self._dll._is_pxi:
            data = self._dlldev.get_pxi_trigger()
            d = [('edge', edge_type[data.edge]), ('pxi_en', bool(data.enable)), ('trigger_line', data.line)]
        else:
            data = self._dlldev.get_trigger_edge()
            d = [('edge', edge_type[data])]
        conf = dict_improved(d)
        if all([v is None for v in lcls.values()]):
            return conf
        # Change one of the parameters
        for k, v in lcls.items():
            if v is None and k in conf:
                lcls[k] = conf[k]
        if self._dll._is_pxi:
            args = list(map(lcls, ['edge', 'pxi_en', 'trigger_line']))
            args[0] = iedge_type[args[0]]
            self._dlldev.set_pxi_trigger(args)
        else:
            self._dlldev.set_trigger_edge(iedge_type[lcls['edge']])

    def status(self):
        # This is taken from signalcore_SC5511_libusb
        s1 = self.status1_raw.get()
        if hasattr(self, 'status2_raw'):
            s2 = self.status2_raw.get()
            old_fw = False
        else:
            s2 = 0
            old_fw = True
        #print(hex(s2))
        b = lambda n, s=s1, **kwarg: bitr(s, n, **kwarg)
        d = [('trig_out_on_cycles_en', b(47)),
            ('trig_out_en', b(46)),
            ('list_return_to_start_en', b(45)),
            ('step_on_trig_in_en', b(44)),
            ('hardware_trig_en', b(43)),
            ('sweep_waveform_sel', b(42, **self._waveform_sel)),
            ('reverse_direction_en', b(41)),
            ('sweep_mode_en', b(40)),
            ('spur_suppresion_en', b(38, **self._spur_sup_sel)),
            ('over_temp_error', b(37)),
            ('sweep_list_mode_en', b(36)),
            ('sweep_list_running', b(35)),
            ('ref_out_freq_sel', b(34, **self._ref_freq_sel)),
            ('ref_out_freq_sel2', b(9-8, s2, **self._ref_freq_sel)),
            ('extref_in_detected', b(33)),
            ('extref_in_lock_en', b(32)),
            ('extref_in_lock_en2', b(8-8, s2)),
            ('extref_in_freq_sel', b(12-8, s2, **self._ref_freq_sel)),
            ('extref_in_100MHz_direct_en', b(11-8, s2)),
            ('pxi10_front_export_en', b(10-8, s2)),
            ('rf1_out_en', b(31)),
            ('alc_disabled', b(30)),
            ('auto_level_disabled', b(29)),
            ('rf1_standby_en', b(28)),
            ('rf2_standby_en', b(27)),
            ('system_active_led_en', b(26)),
            ('loop_gain_low_en', b(25)),
            ('lock_mode_fracN_en', b(24)),
            ('pll_rf2_locked', b(23)),
            ('pll_TCXO_10MHz_locked', b(22)),
            ('pll_VCXO_100MHz_locked', b(21)),
            ('pll_crs_aux_locked', b(20)),
            ('pll_crs_ref_locked', b(19)),
            ('pll_dds_fine_locked', b(18)),
            ('pll_crs_locked', b(17)),
            ('pll_main_locked', b(16))]
        if old_fw:
            d = [(k,v) for k, v in d if k not in ['ref_out_freq_sel2',
                                              'extref_in_lock_en2']]
                                              #'extref_in_freq_sel',
                                              #'extref_in_100MHz_direct_en',
                                              #'pxi10_front_export_en']]
        return dict_improved(d)

    def status_struct(self):
        return self._dlldev.get_device_status()

    def _status1_raw_getdev(self):
        # the shift by 16 is to have the same values as signalcore_SC5511_libusb
        return self._dlldev.reg_read(0x22, 0)<<16

    def _status2_raw_getdev(self):
        return self._dlldev.reg_read(0x22, 1)

    def _system_active_led_en_getdev(self):
        return bool(self._dlldev.get_device_status().operate_status.device_access)

    def _system_active_led_en_setdev(self, val):
        self._dlldev.reg_write(0x02, val)

    def _create_devs(self):
        fw_rev = self._dlldev.get_device_info().firmware_revision
        old_fw = False
        if fw_rev < 2:
            old_fw = True
        minF = 100e6
        maxF = 20e9
        minP = -40
        maxP = 30
        self.freq1 = SC_dev_dll(self._dlldev.get_rf_parameters, self._dlldev.set_freq, read_name='rf1_freq', setget=True, min=minF, max=maxF)
        self.freq2 = SC_dev_dll(self._dlldev.get_rf_parameters, self._dlldev.set_rf2_freq, read_name='rf2_freq', scale=1e6,
                                force_type=int, setget=True, min=25e6, max=3e9,
                                doc="Garanteed frequency resolution is 25 MHz. At 200 MHz it is ~3 MHz, at 1GHz it is 13 MHz.")
        self.level_dBm = SC_dev_dll(self._dlldev.get_rf_parameters, self._dlldev.set_level, read_name='rf_level', setget=True, min=minP, max=maxP)
        self.phase_deg = SC_dev_dll(self._dlldev.get_signal_phase, self._dlldev.set_signal_phase, setget=True)
        self.temperature = SC_dev_dll(self._dlldev.get_temperature)
        self.sweep_freq_start = SC_dev_dll(self._dlldev.get_rf_parameters, self._dlldev.list_start_freq, read_name='start_freq', setget=True)
        self.sweep_freq_stop = SC_dev_dll(self._dlldev.get_rf_parameters, self._dlldev.list_stop_freq, read_name='stop_freq', setget=True)
        self.sweep_freq_step = SC_dev_dll(self._dlldev.get_rf_parameters, self._dlldev.list_step_freq, read_name='step_freq', setget=True)
        self.sweep_dwell = SC_dev_dll(self._dlldev.get_rf_parameters, self._dlldev.list_dwell_time, read_name='sweep_dwell_time', scale=0.5e-3, force_type=int, setget=True)
        self.cycle_count = SC_dev_dll(self._dlldev.get_rf_parameters, self._dlldev.list_cycle_count, read_name='sweep_cycles', setget=True,
                                      doc="A cycle_count of 0 means cycle forever.")
        self.list_nbpoints = SC_dev_dll(self._dlldev.get_rf_parameters, self._dlldev.list_buffer_points, read_name='buffer_points', min=0, max=2048, setget=True)
        self._devwrap('status1_raw')
        if not old_fw:
            self._devwrap('status2_raw')
        self.out_en = SC_dev_dll(self._dlldev.get_device_status, self._dlldev.set_output, read_access_func=lambda v: bool(v.operate_status.rf1_out_enable))
        self.standby1_en = SC_dev_dll(self._dlldev.get_device_status, self._dlldev.set_standby, read_access_func=lambda v: bool(v.operate_status.rf1_standby))
        self.standby2_en = SC_dev_dll(self._dlldev.get_device_status, self._dlldev.set_rf2_standby, read_access_func=lambda v: bool(v.operate_status.rf2_standby))
        self._devwrap('system_active_led_en')
        # # TODO: There is not read of the reference_dac
        # # self.reference_dac_val = SC_dev_dll(???, self._dlldev.set_reference_dac, min=0, max=2**14-1)
        self.alc_dac_val = SC_dev_dll(self._dlldev.get_alc_dac, self._dlldev.set_alc_dac, min=0, max=2**14-1, setget=True)
        self.alc_auto_level_en = SC_dev_dll(self._dlldev.get_device_status, self._dlldev.set_auto_level_disable,
                                                 read_access_func=lambda v: not bool(v.operate_status.auto_pwr_disable),
                                                 write_access_func=lambda v: not v)
        self.alc_close_loop_mode_en = SC_dev_dll(self._dlldev.get_device_status, self._dlldev.set_alc_mode,
                                                 read_access_func=lambda v: not bool(v.operate_status.alc_mode),
                                                 write_access_func=lambda v: not v)
        # This needs to be last to complete creation
        super(signalcore_SC5511_dll, self)._create_devs()
