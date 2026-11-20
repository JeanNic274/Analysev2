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

import functools
import sys
import time
import ctypes
import numpy as np
from collections import defaultdict
import types
import weakref

from ..instruments_base import BaseInstrument, BaseDevice, locked_calling,\
                                ChoiceSimpleMap, ProxyMethod, MemoryDevice,\
                                Base2Device, MemoryDevice_update, ChoiceValMap,\
                                OrderedDict, ChoiceBase, _retry_wait, ReadvalDev,\
                                _sleep_signal_context_manager, mainStatusLine, sleep

from ..instruments_registry import register_instrument, add_to_instruments

from ..types import StructureImproved, UnionImproved, dict_improved

from ..comp2to3 import fu, string_bytes_types, is_py2, IntEnum

pyAndorSDK2 = None
AndorSDKwrapper = None
AndorSDKwrapper_instance = None
def import_camera_sdk():
    global pyAndorSDK2, AndorSDKwrapper, AndorSDKwrapper_instance
    try:
        import pyAndorSDK2
        import pyAndorSDK2.atmcd_errors
        import pyAndorSDK2.atmcd_acquisition
        import pyAndorSDK2.atmcd_codes
        import pyAndorSDK2.atmcd_capabilities
    except ImportError:
        raise RuntimeError(r"Package pyAndorSDK2 needs to be installed. Probably need to run (from within C:\Program Files\Andor SDK\Python\pyAndorSDK2): python setup.py install")

    # the pyAndorSDK2.atmcd module is overloaded in init by pyAndorSDK2.atmcd.atmcd
    # so fetch it and keep it
    if AndorSDKwrapper_instance is not None:
        return AndorSDKwrapper_instance
    pyAndorSDK2._atmcd = sys.modules['pyAndorSDK2.atmcd']
    # Generate a wrapper class that handles return values better and
    # it allows using the original func by using _bypass=True
    class AndorSDKwrapper(pyAndorSDK2.atmcd):
        _noraise_ = ['GetTemperature', 'GetTemperatureF']
        _notwrapped = ['dll', 'handle_return', 'acquire', 'acquire_series']
        def __init__(self):
            self._cached_funcs = {}
            super(AndorSDKwrapper, self).__init__()
        def __getattribute__(self, name):
            attr = super(AndorSDKwrapper, self).__getattribute__(name)
            if name.startswith('_') or name in self._notwrapped:
                return attr
            func = self._cached_funcs.get(name, None)
            if func is not None:
                return func
            @functools.wraps(attr)
            def newfunc(*args, **kwargs):
                _bypass = kwargs.pop('_bypass', False)
                ret = attr(*args, **kwargs)
                if _bypass:
                    return ret
                if isinstance(ret, tuple):
                    retcode = ret[0]
                    ret = ret[1:]
                else:
                    retcode = ret
                    ret = []
                error_codes = pyAndorSDK2.atmcd_errors.Error_Codes
                try:
                    code = error_codes(retcode)
                except ValueError:
                    code = "Unknown error (%d)"%retcode
                if code != error_codes.DRV_SUCCESS:
                    if name not in self._noraise_:
                        raise RuntimeError('Error calling %s, return value is %r.'%(name, code))
                if name in self._noraise_:
                    ret = (code,) + ret
                if len(ret) == 0:
                    ret = None
                elif len(ret) == 1:
                    ret = ret[0]
                return ret
            self._cached_funcs[name] = newfunc
            return newfunc
        # The GetAcquiredData from the 0.1 version is wrong
        def GetAcquiredData(self, size):
            csize = ctypes.c_ulong(size)
            carr = (ctypes.c_int*size)()
            ret = self.dll.GetAcquiredData(ctypes.byref(carr), csize)
            return (ret, np.ctypeslib.as_array(carr))
        GetAcquiredData.__doc__ = pyAndorSDK2.atmcd.GetAcquiredData.__doc__
        # The GetAcquiredData from the 0.1 version is wrong
        def GetAcquiredData16(self, size):
            csize = ctypes.c_ulong(size)
            carr = (ctypes.c_short*size)()
            ret = self.dll.GetAcquiredData(ctypes.byref(carr), csize)
            return (ret, np.ctypeslib.as_array(carr))
        GetAcquiredData16.__doc__ = pyAndorSDK2.atmcd.GetAcquiredData16.__doc__
        # The GetAcquiredData from the 0.1 version is wrong
        def SetRandomTracks(self, numTracks, areas):
            cnumTracks = ctypes.c_int(numTracks)
            careas = (ctypes.c_int * (numTracks*2))(*areas)
            ret = self.dll.SetRandomTracks(cnumTracks, careas)
            return (ret)
        SetRandomTracks.__doc__ = pyAndorSDK2.atmcd.SetRandomTracks.__doc__
    AndorSDKwrapper_instance = AndorSDKwrapper()
    return AndorSDKwrapper_instance


class Andor_Choice_Enum(ChoiceSimpleMap):
    def __init__(self, enum, lower=True, remove=None, **kwargs):
        def clean(name):
            if remove is not None:
                if name.startswith(remove):
                    name = name[len(remove):]
            if lower:
                name = name.lower()
            return name
        d = {v.value: clean(v.name) for v in enum}
        super(Andor_Choice_Enum, self).__init__(d, **kwargs)


class AndorDev(Base2Device):
    def __init__(self, read_func=None, write_func=None, force_type=None,
                 scale=None, generate_arg=None, **kwargs):
        """
        generate_arg is a function (dev_obj, val, options, isget=False) that generates the args to be used.
               the isget parameter will be True for get
        """
        self.force_type = force_type
        self.generate_arg = generate_arg
        self.scale = scale
        if write_func is not None and read_func is None:
            kwargs['cache_as_get'] = True
        super(AndorDev, self).__init__(**kwargs)
        self.read_func = read_func
        self.write_func = write_func
        self._getdev_p = True
        if write_func is not None:
            self._setdev_p = True

    def _set_write(self, val, options):
        if self.scale is not None:
            val = val / self.scale
        if self.force_type is not None:
            val = self.force_type(val)
        if isinstance(self.choices, ChoiceBase):
            val = self.choices.tostr(val)
        if self.generate_arg is not None:
            vals = self.generate_arg(self, val, options, isget=False)
        else:
            vals = (val,)
        args = vals
        self.write_func(*args)

    def _get_ask(self, options):
        if self.generate_arg is not None:
            args = self.generate_arg(self, None, options, isget=True)
        else:
            args = ()
        val = self.read_func(*args)
        if self.scale is not None:
            val = val * self.scale
        if isinstance(self.choices, ChoiceBase):
            val = self.choices(val)
        return val


#######################################################
##    Andor iDus
#######################################################

