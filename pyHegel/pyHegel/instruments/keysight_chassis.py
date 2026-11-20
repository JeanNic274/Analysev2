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

from __future__ import absolute_import, print_function, division

import numpy as np
import re
import sys
import glob
import os.path
import contextlib

from ..instruments_base import BaseInstrument, Base2Device, MemoryDevice, ReadvalDev,\
                                locked_calling, ChoiceSimpleMap, ChoiceBase,\
                                ProxyMethod, reorganize_conf_with_ch, MemoryDevice_update
from ..instruments_registry import register_instrument, register_idn_alias
from ..comp2to3 import fb, is_py3

if is_py3:
    from socketserver import TCPServer
else:
    from SocketServer import TCPServer

def find_free_port():
    with TCPServer(("localhost", 0), None) as s:
        free_port = s.server_address[1]
    return free_port


#######################################################
##    General Waveform Generator (AM, FM modulation)
#######################################################

class WaveformGenerator(object):
    def __init__(self, min_length=32, max_length=2**29, granularity=8, max_delay=(2**16-1) / 300E6,
                 nbits=16, sample_rate=2.4e9, full_scale_amp=0.2925):
        # From labber interface, FULL_SCALE_AMP is in Vpeak (=2.33 dBm)
#        self.MIN_WAVEFORM_LENGTH = 32
#        MAX_WAVEFORM_LENGTH = 2**29
#        SAMPLE_GRANULARITY = 8
#        MAX_DELAY = (2**16-1) / 300E6
#        N_BIT = 16
#        SAMPLE_RATE = 2.4e9
#        FULL_SCALE_AMP = 0.2925
#        DT = 1/SAMPLE_RATE
        self.MIN_WAVEFORM_LENGTH = min_length
        self.MAX_WAVEFORM_LENGTH = max_length
        self.SAMPLE_GRANULARITY = granularity
        self.MAX_DELAY = max_delay
        self.N_BIT = nbits
        self.SAMPLE_RATE = sample_rate
        self.FULL_SCALE_AMP = full_scale_amp
        self.DT = 1./self.SAMPLE_RATE
        self._last_data = None
        self._last_N = None
        self._last_freq = None
        self._last_t = None


    def find_optimum_N(self, freq, min_N, max_N, Ncycle_max=1e9, round_freq_digit=12):
        # If Ncycle_max makes N too small, at least min_N is used
        GRAN = self.SAMPLE_GRANULARITY
        SAMPLE_RATE = self.SAMPLE_RATE
        Nlim = lambda n: np.clip(n//GRAN*GRAN, self.MIN_WAVEFORM_LENGTH, self.MAX_WAVEFORM_LENGTH)
        min_N = Nlim(min_N)
        max_N = Nlim(max_N)
        if min_N > max_N:
            raise ValueError('min_N should be smaller than max_N')
        if Ncycle_max < 1:
            raise ValueError('Ncycle_max should be at least 1')
        if freq >=SAMPLE_RATE/2:
            return SAMPLE_RATE/2, min_N
        if max_N / (SAMPLE_RATE/freq) > Ncycle_max:
            end = Nlim(SAMPLE_RATE/freq*Ncycle_max)
            if end < min_N:
                end = min_N
        else:
            end = max_N
        Ns = np.arange(min_N, end+1, GRAN)
        # This finds closest freq that fits exactly as a multiple of f1 and makes sure it is not zero but at mimimum f1
        adjust_freq = lambda f, f1: np.maximum(np.round(f/f1)*f1, f1)
        f1s = SAMPLE_RATE/Ns # minimum frequency possible
        freqs = adjust_freq(freq, SAMPLE_RATE/Ns)
        #min_id = abs(freqs-freq).argmin()
        min_id = np.round(abs(freqs/freq-1), round_freq_digit).argmin()
        N = Ns[min_id]
        freq = freqs[min_id]
        return freq, int(N)

    def find_optimum_N_2(self, freq, min_N, max_N, Ncycle_max=1e9, round_freq_digit=12):
        """
        To limit the calculation time, you can decrease max_N (the maximum length of the optimum length.
        You can also limit the number of repeated cycles that will be used by changing Ncycle_max,
        but there will at least be the number of cycles required by min_N.
        Both of those changes will decrease the resolution of the returned frequency.
        Decreasing round_freq_digit will not decrease the calculation time but will find shorter optimum N.
        round_freq_digit is the number of digits to try to reproduce from freq. For example, if you
        ask for 4567 kHz with round_freq_digit at 3, you might get 4569 kHz as the result.
        Note that min_N and max_N are internally adjusted for the minimum and maximum waveform length and
        for the sample granularity. So the actual N returned could be a little smaller thant min_N (because of
        the granularity).
        """
        # If Ncycle_max makes N too small, at least min_N is used
        GRAN = self.SAMPLE_GRANULARITY
        SAMPLE_RATE = self.SAMPLE_RATE
        Nlim = lambda n: np.clip(n//GRAN*GRAN, self.MIN_WAVEFORM_LENGTH, self.MAX_WAVEFORM_LENGTH)
        min_N = Nlim(min_N)
        max_N = Nlim(max_N)
        if min_N > max_N:
            raise ValueError('min_N should be smaller than max_N')
        if Ncycle_max < 1:
            raise ValueError('Ncycle_max should be at least 1')
        No = SAMPLE_RATE/freq
        if No >= max_N:
            return SAMPLE_RATE/max_N, max_N
        elif freq >=SAMPLE_RATE/2:
            return SAMPLE_RATE/2, min_N
        min_N8 = min_N/GRAN
        max_N8 = max_N/GRAN
        No8 = No/GRAN
        if No8 < 2:
            # The simpler algorithm is probably more efficient here.
            return self.find_optimum_N(freq, min_N, max_N, Ncycle_max, round_freq_digit)
        start = np.ceil(min_N8/No8)
        end = np.floor(max_N8/No8)
        if end > Ncycle_max:
            end = Ncycle_max
            if end < start:
                end = start
        mult = np.arange(start, end+1)
        No8m = No8*mult
        lower = np.floor(No8m)
        upper = np.ceil(No8m)
        # check the extreme conditions. These should be unecessary except for
        # when No8m are integers. Then if (min_N8/No8)*No8 is not exactly min_N8 there
        # could be a mistake (in this case if it is sligthly less).
        if lower[0] < min_N8:
            lower[0] = min_N8
        if upper[-1] > max_N8:
            upper[-1] = max_N8
        lu = np.stack([lower, upper], axis=1).flatten()
        mult_lu = np.stack([mult, mult], axis=1).flatten()
        # find best mult
        #min_id = abs(1./No8 - mult_lu/lu).argmin()
        #min_id = abs(No8 - lu/mult_lu).argmin()
        min_id = np.round(abs(mult_lu/lu*No8 -1), round_freq_digit).argmin()
        best_N = int(lu[min_id]*GRAN)
        best_mult = mult_lu[min_id]
        best_freq = (SAMPLE_RATE/best_N)*best_mult
        return best_freq, best_N

    def remember_last(self, data, N, freq=None, t=None):
        self._last_data = data
        self._last_N = N
        self._last_freq = freq
        self._last_t = t

    def fm_mod_factor_to_amp(self, freq, factor):
        return freq*factor
    def fm_mod_amp_to_factor(self, freq, amp):
        return amp/freq

    def generate_fm_mod(self, mod_freq, mod_amplitude=None, mod_factor=None, min_N=2**10, max_N=100*2**10, Ncycle_max=1e9, round_freq_digit=12):
        """
            min_N and max_N will be used to select the correct number of points to increase
            the mod_freq resolution. They will be rounded appropriately.
            You need to provide one of mod_amplitude (absolute) or mod_factor (relative to mod_freq)
            for the modulation.
            It returns the data, the actual mod_freq used, the actual mod_amplitude used and the actual N.
        """
        if mod_amplitude is None and mod_factor is None:
            raise ValueError('You need to specify one of mod_amplitude or mod_factor')
        elif mod_amplitude is not None and mod_factor is not None:
            raise ValueError('You need to specify one of mod_amplitude or mod_factor')
        freq, N = self.find_optimum_N_2(mod_freq, min_N, max_N, Ncycle_max, round_freq_digit)
        DT = self.DT
        t = np.arange(N)*DT
        if mod_factor is None:
            #mod_factor = mod_amplitude/freq
            mod_factor = self.fm_mod_amp_to_factor(freq, mod_amplitude)
        wm = 2*np.pi*freq
        K = 1j*mod_factor
        data = np.exp(K * np.sin(wm*t))
        self.remember_last(data, N, freq, t)
        return data, freq, mod_factor*freq, N

    def generate_am_mod(self, mod_freq, mod_amp_I=1., mod_amp_Q=0., mod_offset=0., min_N=2**10, max_N=100*2**10, Ncycle_max=1e9, round_freq_digit=12):
        """ mod amplitudes and offset can be complex numbers
            for normal IQ modulation, both mod_amplitude should be real.
        """
        freq, N = self.find_optimum_N_2(mod_freq, min_N, max_N, Ncycle_max, round_freq_digit)
        DT = self.DT
        t = np.arange(N)*DT
        wm = 2*np.pi*freq
        data = mod_amp_I * np.cos(wm*t)  + 1j*mod_amp_Q*np.sin(wm*t) + mod_offset
        self.remember_last(data, N, freq, t)
        return data, freq, N


def _delayed_import(mod = 'm5300'):
    try:
        if mod == 'm5300':
            pip_import = 'Can be installed with (replace * with correct version):\n pip install "C:\\Program Files\\Keysight\\M5300x\\python\\keysight_ktm5300x-*-win_amd64.whl"'
            import keysight_ktm5300x as m
        elif mod == 'm9032':
            pip_import = 'Can be installed with (replace * with correct version):\n pip install "C:\\Program Files\\Keysight\\M9032x\\python\\keysight_ktm9032x-*-win_amd64.whl"'
            import keysight_ktm9032x as m
        elif mod == 'SD1':
            pip_import = 'Can be installed with (replace * with correct version):\n pip install "C:\\Program Files\\Keysight\\SD1\\Libraries\\Python\\keysightSD1-*.tar.gz"'
            import keysightSD1 as m
        elif mod == 'chassis':
            try:
                # first try if it works
                from Keysight import KtMPxiChassis as m
            except ImportError:
                # it did not work so do the full sequence of operation to load it.
                pip_import = 'Make sure pythonnet is installe (pip install pythonnet) and that the Chassis IVI drivers have been installed.'
                # First find dll
                filenames = glob.glob(r'C:\Program Files\IVI Foundation\IVI\Microsoft.NET\Framework64\*\*\Keysight.KtMPxiChassis.*dll')
                if len(filenames) != 1:
                    raise ImportError('Unable to find a single Keysight.KtMPxiChassis.*dll (found none or multiple ones)')
                d, f = os.path.split(filenames[0])
                base, ext = os.path.splitext(f)
                import clr
                if d not in sys.path:
                    sys.path.append(d) #r'C:\Program Files\IVI Foundation\IVI\Microsoft.NET\Framework64\v4.0.30319\Keysight.KtMPxiChassis 1.7.741'
                    clr.AddReference(base) #'Keysight.KtMPxiChassis.Fx40'
                from Keysight import KtMPxiChassis as m
        else:
            raise ValueError('Unknow import module name')
    except ImportError as exc:
        raise RuntimeError('Unable to import %s because of: %s.\n%s'%(mod, exc, pip_import))
    return m


class FuncDev(Base2Device):
    def __init__(self, setdev=None, getdev=None, base=None, compile_code=True, set_exec_type='exec', **kwargs):
        super(FuncDev, self).__init__(**kwargs)
        self._base = base
        self._set_exec_type = set_exec_type
        if compile_code:
            if setdev is not None:
                self._setdev_p = compile(setdev, '<string>', set_exec_type)
            if getdev is not None:
                self._getdev_p = compile(getdev, '<string>', 'eval')
        else:
            self._setdev_p = setdev
            self._getdev_p = getdev
    def _tostr(self, val):
        # convert from python value to interface value (can be a string like for scpi or not)
        if isinstance(self.choices, ChoiceBase):
            return self.choices.tostr(val)
        return val
    def _fromstr(self, valstr):
        # convert from interface value to python value (input can be a string like for scpi or not)
        if isinstance(self.choices, ChoiceBase):
            return self.choices(valstr)
        return valstr
    def _set_write(self, val, options):
        op = options.copy()
        op['base'] = self._base
        op['val'] = val
        if self._set_exec_type == 'exec':
            exec(self._setdev_p, op)
        else:
            val = eval(self._setdev_p, op)
            if hasattr(self, '_set_write_check'):
                self._set_write_check(val)
    def _get_ask(self, options):
        self._get_para_checked()
        op = options.copy()
        op['base'] = self._base
        val = eval(self._getdev_p, op)
        if hasattr(self, '_get_ask_check'):
            self._get_ask_check(val)
        return val


#######################################################
##    Keysight M5300 AWG card
#######################################################

class ChoiceFromEnum(ChoiceSimpleMap):
    def __init__(self, enum_class, strip=None, **kwargs):
        names = dir(enum_class)
        if strip:
            def cleanup(s):
                if not s.startswith(strip):
                    raise ValueError('Enum values do not start with "%s"'.strip)
                return s[len(strip):]
        else:
            cleanup = lambda s: s
        # mro is for m3000, name, value is for m5000
        enums = [(cleanup(n).lower(), n) for n in names if not (n.startswith('__') or n in ['name', 'value', 'mro'])]
        d = {getattr(enum_class, k):v for v, k in enums}
        super(ChoiceFromEnum, self).__init__(d, **kwargs)

class M5dev(FuncDev):
    def __init__(self, variable, base, get_only=False, **kwargs):
        self._variable = variable
        if not get_only:
            setdev = variable + '=val'
        else:
            setdev = None
        getdev = variable
        super(M5dev, self).__init__(setdev, getdev, base, **kwargs)


class keysight_M5xxx(BaseInstrument):
    def __init__(self, address, force_align='auto', reset=False, options='', as_client='auto', port='std', skip_id_test=False, verify_id=True, **kwargs):
        """ address is a tuple (chassis#, slot#)
            force_align can be True, False or 'auto'. For auto it is True when as_client is False (a server) and False when it is a client.
            options is a string that can be:
                  OpenSfp 	Default='0/false'. If '1/true', the SFP will be opened immediately. Effectively identical to calling System.Sfp.Open after Initialize().
                  AllowSfpAttach 	Default='0/false'. If '1/true', an independently launched SFP may attach to this instance.
            as_client when True, will connect to another instance using port, when False will open port for remote connection
                       when 'auto', will first try False then if it does not work will try True.
            port is used to start a server or connect from a client. it can be "auto" (finds some open port), "std" (use labber numbering),
                  False (to disable server), a number or and (address, port) tuple.
            verify_id when True (default), will test to make sure the module is of the correct type.
        """
        # self._module_class # needs to be set by child class.
        self._is_closed = True
        self._is_server_running = False
        self._server_port = None
        self._is_client_state = None # can be None, True, False
        self._address = address
        self.open(address, force_align, reset, options, as_client, port, verify_id)
        self._check_id_test(skip_id_test)
        super(keysight_M5xxx, self).__init__(**kwargs)

    def _get_server_port(self, address, port, as_client):
        # return address, port
        chassis, slot = address
        text_addr = "PXI0::CHASSIS%d::SLOT%d::INSTR"%address
        remote_host = 'localhost'
        #text_addr = "PXI0::CHASSIS%d::SLOT%d::INDEX0::INSTR"%address
        if port is False:
            return text_addr, None
        elif isinstance(port, tuple):
            remote_host, port = port
        if port == 'std':
            port = '5%d%02d'%(chassis, slot)
        elif port == 'auto':
            port = str(find_free_port())
        elif port < 0:
            raise ValueError('Invalid port number')
        else:
            port = str(port)
        if as_client:
            text_addr = 'rpc://%s:%s/'%(remote_host, port)+ text_addr
        return text_addr, port

    def _open(self, address=None, force_align='auto', reset=False, options='', as_client=False, port='std', verify_id=True):
        if not as_client:
            print('Wait, this will take some time.')
        self._is_closed = True
        if address is None:
            address = self._address
        address, port = self._get_server_port(address, port, as_client)
        self._server_port = port
        if port is not None:
            if options != '':
                options += ','
            options += 'AllowMultipleClientAttach=1'
        if force_align == 'auto':
            force_align = False if as_client else True
        self._module = self._module_class(address, verify_id, reset, options)
        self._is_client_state = as_client
        if not as_client and port is not None:
            self._module.system.remote_server.port = port
            self._module.system.remote_server.enabled = True
            self._is_server_running = True
        else:
            self._is_server_running = False
        self._is_closed = False
        if force_align:
            self.get_error() # clean up errors
            self.align()
        self.check_error()

    def open(self, address=None, force_align='auto', reset=False, options='', as_client='auto', port='std', verify_id=True):
        if as_client == 'auto':
            try:
                self._open(address, force_align, reset, options, False, port, verify_id)
            except RuntimeError as exc:
                if 'VI_ERROR_RSRC_LOCKED' in exc.args[0]:
                    self._open(address, force_align, reset, options, True, port, verify_id)
                else:
                    raise
        else:
            self._open(address, force_align, reset, options, as_client, port, verify_id)

    def close(self):
        if not self._is_closed:
            if self._is_server_running:
                self._module.system.remote_server.enabled = False
                self._is_server_stopped = True
            try:
                self._module.close()
            except RuntimeError: # could happen if remote server connection is already closed by other end
                pass
            self._is_closed = True
            self._is_client_state = None

    def __del__(self):
        self.close()
        super(keysight_M5xxx, self).__del__()

    def idn(self):
        manuf = self._module.identity.instrument_manufacturer
        model = self._module.identity.instrument_model
        # also have identity.vendor identity.identifier identity.revision which refer to the driver's version
        serial = self._module.system.serial_number
        about = self._module.system.about
#M5300A - MY62260196 - Manufacturing Number: 1E62260196:
#      PCA, @,
#         M5300A_PCA: 1.1.205.0,
        r = re.search(r'M5300A_PCA: *([\d.]*),', about)
        if r is not None:
            fm_v = r.group(1)
        else:
            fm_v = 'X'
        fw = 'sw:%s_fw:%s_hw_rev:%s'%(self._module.identity.revision, fm_v, self._module.identity.instrument_firmware_revision)
        return '%s,%s,%s,%s'%(manuf, model, serial, fw)

    def get_error(self):
        return self._module.utility.error_query()

    def check_error(self):
        errno, errmsg = self.get_error()
        if errno != 0:
            raise RuntimeError('There was a problem (%d): %s'%(errno, errmsg))

    def sfp_open(self):
        self._module.system.sfp.open()
    def sfp_refresh(self):
        self._module.system.sfp.refresh(True)
    def sfp_close(self):
        self._module.system.sfp.close()


keysight_ktm5300x = None

@register_instrument('Keysight Technologies', 'M5300A')
class keysight_M5300(keysight_M5xxx):
    """
    This controls the keysight M5300A AWG cards.
    Important devices:
        frequency
        amplitude_percent
        output_mode
        output_en
        align_status
        modulation_*
    Note that all the modulation_ devices are memory devices so they do not match the instrument setup upon
    loading the instrument.
    Useful method:
        sfp_open
    Address example:
           use (1, 12) for 'PXI0::CHASSIS1::SLOT12::INDEX0::INSTR'
    """
    def __init__(self, address, force_align='auto', reset=False, options='', as_client='auto', port='std', skip_id_test=False, verify_id=True, **kwargs):
        """ address is a tuple (chassis#, slot#)
            force_align can be True, False or 'auto'. For auto it is True when as_client is False (a server) and False when it is a client.
            options is a string that can be:
                  OpenSfp 	Default='0/false'. If '1/true', the SFP will be opened immediately. Effectively identical to calling System.Sfp.Open after Initialize().
                  AllowSfpAttach 	Default='0/false'. If '1/true', an independently launched SFP may attach to this instance.
            as_client when True, will connect to another instance using port, when False will open port for remote connection
            port is used to start a server or connect from a client. it can be "auto" (finds some open port), "std" (use labber numbering),
                  False (to disable server), a number or and (address, port) tuple.
            verify_id when True (default), will test to make sure the module is of the correct type.
        """
        global keysight_ktm5300x
        keysight_ktm5300x = _delayed_import('m5300')
        self._module_class = keysight_ktm5300x.KtM5300x
        super(keysight_M5300, self).__init__(address, force_align=force_align, reset=reset, options=options, as_client=as_client,
                                             port=port, skip_id_test=skip_id_test, verify_id=verify_id, **kwargs)
        # From labber interface, FULL_SCALE_AMP is in Vpeak (=2.33 dBm)
        self.waverform_gen = WaveformGenerator(min_length=32, max_length=2**29, granularity=8, max_delay=(2**16-1) / 300E6,
                                               nbits=16, sample_rate=2.4e9, full_scale_amp=0.2925)

    @property
    def _awg(self):
        return self._module

    # find init/reset alignment option
    def align(self):
        self._awg.clock.align()
        self.check_error()

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        orig_ch = self.current_channel.get()
        ch_info = []
        for ch in range(1, 4+1):
            self.current_channel.set(ch)
            base_info = self._conf_helper('output_en', 'output_mode', 'frequency', 'amplitude_percent')
            mod_info = self._conf_helper('modulation_type', 'modulation_freq',
                                         'modulation_min_N', 'modulation_max_N', 'modulation_Ncycle_max', 'modulation_round_freq_digit',
                                         'modulation_Nsamples_used',
                                         'modulation_fm_amplitude', 'modulation_fm_factor_en', 'modulation_fm_factor',
                                         'modulation_am_amp_I', 'modulation_am_amp_Q', 'modulation_am_offset')
            ch_info.append(base_info+mod_info)
        self.current_channel.set(orig_ch)
        ch_info_r = reorganize_conf_with_ch(ch_info)
        return ch_info_r + self._conf_helper(options)

    def setup_mode(self, mode='modulated', ch=None, freq=1e9, amplitude=None, enabled=True):
        """
           freq is used as carrier or main frequency for modulated (IQ modulation) and std mode. It is unused for baseband mode.
        """
        if amplitude is None:
            amplitude = self.waverform_gen.FULL_SCALE_AMP*.5
        self.output_mode.set(mode, ch=ch)
        self.check_error()
        self.amplitude_percent.set(amplitude/self.waverform_gen.FULL_SCALE_AMP*100)
        self.check_error()
        self.frequency.set(freq)
        self.check_error()
        self.output_en.set(False) # sometimes need to reset the state maybe??
        self.check_error()
        self.output_en.set(enabled)
        self.check_error()

    def _get_ch(self, ch=None):
        if ch is None:
            ch = self.current_channel.get()
        else:
            self.current_channel.set(ch)
        return ch, self._awg.channels[ch-1]

    def _get_ch_basic(self, ch=None):
        return self._get_ch(ch)[0]

    def load_modulation(self, data, ch=None, mod_id=1, clear=True):
        """ data needs to be a 1D of float or complex with max amplitude of 1. """
        # make sure data is complex and 1D array
        if len(data.shape) != 1:
            raise ValueError('Data is not 1D array')
        data = data.astype(complex, copy=False)
        if abs(data).max() > 1:
            raise ValueError("Some values have amplitude larger than 1.")
        ch_num, ch = self._get_ch(ch)
        if clear:
            ch.arbitrary_waveform.clear_waveform_memory()
            self.check_error()
        # convert data
        real_iq = data.view(float)
        # could convert to 16 bit sign and use create16
        #   range of in 2**15 -1 to -2**15: 32767 to -32768
        ch.arbitrary_waveform.create(real_iq, mod_id)
        self.check_error()

    def enable_modulation(self, mod_ids=[1], num_cycles=[0], start_delays=[0], ch=None):
        """ num_cycles of 0 repeats forever """
        AUTO_TRIG = keysight_ktm5300x.TriggerMode.AUTO_TRIG
        ch_num, ch = self._get_ch(ch)
        ch.awg_stop()
        if not isinstance(mod_ids, (list, tuple, np.ndarray)):
            mod_ids = [mod_ids]
        if not isinstance(num_cycles, (list, tuple, np.ndarray)):
            num_cycles = [num_cycles]
        if not isinstance(start_delays, (list, tuple, np.ndarray)):
            start_delays = [start_delays]
        ch.awg_queue_flush()
        ch.arbitrary_waveform.playback_mode = keysight_ktm5300x.PlaybackMode.CYCLIC
        # Note that with CYCLIC, if the total number of points is small (something <1536)
        # then the data is improperly output and there is dead time added (not always in the same spot)
        # This might be mentioned in the Firmware release note.
        for mod_id, ncycles, start_delay in zip(mod_ids, num_cycles, start_delays):
            ch.awg_queue_waveform(AUTO_TRIG, start_delay, ncycles, mod_id)
        ch.awg_start()

    def disable_modulation(self, ch=None):
        ch_num, ch = self._get_ch(ch)
        ch.awg_stop()

    def setup_fm_modulation(self, mod_freq, mod_amplitude=None, mod_factor=None, min_N=2**10*2, max_N=2**20, Ncycle_max=1e6, round_freq_digit=12, ch=None):
        ch = self._get_ch_basic(ch)
        self.modulation_type.set('fm', skip_update=True)
        self.modulation_freq.set(mod_freq, skip_update=True)
        if mod_amplitude is not None:
            self.modulation_fm_amplitude.set(mod_amplitude, skip_update=True)
        else:
            self.modulation_fm_factor.set(mod_factor, skip_update=True)
        self.modulation_min_N.set(min_N, skip_update=True)
        self.modulation_max_N.set(max_N, skip_update=True)
        self.modulation_Ncycle_max.set(Ncycle_max, skip_update=True)
        self.modulation_round_freq_digit.set(round_freq_digit, skip_update=True)
        data, fm, fa, N = self.waverform_gen.generate_fm_mod(mod_freq, mod_amplitude, mod_factor, min_N, max_N, Ncycle_max, round_freq_digit)
        delta = fm-mod_freq
        print('Using mod_freq={} ({} Hz or {}% different) with N={}'.format(fm, delta, delta/mod_freq*100, N))
        self.modulation_freq.set(fm, skip_update=True)
        self.modulation_Nsamples_used.set(N)
        self.load_modulation(data)
        self.enable_modulation()

    def setup_am_modulation(self, mod_freq, mod_amp_I=1., mod_amp_Q=0., mod_offset=0., min_N=2**10*2, max_N=2**20, Ncycle_max=1e6, round_freq_digit=12, ch=None):
        ch = self._get_ch_basic(ch)
        self.modulation_type.set('am', skip_update=True)
        self.modulation_freq.set(mod_freq, skip_update=True)
        self.modulation_am_amp_I.set(mod_amp_I, skip_update=True)
        self.modulation_am_amp_Q.set(mod_amp_Q, skip_update=True)
        self.modulation_am_offset.set(mod_offset, skip_update=True)
        self.modulation_min_N.set(min_N, skip_update=True)
        self.modulation_max_N.set(max_N, skip_update=True)
        self.modulation_Ncycle_max.set(Ncycle_max, skip_update=True)
        self.modulation_round_freq_digit.set(round_freq_digit, skip_update=True)
        data, fm, N = self.waverform_gen.generate_am_mod(mod_freq, mod_amp_I, mod_amp_Q, mod_offset, min_N, max_N, Ncycle_max, round_freq_digit)
        delta = fm-mod_freq
        print('Using mod_freq={} ({} Hz or {}% different) with N={}'.format(fm, delta, delta/mod_freq*100, N))
        self.modulation_freq.set(fm, skip_update=True)
        self.modulation_Nsamples_used.set(N)
        self.load_modulation(data)
        self.enable_modulation()

    def _update_modulation(self, ch, dev):
        # ch is already set
        mod_type = self.modulation_type.get()
        if mod_type == 'unknown':
            return
        elif mod_type == 'off':
            if dev == self.modulation_type:
                self.disable_modulation(ch)
            return
        mod_freq = self.modulation_freq.get()
        min_N = self.modulation_min_N.get()
        max_N = self.modulation_max_N.get()
        Ncycle_max = self.modulation_Ncycle_max.get()
        round_freq_digit = self.modulation_round_freq_digit.get()
        base_mod = [self.modulation_type, self.modulation_freq,
                    self.modulation_min_N, self.modulation_max_N, self.modulation_Ncycle_max, self.modulation_round_freq_digit]
        fm_mod = [self.modulation_fm_amplitude, self.modulation_fm_factor]
        am_mod = [self.modulation_am_amp_I, self.modulation_am_amp_Q, self.modulation_am_offset]
        if mod_type == 'am' and dev in base_mod+am_mod:
            mod_amp_I = self.modulation_am_amp_I.get()
            mod_amp_Q = self.modulation_am_amp_Q.get()
            mod_offset = self.modulation_am_offset.get()
            data, fm, N = self.waverform_gen.generate_am_mod(mod_freq, mod_amp_I, mod_amp_Q, mod_offset, min_N, max_N, Ncycle_max, round_freq_digit)
        elif mod_type == 'fm' and dev in base_mod+fm_mod:
            if self.modulation_fm_factor_en.get():
                mod_factor = self.modulation_fm_factor.get()
                mod_amp = None
            else:
                mod_factor = None
                mod_amp = self.modulation_fm_amplitude.get()
            data, fm, fa, N = self.waverform_gen.generate_fm_mod(mod_freq, mod_amp, mod_factor, min_N, max_N, Ncycle_max, round_freq_digit)
        else:
            return
        self.modulation_freq.set(fm, skip_update=True)
        self.modulation_Nsamples_used.set(N)
        self.load_modulation(data)
        self.enable_modulation()

    def _update_fm_amp(self, ch, dev):
        freq = self.modulation_freq.get()
        update_amp = False
        if dev == self.modulation_freq:
            if self.modulation_fm_factor_en.get():
                update_amp = True
        elif dev == self.modulation_fm_amplitude:
            update_amp = False
            self.modulation_fm_factor_en.set(False, skip_update=True)
        else: # dev == self.modulation_fm_factor
            update_amp = True
            self.modulation_fm_factor_en.set(True, skip_update=True)
        if update_amp:
            factor =  self.modulation_fm_factor.get()
            amp = self.waverform_gen.fm_mod_factor_to_amp(freq, factor)
            self.modulation_fm_amplitude.set(amp, skip_update='both')
        else:
            amp = self.modulation_fm_amplitude.get()
            factor = self.waverform_gen.fm_mod_amp_to_factor(freq, amp)
            self.modulation_fm_factor.set(factor, skip_update='both')

    def _create_devs(self):
        self.current_channel = MemoryDevice(1, choices=[1, 2, 3, 4], no_type_conv=True)
        def M5dev_ch(variable, *args, **kwargs):
            base = self._awg.channels
            options = kwargs.pop('options', {}).copy()
            options.update(ch=self.current_channel)
            app = kwargs.pop('options_apply', ['ch'])
            kwargs.update(options=options, options_apply=app)
            return M5dev('base[ch-1].'+variable, base, *args, **kwargs)
        #self.frequency = M5dev('base[ch-1].standard_waveform.frequency', self._awg.channels, options=dict(ch=self.current_channel), options_apply=['ch'])
        self.frequency = M5dev_ch('standard_waveform.frequency')
        self.amplitude_percent = M5dev_ch('amplitude', min=0, max=100)
        self.output_mode = M5dev_ch('output_type', choices=ChoiceFromEnum(keysight_ktm5300x.OutputWaveform))
        self.output_en = M5dev_ch('enabled')
        update_mod = ProxyMethod(self._update_modulation)
        ch_helper = ProxyMethod(self._get_ch_basic)
        ModType = lambda *args, **kwargs: MemoryDevice_update(*args, nch=4, update_func=update_mod, ch_helper_func=ch_helper, **kwargs)
        ModType_no_upd = lambda *args, **kwargs: MemoryDevice_update(*args, nch=4, ch_helper_func=ch_helper, **kwargs)
        self.modulation_type = ModType('unknown', choices=['off', 'am', 'fm'], doc=
                                        """ Note that 'off' stops the awg so no output will be present.
                                            you might want output_mode set to 'std'
                                            or set a fm modulation without amplitude, or am modulation with just offset.
                                        """)
        self.modulation_freq = ModType(1000., uncond_update_func=self._update_fm_amp)
        self.modulation_fm_amplitude = ModType(1000., uncond_update_func=self._update_fm_amp)
        self.modulation_fm_factor_en = ModType(True, choices=[True, False])
        self.modulation_fm_factor = ModType(1., uncond_update_func=self._update_fm_amp)
        self.modulation_am_amp_I = ModType(1.)
        self.modulation_am_amp_Q = ModType(0.)
        self.modulation_am_offset = ModType(0.)
        self.modulation_min_N = ModType(2**10*2)
        self.modulation_max_N = ModType(2**20)
        self.modulation_Ncycle_max = ModType(1e6)
        self.modulation_round_freq_digit = ModType(12)
        self.modulation_Nsamples_used = ModType_no_upd(0)
        self.align_status = M5dev('base.clock.alignment_status', base=self._awg, get_only=True, autoinit=False, choices=ChoiceFromEnum(keysight_ktm5300x.AlignmentStatus))
        super(keysight_M5300, self)._create_devs()

#######################################################
##    Keysight M9032 SyncModule card
#######################################################

keysight_ktm9032x = None

@register_instrument('Keysight Technologies', 'M9032A')
class keysight_M9032(keysight_M5xxx):
    """
    This controls the keysight  M9032 SyncModule card.
    Important devices:
        frequency
        amplitude_percent
        output_mode
        output_en
        align_status
    Useful method:
        sfp_open
    Address example:
           use (1, 10) for 'PXI0::CHASSIS1::SLOT10::INDEX0::INSTR'
    """
    def __init__(self, address, reset=False, options='', skip_id_test=False, verify_id=True, **kwargs):
        """ address is a tuple (chassis#, slot#)
            options is a string that can be:
                  OpenSfp 	Default='0/false'. If '1/true', the SFP will be opened immediately. Effectively identical to calling System.Sfp.Open after Initialize().
                  AllowSfpAttach 	Default='0/false'. If '1/true', an independently launched SFP may attach to this instance.
            verify_id when True (default), will test to make sure the module is of the correct type.
        """
        global keysight_ktm9032x
        keysight_ktm9032x = _delayed_import('m9032')
        self._module_class = keysight_ktm9032x.KtM9032x
        super(keysight_M9032, self).__init__(address, force_align=False, reset=reset, options=options, as_client=False,
                                             port=False, skip_id_test=skip_id_test, verify_id=verify_id, **kwargs)

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        return self._conf_helper('reference_mode', 'setup_freq_locked', 'lmkpll_locked', options)

    @locked_calling
    def show_reference_conf(self):
        m = self._module.reference
        d = dict(clk100_en=m.clk100_stm.enable, clk100_src=m.clk100_stm.source, clk100_numerator=m.clk100_stm.frequency_numerator,
                 feedback_clock=m.feedback_clock,
                 system_sync_fwdclk=m.system_sync_fwdclk.source,
                 pxi_clk10_in_en=m.pxi_clk10_in__enable,
                 in_src=m.input.source, in_src_num=m.input.frequency.numerator, in_src_den=m.input.frequency.denominator,
                 lmk_fwd_en=m.lmk_fwd_clk_out.enable, lmk_fwd_num=m.lmk_fwd_clk_out.frequency.numerator, lmk_fwd_den=m.lmk_fwd_clk_out.frequency.denominator,
                 sclk_out_en=m.sclk_out.enable, sclk_out_num=m.sclk_out.frequency.numerator, sclk_out_den=m.sclk_out.frequency.denominator,
                 dstara_fb_en=m.dstara_fb.enable, dstara_fb_num=m.dstara_fb.frequency.numerator, dstara_fb_den=m.dstara_fb.frequency.denominator,
                 dstara_freq1_en=m.dstara.frequency1.enable, dstara_freq1_num=m.dstara.frequency1.numerator, dstara_freq1_den=m.dstara.frequency1.denominator,
                 dstara_freq2_en=m.dstara.frequency2.enable, dstara_freq2_num=m.dstara.frequency2.numerator, dstara_freq2_den=m.dstara.frequency2.denominator,
                 dstara_bank0=m.dstara.get_dstara_bank(keysight_ktm9032x.DSTARABank.BANK0),
                 dstara_bank1=m.dstara.get_dstara_bank(keysight_ktm9032x.DSTARABank.BANK1),
                 dstara_bank2=m.dstara.get_dstara_bank(keysight_ktm9032x.DSTARABank.BANK2),
                 dstara_bank3=m.dstara.get_dstara_bank(keysight_ktm9032x.DSTARABank.BANK3),
                 )
        return d

    def _create_devs(self):
        apply = self._module.reference.apply
        self.reference_mode = M5dev('base.mode', base=self._module.reference,
                                    choices=ChoiceFromEnum(keysight_ktm9032x.UseCase),
                                    extra_set_after_func= lambda orig_val, obj, **options: apply())
        self.setup_freq_locked = M5dev('base.is_lmkpll_status_locked', base=self._module.reference, get_only=True)
        self.lmkpll_locked = M5dev('base.is_setup_frequency_valid', base=self._module.reference, get_only=True)
        super(keysight_M9032, self)._create_devs()


#######################################################
##    Keysight SD1 cards
#######################################################
keysightSD1 = None

class SD1_Dev(FuncDev):
    def __init__(self, *args, **kwargs):
        super(SD1_Dev, self).__init__(*args, set_exec_type='eval', **kwargs)
    def _check_return_error(self, val):
        if val < 0:
            raise RuntimeError(self.perror('Invalid return value. (%d) %s'%(val, keysightSD1.SD_Error.getErrorMessage(val))))
    def _set_write_check(self, val):
        self._check_return_error(val)
    def _get_ask_check(self, val):
        self._check_return_error(val)

@register_instrument('Keysight Technologies', 'M3302A')
class keysight_SD1(BaseInstrument):
    """
    This controls the keysight SD1 type cards (AWG, Digitizer and combo).
    Important devices:
        frequency
        amplitude_percent
        output_mode
        output_en
        align_status
    Useful method:
        sfp_open
    """
    def __init__(self, slot=None, chassis=1, model=None, serial=None, options="", skip_id_test=False, **kwargs):
        """
        provide either model+serial or slot+chassis
        chassis and slot are integers. model and serial are strings.
        chassis defaults to 1.
        model is something like 'M3302A'
        options is something like "simulate=true,HVI2=false"
        """
        global keysightSD1
        keysightSD1 = _delayed_import('SD1')
        self._is_closed = True
        self._model_number = model
        self._slot_number = slot
        self._chassis_number = chassis
        self.open(slot, chassis, model, serial, options)
        self._check_id_test(skip_id_test)
        super(keysight_SD1, self).__init__(**kwargs)

    def open(self, slot=None, chassis=1, model=None, serial=None, options=""):
        """
        provide either model+serial or slot+chassis
        With no parameters, it will reuse the previously openned module.
        chassis and slot are integers. model and serial are strings.
        chassis defaults to 1.
        model is something like 'M3302A'
        """
        self._is_closed = True
        para_None = [n is None for n in [model, serial, slot]]
        if para_None == [True]*3:
            if slot is None:
                slot_number = self._slot_number
            if chassis is None:
                chassis = self._chassis_number
            para_None = [n is None for n in [model, serial, slot, chassis]]
        if para_None != [True, True, False] and  para_None != [False, False,True]:
            raise RuntimeError('Only specify either model+serial or slot+chassis')
        m = keysightSD1.SD_Module()
        if model is not None:
            # we have model and serial
            info = lambda i: (m.getChassisByIndex(i), m.getSlotByIndex(i))
            check = lambda i: m.getProductName(i)==model and m.getSerialNumber(i)==serial
            chassis_slot =  [info(i) for i in range(m.moduleCount()) if check(i)]
            if len(chassis_slot) != 1:
                raise ValueError('Unable to find model+serial combination')
            chassis, slot = chassis_slot[0]
        mod_type_i = m.getTypeBySlot(chassis, slot)
        if mod_type_i == 2:
            mod_type = 'awg'
            instr = keysightSD1.SD_AOU()
        elif mod_type_i == 6:
            mod_type = 'dig'
            instr = keysightSD1.SD_AIN()
        elif mod_type_i == 7:
            mod_type = 'combo'
            instr = keysightSD1.SD_AIO()
        else: # possibly 9
            raise ValueError('Invalid chassis/slot. The requested card does not exist or is not handled by this driver.')
        self._instr_name = m.getProductNameBySlot(chassis, slot)
        self._instr_serial = m.getSerialNumberBySlot(chassis, slot)
        self._instr_type = mod_type
        self._instr = instr
        # The model string needs to be exact but could be shorter. It actually works to only specifi the empty string ""
        # When it works, the returned moduleId is in instr._SD_Object__handle
        error = instr.openWithOptions(self._instr_name, chassis, slot, options)
        # if error == -8080: # keysightSD1.SD_Error.SW_UPGRADE_REQUIRED
        if error == keysightSD1.SD_Error.OPENING_MODULE: # this is -8000
            raise RuntimeError("Error opening instrument in chassis: {}, slot: {}! Module probably already opened. Error code: {} - {}.".format(chassis, slot, error, keysightSD1.SD_Error.getErrorMessage(error)))
        elif error < 0:
            raise RuntimeError("Error opening instrument in chassis: {}, slot: {}! Error code: {} - {}.".format(chassis, slot, error, keysightSD1.SD_Error.getErrorMessage(error)))
        self._is_closed = False
        self._slot_numnber = slot
        self._chassis_number = chassis
        options_names = instr.getOptions('?').split('\n')
        self._instr_options = {n: instr.getOptions(n) for n in options_names}
        # memory options:
        #   M01: 16 MB = 8 MS
        #   M12: 128 MB = 60 MS (probably meant 64)
        #   M20: 2 GB = 1 GS
        nchs = self._instr_options['channels']
        if len(nchs) != 3 or nchs[0] != 'C':
            raise RuntimeError('Invalid channels options data')
        if mod_type != 'combo' and nchs[1] != 'H': # nchs is like CH4 or CH8
            raise RuntimeError('Invalid channels options data')
        if mod_type == 'combo':
            n_awg = int(nchs[1])
            n_dig = int(nchs[2])
        elif mod_type == 'awg':
            n_awg = int(nchs[2])
            n_dig = 0
        else: # dig
            n_awg = 0
            n_dig = int(nchs[2])
        self._instr_n_awg = n_awg
        self._instr_n_dig = n_dig

    def close(self):
        if not self._is_closed:
            if self._instr.isOpen():
                self._instr.close()
            self._is_closed = True

    def __del__(self):
        self.close()
        super(keysight_SD1, self).__del__()

    def idn(self):
        product= self._instr.getProductName()
        serial = self._instr.getSerialNumber()
        fw = self._instr.getFirmwareVersion().strip('\0')
        hw = self._instr.getHardwareVersion().strip('\0')
        return 'Keysight Technologies,%s,%s,fw:%s_hw:%s'%(product, serial, fw, hw)

    def _input_fullscale_set_cleanup(self, val_orig, obj, **options):
        self.input_coupling.setcache(None)
        self.input_impedance.setcache(None)

    def _create_devs(self):
        n_awg = self._instr_n_awg
        n_dig = self._instr_n_dig
        if n_awg:
            self.current_outch = MemoryDevice(1, choices=list(range(1,n_awg+1)), no_type_conv=True)
        if n_dig:
            self.current_inch = MemoryDevice(1, choices=list(range(1,n_dig+1)), no_type_conv=True)
        self.temperature = FuncDev(getdev="base.getTemperature()", base=self._instr)
        if n_dig:
            def Inch_Dev(*arg, **kwarg):
                options = kwarg.pop('options', {}).copy()
                options.update(inch=self.current_inch)
                app = kwarg.pop('options_apply', ['inch'])
                kwarg.update(options=options, options_apply=app)
                kwarg.update(base=self._instr)
                return SD1_Dev(*arg, **kwarg)
            self.input_coupling = Inch_Dev(getdev="base.channelCoupling(inch)",
                                    choices=ChoiceFromEnum(keysightSD1.AIN_Coupling, strip='AIN_COUPLING_'),
                                    doc='Use input_fullcale to change it.')
            self.input_impedance = Inch_Dev(getdev="base.channelImpedance(inch)",
                                    choices=ChoiceFromEnum(keysightSD1.AIN_Impedance, strip='AIN_IMPEDANCE_'),
                                    doc='Use input_fullcale to change it.')
            self.input_fullscale = Inch_Dev(setdev="base.channelInputConfig(inch, val, impedance, coupling)", getdev="base.channelFullScale(inch)",
                                    options=dict(inch=self.current_inch, impedance=self.input_impedance, coupling=self.input_coupling),
                                    setget=True, extra_set_after_func=ProxyMethod(self._input_fullscale_set_cleanup))
            self.input_prescaler = Inch_Dev(setdev="base.channelPrescalerConfig(inch, val)", getdev="base.channelPrescaler(inch)",
                                    choices=list(range(0, 4+1)))

        if n_awg:
            def Outch_Dev(*arg, **kwarg):
                options = kwarg.pop('options', {}).copy()
                options.update(outch=self.current_outch)
                app = kwarg.pop('options_apply', ['outch'])
                kwarg.update(options=options, options_apply=app)
                kwarg.update(base=self._instr, cache_as_get=(['outch'],), autoinit=False)
                return SD1_Dev(*arg, **kwarg)
            self.output_waveshape = Outch_Dev(setdev="base.channelWaveShape(outch, val)",
                                    choices=ChoiceFromEnum(keysightSD1.SD_Waveshapes, strip='AOU_'), doc="HiZ only available on M3302A.")
            self.output_frequency = Outch_Dev(setdev="base.channelFrequency(outch, val)")
            self.output_phase_deg = Outch_Dev(setdev="base.channelPhase(outch, val)")
            self.output_amplitude_Vpk = Outch_Dev(setdev="base.channelAmplitude(outch, val)", min=-1.5, max=1.5)
            self.output_offset = Outch_Dev(setdev="base.channelOffset(outch, val)", min=-1.5, max=1.5)
        if self._instr_options['clock'] == 'CLV':
            if self._instr_type == 'combo':
                self.input_clock_freq = SD1_Dev(setdev='base.clockSetFrequency(2, val)', getdev='base.clockGetFrequence(2)')
                self.output_clock_freq = SD1_Dev(setdev='base.clockSetFrequency(1, val)', getdev='base.clockGetFrequence(1)')
            elif n_awg:
                self.output_clock_freq = SD1_Dev(setdev='base.clockSetFrequency(val)', getdev='base.clockGetFrequence()')
            else:
                self.input_clock_freq = SD1_Dev(setdev='base.clockSetFrequency(val)', getdev='base.clockGetFrequence()')
            self.clock_sync_freq = SD1_Dev(setdev='base.clockSetFrequency(1, val)', getdev='base.clockGetFrequence(1)')
        #self.alias = self.output_offset
        super(keysight_SD1, self)._create_devs()

#############################
# m = instruments.keysight_chassis._delayed_import('chassis')
# mm = m.KtMPxiChassis('PXI0::1::BACKPLANE', True, False, '')
# mm.TemperatureSensors['TS1'].Temperature
# mm.TemperatureSensors.Alarm.get_MaxTemperature
# mm.ReferenceClock.Source.ToString()
# mm.ReferenceClock.Source.value__
# int(mm.ReferenceClock.Source)
#  # enum m.RefClockSource

# sys.path.append(r'C:\Program Files\IVI Foundation\IVI\Bin\Primary Interop Assemblies')
# clr.AddReference('Keysight.KtM9546x.Interop')
# import Keysight.KtM9546x.Interop
# m = Keysight.KtM9546x.Interop.KtM9546x()
# m.Initialize('PXI0::CHASSIS1::SLOT19::INDEX0::INSTR', False, False, "")
# m.Reference.HighFrequencyReferenceOutput.ActiveHighFrequencyReferenceOutput='HF_Out2'
# m.Reference.HighFrequencyReferenceOutput.OutputFrequency.ToString()
# m.Close()