@register_instrument('Andor', 'iDus')
class andor_iDus(BaseInstrument):
    """
    This controls the Andor iDus camera
    Useful devices:
        readval
        fetch
        cooler_en
        temperature
        temperature_last_status
        status
        shutter
    Useful methods:
        conf
        do_warm_up
        cool_device
        get_timings
        set_spectro_instr
    """
    def __init__(self, camera_index=0, cooler_temp=None, spectro_instr=None, shutter_init=False, shutter_params=dict(ttl='high', close_time=.1, open_time=.1, on_close=False), **kwargs):
        """
        camera_index can be used to select a camera if more than one is connected.
        cooler_temp if given will start the cooler at that temperature
        spectro_instr can be used to set the spectro_meter instrument that allows
                      it to obtain a calibrated scale. It should be a Kymera spectrometer.
        shutter_init will be the state if the shutter after loading. Can be True, False or None
                   None does not change the shutter state, but it will probably be closed.
        shutter_params is a dictionnary of ttl which is 'high' or 'low' and close_time, open_time in seconds
                      and on_close which will be the state when unloading this instrument.
        """
        self._sdk = import_camera_sdk()
        if camera_index != 0:
            n_camera = self._sdk.GetAvailableCameras()
            if camera_index >= n_camera:
                raise ValueError("camera_index is too large. Max value is currently %d"%(n_camera-1))
        # In case a discover was done, force selection
        hndl = self._sdk.GetCameraHandle(camera_index)
        # To handle more than one camera inside the same program
        # we would need to SetCurrentCamera before every call
        self._sdk.SetCurrentCamera(hndl)
        self._camera_handle = hndl
        self._camera_index = camera_index
        self._sdk.Initialize("")
        self._track_options_cache = defaultdict(lambda : None)
        self._horiz_binning_cache = defaultdict(lambda : 1)
        self._vert_binning_cache = defaultdict(lambda : 1)
        self._multitrack_conf_result = dict_improved(bottom=0, gap=0)
        super(andor_iDus, self).__init__(**kwargs)
        self._last_t_status = None
        if cooler_temp is not None:
            self.cool_device(cooler_temp, wait=False)
        self._initialize()
        self._shutter_params = shutter_params
        if shutter_init is not None:
            self.shutter.set(shutter_init)
        self._async_mode = 'poll'
        self._last_n_acq_img = -1
        self.set_spectro_instr(spectro_instr)

    @staticmethod
    def discover(_sdk=None):
        """
        returns a list of idn. To select one to use, use its index for the camera_index param.
        Note that this can be slow. All cameras need to be initialized to read the idn.
        """
        if _sdk is None:
            sdk = import_camera_sdk()
        else:
            sdk = _sdk
        ret = []
        n_camera = sdk.GetAvailableCameras()
        for i in range(n_camera):
            hndl = sdk.GetCameraHandle(i)
            sdk.SetCurrentCamera(hndl)
            sdk.Initialize("")
            idn = andor_iDus.idn(None, sdk)
            sdk.ShutDown()
            ret.append(idn)
        return ret

    def set_spectro_instr(self, spectro_instr):
        """ set the spectrometer pyHegel instrument. It should be an Andor Kymera instrument.
        """
        self._spectro_instr = spectro_instr
        if spectro_instr is not None:
            spectro_instr.sensor_pixel_num.set(self._detector.Nxy[0])
            spectro_instr.sensor_pixel_width_um.set(self._detector.pixel_size_xy_um[0])

    def __del__(self):
        on_close = self._shutter_params['on_close']
        ## the self.shutter fails because of weakly references have been removed.
        #self.shutter.set(on_close)
        ch = self.shutter.choices
        args = self._generate_shutter_args(None, ch.tostr(on_close), None)
        self._sdk.SetShutter(*args)
        self._sdk.ShutDown()
        super(andor_iDus, self).__del__()

    def idn(self, _sdk=None):
        if _sdk is None:
            _sdk = self._sdk
        dllver = _sdk.GetSoftwareVersion()[4:]
        sdk = fu(_sdk.GetVersionInfo(0x40000000, 1024).value)
        driver = fu(_sdk.GetVersionInfo(0x40000001, 1024).value)
        usbfw = _sdk.GetUSBDeviceDetails()[2]
        fw = _sdk.GetHardwareVersion()[4]
        serial = _sdk.GetCameraSerialNumber()
        camera_type = _sdk.GetCapabilities().ulCameraType
        ct = pyAndorSDK2.atmcd_capabilities.cameratype(camera_type)
        ct_name = ct.name.replace('AC_CAMERATYPE_', '')
        head = fu(_sdk.GetHeadModel()).replace(',', '')
        model = ct_name + ' ' + head
        python_sdk = pyAndorSDK2.__version__
        ver = 'fw:%i_drv:%s_sdk:%s_usb:%d_dllver:%d.%d_pyver:%s'%(fw, driver, sdk, usbfw, dllver[1], dllver[0], python_sdk)
        return "Andor,%s,%s,%s"%(model, serial, ver)

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        base = ['conf=%s'%self.conf()]
        base.extend(self._conf_helper('cooler_en', 'temperature', 'temperature_last_status',
                                      'status', 'cosmic_filter_en', 'shutter',
                                      'vertical_amplitude', 'vertical_speed_us'))
        base.append('detector=%s'%self._detector)
        base.append('timings=%s'%self.get_timings())
        if self._spectro_instr is not None:
            base.append('spectro_conf:=[%s]'%(', '.join(self._spectro_instr._current_config())))
        return base + self._conf_helper(options)

    def prepare_acquisition(self):
        self._sdk.PrepareAcquisition()

    def start_acquisition(self):
        self._sdk.StartAcquisition()

    def stop_acquisition(self):
        self._sdk.AbortAcquisition()

    def _cooler_en_setdev(self, val):
        if val:
            self._sdk.CoolerON()
        else:
            self._sdk.CoolerOFF()

    def _cooler_en_getdev(self):
        return bool(self._sdk.IsCoolerOn())

    def get_capabilities(self):
        d = self._sdk.GetCapabilities()
        def parse_flags(val, enum_type):
            ret = []
            for enum_val in enum_type:
                if val & enum_val:
                    ret.append(enum_val)
            return ret
        def parse_enum(val, enum_type):
            try:
                return enum_type(val)
            except ValueError:
                return "??"
        # structure fields:
        # ulSize is the structure size
        conf = [('ulSize', None, None, None),
                ('ulCameraType', 'camera_type', parse_enum, pyAndorSDK2.atmcd_capabilities.cameratype),
                ('ulAcqModes', 'acq_modes', parse_flags, pyAndorSDK2.atmcd_capabilities.acquistionModes),
                ('ulReadModes', 'read_modes', parse_flags, pyAndorSDK2.atmcd_capabilities.readmodes),
                ('ulFTReadModes', 'FT_read_modes', parse_flags, pyAndorSDK2.atmcd_capabilities.readmodes),
                ('ulPixelMode', 'pixel_mode', parse_flags, pyAndorSDK2.atmcd_capabilities.PixelModes),
                ('ulTriggerModes', 'trigger_modes', parse_flags, pyAndorSDK2.atmcd_capabilities.triggermodes),
                ('ulFeatures', 'features', parse_flags, pyAndorSDK2.atmcd_capabilities.Features),
                ('ulFeatures2', 'features2', parse_flags, pyAndorSDK2.atmcd_capabilities.Features2),
                ('ulEMGainCapability', 'em_gain_capabilities', parse_flags, pyAndorSDK2.atmcd_capabilities.EmGainModes),
                ('ulSetFunctions', 'set_functions', parse_flags, pyAndorSDK2.atmcd_capabilities.SetFunctions),
                ('ulGetFunctions', 'get_functions', parse_flags, pyAndorSDK2.atmcd_capabilities.GetFunctions),
                ('ulPCICard', 'pci_card_max_speed', None, None)]
        ret = []
        snames = []
        for struct_name, name, func, arg in conf:
            snames.append(struct_name)
            if name is None:
                continue
            val = getattr(d, struct_name)
            if func is None:
                ret.append((name, val))
            else:
                ret.append((name, func(val, arg)))
                ret.append((name+'_raw', val))
        for v in d._fields_:
            if v[0] not in snames:
                ret.append((v[0], getattr(d, v[0])))
        return dict_improved(ret)

    def _status_getdev(self):
        status = self._sdk.GetStatus()
        return pyAndorSDK2.atmcd_errors.Error_Codes(status)

    def _temperature_getdev(self):
        Tstatus, temp = self._sdk.GetTemperatureF()
        self._last_t_status = Tstatus
        return temp

    def _temperature_last_status_getdev(self, readnow=False):
        """ returns the temperature status.
        It returns the one obtained during the last temperature get by default.
        if option readnow=True is given, the temperature is read, so the status
        will be a new one, and the temperature cache will be updated.
        """
        if readnow:
            self.temperature.get()
        return self._last_t_status

    def wait_for_cooler_stable(self, stop_below_temp=None, stop_above_temp=None):
        """ waits until temp is below stop_below_temp or it is stabilized """
        target = self.temperature_setpoint.get()
        if stop_below_temp is not None:
            extra = '(target=%s, stop_below=%s)'%(target, stop_below_temp)
        elif stop_above_temp is not None:
            extra = '(target=%s, stop_above=%s)'%(target, stop_above_temp)
        else:
            extra = '(target=%s)'%target
        start = time.time()
        with mainStatusLine.new() as progress:
            while True:
                status, temp = self.temperature_raw.get()
                stable = status == pyAndorSDK2.atmcd_errors.Error_Codes.DRV_TEMPERATURE_STABILIZED
                below = temp < stop_below_temp if stop_below_temp is not None else False
                above = temp > stop_above_temp if stop_above_temp is not None else False
                progress(('Waiting %.1f min for cooler T = %.2f C '%((time.time()-start)/60., temp)) + extra)
                if stable or below or above:
                    break
                sleep(1)

    def cool_device(self, setpoint=0, wait=True):
        self.temperature_setpoint.set(setpoint)
        self.cooler_en.set(True)
        if wait:
            self.wait_for_cooler_stable()

    def do_warm_up(self, at_least=-20, wait=True):
        self.cooler_en.set(False)
        if wait:
            self.wait_for_cooler_stable(stop_above_temp=at_least)

    # TODO deal with fast_kinetics,
    #      also change Vreadout Hreadout, preampgain
    #      test FrameTransfer (I don't have it)
    #      and deal with cropped Images
    def _initialize(self):
        """ This is to provide defaults for all the modes """
        Nx, Ny = self._detector.Nxy
        self.conf(exposure_time=0, acc_N=1, acc_cycle_time=.0, kinetics_N=1, kinetics_cycle_time=1, trigger_mode='internal')
        # When not initialized, single probaby reads just one line, which one?
        #self.conf('single_scan', 'single_track', horiz_binning=1, vert_binning=None, track_options=[Ny//2, 1])
        self.conf('single_scan', 'single_track', horiz_binning=1, vert_binning=None, track_options=[Ny//2, Ny])
        # When not initialized, multi probaby reads just one line, which one?
        #self.conf('single_scan', 'multi_track', horiz_binning=1, vert_binning=None, track_options=[1, 1, 0])
        self.conf('single_scan', 'multi_track', horiz_binning=1, vert_binning=None, track_options=[1, Ny, 0], quiet=True)
        # When not initialized, random_track does not work.
        self.conf('single_scan', 'random_track', horiz_binning=1, vert_binning=None, track_options=[1, Ny])
        # image does not work without a default. This first one is the same as full_vertical_binning. The other a full image
        #self.conf('single_scan', 'image', horiz_binning=1, vert_binning=256, track_options=[1, 1024, 1, 256])
        self.conf('single_scan', 'image', horiz_binning=1, vert_binning=1, track_options='full')
        self.conf('single_scan', 'full_vertical_binning', horiz_binning=1, vert_binning=None, track_options=None)
        #  All of the above are equivalent to full_vertical_binning returning the same noise (dark count at T=-5 C) except for
        #   full_vertical_binning, because that one has a shorted read time.
        #  That test was done with an exposure time of .1 s
        # Without any initialization, the default seems to be full resolution image with 1e-5 exposure.

    def conf(self, acq_mode=None, read_mode=None, exposure_time=None, acc_N=None, acc_cycle_time=None,
             kinetics_N=None, kinetics_cycle_time=None, horiz_binning=None, vert_binning=None,
             trigger_mode=None, track_options=None, quiet=False):
        """
        When None of the values are given, returns the current configuration.
        Otherwise it changes only the given parameters.
        acq_mode can be: 'single_scan', 'accumulate', 'kinetics', 'fast_kinetics', 'run_till_abort'
        read_mode can be: 'full_vertical_binning', 'multi_track', 'random_track', 'single_track', 'image'
        trigger_mode can be: 'internal', 'external', 'external_start', 'external_exposure_bulb',
                            'external_fvb_em', 'software_trigger', 'external_charge_shifting'
                you might also want to change the trigger_level and trigger_falling_en devices.
        All modes requires exposure_time
        For accumulate, also provide acc_N and acc_cycle_time (for internal trigger_mode)
        For kinetics, also provide acc_N, acc_cycle_time, kinetics_N, kinetics_cycle_time
                 Note that kinetics_cycle_time seems to be overwriting acc_cycle_time
                 in the SDK v2.104.30065.0
        For fast_kinetics, also provide  kinetics_N, kinetics_cycle_time
        For run_till_abort, also provide kinetics_cycle_time
        track_options depends on read_mode:
            'full_vertical_binning': only None
            'single_track': [center, height]
            'multi_track': [N, height, offset]
            'random_track': [start1, stop1, start2, stop2, ..., startN, stopN]
            'image': [horiz_start, horiz_end, vert_start, vert_end] or "full"
        horiz_binning, vert_binning and track_options are remembered depending on read_mode.
        """
        lcls = locals().copy()
        lcls.pop('self')
        quiet = lcls.pop('quiet')
        d_in = [("acq_mode", self.acquisition_mode),
                 ("read_mode", self.read_mode),
                 ("exposure_time", self.exposure_time),
                 ("acc_N", self.accumulation_number),
                 ("acc_cycle_time", self.accumulation_cycle_time),
                 ("kinetics_N", self.kinetics_number),
                 ("kinetics_cycle_time", self.kinetics_cycle_time),
                 ("trigger_mode", self.trigger_mode),
                 ("horiz_binning", None),
                 ("vert_binning", None),
                 ("track_options", None)]
        d = OrderedDict(d_in)
        if all([v is None for v in lcls.values()]):
            # Show current conf
            data = []
            rd_mode = None
            for k, v in d.items():
                if v is not None:
                    val = v.get()
                    data.append((k, val))
                    if k == 'read_mode':
                        rd_mode = val
                else:
                    if k == 'track_options':
                        # this is read after rd_mode
                        data.append((k, self._track_options_cache[rd_mode]))
                    else: # "horiz_binning"
                        data.append((k, self._horiz_binning_cache[rd_mode]))
            return dict_improved(data)
        # configure
        rd_mode = self.read_mode.get()
        for k, v in d.items():
            val = lcls[k]
            if val is not None:
                if v is not None:
                    v.set(val)
                    if k == 'read_mode':
                        rd_mode = val
                elif k == 'track_options':
                    if rd_mode == 'full_vertical_binning':
                        if val is not None:
                            raise ValueError('full_vertical_binning read mode only handles None for track_options')
                    elif rd_mode == 'single_track':
                        if not isinstance(val, (list, tuple, np.ndarray)) or len(val) != 2:
                            raise ValueError('Invalid format for track_options in single_track read_mode. It needs to be [center, height]')
                        self._sdk.SetSingleTrack(*val)
                    elif rd_mode == 'multi_track':
                        if not isinstance(val, (list, tuple, np.ndarray)) or len(val) != 3:
                            raise ValueError('Invalid format for track_options in multi_track read_mode. It needs to be [N, height, offset]')
                        bottom, gap = self._sdk.SetMultiTrack(*val)
                        # self._sdk.SetMultiTrackHRange(iStart, iEnd)
                        if not quiet:
                            print("multi-track conf result: bottom=%s,  gap=%s"%(bottom, gap))
                        self._multi_track_conf = dict_improved(bottom=bottom, gap=gap)
                        self._multitrack_conf_result = dict_improved(bottom=bottom, gap=gap)
                    elif rd_mode == 'random_track':
                        if not isinstance(val, (list, tuple, np.ndarray)) or len(val) < 2 or len(val)%2 != 0:
                            raise ValueError('Invalid format for track_options in random_track read_mode. It needs to be [start1, stop1, start2, stop2, ..., startN, stopN]')
                        self._sdk.SetRandomTracks(len(val)//2, val)
                        # could look at using SetComplexImage instead.
                    elif rd_mode == 'image':
                        if val == 'full':
                            Nx, Ny = self._detector.Nxy
                            val = [1, Nx, 1, Ny]
                        if not isinstance(val, (list, tuple, np.ndarray)) or len(val) != 4:
                            raise ValueError('Invalid format for track_options in image read_mode. It needs to be [horiz_start, horiz_stop, vert_start, vert_end]')
                        # the rest is handled later
                    else:
                        raise ValueError('handling track_options for read_mode %r is not implemented'%rd_mode)
                    self._track_options_cache[rd_mode] = val
                elif k == 'horiz_binning':
                    if rd_mode == 'full_vertical_binning':
                        self._sdk.SetFVBHBin(val)
                    elif rd_mode == 'single_track':
                        self._sdk.SetSingleTrackHBin(val)
                    elif rd_mode == 'multi_track':
                        self._sdk.SetMultiTrackHBin(val)
                    elif rd_mode == 'random_track':
                        self._sdk.SetCustomTrackHBin(val)
                    elif rd_mode == 'image':
                        # handled later
                        pass
                    else:
                        raise ValueError('handling horiz_binning for read_mode %r is not implemented'%rd_mode)
                    self._horiz_binning_cache[rd_mode] = val
                elif k == 'vert_binning':
                    if rd_mode != 'image':
                        if val is not None:
                            raise ValueError('%s read mode only handles None for vert_binning'%rd_mode)
                    else:
                        # handled later
                        pass
                    self._vert_binning_cache[rd_mode] = val
                else:
                    raise RuntimeError('Got an unexpected key.')
        if rd_mode == 'image':
            hbin = self._horiz_binning_cache[rd_mode]
            vbin = self._vert_binning_cache[rd_mode]
            val = self._track_options_cache[rd_mode]
            if val is None:
                raise ValueError('For image read_mode you need to have provided a track_options. It needs to be [horiz_start, horiz_end, vert_start, vert_end], or "full"')
            self._sdk.SetImage(hbin, vbin, *val)
        # exposure_time, accumulate_time, kinetics_time = self._sdk.GetAcquisitionTimings()
        # read_time = self._sdk.GetReadOutTime()
        # # timings in s
        # self._timings = dict_improved(exposure=exposure_time, accumulate=accumulate_time, kinetics=kinetics_time, read=read_time)

        #SetSingleTrack(center, height)
        #SetSingleTrackHBin
        #SetMultiTrack(N, height, offset). returns first_row and gap_size
        #SetRandomTracks( # pass ntrack=len(array)//2 and array of [start1, stop1, start2, stop2]
        #SetCustomTrackHBin(bin_size)
        #SetComplexImage(int numAreas, int* areas), areas for each track: top, bottom, left, right, horiz_bin, vert_bin
        #SetImage(n_px_horiz_bin, n_px_vert_bin, horiz_start, horiz_end, vert_start, vert_end)
        #  SetIsolatedCropMode(crop_mode_en, cropheight, cropwidth, vertical_binning, horiz_binning)
        # acq Runtill abord
        #  SetExposureTime
        #  SetRingExposureTimes(int numTimes, float* times)
        #  SetKineticCycleTime
        # Trigger
        #  SetTriggerInvert(falling_en)
        #  SetTriggerLevel
        #  SetTriggerMode
        # SetFrameTransferMode(frame_trans_en)

    def _async_detect_poll_helper(self):
        if self._last_n_acq_img != -1:
            n_acq = self._sdk.GetTotalNumberImagesAcquired()
            return n_acq > self._last_n_acq_img
        status = self.status.get()
        codes = pyAndorSDK2.atmcd_errors.Error_Codes
        if status == codes.DRV_IDLE:
            return True
        elif status in [codes.DRV_ACQUIRING, codes.DRV_TEMPCYCLE]:
            return False
        raise RuntimeError('Problem when detecting state. Got %r '%status)

    @locked_calling
    def _async_trig(self):
        super(andor_iDus, self)._async_trig()
        if self._async_mode == 'wait':
            return
        # make sure previous one is stopped
        status = self.status.get()
        codes = pyAndorSDK2.atmcd_errors.Error_Codes
        run_till_abort = self.acquisition_mode.get() == 'run_till_abort'
        if status == codes.DRV_ACQUIRING and not run_till_abort:
            try:
                self.stop_acquisition()
            except RuntimeError:
                # can error it if it is not actually running.
                pass
        if run_till_abort:
            self._last_n_acq_img = self._sdk.GetTotalNumberImagesAcquired()
            if status == codes.DRV_IDLE:
                self.start_acquisition()
        else:
            self._last_n_acq_img = -1
            self.start_acquisition()

    def _async_detect(self, max_time=.5):
        if self._async_mode not in ['wait', 'poll']:
            raise RuntimeError('Invalid async_mode selected')
        if self._async_mode == 'wait':
            return super(andor_iDus, self)._async_detect(max_time)
        elif _retry_wait(self._async_detect_poll_helper, max_time, delay=0.05):
            return True
        return False

    def _acq_size(self):
        acq_mode = self.acquisition_mode.get()
        rd_mode = self.read_mode.get()
        n_repeat = 1
        Nx, Ny = self._detector.Nxy
        hbin = self._horiz_binning_cache[rd_mode]
        vbin = self._vert_binning_cache[rd_mode]
        track_opt = self._track_options_cache[rd_mode]
        if acq_mode in ['kinetics', 'fast_kinetics']:
            n_repeat = self.kinetics_number.get()
        if rd_mode in ['full_vertical_binning', 'single_track']:
            Ny = 1
            Nx = Nx//hbin
        elif rd_mode == 'multi_track':
            Ny = track_opt[0]
            Nx = Nx//hbin
        elif rd_mode == 'random_track':
            Ny = len(track_opt)//2
            Nx = Nx//hbin
        else: #rd_image == 'image'
            hs, he, vs, ve = track_opt
            Nx = (he - hs + 1)//hbin
            Ny = (ve - vs + 1)//vbin
        return n_repeat, Ny, Nx

    def get_timings(self):
        exposure_time, accumulate_time, kinetics_time = self._sdk.GetAcquisitionTimings()
        read_time = self._sdk.GetReadOutTime()
        clean_time = self._sdk.GetKeepCleanTime()
        # timings in s
        self._timings = dict_improved(exposure=exposure_time, accumulate=accumulate_time,
                                      kinetics=kinetics_time, read=read_time, clean=clean_time)
        return self._timings

#      To read data:
#           GetAcquiredData  reads all after an acquisition is complete
#           GetOldestImage, GetMostRecentImage, GetImages
#                 read from 48M circular buffer (can be used while taking data)
#                 GetOldestImage removes the data from the buffer.
#                 idus._sdk.GetNumberAvailableImages, idus._sdk.GetNumberNewImages
#      The max data I have seen is 2**16 -1 so it is better to use the 32 btit version of the functions
#      The 16 bit version is signed so it returns negative counts (it is stil correct if cast to uint16)

    def _fetch_getformat(self, **kwarg):
        xaxis = kwarg.get('xaxis', 'auto')
        if xaxis == 'auto':
            xaxis = self._spectro_instr is not None
        if xaxis == True:
            multi = ['wavekength(nm)']
        else:
            multi = []
        multi += ['rows...']
        multi = tuple(multi)
        fmt = self.fetch._format
        fmt.update(multi=multi, xaxis=xaxis)
        return BaseDevice.getformat(self.fetch, **kwarg)


    def _fetch_getdev(self, read='newest', xaxis='auto', bkg_rem=None):
        """ read: this option is only used when acq_mnode is 'run_till_abort'
                  it cnb be 'oldest', to read the oldest image.
                  it can be 'newest', to read the newest image.
                  it can be 'all', to read all the images
                  it can be n to read at most the oldest n images
                  it can be -n to read at most the newest n images
            xaxis: if True it will add as the first dimension of the data the
                   wavelengths from calculated from the spectrometer
                   if False it does not.
                   if 'auto' it adds it only if a spectrometer is present.
            bkg_rem if not None is a background curve that is substracted from
                   all data. It needs to be the same shape as the data, without the x-axis
            if your data is 3D, you need to save it as bin (like bin=".npy")
        """
        n_repeat, Ny, Nx = self._acq_size()
        if xaxis == 'auto':
            xaxis = self._spectro_instr is not None
        if xaxis:
            if self._spectro_instr is None:
                raise ValueError('Unable to obtain x-axis since spectro_instr is not set')
            xaxis = self._spectro_instr.sensor_wavelengths_nm.get()
            rd_mode = self.read_mode.getcache()
            Nx, _ = self._detector.Nxy
            hbin = self._horiz_binning_cache[rd_mode]
            track_opt = self._track_options_cache[rd_mode]
            if rd_mode in ['full_vertical_binning', 'single_track', 'multi_track', 'random_track']:
                # we presume the wavelength is that of the beginning of the bin
                # Some test seem to show that the first bin shows the start and the last
                # bin shows the end. I don't know how to deal with that!
                # So just presume it is the beginning of a bin.
                xaxis = xaxis[::hbin]
            else: #rd_image == 'image'
                hs, he, vs, ve = track_opt
                xaxis = xaxis[hs-1:he:hbin]
        else:
            xaxis = None
        if self.acquisition_mode.get() == 'run_till_abort':
            N = Ny * Nx
            if read == 'newest':
                n_repeat = 1
                ret = self._sdk.GetMostRecentImage(N)
            elif read == 'oldest':
                n_repeat = 1
                ret = self._sdk.GetOldestImage(N)
            elif read == 'all':
                first, last = self._sdk.GetNumberNewImages()
                n_repeat = last-first + 1
                ret, valid_first, valid_last = self._sdk.GetImages(first, last, N*n_repeat)
            else:
                if read < 0:
                    # This allows rereading data
                    first, last = self._sdk.GetNumberAvailableImages()
                    last = first - 1 + min(last-first + 1, -read)
                elif read > 0:
                    first, last = self._sdk.GetNumberNewImages()
                    first = last + 1 - min(last-first + 1, read)
                else:
                    raise ValueError('Invalid read value')
                n_repeat = last - first + 1
                ret, valid_first, valid_last = self._sdk.GetImages(first, last, N*n_repeat)
        else:
            N = n_repeat * Ny * Nx
            n_acq = self._sdk.GetTotalNumberImagesAcquired()
            # cosmic filter makes n_acq returns the the number of acc instead of 1
            if not self.cosmic_filter_en.get() and n_acq != n_repeat:
                raise RuntimeError('Did not receive all the expected images')
            ret = self._sdk.GetAcquiredData(N) # this reads all the data in the Buffer
        # buf_size_N = self._sdk.GetSizeOfCircularBuffer()
        # complete_acq, complete_kinetic = self._sdk.GetAcquisitionProgress()
        #
        sh = (Nx,)
        if xaxis is not None:
            Ny += 1
        if Ny != 1:
            sh = (Ny, Nx)
        if n_repeat != 1:
            sh = (n_repeat,) + sh
        if xaxis is not None:
            oldsh = sh[:-2] + (sh[-2]-1, ) + (sh[-1], )
            ret.shape = oldsh
            new_ret = np.empty(sh)
            new_ret[...,0,:] = xaxis
            new_ret[...,1:,:] = ret
            if bkg_rem is not None:
                new_ret[...,1:,:] -= bkg_rem
            ret = new_ret
        else:
            ret.shape = sh
            if bkg_rem is not None:
                ret -= bkg_rem
        return ret

    def _generate_shutter_args(self, dev_obj, val, options, isget=False):
        typ_ch = ChoiceSimpleMap({0:'low', 1:'high'})
        params = self._shutter_params
        typ = typ_ch.tostr(params['ttl'])
        closing = int(params['close_time'] * 1e3)
        opening = int(params['open_time'] * 1e3)
        return typ, val, closing, opening

    def _create_devs(self):
        Nxy = self._sdk.GetDetector()
        pixel_size = self._sdk.GetPixelSize()
        self._detector = dict_improved(Nxy=Nxy, pixel_size_xy_um=pixel_size)
        self.temperature_raw = AndorDev(self._sdk.GetTemperatureF)
        self._devwrap('temperature')
        self._devwrap('temperature_last_status')
        Tmin, Tmax = self._sdk.GetTemperatureRange()
        self.temperature_setpoint = AndorDev(write_func=self._sdk.SetTemperature, force_type=int, min=Tmin, max=Tmax)
        ch_acq_modes = Andor_Choice_Enum(pyAndorSDK2.atmcd_codes.Acquisition_Mode)
        self.acquisition_mode = AndorDev(write_func=self._sdk.SetAcquisitionMode, choices=ch_acq_modes)
        ch_read_modes = Andor_Choice_Enum(pyAndorSDK2.atmcd_codes.Read_Mode)
        self.read_mode = AndorDev(write_func=self._sdk.SetReadMode, choices=ch_read_modes)
        ch_trigger_modes = Andor_Choice_Enum(pyAndorSDK2.atmcd_codes.Trigger_Mode)
        self.trigger_mode = AndorDev(write_func=self._sdk.SetTriggerMode, choices=ch_trigger_modes)
        # trigger_level and trigger_falling_invert probably depend on
        #   pyAndorSDK2.atmcd_capabilities.triggermodes.AC_TRIGGERMODE_INVERTED in idus.get_capabilities().trigger_modes
        #mn,mx = self._sdk.GetTriggerLevelRange()
        #self.trigger_level = AndorDev(write_func=self._sdk.SetTriggerLevel, force_type=float, min=mn, max=mx)
        #self.trigger_falling_en = AndorDev(write_func=self._sdk.SetTriggerInvert, force_type=bool)
        self.exposure_time = AndorDev(write_func=self._sdk.SetExposureTime, min=0)
        self.accumulation_number = AndorDev(write_func=self._sdk.SetNumberAccumulations, min=0, force_type=int)
        self.accumulation_cycle_time = AndorDev(write_func=self._sdk.SetAccumulationCycleTime, min=0)
        self.kinetics_number = AndorDev(write_func=self._sdk.SetNumberKinetics, min=0, force_type=int)
        self.kinetics_cycle_time = AndorDev(write_func=self._sdk.SetKineticCycleTime, min=0)
        self.cosmic_filter_en = AndorDev(self._sdk.GetFilterMode, self._sdk.SetFilterMode,
                                         choices=ChoiceSimpleMap({0:False, 2:True}))
        NVspeed = self._sdk.GetNumberVSSpeeds()
        speeds_us = [self._sdk.GetVSSpeed(i) for i in range(NVspeed)]
        self.vertical_speed_us = AndorDev(write_func=self._sdk.SetVSSpeed, choices=ChoiceSimpleMap({i:s for i,s in enumerate(speeds_us)}))
        self.vertical_amplitude = AndorDev(write_func=self._sdk.SetVSAmplitude, force_type=int, choices=[0, 1, 2, 3, 4])
        # # GetFastestRecommendedVSSpeed (int* index, float* speed)
        # Namp = self._sdk.GetNumberAmp()
        # Nadc = self._sdk.GetNumberADChannels()
        # is_amp_avail = self._sdk.IsAmplifierAvailable(1)
        # NHspeed0 = self._sdk.GetNumberHSSpeeds(0) #electron multiplier
        # NHspeed1 = self._sdk.GetNumberHSSpeeds(1) #conventional
        # speeds_MHz0 = [self._sdk.GetHSSpeed(0, 0, i) for i in range(NHspeed0)]
        # speeds_MHz1 = [self._sdk.GetHSSpeed(0, 1, i) for i in range(NHspeed1)]
        # # setHSSpeed first argument is type 0 or 1, then second is the index.
        # self.speed_horizontal_MHz = AndorDev(write_func=self._sdk.SetHSSpeed, choices=ChoiceSimpleMap({i:s for i,s in enumerate(speeds_MHz0)}))
        shutter_mode = pyAndorSDK2.atmcd_codes.Shutter_Mode
        remap = lambda l: [[x[0] for x in l], [x[1] for x in l]]
        shutter_ch = ChoiceSimpleMap({}, keys_values_lists=remap([(shutter_mode.FULLY_AUTO.value, 'auto'),
                                      (shutter_mode.PERMANENTLY_OPEN.value, True),
                                      (shutter_mode.PERMANENTLY_OPEN.value, 'open'),
                                      (shutter_mode.PERMANENTLY_CLOSED.value, False),
                                      (shutter_mode.PERMANENTLY_CLOSED.value, 'closed'),
                                      (shutter_mode.OPEN_FOR_ANY_SERIES.value, "open_for_any"),
                                      (shutter_mode.OPEN_FOR_FVB_SERIES.value, "open_for_fvb")]))
        self.shutter = AndorDev(write_func=self._sdk.SetShutter, choices=shutter_ch, generate_arg=ProxyMethod(self._generate_shutter_args),
                                doc="True and 'open' are the same. False and 'closed' are the same. Other params are set during init by shutter_params option.")

        #self.status = AndorDev(self._sdk.GetStatus, choices=Andor_Choice_Enum(pyAndorSDK2.atmcd_errors.Error_Codes))
        self._devwrap('status')
        self._devwrap('cooler_en')
        self._devwrap('fetch', autoinit=False)
        self.readval = ReadvalDev(self.fetch)
        # This needs to be last to complete creation
        super(andor_iDus, self)._create_devs()


#######################################################
##    Andor Kymera
#######################################################

# in case sometimes reload the instrument
# we could end up with a Init, Init, Close sequence which would leave the
# instrument in a none working state.
# To prevent that we save a Close_on_Cleanup object in every instrument instance
# and only when they are all deleted will the Close function be called.
# We also actually do the Init only when no Close Handler are left around.
#  i.e. when the last operation was Close (or it never was Inited)

class Close_on_Cleanup(object):
    def __init__(self, func, args=[], kwargs={}):
        self.func = func
        self.args = args
        self.kwargs = kwargs
    def __del__(self):
        # print("Doing Close cleanup")
        self.func(*self.args, **self.kwargs)

class Handle_Init_Close(object):
    def __init__(self, init_func, close_func, close_args=[], close_kwargs={}):
        self.init_func = init_func
        self.close_func = close_func
        self.close_args = close_args
        self.close_kwargs = close_kwargs
        self.ref = None
    def do_init(self, *args, **kwargs):
        if self.ref is None:
            obj = None
        else:
            obj = self.ref()
        if obj is None:
            obj = Close_on_Cleanup(self.close_func, self.close_args, self.close_kwargs)
            self.ref = weakref.ref(obj)
            ret = self.init_func(*args, **kwargs)
        else:
            ret = None
        return obj, ret


pyAndorSpectrograph = None
AndorSpectroSDKwrapper_instance = None
AndorSpectroErrors = None
AndorPortPos = None
AndorSlitPos = None
AndorShutterMode = None
AndorFlipperPos = None

def import_kymera_sdk():
    global pyAndorSpectrograph, AndorSpectroSDKwrapper_instance, AndorSpectroErrors,\
           AndorPortPos, AndorSlitPos, AndorShutterMode, AndorFlipperPos
    try:
        import pyAndorSpectrograph
    except ImportError:
        raise RuntimeError(r"Package pyAndorSpectrograph needs to be installed. Probably need to run (from within C:\Program Files\Andor SDK\Python\pyAndorSpectrograph): python setup.py install")

    sdk = pyAndorSpectrograph.ATSpectrograph
    class AndorSpectroErrors(IntEnum):
        ATSPECTROGRAPH_COMMUNICATION_ERROR = sdk.ATSPECTROGRAPH_COMMUNICATION_ERROR
        ATSPECTROGRAPH_ERROR = sdk.ATSPECTROGRAPH_ERROR
        ATSPECTROGRAPH_ERRORLENGTH = sdk.ATSPECTROGRAPH_ERRORLENGTH
        ATSPECTROGRAPH_NOT_AVAILABLE = sdk.ATSPECTROGRAPH_NOT_AVAILABLE
        ATSPECTROGRAPH_NOT_INITIALIZED = sdk.ATSPECTROGRAPH_NOT_INITIALIZED
        ATSPECTROGRAPH_P1INVALID = sdk.ATSPECTROGRAPH_P1INVALID
        ATSPECTROGRAPH_P2INVALID = sdk.ATSPECTROGRAPH_P2INVALID
        ATSPECTROGRAPH_P3INVALID = sdk.ATSPECTROGRAPH_P3INVALID
        ATSPECTROGRAPH_P4INVALID = sdk.ATSPECTROGRAPH_P4INVALID
        ATSPECTROGRAPH_P5INVALID = sdk.ATSPECTROGRAPH_P5INVALID
        ATSPECTROGRAPH_SUCCESS = sdk.ATSPECTROGRAPH_SUCCESS
    class AndorPortPos(IntEnum):
        SIDE = sdk.SIDE
        DIRECT = sdk.DIRECT
    class AndorSlitPos(IntEnum):
        INPUT_SIDE = sdk.INPUT_SIDE
        INPUT_DIRECT = sdk.INPUT_DIRECT
        OUTPUT_SIDE = sdk.OUTPUT_SIDE
        OUTPUT_DIRECT = sdk.OUTPUT_DIRECT
    class AndorShutterMode(IntEnum):
        CLOSED = sdk.SHUTTER_CLOSED
        OPEN = sdk.SHUTTER_OPEN
        BNC = sdk.SHUTTER_BNC
    class AndorFlipperPos(IntEnum):
        INPUT = sdk.INPUT_FLIPPER
        OUTPUT = sdk.OUTPUT_FLIPPER

    if AndorSpectroSDKwrapper_instance is not None:
        return AndorSpectroSDKwrapper_instance
    # Generate a wrapper class that handles return values better and
    # it allows using the original func by using _bypass=True
    class AndorSpectroSDKwrapper(pyAndorSpectrograph.ATSpectrograph):
        _noraise_ = []
        _notwrapped = ['dll', 'handle_return', 'handle_init_close']
        def __init__(self):
            self._cached_funcs = {}
            super(AndorSpectroSDKwrapper, self).__init__()
            self._hndl_init_close = Handle_Init_Close(self.Initialize, self.Close)
        def __getattribute__(self, name):
            attr = super(AndorSpectroSDKwrapper, self).__getattribute__(name)
            if name.startswith('_') or name in self._notwrapped or not isinstance(attr, types.MethodType):
                return attr
            func = self._cached_funcs.get(name, None)
            if func is not None:
                return func
            @functools.wraps(attr)
            def newfunc(*args, **kwargs):
                _bypass = kwargs.pop('_bypass', False)
                ret = attr(*args, **kwargs)
                if _bypass:
                    return ret
                if isinstance(ret, tuple):
                    retcode = ret[0]
                    ret = ret[1:]
                else:
                    retcode = ret
                    ret = []
                try:
                    code = AndorSpectroErrors(retcode)
                except ValueError:
                    code = "Unknown error (%d)"%retcode
                if code != AndorSpectroErrors.ATSPECTROGRAPH_SUCCESS:
                    if name not in self._noraise_:
                        desc = self.GetFunctionReturnDescription(code, 256)
                        raise RuntimeError('Error calling %s, description is %s (%r).'%(name, desc, code))
                if name in self._noraise_:
                    ret = (code,) + ret
                if len(ret) == 0:
                    ret = None
                elif len(ret) == 1:
                    ret = ret[0]
                return ret
            self._cached_funcs[name] = newfunc
            return newfunc
        def handle_init_close(self):
            return self._hndl_init_close.do_init("")[0]
    AndorSpectroSDKwrapper_instance = AndorSpectroSDKwrapper()
    return AndorSpectroSDKwrapper_instance

class Dll_Wrap_Dev(object):
    def __init__(self, parent):
        self._parent = weakref.proxy(parent)
    def __getattr__(self, name):
        return lambda *args, **kwargs: getattr(self._parent._sdk, name)(self._parent._dev, *args, **kwargs)

AndorBool = ChoiceSimpleMap({0:False, 1:True})

def calculate_wavelength_nm(pixel_numbers, coeffs):
    """ pixel_numbers are the pixel starting at 1.
        coeffs are the results for andor_kymera.sensor_coeffs (there are 4)
    """
    x = np.asarray(pixel_numbers)
    c = coeffs
    return c[0] + c[1]*x + c[2]*x**2 + c[3]*x**3


@register_instrument('Andor', 'Kymera')
class andor_kymera(BaseInstrument):
    """
    This controls the Andor Kymera spectrometer
    Useful devices:
        wavelength_nm
        sensor_wavelengths_nm
        sensor_coeffs
        sensor_pixel_num
        sensor_pixel_width_um
    Useful methods:
        calculate_wavelength_nm (see also the module function.)
        discover (static method)
    """
    def __init__(self, serial_or_index=0, **kwargs):
        """
        serial_or_index is to be used to select the camera. A string is to select
                   by serial number. And index is according the the list
                   you get with discover()
        """
        self._sdk = import_kymera_sdk()
        self._sdkdev = Dll_Wrap_Dev(self)
        if isinstance(serial_or_index, str):
            serial_list = self.discover(skip_close=True, _sdk=self._sdk)
            indx = serial_list.index(serial_or_index)
        else:
            self._handle_close = self._sdk.handle_init_close()
            # self._sdk.Initialize('')
            n_spectro = self._sdk.GetNumberDevices()
            if serial_or_index < 0 or serial_or_index >= n_spectro:
                raise ValueError("serial_or_index is too large. Max value is currently %d"%(n_spectro-1))
            indx = serial_or_index
        self._dev = indx
        self._serialno = self._sdkdev.GetSerialNumber(64)
        super(andor_kymera, self).__init__(**kwargs)

    @staticmethod
    def discover(_sdk=None):
        """
        returns a list of serial numbers.
        """
        if _sdk is None:
            sdk = import_kymera_sdk()
        else:
            sdk = _sdk
        ret = []
        # need to temporarilly hold the return from handle_init_close
        # because it gets closed when the variable disappears.
        handle_close = sdk.handle_init_close()
        n_spectro = sdk.GetNumberDevices()
        for i in range(n_spectro):
            serial = sdk.GetSerialNumber(i, 64) # 64 is the max string length
            ret.append(serial)
        return ret

    def idn(self):
        serial = self._serialno
        model = 'Kymera'
        sdk = pyAndorSpectrograph.__version__
        clsver = pyAndorSpectrograph.ATSpectrograph.__version__
        ver = 'sdk:%s_class:%s'%(sdk, clsver)
        return "Andor,%s,%s,%s"%(model, serial, ver)

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        base = self._conf_helper("wavelength_nm", "active_grating", "sensor_pixel_num", "sensor_pixel_width_um",
                                 "sensor_coeffs", "at_zero_order", "active_turret")
        base += ['gratings_info=%s'%self._gratings_info]
        base += ['spectro_info=%s'%self._spectro_info]
        orig_grating = self.current_grating.get()
        vals = [self.gratings_offset.get(grating=p, use_cache=True) for p in self.current_grating.choices]
        self.current_grating.set(orig_grating)
        base += ['gratings_offset=%s'%vals]
        if hasattr(self, 'flipper_port'):
            orig_flip = self.current_flipper.get()
            vals = {p:self.flipper_port.get(flipper=p, use_cache=True) for p in self.current_flipper.choices.values}
            self.current_flipper.set(orig_flip)
            base += ['flipper_ports=%s'%vals]
        if hasattr(self, 'focus_mirror_step_pos'):
            base += self._conf_helper('focus_mirror_step_pos')
        if hasattr(self, 'iris_pct'):
            orig_port = self.current_port.get()
            vals = {p:self.iris_pct.get(port=p, use_cache=True) for p in self.current_port.choices.values}
            self.current_port.set(orig_port)
            base += ['iris_pct=%s'%vals]
        if hasattr(self, 'slit_width'):
            orig_slit = self.current_slit.get()
            vals1 = {p:self.slit_width.get(slit=p, use_cache=True) for p in self.current_slit.choices.values}
            vals2 = {p:self.slit_zero_pos.get(slit=p, use_cache=True) for p in self.current_slit.choices.values}
            self.current_slit.set(orig_slit)
            base += ['slit_width=%s'%vals1, 'slit_zero_pos=%s'%vals2]
        base += ['detector_offset=%s'%self.get_detector_offsets()]
        return base + self._conf_helper(options)

    def _sensor_wavelengths_nm_getdev(self):
        n_pixels = self.sensor_pixel_num.getcache()
        cal = self._sdkdev.GetCalibration(n_pixels)
        return np.array(cal)

    def _sensor_coeffs_getdev(self):
        """ the coeffs are the coefficients of a third order polynomial
            to generate the wavelength in nm
            coeff[0] + coeff[1]*P + coeff[2]*P**2 + coeff[3]*P**3
            Where P is the pixel number starting at 1
        """
        cal = self._sdkdev.GetPixelCalibrationCoefficients()
        return np.array(cal)

    def calculate_wavelength_nm(self, pixel_pos):
        """ Uses the module function calculate_wavelength_nm
            to obtain the wavelength using the coeffs from sensor_coeffs
            pixel_pos start at 1
        """
        coeffs = self.sensor_coeffs.get()
        return calculate_wavelength_nm(pixel_pos, coeffs)

    def flipper_reset(self, flipper=None):
        if not hasattr(self, 'flipper_port'):
            raise NotImplementedError('flipper_reset is not available')
        if flipper is not None:
            self.current_flipper.set(flipper)
        f = self.current_flipper.get()
        self._sdkdev.FlipperMirrorReset(f)

    def focus_mirror_reset(self):
        if not hasattr(self, 'focus_mirror_step_pos'):
            raise NotImplementedError('focus_mirror_reset is not available')
        self._sdkdev.FocusMirrorReset()

    def slit_reset(self, slit=None):
        if not hasattr(self, 'slit_width'):
            raise NotImplementedError('slit_reset is not available')
        if slit is not None:
            self.current_slit.set(slit)
        s = self.current_slit.get()
        self._sdkdev.SlitReset(s)

    def goto_zero_order(self):
        self._sdkdev.GotoZeroOrder()

    def get_detector_offsets(self):
        # TODO: implement SetDetectorOffset?
        result = {}
        for pin in AndorPortPos:
            for pout in AndorPortPos:
                off = self._sdkdev.GetDetectorOffset(pin, pout)
                result[(pin.name.lower(), pout.name.    lower())] = off
        return result

    def _create_devs(self):
        gratings_info = []
        N_grating = self._sdkdev.GetNumberGratings()
        for i in range(1, N_grating+1):
            lines_per_mm, blaze, home_pos, offset = self._sdkdev.GetGratingInfo(i, 256)
            info = dict_improved(lines_per_mm=lines_per_mm, blaze=blaze, home_pos=home_pos, offset=offset)
            gratings_info.append(info)
        self._gratings_info = gratings_info
        focal_length, angular_deviation, focal_tilt = self._sdkdev.EepromGetOpticalParams()
        self._spectro_info = dict_improved(focal_length=focal_length, angular_deviation=angular_deviation, focal_tilt=focal_tilt)
        #is_acc_present = self._sdkdev.IsAccessoryPresent()
        #is_filter_present = self._sdkdev.IsFilterPresent()
        is_flipper_present = { p:self._sdkdev.IsFlipperMirrorPresent(p) for p in AndorFlipperPos }
        #is_input_flipper_present = self._sdkdev.IsFlipperMirrorPresent(AndorFlipperPos.INPUT)
        #is_output_flipper_present = self._sdkdev.IsFlipperMirrorPresent(AndorFlipperPos.OUTPUT)
        is_focus_mirror_present = self._sdkdev.IsFocusMirrorPresent()
        is_grating_present = self._sdkdev.IsGratingPresent()
        is_iris_present = { p:self._sdkdev.IsIrisPresent(p) for p in AndorPortPos}
        #is_direct_iris_present = self._sdkdev.IsIrisPresent(AndorPortPos.DIRECT)
        #is_side_iris_present = self._sdkdev.IsIrisPresent(AndorPortPos.SIDE)
        #is_shutter_present = self._sdkdev.IsShutterPresent()
        # shutter_mode probably requires shutter to be present. I get errors with it not present.
        #is_shutter_mode_possible = {p:self._sdkdev.IsShutterModePossible() for p in AndorShutterMode}
        is_slit_present = {p:self._sdkdev.IsSlitPresent(p) for p in AndorSlitPos}
        is_wavelength_present = self._sdkdev.IsWavelengthPresent()
        # I have Flipper, Focus, Grating, Iris, Slit and Wavelength present.
        # So I will only implement those
        # #print('Acc?', is_acc_present)
        # #print('Filter?', is_filter_present)
        # print('Flipper?', is_flipper_present)
        # #print('Flipper?', is_input_flipper_present, is_output_flipper_present)
        # print('Focus mirror?', is_focus_mirror_present)
        # print('Grating?', is_grating_present)
        # print('Iris?', is_iris_present)
        # #print('Iris?', is_direct_iris_present, is_side_iris_present)
        # #print('Shutter?', is_shutter_present)
        # print('Slit?', is_slit_present)
        # print('Wavelength?', is_wavelength_present)

        def make_gen_args(name):
            def gen_args(dev_obj, val, options, isget=False):
                param = options[name]
                args = (param,)
                if not isget:
                    args += (val,)
                return args
            return gen_args

        gratings_ch = list(range(1, N_grating+1))
        self.current_grating = MemoryDevice(1, choices=gratings_ch, no_type_conv=True)
        self.gratings_offset = AndorDev(self._sdkdev.GetGratingOffset, self._sdkdev.SetGratingOffset,
                                        options={'grating':self.current_grating},
                                        options_apply=['grating'],
                                        generate_arg=make_gen_args('grating'),
                                        multi_cache=(['grating'],),
                                        force_type=int)

        port_ch = Andor_Choice_Enum(AndorPortPos)

        if any(v for v in is_flipper_present.values()):
            flipper_ch = Andor_Choice_Enum(AndorFlipperPos)
            self.current_flipper = MemoryDevice('input', choices=flipper_ch)
            def AndorDevFlipper(*arg, **kwarg):
                options = kwarg.pop('flipper', {}).copy()
                options.update(flipper=self.current_flipper)
                app = kwarg.pop('options_apply', ['flipper'])
                gen_args = make_gen_args('flipper')
                kwarg.update(options=options, options_apply=app, generate_arg=gen_args, multi_cache=(['flipper'],))
                return AndorDev(*arg, **kwarg)
            self.flipper_port = AndorDevFlipper(self._sdkdev.GetFlipperMirror, self._sdkdev.SetFlipperMirror, choices=port_ch)
            #self.flipper_pos = AndorDevFlipper(self._sdkdev.GetFlipperMirrorPosition, self._sdkdev.SetFlipperMirrorPosition, force_type=int)

        if is_focus_mirror_present:
            maxsteps = self._sdkdev.GetFocusMirrorMaxSteps()
            self.focus_mirror_step_pos = AndorDev(self._sdkdev.GetFocusMirror, self._sdkdev.SetFocusMirror, force_type=int, min=0, max=maxsteps)

        if any(v for v in is_iris_present.values()):
            self.current_port = MemoryDevice('direct', choices=port_ch)
            self.iris_pct = AndorDev(self._sdkdev.GetIris, self._sdkdev.SetIris, force_type=int, min=0, max=100,
                                            options={'port':self.current_port},
                                            options_apply=['port'],
                                            generate_arg=make_gen_args('port'),
                                            multi_cache=(['port'],))

        if any(v for v in is_slit_present.values()):
            slit_ch = Andor_Choice_Enum(AndorSlitPos)
            self.current_slit = MemoryDevice('input_direct', choices=slit_ch)
            def AndorDevSlit(*arg, **kwarg):
                options = kwarg.pop('slit', {}).copy()
                options.update(slit=self.current_slit)
                app = kwarg.pop('options_apply', ['slit'])
                gen_args = make_gen_args('slit')
                kwarg.update(options=options, options_apply=app, generate_arg=gen_args, multi_cache=(['slit'],))
                return AndorDev(*arg, **kwarg)
            self.slit_width = AndorDevSlit(self._sdkdev.GetSlitWidth, self._sdkdev.SetSlitWidth, force_type=float, setget=True)
            self.slit_zero_pos = AndorDevSlit(self._sdkdev.GetSlitZeroPosition, self._sdkdev.SetSlitZeroPosition, force_type=int, min=-200, max=0)
            # GetSlitCoefficients is not working

        self.active_grating = AndorDev(self._sdkdev.GetGrating, self._sdkdev.SetGrating, choices=gratings_ch, force_type=int)
        self.wavelength_nm = AndorDev(self._sdkdev.GetWavelength, self._sdkdev.SetWavelength, setget=True, force_type=float)
        self.sensor_pixel_num = AndorDev(self._sdkdev.GetNumberPixels, self._sdkdev.SetNumberPixels, setget=True, force_type=int, min=0)
        self.sensor_pixel_width_um = AndorDev(self._sdkdev.GetPixelWidth, self._sdkdev.SetPixelWidth, setget=True, force_type=float, min=0, doc='unit is micrometer')
        self.at_zero_order = AndorDev(self._sdkdev.AtZeroOrder, choices=AndorBool)
        self.active_turret = AndorDev(self._sdkdev.GetTurret, self._sdkdev.SetTurret, force_type=int)
        #self.wavelength_limits = AndorDev(self._sdkdev.GetWavelengthLimits)
        self._devwrap('sensor_wavelengths_nm', autoinit=False)
        self._devwrap('sensor_coeffs', autoinit=False, multi=['coeff0', 'coeff1','coeff2','coeff3'])

        # This needs to be last to complete creation
        super(andor_kymera, self)._create_devs()
