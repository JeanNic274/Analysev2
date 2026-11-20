# -*- coding: utf-8 -*-
########################## Copyrights and license ############################
#                                                                            #
# Copyright 2024-2026  Christian Lupien <christian.lupien@usherbrooke.ca>    #
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

import enum
import time
from weakref import proxy
import numpy as np
from contextlib import contextmanager
import tempfile
import os
import sys
import functools
import threading
import copy


from ..ctypes_helper import DLL_Wrapper, Buffer, General_POINTER,\
                            c_uint32, c_uint16, c_int, c_float,\
                            c_uint, c_uint_p, c_double_p, c_char,\
                            c_uint32_p, c_float_p, c_int_p, c_int32,\
                            IntEnumC, General_Conv, IntFlagC

from ..types import StructureImproved, UnionImproved, dict_improved

from ..instruments_base import BaseInstrument, BaseDevice, locked_calling,\
                                ChoiceSimpleMap, ProxyMethod, MemoryDevice,\
                                Base2Device, MemoryDevice_update, ChoiceValMap,\
                                OrderedDict, ChoiceBase, _retry_wait, ReadvalDev,\
                                _sleep_signal_context_manager, locked_calling_dev,\
                                wait_on_event, FastEvent

from ..instruments_registry import register_instrument, add_to_instruments

from ..comp2to3 import fu, string_bytes_types, is_py2

if is_py2:
    import Queue as queue
else:
    import queue


#######################################################
##    PicoQuant Taiko PDL M1 laser controller
#######################################################
# C header files are in C:\ProgramData\Taiko PDL M1\API\Demos\MSVCPP\Common_Files
# windows dll in C:\ProgramData\Taiko PDL M1\API\x64

class PicoQuant_Exception(Exception):
    def __init__(self, msg, errno):
        self.errno = errno
        super(PicoQuant_Exception, self).__init__(msg)

_Error_string = {
        1: "Initial value error",
        0: "No Error",
        -1: "Device not found",
        -2: "Not connected",
        -3: "Already Connected",
        -4: "Wrong USB idx",
        -5: "Illegal index",
        -6: "Illegal value",
        -7: "USB msg integrity violated",
        -8: "Illegal node index",
        -9: "Wrong Parameter",
        -10: "Incompatible firmware",
        -11: "Wrong serial number",
        -12: "Wrong product model",
        -13: "Buffer too small",
        -14: "Index not found",
        -15: "FW memory allocation error",
        -16: "Frequency too high",
        -17: "Device busy or blocked",
        -18: "USB inappropriate device",
        -19: "USB get dscr failed",
        -20: "USB invalid handle",
        -21: "USB invalid dscrbuf",
        -22: "USB ioctl failed",
        -23: "USB vcmd failed",
        -24: "USB no such pipe",
        -25: "USB regntfy failed",
        -26: "USB driver has no memory",
        -27: "Device already opened",
        -28: "Open device failed",
        -29: "USB unknown device",
        -30: "Empty queue",
        -31: "Feature not available",
        -32: "Unitialized data",
        -33: "Dll memory allocation error",
        -34: "Unknown tag",
        -35: "Open file",
        -36: "Firmware footer",
        -37: "Firmware update",
        -38: "Firmware update running",
        -39: "Incompatible hardware",
        -40: "value not available",
        -41: "USB set timed out",
        -42: "USB get timed out",
        -43: "USB set failed",
        -44: "USB get failed",
        -45: "USB data size too big",
        -46: "FW version check",
        -47: "Wrong driver",
        -48: "Winusb stored error"}

class Temp_Unit(enum.IntEnum):
    celsius = 0
    fahrenheit = 1
    kelvin = 2

class Laser_Mode(enum.IntEnum):
    cw = 0
    pulse = 1
    burst = 2

class Pulse_Power_Table(enum.IntEnum):
    linear = 0
    max_power = 0

class Trigger_Mode(enum.IntEnum):
    internal = 0
    external_falling = 1
    external_rising = 2

_SERIAL_BUF = Buffer(8) # needs at least 8 char
_LARGE_BUF = Buffer(1024, encoding='latin1')
_LARGE_BUF_None = Buffer(1024, allow_any_size=True, encoding='latin1')
_SUPER_LARGE_BUF = Buffer(1024*100, encoding='latin1')
_STRING = Buffer(None, encoding='latin1')
_PDLM_DEV_STRING = c_char*16
_PDLM_LDH_STRING = c_char*16

class _VersNum(StructureImproved):
    _pack_ = 1
    _fields_ = [('Major', c_uint16),
                ('Minor', c_uint16),
                ('Notes', _PDLM_DEV_STRING)]

class DeviceData(StructureImproved):
    _pack_ = 1
    _fields_ = [('SN', c_uint32),
                ('ArtNo', c_uint32),
                ('Name', _PDLM_DEV_STRING),
                ('Type', _PDLM_DEV_STRING),
                ('Date', _PDLM_DEV_STRING),
                ('VersPCB', _PDLM_DEV_STRING),
                ('VersDev', _VersNum)]

class _LHVersNum(StructureImproved):
    _pack_ = 1
    _fields_ = [('Major', c_uint16),
                ('Minor', c_uint16)]

class LaserData(StructureImproved):
    _pack_ = 1
    _fields_ = [('SN', c_uint32),
                ('Features', c_uint32),
                ('FreqMin', c_uint32),
                ('FreqMax', c_uint32),
                ('CwPowerMax', c_uint32),
                ('PulsePowerMax', c_uint32),
                ('WavelengthNominal', c_uint16),
                ('CaseTempMax', c_uint16, 10),
                ('Protection', c_uint16, 1),
                ('CwCurrentPolarity', c_uint16, 1),
                ('_reserved1', c_uint16, 4),
                ('LHTypeCtrlVoltage', c_uint16, 12),
                ('_reserved2', c_uint16, 4),
                ('LHMaxVoltage', c_uint16, 12),
                ('_reserved3', c_uint16, 4),
                ('CurrentTEP12V', c_uint16),
                ('laserType', c_uint16),
                ('laserVersion', _LHVersNum),
                ('calibratedWarrantHours', c_uint16)]

class LaserInfo(StructureImproved):
    _pack_ = 1
    _fields_ = [('Type', _PDLM_LDH_STRING),
                ('Date', _PDLM_LDH_STRING),
                ('Class', _PDLM_LDH_STRING)]

class ValueType(UnionImproved):
    _fields_ = [('ValueUInt', c_uint32),
                ('ValueInt', c_int32),
                ('ValueFloat', c_float)]

class TagValue(StructureImproved):
    _fields_ = [('Tag', c_uint32),
                ('Value', ValueType)]

DeviceData_p = General_POINTER(DeviceData)
LaserData_p = General_POINTER(LaserData)
LaserInfo_p = General_POINTER(LaserInfo)

TagValueBuf = Buffer(10, TagValue, allow_any_size=True)

class PDLM_Lib_dll(DLL_Wrapper):
    _dll_cache = None
    def __init__(self, dll_name=r'C:\ProgramData\Taiko PDL M1\API\x64\PDLM_Lib.dll', **kwargs):
        super(PDLM_Lib_dll, self).__init__(dll_name, **kwargs)

    def _errcheck(self, result, func, args):
        if result != 0:
            if result >= -48:
                msg = _Error_string[result]
            elif result == -999:
                msg = 'Unknown error code'
            elif -2999 <= result <= -1000:
                msg = 'Hardware error'
            elif result == -9000:
                msg = 'Function is PQ internal'
            elif result == -9999:
                msg = 'Not implemented yet'
            else:
                msg = 'Unknow error'
            raise PicoQuant_Exception('PDLM Error(%i): %s'%(result, msg), result)

    def _create_funcs(self):
        errcheck = ProxyMethod(self._errcheck)
        create_helper = lambda *args, **kwargs: self._create_helper(*args, errcheck=errcheck, name_prefix='PDLM_', **kwargs)
        create_helper('GetLibraryVersion', [('Version_', _LARGE_BUF), ('_Version_N', c_uint32)])
        create_helper('GetUSBDriverInfo', [('Name_', _LARGE_BUF), ('_Name_N', c_uint32),
                                ('Version_', _LARGE_BUF), ('_Version_N', c_uint32), ('Date_', _LARGE_BUF), ('_Date_N', c_uint32)])
        create_helper('DecodeError', [('ErrCode', c_int), ('Buffer_', _LARGE_BUF_None), ('_Buffer_N+', c_uint32_p)])
        create_helper('DecodeError', [('ErrCode', c_int), ('_Buffer', _LARGE_BUF_None, None), ('Buffer_N_', c_uint32_p, 0)], othername="DecodeErrorBufferSize")
        create_helper('GetTagDescription', [('Tag', c_uint32), ('TypeCode_', c_uint32_p), ('Name_', _LARGE_BUF)])
        create_helper('DecodePulseShape', [('shape', c_uint32), ('Buffer_', _LARGE_BUF), ('_Buffer_N', c_uint32)])
        create_helper('DecodeLHFeatures', [('LHFeature', c_uint32), ('Buffer_', _LARGE_BUF), ('_Buffer_N', c_uint32)])
        create_helper('DecodeSystemStatus', [('state', c_uint32), ('Buffer_', _SUPER_LARGE_BUF), ('_Buffer_N', c_uint32)])
        create_helper('OpenDevice', [('USBIdx', c_int), ('cSerNo+', _SERIAL_BUF)])
        # OpenGetSerNumAndClose does not behave as documented. It does not seem to compare the cSerNo
        # and does not seem able to open and already opened device (blocked)
        create_helper('OpenGetSerNumAndClose', [('USBIdx', c_int), ('cSerNo+', _SERIAL_BUF)])
        create_helper('CloseDevice', [('USBIdx', c_int)])
        create_helper('GetExclusiveUI', [('USBIdx', c_int), ('mode_', c_uint32_p)])
        create_helper('SetExclusiveUI', [('USBIdx', c_int), ('mode', c_uint32)])
        create_helper('GetUSBStrDescriptor', [('USBIdx', c_int), ('Descr_', _LARGE_BUF), ('_Descr_N', c_uint32)])
        create_helper('GetHardwareInfo', [('USBIdx', c_int), ('Infos_', _LARGE_BUF), ('_Infos_N', c_uint32)])
        # CreateSupportRequestText crashes when the buffer is not big enough (it crashes even if the buffer is
        #  big enough but the _Buffer_N value is set too small)
        create_helper('CreateSupportRequestText', [('USBIdx', c_int), ('Preamble', _LARGE_BUF), ('CallingSW', _LARGE_BUF),
                                                         ('uiOptions', c_uint32), ('_Buffer_N', c_uint32), ('Buffer_', _SUPER_LARGE_BUF)])
        create_helper('GetFWVersion', [('USBIdx', c_int), ('Version_', _LARGE_BUF), ('_Version_N', c_uint32)])
        create_helper('GetFPGAVersion', [('USBIdx', c_int), ('Version_', _LARGE_BUF), ('_Version_N', c_uint32)])
        create_helper('GetDeviceData', [('USBIdx', c_int), ('Data_', DeviceData_p), ('_Data_size', c_uint32)])
        create_helper('GetLHVersion', [('USBIdx', c_int), ('Version_', _LARGE_BUF), ('_Version_N', c_uint32)])
        create_helper('GetLHData', [('USBIdx', c_int), ('Data_', LaserData_p), ('_Data_size', c_uint32)])
        create_helper('GetLHInfo', [('USBIdx', c_int), ('Info_', LaserInfo_p), ('_Info_size', c_uint32)])
        create_helper('GetQueuedChanges', [('USBIdx', c_int), ('TagValue_', TagValueBuf), ('_TagValue_N+', c_uint32_p)])
        # For TagValue, provide  list of TagValue items. Only need to set Tag so for example:
        # [TagValue(0x94), TagValue(0x95)]
        create_helper('GetTagValueList', [('USBIdx', c_int), ('_TagValue_N', c_uint32), ('TagValue+', Buffer(None, TagValue))])
        create_helper('GetQueuedError', [('USBIdx', c_int), ('ErrCode_', c_int_p)])
        create_helper('GetQueuedErrorString', [('USBIdx', c_int), ('ErrCode', c_int), ('ErrText_', _LARGE_BUF)])
        create_helper('GetLHFeatures', [('USBIdx', c_int), ('LHFeatures_', c_uint32_p)])
        create_helper('GetLocked', [('USBIdx', c_int), ('Locked_', c_uint32_p)])
        create_helper('SetSoftLock', [('USBIdx', c_int), ('SoftLocked', c_uint32)])
        create_helper('GetSoftLock', [('USBIdx', c_int), ('SoftLocked_', c_uint32_p)])
        create_helper('GetSystemStatus', [('USBIdx', c_int), ('mode_', c_uint32_p)])
        create_helper('SetLaserMode', [('USBIdx', c_int), ('mode', c_uint32)])
        create_helper('GetLaserMode', [('USBIdx', c_int), ('mode_', c_uint32_p)])
        create_helper('SetLDHPulsePowerTable', [('USBIdx', c_int), ('TableIdx', c_uint32)])
        create_helper('GetLDHPulsePowerTable', [('USBIdx', c_int), ('TableIdx_', c_uint32_p)])
        create_helper('SetTriggerMode', [('USBIdx', c_int), ('mode', c_uint32)])
        create_helper('GetTriggerMode', [('USBIdx', c_int), ('mode_', c_uint32_p)])
        create_helper('SetTriggerLevel', [('USBIdx', c_int), ('Level', c_float)])
        create_helper('GetTriggerLevel', [('USBIdx', c_int), ('Level_', c_float_p)])
        create_helper('GetExtTriggerFrequency', [('USBIdx', c_int), ('ExtFreq_', c_uint32_p)])
        create_helper('SetFastGate', [('USBIdx', c_int), ('mode', c_uint32)])
        create_helper('GetFastGate', [('USBIdx', c_int), ('mode_', c_uint32_p)])
        create_helper('SetFastGateImp', [('USBIdx', c_int), ('mode', c_uint32)])
        create_helper('GetFastGateImp', [('USBIdx', c_int), ('mode_', c_uint32_p)])
        create_helper('SetSlowGate', [('USBIdx', c_int), ('mode', c_uint32)])
        create_helper('GetSlowGate', [('USBIdx', c_int), ('mode_', c_uint32_p)])
        create_helper('GetFrequencyLimits', [('USBIdx', c_int), ('minFreq_', c_uint32_p), ('maxFreq_', c_uint32_p)])
        create_helper('SetFrequency', [('USBIdx', c_int), ('freq', c_uint32)])
        create_helper('GetFrequency', [('USBIdx', c_int), ('freq_', c_uint32_p)])
        create_helper('SetBurst', [('USBIdx', c_int), ('BurstLength', c_uint32), ('PeriodLength', c_uint32)])
        create_helper('GetBurst', [('USBIdx', c_int), ('BurstLength_', c_uint32_p), ('PeriodLength_', c_uint32_p)])
        create_helper('GetLHTargetTempLimits', [('USBIdx', c_int), ('ScaleID', c_uint32), ('minTemp_', c_float_p), ('maxTemp_', c_float_p)])
        create_helper('SetTempScale', [('USBIdx', c_int), ('ScaleID', c_uint32)]) # only affects instrument GUI
        create_helper('GetTempScale', [('USBIdx', c_int), ('ScaleID_', c_uint32_p)]) # only affects isntrument GUI
        create_helper('SetLHTargetTemp', [('USBIdx', c_int), ('ScaleID', c_uint32), ('TargetTemp', c_float)])
        create_helper('GetLHTargetTemp', [('USBIdx', c_int), ('ScaleID', c_uint32), ('TargetTemp_', c_float_p)])
        create_helper('GetLHCurrentTemp', [('USBIdx', c_int), ('ScaleID', c_uint32), ('CurrentTemp_', c_float_p)])
        create_helper('GetLHCaseTemp', [('USBIdx', c_int), ('ScaleID', c_uint32), ('CaseTemp_', c_float_p)])
        create_helper('GetLHWavelength', [('USBIdx', c_int), ('Wavelength_', c_float_p)])
        create_helper('GetPulsePowerLimits', [('USBIdx', c_int), ('minPower_', c_float_p), ('maxPower_', c_float_p)])
        create_helper('SetPulsePower', [('USBIdx', c_int), ('power', c_float)])
        create_helper('GetPulsePower', [('USBIdx', c_int), ('power_', c_float_p)])
        create_helper('SetPulsePowerPermille', [('USBIdx', c_int), ('permille', c_uint32)])
        create_helper('GetPulsePowerPermille', [('USBIdx', c_int), ('permille_', c_uint32_p)])
        create_helper('GetPulseShape', [('USBIdx', c_int), ('shape_', c_uint32_p)])
        create_helper('GetCwPowerLimits', [('USBIdx', c_int), ('minPower_', c_float_p), ('maxPower_', c_float_p)])
        create_helper('SetCwPower', [('USBIdx', c_int), ('power', c_float)])
        create_helper('GetCwPower', [('USBIdx', c_int), ('power_', c_float_p)])
        create_helper('SetCwPowerPermille', [('USBIdx', c_int), ('permille', c_uint32)])
        create_helper('GetCwPowerPermille', [('USBIdx', c_int), ('permille_', c_uint32_p)])
        create_helper('SetLHFan', [('USBIdx', c_int), ('FanValue', c_uint32)])
        create_helper('GetLHFan', [('USBIdx', c_int), ('FanValue_', c_uint32_p)])
        create_helper('StorePreset', [('USBIdx', c_int), ('PsIdx', c_uint32), ('PsInfo', _STRING), ('_PsInfo_N', c_uint32)])
        create_helper('GetPresetInfo', [('USBIdx', c_int), ('PsIdx', c_uint32), ('PsInfo_', _LARGE_BUF), ('_PsInfo_N', c_uint32)])
        create_helper('GetPresetText', [('USBIdx', c_int), ('PsIdx', c_uint32), ('PsText_', _LARGE_BUF), ('_PsText_N', c_uint32)])
        create_helper('RecallPreset', [('USBIdx', c_int), ('PsIdx', c_uint32)])
        create_helper('ErasePreset', [('USBIdx', c_int), ('PsIdx', c_uint32)])

class Val_Arg:
    pass

class PicoDev(BaseDevice):
    def __init__(self, getname, setname=None, dev_type=None, get_arg=(), set_arg=(Val_Arg,), **kwargs):
        super(PicoDev, self).__init__(**kwargs)
        self._getdev_p = getname
        self._setdev_p = setname
        self._get_arg = get_arg
        self._set_arg = set_arg
        self._dev_type = dev_type
        if dev_type is None:
            self._dev_type = self.choices
    def _setdev(self, val):
        instr = self.instr
        usb_id = instr._usb_id
        if usb_id is None:
            raise RuntimeError(self.perror('You need to connect to a device first.'))
        func = getattr(instr._sdk, self._setdev_p)
        val = self._todev_conv_helper(val)
        args = (usb_id,) + tuple(val if a is Val_Arg else a for a in self._set_arg)
        func(*args)
    def _getdev(self):
        instr = self.instr
        usb_id = instr._usb_id
        if usb_id is None:
            raise RuntimeError(self.perror('You need to connect to a device first.'))
        func = getattr(instr._sdk, self._getdev_p)
        args = (usb_id,) + self._get_arg
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
        t = self._dev_type
        if t == int:
            return val
        elif t == bool:
            return bool(val)
        elif t is None:
            return val
        return t(val)

_PDLM_Lib_dll_cache = None

@register_instrument('PicoQuant', 'Taiko - PDL-M1')
class PicoQuant_Taiko_PDL_M1(BaseInstrument):
    """
    This controls the PicoQuant Taiko PDL M1 laser driver
    Useful devices:
        laser_mode
        cw_power_permille
        cw_power_W
        pulse_burst_power_permille
        pulse_burst_power_W
        pulse_burst_freq_Hz
        softlock_en
    Useful methods:
        get_error
        get_status
        read_tag
        read_all_pending
    """
    def __init__(self, usb_id=0, serial_num='', dll_name=r'C:\ProgramData\Taiko PDL M1\API\x64\PDLM_Lib.dll', force_close=False, extra_paths=None, quiet_delete=False, quiet_load=True):
        """ If you provide serial_num, it will need to match.
        If you know the serial num but not the usb_id, you can make the usb_id=-1, and provide the correct serial_num.
        if neither are specified, it will load the first one it finds.
        """
        # keeping a global value for the sdk prevents it from being deleted in the wrong order.
        # So we should be able to close the device in our __del__ (the sdk should still work.)
        global _PDLM_Lib_dll_cache
        if _PDLM_Lib_dll_cache is None:
            sdk = PDLM_Lib_dll(dll_name=dll_name, extra_paths=extra_paths, quiet_delete=True)
            _PDLM_Lib_dll_cache = sdk
        else:
            sdk = _PDLM_Lib_dll_cache
        self._sdk = sdk
        self._usb_id = None
        self._serial_num = None
        self.open(usb_id, serial_num, force_close)
        super(PicoQuant_Taiko_PDL_M1, self).__init__()

    def idn(self):
        lib_version = self._sdk.GetLibraryVersion()
        usb_driver_info = '_'.join(self._sdk.GetUSBDriverInfo())
        name = None
        fw = 'lib:%s__usbdriver:%s'%(lib_version, usb_driver_info)
        if self._usb_id is not None:
            # usbname = self._sdk.GetUSBStrDescriptor(self._usb_id) # 'PicoQuant, Taiko, 1043361'
            # hwinfo = self._sdk.GetHardwareInfo(self._usb_id) # 'PDL-M1 "Taiko"' which combines data.Name and data.Type
            data = self._sdk.GetDeviceData(self._usb_id)
            fwvers = self._sdk.GetFWVersion(self._usb_id)
            fpgavers = self._sdk.GetFPGAVersion(self._usb_id)
            name = '%s - %s'%(fu(data.Name), fu(data.Type))
            if data.SN != int(self._serial_num):
                raise RuntimeError('Unexpected serial num')
            fw += '__artno:%d__FW:%s__FPGA:%s__Date:%s__PCB:%s__Dev:%s__DevNote:%s'%(
                    data.ArtNo, fwvers, fpgavers, fu(data.Date), fu(data.VersPCB),
                    '%d.%d'%(data.VersDev.Major, data.VersDev.Minor), fu(data.VersDev.Notes))
        return 'PicoQuant,%s,%s,%s'%(name, self._serial_num, fw)

    def laser_head_info(self):
        if self._usb_id is None:
            return None
        #a = self._sdk.GetLHVersion(self._usb_id) # also in b.laserVersion
        b = self._sdk.GetLHData(self._usb_id)
        c = self._sdk.GetLHInfo(self._usb_id)
        #d = self._sdk.GetLHFeatures(self._usb_id) # alos in b.Features
        decoded_features = self._sdk.DecodeLHFeatures(b.Features)
        all_info = [(k, fu(v)) for k,v in c.items()]
        def conv(v):
            if isinstance(v, _LHVersNum):
                return '%d.%d'%(v.Major, v.Minor)
            return v
        all_info += [(k, conv(v)) for k, v in b.items() if not (v == 0 and k.startswith('_reserved'))]
        all_info.append(('features_decoded', decoded_features))
        return dict_improved(all_info)

    def find_all_dev(self, force_close=False):
        """ Note that this will not find an already opened device.
            It returns a list of serial numbers for all the devices for usb_id 0 to 7.
            When no device is present, it returns ''. When the device is already opened it
            returns None.
        """
        serials = []
        for i in range(8):
            if force_close:
                self.close(force_id=i, quiet=True)
            try:
                name = self._sdk.OpenGetSerNumAndClose(i, '')
            except PicoQuant_Exception as exc:
                if exc.errno == -28:
                    # Open device failed
                    name = ''
                elif exc.errno == -27:
                    # Device already opened
                    name = None
                else:
                    raise
            serials.append(name)
        return serials

    def open(self, usb_id=0, serial_num='', force_close=False):
        """ If you provide serial_num, it will need to match.
        If you know the serial num but not the usb_id, you can make the usb_id=-1, and provide the correct serial_num.
        if neither are specified, it will load the first one it finds.
        """
        if force_close:
            self.close(force_id=usb_id)
        if usb_id == -1:
            serials = self.find_all_dev(force_close)
            if serial_num == '':
                for i, s in enumerate(serials):
                    if s is not None and s != '':
                        usb_id = i
                if usb_id == -1:
                    raise RuntimeError('Could not find a usb_id to load.')
            else:
                try:
                    usb_id = serials.index(serial_num)
                except ValueError:
                    raise RuntimeError('The requested serial_num could not be found.')
            self.find_all_dev()
        self._serial_num = self._sdk.OpenDevice(usb_id, serial_num)
        self._usb_id = usb_id

    def close(self, force_id=None, quiet=False):
        if force_id is not None:
            usb_id = force_id
        else:
            usb_id = self._usb_id
        if usb_id is not None and usb_id != -1:
            try:
                self._sdk.CloseDevice(usb_id)
            except PicoQuant_Exception as exc:
                if exc.errno == -20:
                    # USB invalid handle
                    if not quiet:
                        print('Handle was already closed.')
                else:
                    raise
        if usb_id == self._usb_id:
            self._usb_id = None
            self._serial_num = None

    def __del__(self):
        #global _PDLM_Lib_dll_cache
        self.close()
        self._sdk = None
        #_PDLM_Lib_dll_cache = None
        super(PicoQuant_Taiko_PDL_M1, self).__del__()

    def _check_usb_id(self):
        if self._usb_id is None:
            raise RuntimeError(self.perror('You need to connect to a device first.'))

    def get_error(self):
        self._check_usb_id()
        errno = self._sdk.GetQueuedError(self._usb_id)
        errstr = self._sdk.GetQueuedErrorString(self._usb_id, errno)
        return errno, errstr

    def get_status(self):
        self._check_usb_id()
        status = self._sdk.GetSystemStatus(self._usb_id)
        status_str = self._sdk.DecodeSystemStatus(status)
        return status, status_str

    def read_all_pending(self):
        self._check_usb_id()
        ret = []
        while True:
            d = self._sdk.GetQueuedChanges(self._usb_id)
            ret.extend(d)
            if len(d) == 0:
                break
        return ret

    def create_support_request(self, printit=True, options=0):
        """ When printit is False, the functions returns the string.
            options is used to disable some handling. 0xf disables the most. 0 disables nothing
            it includes everything
        """
        self._check_usb_id()
        val = self._sdk.CreateSupportRequestText(self._usb_id, '', 'pyHegel', options)
        if printit:
            print(val)
        else:
            return val

    def _preset_helper(self, preset_index):
        self._check_usb_id()
        if preset_index not in list(range(1, 9+1)):
            raise ValueError('Invalid preset. should ne in range 1-9.')

    def preset_erase(self, preset_index):
        self._preset_helper(preset_index)
        self._sdk.ErasePreset(self._usb_id, preset_index)

    def preset_recall(self, preset_index):
        self._preset_helper(preset_index)
        self._sdk.RecallPreset(self._usb_id, preset_index)

    def preset_store(self, preset_index, name=""):
        """ name is a user string. it is optional and it might not work with your device. """
        self._preset_helper(preset_index)
        self._sdk.StorePreset(self._usb_id, preset_index, name)

    def preset_list(self, printit=True):
        self._check_usb_id()
        ret = []
        for idx in range(1, 9+1):
            name = self._sdk.GetPresetInfo(self._usb_id, idx)
            text = self._sdk.GetPresetText(self._usb_id, idx)
            d = dict(name=name, desc=text)
            ret.append(d)
            if printit:
                print(idx, name)
                extra = ' '*10
                t = text
                CRLF = '\r\n'
                if t.endswith(CRLF):
                    t = t[:-2]
                t = extra+t
                t = t.replace(CRLF, CRLF+extra)
                print(t)
        if not printit:
            return ret

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        info = self._conf_helper('laser_mode', 'cw_power_W', 'cw_power_permille',
                                'pulse_burst_power_W', 'pulse_burst_power_permille', 'pulse_burst_power_table_max_en',
                                'pulse_burst_shape', 'pulse_burst_freq_Hz', 'burst_length', 'burst_period',
                                'locked_en', 'softlock_en',
                                'temp_laser_head_target_C', 'temp_laser_head_C', 'temp_case_C',
                                'laser_head_fan_en', 'laser_head_wavelength_nm',
                                'trigger_mode', 'trigger_level_V', 'trigger_ext_freq_Hz',
                                'gate_slow_en', 'gate_fast_en', 'gate_fast_low_imp_en')
        extra = ['status=%s'%(self.get_status(),), 'laser_head_info=%s'%self.laser_head_info()]
        base = self._conf_helper(options)
        return info+extra+base

    def _get_pulse_burst_helper(self):
        self._check_usb_id()
        return self._sdk.GetBurst(self._usb_id)
    def _set_pulse_burst_helper(self, burst_length, period):
        self._check_usb_id()
        return self._sdk.SetBurst(self._usb_id, burst_length, period)

    def _burst_length_getdev(self):
        l, p = self._get_pulse_burst_helper()
        return l
    def _burst_period_getdev(self):
        l, p = self._get_pulse_burst_helper()
        return p
    def _burst_length_setdev(self, val):
        l, p = self._get_pulse_burst_helper()
        self._set_pulse_burst_helper(val, p)
    def _burst_period_setdev(self, val):
        l, p = self._get_pulse_burst_helper()
        self._set_pulse_burst_helper(l, val)

    def read_tag(self, tag_id):
        self._check_usb_id()
        val = self._sdk.GetTagValueList(self._usb_id, [TagValue(tag_id)])[0]
        if val.Tag != tag_id:
            raise RuntimeError('Unexpected TagId')
        val_int = val.Value.ValueInt
        val_uint = val.Value.ValueUInt
        val_float = val.Value.ValueFloat
        try:
            desc = self._sdk.GetTagDescription(tag_id)
        except PicoQuant_Exception as exc:
            if exc.errno == -34:
                # Unknow tag
                return dict_improved(tag=tag_id, desc='Unkown tag', value=val_uint)
            else:
                raise
        tagtype = desc[0]
        if tagtype in [0x00110001, 0x00110302]:
            val = val_int
        elif tagtype == 0x01000001:
            val = val_float
        else:
            val = val_uint
        if tagtype == 0x00000001:
            # Bool
            val = bool(val)
        elif tagtype == 0x00010101:
            # temps in 0.1 C
            val = val * 0.1
        return dict_improved(tag=tag_id, desc=desc[1], value=val)

    def _create_devs(self):
        pself = proxy(self)
        self.locked_en = PicoDev('GetLocked', dev_type=bool)
        self.softlock_en = PicoDev('GetSoftLock', 'SetSoftLock', dev_type=bool)
        self.laser_mode = PicoDev('GetLaserMode', 'SetLaserMode', choices=ChoiceSimpleMap({0:'cw', 1:'pulsed', 2:'burst'}))
        self.pulse_burst_freq_Hz = PicoDev('GetFrequency', 'SetFrequency', dev_type=int, setget=True)
        self.pulse_burst_power_W = PicoDev('GetPulsePower', 'SetPulsePower', setget=True)
        self.pulse_burst_power_permille = PicoDev('GetPulsePowerPermille', 'SetPulsePowerPermille', dev_type=int, setget=True)
        self.pulse_burst_shape = PicoDev('GetPulseShape', dev_type=lambda x: pself._sdk.DecodePulseShape(x))
        self.pulse_burst_power_table_max_en = PicoDev('GetLDHPulsePowerTable', 'SetLDHPulsePowerTable', dev_type=bool, doc='False means linear power mode, True means max power mode')
        self.cw_power_W = PicoDev('GetCwPower', 'SetCwPower', setget=True)
        self.cw_power_permille = PicoDev('GetCwPowerPermille', 'SetCwPowerPermille', dev_type=int, setget=True)
        self.temp_gui_unit = PicoDev('GetTempScale', 'SetTempScale', choices=ChoiceSimpleMap({0:'C', 1:'F', 2:'K'}))
        self.temp_laser_head_C = PicoDev('GetLHCurrentTemp', get_arg=(Temp_Unit.celsius,))
        self.temp_case_C = PicoDev('GetLHCaseTemp', get_arg=(Temp_Unit.celsius,))
        self.temp_laser_head_target_C = PicoDev('GetLHTargetTemp', 'SetLHTargetTemp', get_arg=(Temp_Unit.celsius,), set_arg=(Temp_Unit.celsius, Val_Arg), setget=True)
        self.laser_head_wavelength_nm = PicoDev('GetLHWavelength', doc='This is the temperature compensated estimation')
        self.laser_head_fan_en = PicoDev('GetLHFan', 'SetLHFan', dev_type=bool)
        self.trigger_mode = PicoDev('GetTriggerMode', 'SetTriggerMode', choices=ChoiceSimpleMap({0:'internal', 1:'falling', 2:'rising'}))
        self.trigger_level_V = PicoDev('GetTriggerLevel', 'SetTriggerLevel', setget=True)
        self.trigger_ext_freq_Hz = PicoDev('GetExtTriggerFrequency')
        self.gate_fast_en = PicoDev('GetFastGate', 'SetFastGate', dev_type=bool)
        self.gate_fast_low_imp_en = PicoDev('GetFastGateImp', 'SetFastGateImp', dev_type=bool,
                                            doc="False means 10 kOhm pull up (defaults ON). True means 50 Ohm pull down (defaults OFF). Signal is TTL high (5V) enables the laser.")
        self.gate_slow_en = PicoDev('GetSlowGate', 'SetSlowGate', dev_type=bool)
        self._devwrap('burst_length', setget=True, doc="burst length in unit of pulses")
        self._devwrap('burst_period', setget=True, doc="burst length in unit of pulses")
        # This needs to be last to complete creation
        super(PicoQuant_Taiko_PDL_M1, self)._create_devs()


#######################################################
##    PicoQuant MultiHarp 150
#######################################################

c_string = Buffer(100) # good for libversion, serial, partno, hwVersion, hw_model and error
c_string_warning = Buffer(16384)
c_string_debug = Buffer(65536)
c_string_control = Buffer(None)

M_MAX_DEV_NUM = 8
MH_MAX_INP_CHAN = 64
MH_BIN_STEPS_MAX = 24
MH_MAX_HIST_LEN = 65536
MH_TT_READ_MAX = 1048576

MH_cnt_buf = Buffer(MH_MAX_INP_CHAN, c_int)
MH_tt_buf = Buffer(MH_TT_READ_MAX, c_uint, use_ndarray=True)
MH_hist_cnt = Buffer(MH_MAX_HIST_LEN, c_uint, allow_any_size=True, use_ndarray=True)
MH_hist_all_cnt = Buffer(None, c_uint, allow_any_size=True, use_ndarray=True)

MH_bool = General_Conv(c_int, bool, force_check=True)
MH_bool_p = General_POINTER(MH_bool)

class MH_init_mode(IntEnumC):
    __ctype__ = c_int
    hist = 0
    t2 = 2
    t3 = 3
MH_init_mode_map = {v.name: v for v in MH_init_mode}

class MH_edge(IntEnumC):
    __ctype__ = c_int
    falling = 0
    rising = 1
MH_edge_map = {v.name: v for v in MH_edge}

class MH_ctc_status(IntEnumC):
    __ctype__ = c_int
    acq_running = 0
    acq_ended = 1

class MH_hysteresis(IntEnumC):
    __ctype__ = c_int
    approx_3mV = 0
    approx_35mV = 1

class MH_init_refsource(IntEnumC):
    __ctype__ = c_int
    internal = 0
    ext_10MHz = 1
    white_rabbit_master_generic = 2
    white_rabbit_slave_generic = 3
    white_rabbit_grand_master_generic = 4
    ext_10MHz_with_GPS_pps = 5
    ext_10MHz_with_GPS_pps_time_uart = 6
    white_rabbit_master_multiharp = 7
    white_rabbit_slave_multiharp = 8
    white_rabbit_grand_master_multiharp = 9
MH_init_refsource_map = {v.name: v for v in MH_init_refsource}

class MH_meas_control(IntEnumC):
    __ctype__ = c_int
    single_shot_ctc = 0
    c1_gated = 1
    c1_start_ctc_stop = 2
    c1_start_c2_stop = 3
    wr_m2s = 4
    wr_s2m = 5
    sw_start_sw_stop = 6 # from ver 3.1

class MH_features_available(IntFlagC):
    __ctype__ = c_int
    dll_license = 1
    tttr_mode = 2
    markers = 4
    long_range = 8 # also called low res
    trigger_out = 0x10
    programmable_dead_time = 0x20
    ext_fpga = 0x40
    programmable_hysteresis = 0x80
    event_filtering = 0x100

class MH_flags(IntFlagC):
    __ctype__ = c_int
    overflow = 1 # histo mode only
    fifo_full = 2 # TTR mode only
    sync_lost = 4
    ref_lost = 8
    sys_error = 0x10
    active = 0x20 # measurement running
    cnts_dropped = 0x40

class MH_warnings(IntFlagC):
    __ctype__ = c_int
    __force_check__ = False
    sync_rate_zero =                0x0001
    sync_rate_very_low =            0x0002
    sync_rate_too_high =            0x0004
    input_rate_zero =               0x0010
    input_rate_too_high =           0x0040
    input_rate_ratio =              0x0100
    divider_greater_one =           0x0200
    time_span_too_small =           0x0400
    offset_unnecessary =            0x0800
    divider_too_small =             0x1000
    counts_dropped =                0x2000
    usb20_speed_only =              0x4000

class MH_dll(DLL_Wrapper):
    _dll_cache = None
    def __init__(self, dll_name=r'mhlib64', **kwargs):
        self._Error_strings = {}
        super(MH_dll, self).__init__(dll_name, **kwargs)
        self._init_error()

    def _errcheck(self, result, func, args):
        if result != 0:
            msg = self._Error_strings[result]
            raise PicoQuant_Exception('MultiHarp Error(%i): %s'%(result, msg), result)

    def _init_error(self):
        for i in range(-1, -60-1, -1):
            self._Error_strings[i] = self.GetErrorString(i)

    def _create_funcs(self):
        errcheck = ProxyMethod(self._errcheck)
        create_helper = lambda *args, **kwargs: self._create_helper(*args, errcheck=errcheck, name_prefix='MH_', **kwargs)
        create_helper('GetLibraryVersion', [('Version_', c_string)])
        version = float(self.GetLibraryVersion())
        if version < 3.0:
            raise RuntimeError('You need at least version 3.0 of MHlib')
        create_helper('GetErrorString', [('err_string_', c_string), ('errcode', c_int)])
        create_helper_dev = lambda name, argdefs=[], **kwargs: create_helper(name, [('devid', c_int)]+argdefs, **kwargs)
        create_helper_dev('OpenDevice', [('serial_', c_string)])
        create_helper_dev('CloseDevice')
        create_helper_dev('Initialize', [('mode', MH_init_mode.ctype), ('ref_source', MH_init_refsource.ctype)])
        create_helper_dev('GetWarnings', [('warnings_', MH_warnings.pointer)])
        create_helper_dev('GetWarningsText', [('text_', c_string_warning), ('warnings', MH_warnings.ctype)])

        create_helper_dev('GetHardwareInfo', [('model_', c_string), ('partno_', c_string),  ('version_', c_string)])
        create_helper_dev('GetSerialNumber', [('serial_', c_string)])
        create_helper_dev('GetFeatures', [('features_', MH_features_available.pointer)])
        create_helper_dev('GetBaseResolution', [('resolution_', c_double_p), ('bin_steps_', c_int_p)])
        create_helper_dev('GetNumOfInputChannels', [('nchannels_', c_int_p)])

        create_helper_dev('SetSyncDiv', [('div', c_int)])
        create_helper_dev('SetSyncEdgeTrg', [('level_mV', c_int), ('edge', MH_edge.ctype)])
        create_helper_dev('SetSyncChannelOffset', [('offset_ps', c_int)])
        create_helper_dev('SetSyncDeadTime', [('enable', MH_bool), ('deadtime_ps', c_int)])
        if version >= 3.1:
            create_helper_dev('SetSyncChannelEnable', [('enable', MH_bool)])

        create_helper_dev('SetInputEdgeTrg', [('channel', c_int), ('level_mV', c_int), ('edge', MH_edge.ctype)])
        create_helper_dev('SetInputChannelOffset', [('channel', c_int), ('offset_ps', c_int)])
        create_helper_dev('SetInputDeadTime', [('channel', c_int), ('enable', MH_bool), ('deadtime_ps', c_int)])
        create_helper_dev('SetInputHysteresis', [('hystcode', MH_hysteresis.ctype)]) # since v3.0
        create_helper_dev('SetInputChannelEnable', [('channel', c_int), ('enable', MH_bool)])

        create_helper_dev('SetStopOverflow', [('stop_on_ovfl_en', MH_bool), ('stop_count', c_uint)])
        create_helper_dev('SetBinning', [('binning', c_int)])
        create_helper_dev('SetOffset', [('offset_ns', c_int)])
        # actual_len will be something like 1024*2**lencode # max len_code is 6
        create_helper_dev('SetHistoLen', [('len_code', c_int), ('actual_len_', c_int_p)])
        create_helper_dev('SetMeasControl', [('control', MH_meas_control.ctype), ('start_edge', MH_edge.ctype), ('stop_edge', MH_edge.ctype)])
        create_helper_dev('SetTriggerOutput', [('period_100ns', c_int)])

        create_helper_dev('ClearHistMem')
        create_helper_dev('StartMeas', [('acq_time_ms', c_int)])
        create_helper_dev('StopMeas')
        create_helper_dev('CTCStatus', [('ctc_status_', MH_ctc_status.pointer)])

        create_helper_dev('GetHistogram', [('chcount_', MH_hist_cnt), ('channel', c_int)]) # does not work for 1024 and 2048 histogram lengths
        create_helper_dev('GetAllHistograms', [('chcount+', MH_hist_all_cnt)])
        create_helper_dev('GetResolution', [('resolution_ps_', c_double_p)])
        create_helper_dev('GetSyncPeriod', [('period_s_', c_double_p)])
        create_helper_dev('GetSyncRate', [('sync_rate_', c_int_p)])
        create_helper_dev('GetCountRate', [('channel', c_int), ('cnt_rate_', c_int_p)])
        create_helper_dev('GetAllCountRates', [('sync_rate_', c_int_p), ('cnt_rates_', MH_cnt_buf)])
        create_helper_dev('GetFlags', [('flags_', MH_flags.pointer)])
        create_helper_dev('GetElapsedMeasTime', [('elapsed_ms_', c_double_p)])
        create_helper_dev('GetStartTime', [('time_dw2_', c_uint_p), ('time_dw1_', c_uint_p), ('time_dw0_ps_', c_uint_p)])

        create_helper_dev('SetMarkerHoldoffTime', [('holdoff_time_ns', c_int)])
        create_helper_dev('SetMarkerEdges', [('me1', MH_edge.ctype), ('me2', MH_edge.ctype), ('me3', MH_edge.ctype), ('me4', MH_edge.ctype)])
        create_helper_dev('SetMarkerEnable', [('en1', MH_bool), ('en2', MH_bool), ('en3', MH_bool), ('en4', MH_bool)])
        create_helper_dev('ReadFiFo', [('buffer_', MH_tt_buf), ('_buffer_N_', c_int_p)])
        if version >= 3.1:
            create_helper_dev('SetOflCompression', [('hold_time', c_int)])
            create_helper_dev('SetRowEventFilter', [('row_idx', c_int), ('time_range', c_int), ('match_count', c_int), ('inverse_en', MH_bool), ('use_channels', c_int), ('pass_channels', c_int)])
            create_helper_dev('EnableRowEventFilter', [('row_idx', c_int), ('enable', MH_bool)])
            create_helper_dev('SetMainEventFilterParams', [('time_range', c_int), ('match_count', c_int), ('inverse_en', MH_bool)])
            create_helper_dev('SetMainEventFilterChannels', [('row_idx', c_int), ('use_channels', c_int), ('pass_channels', c_int)])
            create_helper_dev('EnableMainEventFilter', [('enable', MH_bool)])
            create_helper_dev('SetFilterTestMode', [('test_mode_enable', MH_bool)])
            create_helper_dev('GetRowFilteredRates', [('sync_rate_', c_int_p), ('cnt_rates_', MH_cnt_buf)])
            create_helper_dev('GetMainFilteredRates', [('sync_rate_', c_int_p), ('cnt_rates_', MH_cnt_buf)])

        # debug entries
        create_helper_dev('GetDebugInfo', [('debug_info_', c_string_debug)])
        create_helper_dev('GetNumOfModules', [('num_modules_', c_int_p)])
        create_helper_dev('GetModuleInfo', [('mod_index', c_int), ('model_code_', c_int_p), ('version_code_', c_int_p)])
        if version >= 4.0:
            create_helper_dev('SaveDebugDump', [('file_path', c_string_control)])

_dll_MH_load_cache = {}
def _load_MH_dll(dll_name='mhlib64', **kwargs):
    if dll_name in _dll_MH_load_cache:
        return _dll_MH_load_cache[dll_name]
    dll = MH_dll(dll_name, **kwargs)
    _dll_MH_load_cache[dll_name] = dll
    return dll

class Dll_Wrap_Dev(object):
    def __init__(self, parent):
        self._parent = proxy(parent)
    def __getattr__(self, name):
        return lambda *args, **kwargs: getattr(self._parent._dll, name)(self._parent._dev, *args, **kwargs)


class MH_data_dev(Base2Device):
    def __init__(self, read_func=None, write_func=None, use_ch=False, force_type=None,
                 scale=None, generate_arg=None, **kwargs):
        """
        generate_arg is a function (dev_obj, val) that generates the args to be used.
        """
        self.use_ch = use_ch
        self.force_type = force_type
        self.generate_arg = generate_arg
        self.scale = scale
        if write_func is not None and read_func is None:
            if use_ch:
                kwargs['cache_as_get'] = (['ch'], )
            else:
                kwargs['cache_as_get'] = True
        super(MH_data_dev, self).__init__(**kwargs)
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
            vals = self.generate_arg(self, val)
        else:
            vals = (val,)
        if self.use_ch:
            ch = options['ch']
            args = (ch-1,) + vals
        else:
            args = vals
        self.write_func(*args)

    def _get_ask(self, options):
        if self.use_ch:
            ch = options['ch']
            args = (ch-1,)
        else:
            args = ()
        val = self.read_func(*args)
        if self.scale is not None:
            val = val * self.scale
        if isinstance(self.choices, ChoiceBase):
            val = self.choices(val)
        return val


class Choice_Enum(ChoiceSimpleMap):
    def __init__(self, enum, **kwargs):
        d = {v: v.name for v in enum}
        super(Choice_Enum, self).__init__(d, **kwargs)


class MH_readfifo_thread(threading.Thread):
    def __init__(self, parent, handler, repeat, mode, hndlr_params):
        super(MH_readfifo_thread, self).__init__()
        self.parent = parent
        self.instr = parent # used for locked
        self.handler = handler
        self.__stop = False
        self.daemon = True # This will allow python to exit
        self.data = []
        self.ii = 0
        self.last_ah = False
        self.repeat = repeat
        self.mode = mode
        self.hndlr_params = hndlr_params
        #self.sync_period = []
        self.sync_period = 0

    def cancel(self):
        self.__stop = True

    @locked_calling_dev
    def do_read(self, just_data=False):
        data = self.parent._dlldev.ReadFiFo()
        #self.sync_period.append(self.parent.sync_period.get())
        self.ii += 1
        if len(data) == 0 and not just_data:
            ah = self.parent._async_detect_poll_helper()
            self.last_ah = ah
        else:
            ah = self.last_ah
            #ah = self.parent._async_detect_poll_helper()
        #print('%6d  %10d %5s %.3f'%(self.ii, len(data), ah, time.time()))
        return data, ah

    def run(self):
        # This print is needed on anaconda 2019.10 on windows 10 to prevent
        #  a windows error exeption when later trying to print in the thread (status_line)
        # Doing a print at the beginning of the thread fixes that problem.
        #print('ReadFifo Thread started')
        #self.sync_period.append(self.parent.sync_period.get())
        handler = self.handler
        period = self.sync_period
        mode = self.mode
        repeat = self.repeat
        handler.reset(self.hndlr_params)
        while True:
            if self.__stop:
                return
            data, ah = self.do_read()
            if mode == 't3' and period == 0.:
                # I check and for very slow sync signals (like 10 Hz)
                # reading start at 0. and the it jumps to the correct value.
                # The value will move a little, here we only keep the first valid one.
                period = self.parent.sync_period.get()
                self.sync_period = period
            if len(data != 0):
                handler.new_data(data, period)
            #print(len(data))
            if ah:
                for i in range(repeat):
                    data, ah_ = self.do_read()
                    if len(data) != 0:
                        handler.new_data(data, period)
                handler.done()
                break
            if len(data) == 0:
                #print('async helper', ah)
                #if self.parent._async_detect_poll_helper():
                time.sleep(0.01)

    def wait(self, timeout=None):
        # we use a the context manager because join uses sleep.
        with _sleep_signal_context_manager():
            self.join(timeout)
        return not self.is_alive()

class MH_default_handler(object):
    """ This is the default handler implementation.
    It just concatenates the data together.
    You can subclass it and override most of the functions.
    You probably want to keep calling __init__, pre_reset and wait_completed
     (stuff dealing with completed_event)
    """
    def __init__(self):
        self.completed_event = FastEvent()
    def pre_reset(self):
        """ This is called by start_measurement """
        # the reset is called from readfifo so it can be called after we start wait_completed
        # which would not work. So we make sure the event is cleared at an earlier stage.
        self.completed_event.clear()
    def reset(self, params):
        """ This is to restart an acquisition """
        self.data = []
    def done(self):
        """ This warns that all the data has been submitted """
        self.completed_event.set()
    def new_data(self, data, sync_period=0.):
        self.data.append(data)
    def get_titles(self, xaxis, bins):
        """ returns the data columns names. Called by fetch getdev """
        return ["data"], False
    def get_data(self):
        if hasattr(self, 'data') and len(self.data):
            return np.concatenate(self.data)
        else:
            return np.array([], dtype=np.uint32)
    def wait_completed(self, timeout):
        return self.completed_event.wait(timeout)

class MH_handler_thread(threading.Thread):
    def __init__(self, queue, do_calc, completed_event):
        super(MH_handler_thread, self).__init__()
        self.queue = queue
        self.__stop = False
        self.daemon = True # This will allow python to exit
        self.result = None
        self.do_calc = do_calc
        self.completed_event = completed_event
        self.lock_result = threading.Lock()

    def cancel(self):
        self.__stop = True

    def set_result(self, res):
        with self.lock_result:
            self.result = res

    def run(self):
        # This print is needed on anaconda 2019.10 on windows 10 to prevent
        #  a windows error exeption when later trying to print in the thread (status_line)
        # Doing a print at the beginning of the thread fixes that problem.
        #print('ReadFifo Thread started')
        while True:
            if self.__stop:
                break
            try:
                data, sync_period = self.queue.get(timeout=1.)
            except queue.Empty:
                continue
            if data is None: # finished
                break
            with self.lock_result:
                if self.result is None:
                    reuse = None
                else:
                    reuse = self.result[-1]
            res = self.do_calc(data, sync_period, reuse=reuse)
            self.set_result(res)
            self.queue.task_done()
        # instead of waiting on the thread, we wait on this event.
        # because we can reset the event in the proper order.
        # the thread migth not be started before we try to wait on it.
        self.completed_event.set()

    def get_result(self):
        with self.lock_result:
            if self.result is None:
                return None
            return copy.deepcopy(self.result[:-1])

    def wait(self, timeout=None):
        # we use a the context manager because join uses sleep.
        with _sleep_signal_context_manager():
            self.join(timeout)
        return not self.is_alive()


class MH_Threaded_handler(MH_default_handler):
    """ This is the handler for operation that take a while.
    You can subclass it and override all the functions.
    You probably want to modify reset, do_calc and get_data.
    """
    def __init__(self, config):
        """ See Simple_Slow_Histo_T2 for a description of the paramters """
        super(MH_Threaded_handler, self).__init__()
        self.config = config
        self.queue = queue.Queue()
        self.calc_thread = None
        self.xaxis = True
        self.bins = False
        self.base_resolution_ps = None
        self.base_resolution = -1.
        self.resolution_ps = None
        self.resolution = -.1
        self.mode = None

    def pre_reset(self):
        if self.calc_thread is not None:
            # Need to make sure it is stopped
            # so it cannot sset the completed_event before we start.
            self.calc_thread.cancel()
            self.calc_thread.wait()
            self.calc_thread = None
        super(MH_Threaded_handler, self).pre_reset()
        # empty queue
        while True:
            try:
                self.queue.get(block=False)
            except queue.Empty:
                break

    def reset(self, params):
        """ This is to restart an acquisition. It is called by the readfifo thread. """
        self.xaxis = params['xaxis']
        self.bins = params['bins']
        self.base_resolution_ps = params['base_res_ps']
        self.base_resolution = self.base_resolution_ps*1e-12
        self.resolution_ps = params['res_ps']
        self.resolution = self.resolution_ps*1e-12
        self.mode = params['mode']
        do_calc = ProxyMethod(self.do_calc)
        self.calc_thread = MH_handler_thread(self.queue, do_calc, self.completed_event)
        self.calc_thread.start()

    def done(self):
        """ This warns that all the data has been submitted. It is called by the readfifo thread. """
        self.queue.put((None, 0)) # finished

    def new_data(self, data, sync_period=0.):
        """ This is called to receive new data. It is called by the readfifo thread. """
        self.queue.put((data, sync_period))

    def do_calc(self, data, sync_period=0., reuse=None):
        """ this is called to the actual calcution from the data. It is called by MH_handler_thread.
            It should return useful data.
            The last element is reused in following calls as reuse. It can be used to carry information
            between calls.
        """
        pass

    def _get_data(self):
        """ returns a deepcopy version of the data from the last do_calc, with the last element removed."""
        if self.calc_thread is not None:
            data = self.calc_thread.get_result()
            return data
        return None

    def get_data(self):
        """ returns the data to the correct format. Called by fetch """
        return self._get_data()

    def get_titles(self, xaxis, bins):
        """ returns the data columns names and xaxis state. Called by fetch getdev """
        return ["data"], False


class MH_Simple_Histo_handler(MH_Threaded_handler):
    def __init__(self, ch_histo=1, sync=1, t0=0, t1=5000, dt=5, exclude_of_uf=True):
        config = dict(ch_histo=ch_histo, sync=sync, t0=t0, t1=t1, dt=dt, resolution=None, exclude_of_uf=exclude_of_uf)
        super(MH_Simple_Histo_handler, self).__init__(config)
        self.delayed_data = []

    def reset(self, params):
        super(MH_Simple_Histo_handler, self).reset(params)
        if self.mode == 't3':
            self.config['resolution'] = self.resolution
        else:
            self.config['resolution'] = self.base_resolution

    def do_calc(self, data, sync_period=0., reuse=None):
        if self.mode == 't3':
            conf = self.config.copy()
            func = Simple_Fast_Histo_T3
            conf['sync_period'] = sync_period
            if conf['sync'] != 0:
                # if sync refence is not ch 0, we need a proper sync_period
                if sync_period == 0.:
                    # we delay calculation until we know the sync_period
                    self.delayed_data.append(data)
                    ret = func(data[:0], **conf)
                    ret = ret[:-1] + (None,)
                    return ret
                elif self.delayed_data != []:
                    print(self.delayed_data)
                    for i, d in enumerate(self.delayed_data):
                        if i == 0:
                            ret = func(d, **conf)
                        else:
                            ret = func(d, reuse=ret[-1])
                    reuse = ret[-1]
                    self.delayed_data = []
        else:
            func = Simple_Fast_Histo_T2
            conf = self.config
        if reuse is None:
            return func(data, **conf)
        else:
            return func(data, reuse=reuse)

    def get_titles(self, xaxis, bins):
        titles = []
        if xaxis:
            if bins:
                titles = ['bin_#']
            else:
                titles = ['time(s)']
        titles.append("data")
        # use tuple to make it an external file
        return tuple(titles), xaxis

    def get_data(self):
        ret_data = self._get_data()
        if ret_data is None:
            return np.array([])
        data = []
        if self.xaxis:
            if self.bins:
                data = [ret_data[1]]
            else:
                data = [ret_data[2]]
        data.append(ret_data[0])
        return np.asarray(data)


class MH_Full_Histo_handler(MH_Threaded_handler):
    def __init__(self, ch_histo=1, sync=1, t0=0, t1=5000, dt=5, exclude_of_uf=True, time_is_bin=False, max_N=100e5,
                 notify_func=None, notify_interval=1.):
        """
        notifiy_func, if given, will be called after every notify_interval.
              The function is called with this object (self) as a first parameter and a second parameter
              of  reset which is True when the measurement restarts.
              You can use an emit function for a PyQt signal,
              and then call the get_data method to obtain parial data
              that can be ploted.
              Note that this function is called from the calculation thread,
              not the main thread.
              Here is an example of use:
        --------
        from PyQt5 import QtCore
        class Observer(QtCore.QObject):
            def __init__(self):
                super(Observer, self).__init__()
                self.new_data.connect(self.test_slot)
            new_data = QtCore.pyqtSignal([object, __builtin__.bool])
            def test_slot(self, ob, reset=False):
                if reset:
                    figure("Observer_Data")
                    clf()
                    draw()
                    return
                v = ob.get_data()
                if len(v):
                    figure("Observer_Data")
                    plot(v[0], v[1])
                    draw()
        obs = Observer()
        handler = instruments.picoQuant.MH_Full_Histo_handler(1, 0, t0=0, t1=1e-6, dt=1e-9, notify_func=obs.new_data.emit)
        set(mh.meas_duration, 20)
        v = get(mh.readval, handler=handler)
        # or set default handler with:
        mh.set_default_handler(handler)
        ---------
        For all the other parameters, see either Full_Fast_Histo_T2 or Full_Fast_Histo_T3.
        """
        config = dict(ch_histo=ch_histo, sync=sync, t0=t0, t1=t1, dt=dt, resolution=None,
                      exclude_of_uf=exclude_of_uf, time_is_bin=time_is_bin, max_N=max_N)
        self.notify_func = notify_func
        self.notify_interval = notify_interval
        self.last_notify = 0.
        super(MH_Full_Histo_handler, self).__init__(config)
        self.delayed_data = []

    def reset(self, params):
        super(MH_Full_Histo_handler, self).reset(params)
        self.delayed_data = []
        if self.mode == 't3':
            self.config['resolution'] = self.resolution
        else:
            self.config['resolution'] = self.base_resolution
        self.last_notify = time.time()
        if self.notify_func:
            self.notify_func(self, True)  # reset True

    def do_calc(self, data, sync_period=0., reuse=None):
        if self.mode == 't3':
            conf = self.config.copy()
            func = Full_Fast_Histo_T3
            conf['sync_period'] = sync_period
            if conf['sync'] != 0:
                # if sync refence is not ch 0, we need a proper sync_period
                if sync_period == 0.:
                    # we delay calculation until we know the sync_period
                    self.delayed_data.append(data)
                    ret = func(data[:0], **conf)
                    ret = ret[:-1] + (None,)
                    return ret
                elif self.delayed_data != []:
                    print(self.delayed_data)
                    for i, d in enumerate(self.delayed_data):
                        if i == 0:
                            ret = func(d, **conf)
                        else:
                            ret = func(d, reuse=ret[-1])
                    reuse = ret[-1]
                    self.delayed_data = []
        else:
            func = Full_Fast_Histo_T2
            conf = self.config
        if reuse is None:
            ret = func(data, **conf)
        else:
            ret = func(data, reuse=reuse)
        now = time.time()
        if self.notify_func and now > (self.last_notify + self.notify_interval):
            self.last_notify = now
            self.notify_func(self, False) # reset False
        return ret

    def get_titles(self, xaxis, bins):
        tmp_config = self.config.copy()
        tmp_config['resolution'] = 1e-12 # smaller than smalles resolution which should be 5e-12.
                                         # This is to prevent _parse_histo_param from generating errors.
        params = _parse_histo_param(**tmp_config)
        titles = []
        for meas, sync in zip(params[0], params[1]):
            if xaxis:
                if bins:
                    titles.append('bin_%d_%d_#'%(meas, sync))
                else:
                    titles.append('time_%d_%d(s)'%(meas, sync))
            titles.append("count_%d_%d"%(meas, sync))
        # use tuple to make it an external file
        return tuple(titles), xaxis

    def get_data(self):
        ret_data = self._get_data()
        if ret_data is None:
            return np.array([])
        max_len = max([len(h) if h is not None else 0 for h in ret_data[0]])
        if self.xaxis:
            dim_factor = 2
            ret_offset = 1
        else:
            dim_factor = 1
            ret_offset = 0
        shape = (len(ret_data[0])*dim_factor, max_len)
        ret = np.full(shape, np.nan)
        for i, (h, b, t) in enumerate(zip(*ret_data)):
            n = len(h)
            if self.xaxis:
                if self.bins:
                    ret[i*2, :n] = b
                else:
                    ret[i*2, :n] = t
            ret[i*dim_factor + ret_offset, :n] = h
        return ret

    def wait_completed(self, timeout):
        ret = super(MH_Full_Histo_handler, self).wait_completed(timeout)
        if ret:
            self.last_notify = time.time()
            if self.notify_func:
                self.notify_func(self, False)  # reset False
        return ret


#######################################################
##    PicoQuant MultiHarp 150 dll driver
#######################################################

@register_instrument('PicoQuant', 'MultiHarp')
class PicoQuant_MultiHarp_dll(BaseInstrument):
    """
    This controls the picoQuant MultiHarp (at least model 150).
    Useful devices:
        fetch
        readval
        hist_sum
        flags
        is_acquisition_complete
        elapsed_time
        last_acq_flags
        start_time
        async_wait (is the time for readval when reading counts, defaults to 0.1 s)
    Useful methods:
        discover (static method)
        conf_ch
        conf_sync
        conf_global
        conf_markers
        set_mode_refsrc
        set_default_handler
        get_warnings
        get_debug_info
        start_measurement
        stop_measurement
        clear_histogram
    Note that some parameters (like sync_divisor) should be changed only when
    measurements are stopped.
    Note also that for t2/t3 data with low count rates, the acquisition length
    might need to be adjusted. You should make sure that fifo_compression is
    not too large (defaults to 2, can be 0 to disable it). And adjust the number of
    extra readings after the capture. Use check_fifo_residuals to verify the configuration.
    """
    def __init__(self, dev_num_name=0, mode='hist', ref_src='internal', dll_name='mhlib64', fifo_extra_readings=1, **kwargs):
        self._dev = None
        self._dll = _load_MH_dll(dll_name=dll_name)
        self._serial_num = None
        self._hist_sum = None
        self._last_flags = []
        self._last_acq_flags = 0
        self._readfifo_thread = None
        self._default_handler = MH_default_handler()
        self._last_handler = None
        self._fifo_extra_readings = fifo_extra_readings

        conf_sync = kwargs.pop('conf_sync', None)
        conf_global = kwargs.pop('conf_global', None)
        conf_markers = kwargs.pop('conf_markers', None)
        names = sorted([k for k in kwargs if k.startswith('conf_ch')])
        conf_chs = [kwargs.pop(n) for n in names]
        self._dlldev = Dll_Wrap_Dev(self)
        self.open(dev_num_name)
        # locks are not available yet but we need to do init before _create_devs
        # is called. Hence the use of _set_mode_refsrc instead of set_mode_refsrc
        # before __init__
        self._set_mode_refsrc(mode, ref_src, _init=True)
        super(PicoQuant_MultiHarp_dll, self).__init__(**kwargs)
        self._delayed_init()
        if conf_sync is not None:
            if isinstance(conf_sync, dict):
                self.conf_sync(**conf_sync)
            else:
                self.conf_sync(*conf_sync)
        if conf_global is not None:
            if isinstance(conf_global, dict):
                self.conf_global(**conf_global)
            else:
                self.conf_global(*conf_global)
        if conf_markers is not None:
            if isinstance(conf_markers, dict):
                self.conf_markers(**conf_markers)
            else:
                self.conf_markers(*conf_markers)
        for conf_ch in conf_chs:
            if isinstance(conf_ch, dict):
                self.conf_ch(**conf_ch)
            else:
                self.conf_ch(*conf_ch)
        self._async_detect_with_lock = False
        self._async_mode = 'poll' # not wait
        self.async_wait.set(.1) # async wait time when fetching count by default.
    __init__.__doc__ = \
        """
        dev_num_name can be a number, which selects that device discovered.
                It can also be a serial number string to select one
                You can use the static method discover to list devices.
        mode must be one of %r
        ref_src must be one of %r
        fifo_extra_readings is the number of extra readings to take after a t2/t3 measurement.
                It should be at least 1. It should be made longer for very small count rate.
                You can change it later by modifying the _fifo_extra_readings attribute.
        You can have parameters conf_sync, conf_global, conf_markers and conf_ch?? (where ?? can be any extra characters
        you want, they will be used in alphabetical order) and those values will be passed to
        conf_sync, conf_global, conf_markers and conf_ch after initialization.
        The values can be dict or lists.
        """%(list(MH_init_mode_map.keys()), list(MH_init_refsource_map.keys()))

    @staticmethod
    def discover(_dll=None, _dll_name='mhlib64'):
        """
        returns a list of names (serial number)
        """
        if _dll is None:
            dll = _load_MH_dll(dll_name=_dll_name)
        else:
            dll = _dll
        ret = []
        i = 0
        while i<8:
            try:
                val = dll.OpenDevice(i)
            except PicoQuant_Exception as exc:
                if exc.errno == -1: #MH_ERROR_DEVICE_OPEN_FAIL
                    break
            dll.CloseDevice(i)
            ret.append(val)
            i += 1
        return ret

    def open(self, dev_num_name=0):
        if isinstance(dev_num_name, string_bytes_types):
            dev_num = self.discover(_dll=self._dll).index(dev_num_name)
        else:
            dev_num = dev_num_name
        self._dev = dev_num
        serial = self._dll.OpenDevice(dev_num)
        self._serial_num = serial

    def _close(self):
        if hasattr(self, '_dev') and self._dev is not None:
            self._stop_measurement()
            self._dll.CloseDevice(self._dev)
            self._dev = None
    @locked_calling
    def close(self):
        self._close()

    @locked_calling
    def _delayed_init(self):
        # Appply what I think the defaults are in case they are the wrong defaults.
        conf_sync = self.conf_sync()
        conf_chs = self.conf_ch()
        conf_global = self.conf_global()
        conf_markers = self.conf_markers()
        self.conf_sync(**conf_sync)
        self.conf_global(**conf_global)
        self.conf_markers(**conf_markers)
        for conf_ch in conf_chs:
            self.conf_ch(**conf_ch)

    def _get_handler_helper(self, params):
        handler = params.get('handler', None)
        if handler is None:
            handler = self._default_handler
        return handler

    def _async_select(self, devs):
        self._async_mode = 'wait'
        if self._readfifo_thread:
            self._readfifo_thread.cancel()
        self._readfifo_thread = None
        for dev in devs:
            if isinstance(dev, tuple):
                d = dev[0]
                p = dev[1]
            else:
                d = dev
                p = {}
            if d in [self.fetch, self.readval]:
                count = p.get('count', False)
                if not count:
                    self._async_mode = 'poll'
                    if self._init_mode != 'hist':
                        xaxis = p.get('xaxis', True)
                        bins = p.get('bins', False)
                        handler = self._get_handler_helper(p)
                        self._last_handler = handler
                        s = proxy(self)
                        hndlr_params = dict(xaxis=xaxis, bins=bins, base_res_ps=self._resolution_base_ps,
                                            res_ps=self.resolution_ps.get(), mode=self._init_mode)
                        self._readfifo_thread = MH_readfifo_thread(s, handler, self._fifo_extra_readings, self._init_mode, hndlr_params)
            if d == self.hist_sum:
                self._async_mode = 'poll'

    @locked_calling
    def _async_trig(self):
        super(PicoQuant_MultiHarp_dll, self)._async_trig()
        if self._async_mode == 'wait':
            return
        # make sure previous one is stopped
        self.stop_measurement(no_handler=True)
        if self._init_mode == 'hist':
            self._hist_sum = None
            self.clear_histogram()
        # clear status
        self.is_acquisition_complete.get()
        self.flags.get()
        self._last_acq_flags = MH_flags(0)
        self.start_measurement()

    def _async_detect_poll_helper(self):
        flags = self.flags.get()
        #elapse = self.elapsed_time.get()
        #full = self.meas_duration.get()
        complete = self.is_acquisition_complete.get()
        if complete:
            return True
        if MH_flags.overflow in flags:
            return True
        return False

    def _async_detect(self, max_time=.5):
        if self._async_mode not in ['wait', 'poll']:
            raise RuntimeError('Invalid async_mode selected')
        if self._async_mode == 'wait':
            return super(PicoQuant_MultiHarp_dll, self)._async_detect(max_time)
        if self._readfifo_thread:
            return wait_on_event(self._readfifo_thread.handler.wait_completed)
            # if _retry_wait(lambda : not self._readfifo_thread.is_alive(), max_time, delay=0.05):
            #     if _retry_wait(self._readfifo_thread.handler.is_completed, max_time, delay=0.05):
            #         return True
        elif _retry_wait(self._async_detect_poll_helper, max_time, delay=0.05):
            return True
        return False

    def _async_cleanup_after(self):
        if self._async_mode == 'poll':
            self.stop_measurement()
        super(PicoQuant_MultiHarp_dll, self)._async_cleanup_after()

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        opts = ['conf_sync=%r'%self.conf_sync()]
        opts += ['conf_ch=%r'%self.conf_ch()]
        opts += ['conf_global=%r'%self.conf_global()]
        opts += ['conf_markers=%r'%self.conf_markers()]
        opts += ['set_mode=%r'%self.set_mode_refsrc()]
        opts += ['base_resolution_ps=%r'%self._resolution_base_ps]
        opts += ['fifo_extra_readings=%r'%self._fifo_extra_readings]
        opts += ['features=%r'%self._features]
        return opts + self._conf_helper(options)

    def _set_mode_refsrc(self, mode=None, ref_src=None, _init=False):
        if mode is None and ref_src is None:
            return dict_improved(mode=self._init_mode, ref_src=self._init_refsrc)
        if mode is None:
            mode = self._init_mode
        elif mode not in MH_init_mode_map:
            raise ValueError(self.perror('Invalid mode. Needs to be one of %r'%list(MH_init_mode_map.keys())))
        if ref_src is None:
            ref_src = self._init_refsrc
        elif ref_src not in MH_init_refsource_map:
            raise ValueError(self.perror('Invalid ref_src. Needs to be one of %r'%list(MH_init_refsource_map.keys())))
        if not _init:
            conf_sync = self.conf_sync()
            conf_chs = self.conf_ch()
            conf_global = self.conf_global()
            conf_markers = self.conf_markers()
        self._dlldev.Initialize(MH_init_mode_map[mode], MH_init_refsource_map[ref_src])
        self._init_mode = mode
        self._init_refsrc = ref_src
        if not _init:
            # Init resets all the parameters, we set them back to what they were
            self.conf_sync(**conf_sync)
            self.conf_global(**conf_global)
            self.conf_markers(**conf_markers)
            for conf_ch in conf_chs:
                self.conf_ch(**conf_ch)

    @locked_calling
    def set_mode_refsrc(self, mode=None, ref_src=None, _init=False):
        return self._set_mode_refsrc(mode, ref_src, _init)
    set_mode_refsrc.__doc__ = \
        """ set the mode and refsrc
            if both are None, return the current one.
            Otherwise changes one or both
            mode must be one of %r
            ref_src must be one of %r
        """%(list(MH_init_mode_map.keys()), list(MH_init_refsource_map.keys()))


    def set_default_handler(self, handler):
        """ sets the default handler to be used when obtaining data in t2/t3 mode.
        for example:
            instr.set_default_handler(instruments.picoQuant.MH_Simple_Histo_handler(0, 0,
                            t0=99900, t1=100100, dt=1, exclude_of_uf=False)
        """
        self._default_handler = handler

    def __del__(self):
        try:
            # we might have lost access to locks already. So skip doing locking.
            self._close()
        except PicoQuant_Exception as exc:
            print("!! Error during del: %r"%exc)
        super(PicoQuant_MultiHarp_dll, self).__del__()

    @locked_calling
    def idn(self):
        model, partno, version = self._dlldev.GetHardwareInfo()
        libversion = self._libversion
        serial = self._serial_num
        ver = 'hw:%s_lib:%s'%(version, libversion)
        return "PicoQuant,%s,%s,%s"%(model, serial, ver)

    def _count_rate_all_getdev(self):
        sync_count, ch_count = self._dlldev.GetAllCountRates()
        return np.concatenate(([sync_count], ch_count[:self._num_of_ch]))

    def _update_ch_trig(self, ch, obj):
        edge = self.input_ch_edge_type.get(ch=ch)
        edge = self.input_ch_edge_type.choices.tostr(edge)
        level = self.input_ch_edge_level.get()*1e3
        self._dlldev.SetInputEdgeTrg(ch-1, int(level), edge)

    def _update_sync_trig(self, ch, obj):
        edge = self.sync_edge_type.get()
        edge = self.sync_edge_type.choices.tostr(edge)
        level = self.sync_edge_level.get()*1e3
        self._dlldev.SetSyncEdgeTrg(int(level), edge)

    def _update_meas(self, ch, obj):
        def get(dev):
            v = dev.get()
            v = dev.choices.tostr(v)
            return v
        control = get(self.meas_control_type)
        start = get(self.meas_start_edge)
        stop = get(self.meas_stop_edge)
        self._dlldev.SetMeasControl(control, start, stop)

    def _ch_helper(self, ch):
        if ch is not None:
            self.current_ch.set(ch)
        return self.current_ch.get()

    @contextmanager
    def _protect_ch_change(self, cleanup=True):
        orig_ch = None
        try:
            orig_ch = self.current_ch.get()
            d = dict(cleanup=cleanup)
            yield d
        finally:
            if d["cleanup"] and orig_ch is not None:
                self.current_ch.set(orig_ch)

    @locked_calling
    def conf_ch(self, ch=None, enabled=None, edge_type=None, edge_level=None,
                offset_ps=None, deadtime_ps=None):
        """ With no paramters or just ch, returns the current (cached) configuration.
        With any parameter changes it.
        Upon reading, ch can be None (returns all channels), a single ch or a list of ch
        Upon changing values, ch can be a single ch, or a list of ch.
        It can also be 0 to mean all channels.
        """
        lcls = locals().copy()
        lcls.pop('self')
        lcls.pop('ch')
        d_in = [("enabled", self.input_ch_en),
                 ("edge_type", self.input_ch_edge_type),
                 ("edge_level", self.input_ch_edge_level),
                 ("offset_ps", self.input_ch_offset_ps)]
        if  MH_features_available.trigger_out in self._features:
             d_in += [("deadtime_ps", self.input_ch_deadtime_ps)]
        d = OrderedDict(d_in)
        if all([v is None for v in lcls.values()]):
            single = False
            if ch is None:
                chs = self._all_chs
            elif not isinstance(ch, (list, tuple, np.ndarray)):
                single = True
                chs = [ch]
            else:
                chs = ch
            ret = []
            with self._protect_ch_change(cleanup=not single):
                for c in chs:
                    self.current_ch.set(c)
                    data = [('ch', c)]
                    for k, v in d.items():
                        data.append((k, v.get()))
                    dd = dict_improved(data)
                    ret.append(dd)
            if single:
                ret = ret[0]
            return ret
        # We are to set some values but only if ch is given
        single = False
        if ch is None:
            raise ValueError('You need to specify a ch.')
        if ch == 0:
            ch = self._all_chs
        if not isinstance(ch, (list, tuple, np.ndarray)):
            ch = [ch]
            single = True
        with self._protect_ch_change(cleanup=not single):
            for c in ch:
                self.current_ch.set(c)
                for k, v in d.items():
                    val = lcls[k]
                    if val is not None:
                        v.set(val)

    @locked_calling
    def conf_sync(self, edge_type=None, edge_level=None, divisor=None, offset_ps=None, deadtime_ps=None, enabled=None):
        """ enabled will only work for t2 mode """
        lcls = locals().copy()
        lcls.pop('self')
        d_in = [("edge_type", self.sync_edge_type),
                 ("edge_level", self.sync_edge_level),
                 ("divisor", self.sync_divisor),
                 ("offset_ps", self.sync_offset_ps)]
        if  MH_features_available.trigger_out in self._features:
            d_in += [("deadtime_ps", self.sync_deadtime_ps)]
        if hasattr(self, "sync_en"):
            d_in += [("enabled", self.sync_en)]
        d = OrderedDict(d_in)
        if all([v is None for v in lcls.values()]):
            data = []
            for k, v in d.items():
                data.append((k, v.get()))
            dd = dict_improved(data)
            return dd
        # We are to set some values
        for k, v in d.items():
            val = lcls[k]
            if val is not None:
                if k == 'enabled' and self._init_mode != 't2':
                    v.check(val)
                    v.setcache(val)
                else:
                    v.set(val)

    @locked_calling
    def conf_global(self, meas_duration=None, stop_on_overflow=None, histogram_binning=None,
                    histogram_offset_ns=None, histogram_len=None,
                    trigger_output_period=None,
                    input_hysteresis=None, fifo_compression_ms=None,
                    meas_control_type=None, meas_start_edge=None, meas_stop_edge=None):
        """
        some parameters only apply in certain modes:
        only hist: stop_on_overflow, histogram_len
        only t3, hist: histogram_binning, histogram_offset_ns
        if a feature is not available, it is not returned (setting it will have not effect.)
        """
        lcls = locals().copy()
        lcls.pop('self')
        d_in = [("meas_duration", (self.meas_duration, ['hist', 't2', 't3'])),
                 ("stop_on_overflow", (self.stop_on_overflow, ['hist'])),
                 ("histogram_binning", (self.histogram_binning, ['hist', 't3'])),
                 ("histogram_offset_ns", (self.histogram_offset_ns, ['hist', 't3'])),
                 ("histogram_len", (self.histogram_len, ['hist']))]
        if  MH_features_available.trigger_out in self._features:
                 d_in += [("trigger_output_period", (self.trigger_output_period, ['hist', 't2', 't3']))]
        if hasattr(self, "input_hysteresis") and MH_features_available.programmable_hysteresis in self._features:
            d_in.append(("input_hysteresis", (self.input_hysteresis, ['hist', 't2', 't3'])))
        if hasattr(self, "fifo_compression_ms"):
            d_in.append(("fifo_compression_ms", (self.fifo_compression_ms, ['hist', 't2', 't3'])))
        d_in += [("meas_control_type", (self.meas_control_type, ['hist', 't2', 't3'])),
                 ("meas_start_edge", (self.meas_start_edge, ['hist', 't2', 't3'])),
                 ("meas_stop_edge", (self.meas_stop_edge, ['hist', 't2', 't3']))]
        d = OrderedDict(d_in)
        if all([v is None for v in lcls.values()]):
            data = []
            for k, (v, mode) in d.items():
                data.append((k, v.get()))
            dd = dict_improved(data)
            return dd
        # We are to set some values
        for k, (v, mode) in d.items():
            val = lcls[k]
            if val is not None:
                if self._init_mode in mode:
                    v.set(val)
                else:
                    v.check(val)
                    v.setcache(val)

    @locked_calling
    def conf_markers(self, holdoff_time_ns=None, en1=None, edge1=None, en2=None, edge2=None, en3=None, edge3=None, en4=None, edge4=None):
        """ Markers will only work on T2 and T3 modes, not in histogram
        If markers are not available, it returns an empty dict.
        """
        if MH_features_available.markers not in self._features:
            return {}
        lcls = locals().copy()
        lcls.pop('self')
        if not hasattr(self, "_cache_markers"):
            self._cache_markers = dict(en1=False, en2=False, en3=False, en4=False,
                                       edge1='falling', edge2='falling', edge3='falling', edge4='falling')
        if all([v is None for v in lcls.values()]):
            holdoff = self.marker_holdoff_time_ns.get()
            names = ['en1', 'edge1', 'en2', 'edge2', 'en3', 'edge3', 'en4', 'edge4']
            d = [('holdoff_time_ns', holdoff)]
            for n in names:
                d.append((n, self._cache_markers[n]))
            return dict_improved(d)
        # We are to set some values
        if self._init_mode not in ['t2', 't3']:
            do_func = False
        else:
            do_func = True
        if holdoff_time_ns is not None:
            if do_func:
                self.marker_holdoff_time_ns.set(holdoff_time_ns)
            else:
                self.marker_holdoff_time_ns.check(holdoff_time_ns)
                self.marker_holdoff_time_ns.setcache(holdoff_time_ns)
        lcls.pop('holdoff_time_ns')
        en = ['en%d'%i for i in range(1,4+1)]
        edge = ['edge%d'%i for i in range(1,4+1)]
        if not all([lcls[n] is None for n in en]):
            for n in en:
                if lcls[n] is None:
                    lcls[n] = self._cache_markers[n]
                elif lcls[n] not in [True, False]:
                    raise ValueError('Invalid value for marker enable')
            if do_func:
                self._dlldev.SetMarkerEnable(*[lcls[n] for n in en])
            for n in en:
                self._cache_markers[n] = lcls[n]
        if not all([lcls[n] is None for n in edge]):
            for n in edge:
                if lcls[n] is None:
                    lcls[n] = self._cache_markers[n]
                elif lcls[n] not in ['rising', 'falling']:
                    raise ValueError('Invalid value for marker edge')
            if do_func:
                self._dlldev.SetMarkerEdges(*[MH_edge_map[lcls[n]] for n in edge])
            for n in edge:
                self._cache_markers[n] = lcls[n]

    @locked_calling
    def get_warnings(self, warn_value=None):
        if warn_value is None:
            warn_value = self.warnings.get()
        return self._dlldev.GetWarningsText(warn_value)

    @locked_calling
    def get_debug_info(self, skip_txt=False):
        num_mod = self._dlldev.GetNumOfModules()
        modules = []
        for m in range(num_mod):
            model_code, version_code = self._dlldev.GetModuleInfo(m)
            modules.append(dict_improved(model_code=model_code, version_code=version_code))
        serial = self._dlldev.GetSerialNumber()
        model, partno, version = self._dlldev.GetHardwareInfo()
        features = self._dlldev.GetFeatures()
        if not skip_txt:
            dbg = self._dlldev.GetDebugInfo()
        else:
            dbg = ''
        return dict_improved(model=model, serial=serial, part_number=partno, features=features,
                             version=version, libversion=self._libversion, modules=modules,
                             debug_txt=dbg)

    def _start_time_getdev(self):
        data = self._dlldev.GetStartTime()
        # data is 3 number. The last one is in ps.
        full = data[2] + (data[1]<<32) + (data[0]<<64)
        return full//int(1e12), full%int(1e12)

    @locked_calling
    def start_measurement(self, duration=None):
        """ if duration is None, it uses the meas_duration device value """
        if duration is None:
            duration = self.meas_duration.get()
        if not 0.001 <= duration <= 360000:
            raise ValueError('duration needs to be at least 1 ms and at most 100 hours')
        self._dlldev.StartMeas(int(duration*1e3))
        if self._readfifo_thread:
            self._readfifo_thread.handler.pre_reset()
            self._readfifo_thread.start()
        #print("Doing Start")

    @locked_calling
    def clear_histogram(self):
        self._dlldev.ClearHistMem()

    @locked_calling
    def _stop_measurement(self, no_handler=False):
        #print("Doing Stop")
        if self._readfifo_thread and not no_handler:
            self._readfifo_thread.cancel()
            #self._readfifo_thread.wait()
        # in case we are called from the __del__ handler, ._dlldev might
        # have lost the proxy so use .dll instead
        self._dll.StopMeas(self._dev)

    def stop_measurement(self, no_handler=False):
        self._stop_measurement(no_handler)

    def _histogram_len_setdev(self, val):
        n = int(np.log2(val))
        if not 10<=n<=16:
            raise ValueError('Invalid histogram length')
        val = self._dlldev.SetHistoLen(n-10)
        self.histogram_len._set_delayed_cache = val

    def _histogram_len_getdev(self):
        return self.histogram_len.getcache()

    def _active_channels_getdev(self):
        enabled = []
        with self._protect_ch_change():
            for c in self._all_chs:
                if self.input_ch_en.get(ch=c):
                    enabled.append(c)
        return enabled

    def _fetch_ch_helper(self, chs, count=False):
        if chs is None:
            chs = self.active_channels.get()
            if count:
                chs = [0] + chs
        if not isinstance(chs, (list, tuple, np.ndarray)):
            chs = [chs]
        for c in chs:
            if c == 0:
                if not count:
                    raise ValueError(self.perror('Invalid chs selection in fetch. 0 is only valid with count'))
            elif c not in self._all_chs:
                raise ValueError(self.perror('Invalid chs selection in fetch'))
        return chs

    def _fetch_getformat(self, **kwarg):
        chs = kwarg.get('chs', None)
        count = kwarg.get('count', False)
        xaxis = kwarg.get('xaxis', True)
        bins = kwarg.get('bins', False)
        graph = []
        if count:
            chs = self._fetch_ch_helper(chs, count)
            xaxis = False
            multi = []
            graph = list(range(len(chs)))
            for c in chs:
                if c == 0:
                    multi.append('sync')
                else:
                    multi.append('ch%i'%c)
        else:
            if self._init_mode == 'hist':
                chs = self._fetch_ch_helper(chs)
                if xaxis:
                    if bins:
                        multi = ['bin_#']
                    else:
                        multi = ['time(s)']
                else:
                    multi = []
                for c in chs:
                    multi.append('ch%i'%c)
                multi = tuple(multi)
            else:
                handler = self._get_handler_helper(kwarg)
                multi, xaxis = handler.get_titles(xaxis, bins)
        fmt = self.fetch._format
        fmt.update(multi=multi, graph=graph, xaxis=xaxis)
        return BaseDevice.getformat(self.fetch, **kwarg)

    def _fetch_getdev(self, chs=None, count=False, xaxis=True, bins=False, handler=None):
        """ options are:
            count: to return count_rate instead of histogram or t2,t3 events.
            chs: only for histogram or counts.
                 to select which channels to return.
                 when None, returns all active chs
                 otherwise can be a single ch or a list
                 of ch. if ch=0 it means the sync ch.
            xaxis: only for histogram. t2/t3 code might also handle this.
            bins: when True, will return xaxis in bins instead of time.
            handler: to specify a handler class for this call
        """
        if count or self._init_mode == 'hist':
            chs = self._fetch_ch_helper(chs, count)
            if count:
                counts = self.count_rate_all.get()
                data = counts[chs]
            else:
                # hist mode
                Nch = self._num_of_ch
                N = self.histogram_len.get()
                data = np.empty(Nch * N, dtype='uint32')
                # for single channel could use GetHistogram but
                # it does not work for 1024 and 2048 bins.
                self._dlldev.GetAllHistograms(data)
                data.shape = (Nch, N)
                self._hist_sum = data.sum(axis=-1)
                data = data[np.array(chs)-1]
                if xaxis:
                    res_ps = self.resolution_ps.get()
                    offset_ns = self.histogram_offset_ns.get()
                    base_res_ps = self._resolution_base_ps
                    if bins:
                        x_factor = 1.
                        # I think the offset is in base unit
                        x_offset = ((offset_ns*1e3)//base_res_ps) / (res_ps/base_res_ps) *1e-12
                    else:
                        x_factor = res_ps * 1e-12
                        x_offset = offset_ns * 1e-9
                    x = np.arange(N) * x_factor + x_offset
                    data = np.concatenate([x[np.newaxis, :], data], axis=0)
        else:
            data = self._readfifo_thread.handler.get_data()
        return data

    def _hist_sum_getformat(self, **kwarg):
        if self._init_mode != 'hist':
            raise ValueError(self.perror('hist_sum can only be used in hist mode'))
        chs = kwarg.get('chs', None)
        chs = self._fetch_ch_helper(chs)
        multi = []
        for c in chs:
            multi.append('ch%i'%c)
        fmt = self.hist_sum._format
        fmt.update(multi=multi)
        return BaseDevice.getformat(self.hist_sum, **kwarg)

    def _hist_sum_getdev(self, chs=None):
        if self._init_mode != 'hist':
            raise ValueError(self.perror('hist_sum can only be used in hist mode'))
        chs = self._fetch_ch_helper(chs)
        if self._hist_sum is None:
            self.fetch.get(xaxis=False)
        return self._hist_sum[np.array(chs)-1]

    def _flags_getdev(self):
        flags = self._dlldev.GetFlags()
        if MH_flags.sys_error in flags:
            print('!!!!!!!!!!!!!!!!!!!!!!!!!!')
            print('MultiHarp SYSTEM ERROR.')
            print('You might need to contact PiqoQuant support')
            print('Here is info you might need:')
            print('------------------')
            d = self.get_debug_info()
            print(d.debug_txt)
            del d.debug_txt
            print('------------------')
            print('extra_information')
            print(d)
            print('------------------')
            raise RuntimeError(self.perror('MultiHarp had a system error. See description above exception.'))
        if MH_flags.fifo_full in flags:
            print('!!! MultiHarp fifo full')
        if MH_flags.cnts_dropped in flags:
            print('!!! MultiHarp counts dropped')
        if MH_flags.ref_lost in flags:
            raise RuntimeError(self.perror('MultiHarp lost its reference.'))
        if flags != 0:
            self._last_flags.append((flags, time.time()))
            if len(self._last_flags) > 10:
                del self._last_flags[0]
            self._last_acq_flags |= flags
        return flags

    def _last_acq_flags_getdev(self):
        """ This is the or values of all the last acq flags since the start of an acquisition """
        return self._last_acq_flags

    def _create_devs(self):
        # defaults are from snapi documentation
        self._libversion = float(self._dll.GetLibraryVersion())
        self._num_of_ch = self._dlldev.GetNumOfInputChannels()
        self._resolution_base_ps, self._max_bin_steps = self._dlldev.GetBaseResolution()
        self._features = self._dlldev.GetFeatures()
        self._all_chs = list(range(1, self._num_of_ch+1))
        self.warnings = MH_data_dev(read_func=self._dlldev.GetWarnings, doc="For this to return something useful, you need have recently read the count rates")
        self.current_ch = MemoryDevice(1, no_type_conv=True, choices=self._all_chs)
        self.meas_duration = MemoryDevice(1., min=0.001, max=3600*100)
        def Mem_Ch_dev(*args, **kwargs):
            kwargs['nch'] = self._num_of_ch
            kwargs['update_func'] = self._update_ch_trig
            kwargs['ch_helper_func'] = self._ch_helper
            return MemoryDevice_update(*args, **kwargs)
        def Mem_Sync_dev(*args, **kwargs):
            kwargs['update_func'] = self._update_sync_trig
            return MemoryDevice_update(*args, **kwargs)
        def Mem_Meas_dev(*args, **kwargs):
            kwargs['update_func'] = self._update_meas
            return MemoryDevice_update(*args, **kwargs)
        def MH_Ch_dev(*args, **kwargs):
            options = kwargs.pop('options', {}).copy()
            options.update(ch=self.current_ch)
            app = kwargs.pop('options_apply', ['ch'])
            kwargs.update(options=options, options_apply=app)
            kwargs['use_ch'] = True
            return MH_data_dev(*args, **kwargs)
        def _gen_arg_deadtime(obj, val):
            if val == 0:
                return (False, 800)
            return (True, int(val))
        self.meas_control_type = Mem_Meas_dev('single_shot_ctc', choices=Choice_Enum(MH_meas_control))
        self.meas_start_edge = Mem_Meas_dev('falling', choices=Choice_Enum(MH_edge))
        self.meas_stop_edge = Mem_Meas_dev('falling', choices=Choice_Enum(MH_edge))
        self.sync_edge_type = Mem_Sync_dev('rising', choices=Choice_Enum(MH_edge))
        self.sync_edge_level = Mem_Sync_dev(-50e-3, min=-1.2, max=1.2, doc="resolution is 2.34 mV")
        self.sync_deadtime_ps = MH_data_dev(write_func=self._dlldev.SetSyncDeadTime, cache_init=0,
                                                generate_arg = _gen_arg_deadtime,
                                                choices=ChoiceValMap({0.:0.}, min=800, max=160e3),
                                                doc='A dead time of 0 disables the dead time')
        self.sync_offset_ps = MH_data_dev(write_func=self._dlldev.SetSyncChannelOffset,
                                            min=-99999, max=99999, cache_init=0, force_type=int)
        self.sync_divisor = MH_data_dev(write_func=self._dlldev.SetSyncDiv, choices=list(range(1,16+1)),
                                            cache_init=1, force_type=int)
        if self._libversion >= 3.0:
            self.sync_en = MH_data_dev(write_func=self._dlldev.SetSyncChannelEnable, cache_init=True)
        self.input_ch_edge_type = Mem_Ch_dev('rising', choices=Choice_Enum(MH_edge))
        self.input_ch_edge_level = Mem_Ch_dev(-50e-3, min=-1.2, max=1.2, doc='in steps of 2.34 mV')
        self.input_ch_en = MH_Ch_dev(write_func=self._dlldev.SetInputChannelEnable, cache_init=True)
        self.input_ch_offset_ps = MH_Ch_dev(write_func=self._dlldev.SetInputChannelOffset,
                                            min=-99999, max=99999, cache_init=0, force_type=int)
        if self._libversion >= 3.0:
            self.input_hysteresis = MH_data_dev(write_func=self._dlldev.SetInputHysteresis, cache_init='approx_3mV',
                                                   choices=Choice_Enum(MH_hysteresis))
        self.input_ch_deadtime_ps = MH_Ch_dev(write_func=self._dlldev.SetInputDeadTime, cache_init=0,
                                                generate_arg = _gen_arg_deadtime,
                                                choices=ChoiceValMap({0.:0.}, min=800, max=160e3),
                                                doc='A dead time of 0 disables the dead time')
        cnt_titles = ['sync'] + ['ch%d'%i for i in range(1, self._num_of_ch+1)]
        self._devwrap('count_rate_all', multi=cnt_titles, autoinit=False)
        self.count_rate_ch = MH_Ch_dev(read_func=self._dlldev.GetCountRate, autoinit=False)
        self.count_rate_sync = MH_data_dev(read_func=self._dlldev.GetSyncRate, autoinit=False)
        self.stop_on_overflow = MH_data_dev(write_func=self._dlldev.SetStopOverflow, cache_init=4294967295,
                                                generate_arg = _gen_arg_deadtime,
                                                choices=ChoiceValMap({0.:0.}, min=1, max=4294967295),
                                                doc='An overflow time of 0 disables the stop on overflow')
        self.is_acquisition_complete = MH_data_dev(read_func=self._dlldev.CTCStatus,
                                             choices=ChoiceSimpleMap({MH_ctc_status.acq_running:False, MH_ctc_status.acq_ended:True}))
        self.resolution_ps = MH_data_dev(read_func=self._dlldev.GetResolution)
        self.sync_period = MH_data_dev(read_func=self._dlldev.GetSyncPeriod, doc='This only seems to work for t3 mode. Read it during or after a measurement.')
        #self.flags = MH_data_dev(read_func=self._dlldev.GetFlags)
        self._devwrap('flags')
        self.elapsed_time = MH_data_dev(read_func=self._dlldev.GetElapsedMeasTime, scale=1e-3, doc='in ms resolution')
        # TODO 25 is not producing an immediate error. Check this.
        self.histogram_binning = MH_data_dev(write_func=self._dlldev.SetBinning, min=0, max=self._max_bin_steps-1, force_type=int, cache_init=0)
        self.histogram_offset_ns = MH_data_dev(write_func=self._dlldev.SetOffset, min=0, max=100e6, force_type=int, cache_init=0)
        self.trigger_output_period = MH_data_dev(write_func=self._dlldev.SetTriggerOutput, cache_init=0,
                                                 min=0, max=16777215e-7, scale=100e-9, force_type=int, doc='resolution is 100 ns')
        self.marker_holdoff_time_ns = MH_data_dev(write_func=self._dlldev.SetMarkerHoldoffTime, cache_init=0,
                                                 min=0, max=25500, force_type=int)
        if self._libversion >= 3.1:
            self.fifo_compression_ms = MH_data_dev(write_func=self._dlldev.SetOflCompression, force_type=int, cache_init=2)

        # This should be seconds since the unix epoch according to documentation
        # but looks to be a different data. Or the internal clock was reset.
        self._devwrap('start_time', multi=['sec', 'ps'])
        self._devwrap('histogram_len', choices=[2**n for n in range(10, 16+1)])
        self.histogram_len.setcache(2**16, nolock=True)
        self._devwrap('active_channels')
        self._devwrap('fetch', autoinit=False, trig=True)
        self._devwrap('hist_sum', autoinit=False, trig=True)
        self._devwrap('last_acq_flags', autoinit=False, trig=True)
        self.readval = ReadvalDev(self.fetch)
        # This needs to be last to complete creation
        super(PicoQuant_MultiHarp_dll, self)._create_devs()

    @locked_calling
    def check_fifo_residuals(self, repeat=20):
        """ This checks if any data is left in the fifo after the
        reading is finished. If some data is left, you might want to make
        fifo_extra_readings longer. If no data is left you might try to make
        it smaller.
        It needs to be executed after a t2/t3 acquisition (readval)
        """
        residuals = False
        for i in range(repeat):
            data = self._dlldev.ReadFiFo()
            if len(data) != 0:
                residuals = True
                print("Non-zero buf for iteration", i, 'data length', len(data))
        if not residuals:
            print("No residuals present for %d repeats"%repeat)

class MH_T2_data(object):
    WRAP_ARROUND = 33554432 # 2**25
    def __init__(self, data):
        """ data strucuture is:
            bit 31: special
            bit 30-25: channel
            bit 24-0: time tag (in _resolution_base_ps)
            if special == 1:
                if channel == 0x3f:
                    overflow, time_tag is size of overflow
                    time to add: WRAP_ARROUND * time_tag
                elif channel == 0:
                    sync event
                else:
                    marker event. (if 1 <= ch <= 15)
            else
              full_time = time_tag + overflow_accumulation
            Any of the is_ can be used to select part of the data.
            for t = MH_T2_data, you can do:
                t[where(t.is_normal)]
            or
                t[bool(t.normal)]
            or
                t[t.normal.astype(bool)]
        """
        if isinstance(data, list):
            data = np.asarray(data, dtype=np.uint32)
        if (not isinstance(data, np.ndarray)) or data.dtype != np.uint32 or data.ndim != 1:
            raise ValueError('Wrong input data format. Should be a list or 1d numpy array of uint32.')
        self.data = data
    def __getitem__(self, slice):
        return MH_T2_data(self.data[slice])
    @property
    def time_tag(self):
        return self.data&0x1ffffff
    @property
    def ch(self):
        return (self.data>>25)&0x3f
    @property
    def is_normal(self):
        return self.is_special^1
    @property
    def is_special(self):
        return (self.data>>31)&1
    @property
    def is_overflow(self):
        return self.is_special * (self.ch == 0x3f)
    @property
    def is_sync(self):
        return self.is_special * (self.ch == 0)
    @property
    def is_marker(self):
        return self.is_special * (self.ch >= 1) * (self.ch <= 15)

class MH_T3_data(object):
    WRAP_ARROUND = 1024 # 2**10
    def __init__(self, data):
        """ data strucuture is:
            bit 31: special
            bit 30-25: channel
            bit 24-10: dtime (offset from last sync) in resolution_ps.
                             (histogram_binning can change it)
                             (max 32767 = 2**15-1)
            bit 9-0: nsync (max 1023)
            if special == 1:
                if channel == 0x3f:
                    sync overflow, nsync is size of overflow
                    syncs to add: WRAP_ARROUND * nsync
                else:
                    marker event. (if 1 <= ch <= 15)
            else
              full_time = (overflow_accumulation + nsync) * sync_period + dtime
            Any of the is_ can be used to select part of the data.
            for t = MH_T3_data, you can do:
                t[where(t.is_normal)]
            or
                t[bool(t.normal)]
            or
                t[t.normal.astype(bool)]
        """
        if isinstance(data, list):
            data = np.asarray(data, dtype=np.uint32)
        if (not isinstance(data, np.ndarray)) or data.dtype != np.uint32 or data.ndim != 1:
            raise ValueError('Wrong input data format. Should be a list or 1d numpy array of uint32.')
        self.data = data
    def __getitem__(self, slice):
        return MH_T3_data(self.data[slice])
    @property
    def nsync(self):
        return self.data&0x3ff
    @property
    def dtime(self):
        return (self.data>>10)&0x7fff
    @property
    def ch(self):
        return (self.data>>25)&0x3f
    @property
    def is_normal(self):
        return self.is_special^1
    @property
    def is_special(self):
        return (self.data>>31)&1
    @property
    def is_overflow(self):
        return self.is_special * (self.ch == 0x3f)
    @property
    def is_marker(self):
        return self.is_special * (self.ch >= 1) * (self.ch <= 15)

def Verify_time_increases(data, is_t2=True):
    if is_t2:
        d = MH_T2_data(data)
        times = d.time_tag.astype(np.int64)
        overi = np.nonzero(d.is_overflow)[0]
        over = times[overi]
        over = over.cumsum() * d.WRAP_ARROUND
        # Assuming over are not too frequent
        Nover = len(overi)
        for i in range(Nover):
            start = overi[i]
            if i+1 >= Nover:
                stop = None
            else:
                stop = overi[i+1]
            times[start:stop] += over[i]
        sel = (d.is_normal + d.is_sync).astype(bool)
        diff_t = np.diff(times[sel])
        if np.any(diff_t < 0):
            raise ValueError('Time data does not stricly increase.')
    else:
        d = MH_T3_data(data)
        nsyncs = d.nsync.astype(np.int64)
        dtimes = d.dtime.astype(np.int64)
        overi = np.nonzero(d.is_overflow)[0]
        over = nsyncs[overi]
        over = over.cumsum() * d.WRAP_ARROUND
        # Assuming over are not too frequent
        Nover = len(overi)
        for i in range(Nover):
            start = overi[i]
            if i+1 >= Nover:
                stop = None
            else:
                stop = overi[i+1]
            nsyncs[start:stop] += over[i]
        sel = d.is_normal.astype(bool)
        diff_nsyncs = np.diff(nsyncs[sel])
        if np.any(diff_nsyncs < 0):
            raise ValueError('Time data (nsync) does not stricly increase.')
        w = np.nonzero(diff_nsyncs == 0)[0]
        diff_dtimes = np.diff(dtimes[sel])
        if np.any(diff_dtimes[w] < 0):
            raise ValueError('Time data (dtime) does not stricly increase.')


def Simple_Slow_Histo_T2(data, ch_histo=1, sync=1, t0=0, t1=5000, dt=5, resolution=10e-12, exclude_of_uf=True, reuse=None):
    """
    Will calculate the histogram of time differences between ch_histo and sync.
    t0, t1 and dt are to calculate the bins. They are in instrument bin numbers.
    ch_histo is the channel to do the histo on can be 0 for sync channel
    sync is channel to do the histo with respect to. can also be 0 for sync channel.
    resolution is the time resolution for the acquisition bins
    exclude_of_uf specify if the overflow and underflow are calculated and kept
    reuse can be used to extend a calculation with new data, in the the incoming stream
      is broken into blocks. When reuse is not None, all other keyword parameters are unused.
    returns
      histo, bins, times, reuse
    where bins are the starting value of the bin and times is that value converted to
      actual time in s. reuse is the value to pass into reuse to add to a previous call.
    Note that the algorithm assumes that the incoming data time_tag are always increasing.
    You can check that with Verify_time_increases.
    If multiple events arrive at the same time it takes them in the order they show up.
    So if sync=2 and ch_histo=1 and the event are always in ch order, then
    1 shows up before 2, then delta t will never be 0. In the opposite order,
    sync=1 and ch_histo=2 then delta t will be 0. Therefore 0 time event will depend on
    the stream order and can be totally absent. Negative time event are not possible.
    """
    if reuse is None:
        t0 = int(t0)
        t1 = int(t1)
        dt = int(dt)
        if t1 <= t0:
            raise ValueError('t1 needs to be greater than t0')
        if dt <= 0 or (t1-t0)//dt < 2:
            raise ValueError('dt needs to be positive and create at least 2 points between t1 and t0')
        bins = np.arange(t0-dt, t1+2*dt, dt) #-dt, +dt to count under/over flows
        t00 = bins[0]
        N = len(bins)
        histo = np.zeros(N, dtype=np.int64)
        last_sync = None
        sync -= 1
        ch_histo -= 1
    else:
        histo, bins, t00, dt, N, last_sync, ch_histo, sync, resolution, exclude_of_uf = reuse
    d = MH_T2_data(data)
    over = 0
    if sync == -1 or ch_histo == -1:
        do_sync = sync == -1, ch_histo == -1
    else:
        do_sync = False
    if sync >= 0 or ch_histo >= 0:
        do_ch = True
    else:
        do_ch = False
    for v in d:
        # we need to handle sync after ch_histo
        # so that if they are the same ch they will give the diff
        # between events.
        if v.is_overflow:
            # we convert time_tag (uint32) to python int so it cannot overflow
            over += v.WRAP_ARROUND * int(v.time_tag)
            continue
        t_sync, t_data = -1, -1
        if do_sync and v.is_sync:
            t = int(v.time_tag)
            if do_sync[0]:
                t_sync = t
            if do_sync[1]:
                t_data = t
        if do_ch and v.is_normal:
            t = int(v.time_tag)
            ch = v.ch
            if sync == ch:
                t_sync = t
            if ch_histo == ch:
                t_data = t
        if t_data != -1 and last_sync is not None:
            t = t_data + over - last_sync
            b = (t-t00)//dt
            b = min(max(b, 0), N-1)
            histo[b] += 1
        if t_sync != -1:
            last_sync = t_sync
            over = 0
    if last_sync is not None:
        last_sync -= over
    reuse = histo, bins, t00, dt, N, last_sync, ch_histo, sync, resolution, exclude_of_uf
    if exclude_of_uf:
        histo = histo[1:-1]
        bins = bins[1:-1]
    times = bins*resolution
    return histo, bins, times, reuse

def Simple_Slow_Histo_T3(data, ch_histo=1, sync=0, t0=0, t1=5000, dt=5, resolution=10e-12, exclude_of_uf=True, sync_period=None, reuse=None):
    """
    Will calculate the histogram of time differences between ch_histo and sync.
    t0, t1 and dt are to calculate the bins. They are in instrument bin numbers.
    ch_histo is the channel to do the histo on can not be 0 for sync channel (T3 does
    not keep track of sync events).
    sync is channel to do the histo with respect to. Can be 0 for sync channel.
    resolution is the time resolution for the acquisition bins in s.
    exclude_of_uf specify if the overflow and underflow are calculated and kept
    sync_period is required when sync is not 0. It is in s.
    reuse can be used to extend a calculation with new data, in the the incoming stream
      is broken into blocks. When reuse is not None, all other keyword parameters are unused.
    returns
      histo, bins, times, reuse
    where bins are the starting value of the bin and times is that value converted to
      actual time in s. reuse is the value to pass into reuse to add to a previous call.
    Note that the algorithm assumes that the incoming data nsync and dtime are always increasing.
    You can check that with Verify_time_increases.
    If multiple events arrive at the same time it takes them in the order they show up.
    So if sync=2 and ch_histo=1 and the event are always in ch order, then
    1 shows up before 2, then delta t will never be 0. In the opposite order,
    sync=1 and ch_histo=2 then delta t will be 0. Therefore 0 time event will depend on
    the stream order and can be totally absent. Negative time event are not possible.
    """
    if reuse is None:
        t0 = int(t0)
        t1 = int(t1)
        dt = int(dt)
        if t1 <= t0:
            raise ValueError('t1 needs to be greater than t0')
        if dt <= 0 or (t1-t0)//dt < 2:
            raise ValueError('dt needs to be positive and create at least 2 points between t1 and t0')
        bins = np.arange(t0-dt, t1+2*dt, dt) #-dt, +dt to count under/over flows
        t00 = bins[0]
        N = len(bins)
        histo = np.zeros(N, dtype=np.int64)
        last_sync = None
        sync -= 1
        ch_histo -= 1
        if sync != -1 and sync_period is None:
            raise ValueError('When sync != 0, sync_period needs to be given.')
        if ch_histo == -1:
            raise ValueError('ch_histo can not be 0 for T3.')
    else:
        histo, bins, t00, dt, N, last_sync, ch_histo, sync, resolution, exclude_of_uf, sync_period = reuse
    d = MH_T3_data(data)
    over = 0
    if sync != -1:
        sync_is_ch = True
        sync_period_bin = sync_period/(resolution)
    else:
        sync_is_ch = False
        last_sync = 0
    for v in d:
        # we need to handle sync after ch_histo
        # so that if they are the same ch they will give the diff
        # between events.
        if v.is_overflow:
            if sync_is_ch:
                # we convert time_tag (uint32) to python int so it cannot overflow
                over += v.WRAP_ARROUND * int(v.nsync)
            continue
        t_sync, t_data = -1, -1
        if v.is_normal:
            t = int(v.dtime)
            ns = int(v.nsync)
            ch = v.ch
            if sync_is_ch:
                if sync == ch:
                    t_sync = t, ns
                if ch_histo == ch:
                    t_data = t, ns
            else:
                if ch_histo == ch:
                    t_data = t
        if t_data != -1 and last_sync is not None:
            if sync_is_ch:
                dtime = t_data[0] - last_sync[0]
                dsync = t_data[1] - last_sync[1] + over
                t = dtime + dsync*sync_period_bin
            else:
                t = t_data
            b = (t-t00)//dt
            b = int(b)
            b = min(max(b, 0), N-1)
            #print(t, b)
            histo[b] += 1
        if t_sync != -1:
            last_sync = t_sync
            over = 0
    if last_sync is not None and sync_is_ch:
        last_sync = last_sync[0], last_sync[1] - over
    reuse = histo, bins, t00, dt, N, last_sync, ch_histo, sync, resolution, exclude_of_uf, sync_period
    if exclude_of_uf:
        histo = histo[1:-1]
        bins = bins[1:-1]
    times = bins*resolution
    return histo, bins, times, reuse


def _increment_histo(histo, diff_t, t00, dt, N):
    # force diff_t to be integer, copy=False makes it a nop if the type is already ok
    diff_t = diff_t.astype(np.int64, copy=False)
    b = (diff_t-t00)//dt
    #print(t00, dt, N, b.max(), b.min())
    #print(diff_t, b)
    np.clip(b, 0, N-1, out=b)
    # This will fail if some b values repeat
    #histo[b] += 1
    # This will work instead
    np.add.at(histo, b, 1)


def _parse_histo_param(ch_histo, sync, t0, t1, dt, resolution, exclude_of_uf, time_is_bin=False, max_N=100e5):
    """ here ch_histo, sync and the measurrment and sync channels
        where 0 means the sync input.
        t0, t1 and dt are in time(s) unless time_is_bin is True.
        max_N: this will limit the number of bins. It will capture some errors on t0, t1, dt
        All the parameters can be arrays (in which case at least ch_histo needs to be an array)
        of the same length except for resolution and max_N. When not given as an array,
        it applies to all.
    """
    def do_dim(v, ndim=1):
        if not isinstance(v, (list, tuple, np.ndarray)):
            return [v]*ndim
        return v
    ch_histos = do_dim(ch_histo)
    ndim = len(ch_histos)
    do_dimn = lambda v: do_dim(v, ndim)
    syncs = do_dimn(sync)
    t0s = do_dimn(t0)
    t1s = do_dimn(t1)
    dts = do_dimn(dt)
    exclude_of_ufs = do_dimn(exclude_of_uf)
    if time_is_bin:
        resolution=1.
    bins_list = []
    t00s = []
    dts_out = []
    Ns = []
    histos = []
    for t0, t1, dt in zip(t0s, t1s, dts):
        t0 = int(t0/resolution)
        t1 = int(t1/resolution)
        dt = int(dt/resolution)
        if t1 <= t0:
            raise ValueError('t1 needs to be greater than t0')
        if dt <= 0 or (t1-t0)//dt < 2:
            raise ValueError('dt needs to be positive and create at least 2 points between t1 and t0')
        if (t1-t0)/dt > max_N:
            raise ValueError('t0, t1, dt combination generates more than max_N(%s) points.'%max_N)
        bins = np.arange(t0-dt, t1+2*dt, dt) #-dt, +dt to count under/over flows
        t00 = bins[0]
        N = len(bins)
        histo = np.zeros(N, dtype=np.int64)
        bins_list.append(bins)
        t00s.append(t00)
        dts_out.append(dt)
        Ns.append(N)
        histos.append(histo)
    return ch_histos, syncs, bins_list, t00s, dts_out, Ns, histos, exclude_of_ufs

# according to some tests casting to bool is faster
#t = d[d.is_sync.astype(bool)].time_tag
# other options
# t = d[np.nonzero(d.is_sync)].time_tag
# t = d[np.where(d.is_sync)].time_tag
# But I need the indexes

def _extract_ch_data(data, ch_histos, syncs, is_t3=False):
    if is_t3:
        first = 1
        ret = [None]
    else:
        # t2 mode. We can extract sync data
        first = 0
        ret = []
    maxch = max(max(ch_histos), max(syncs))
    for i in range(first, maxch+1):
        if i in ch_histos or i in syncs:
            if i == 0:
                idx = np.nonzero(data.is_sync)[0]
            else:
                ch = i - 1
                idx = np.nonzero(data.is_normal * (data.ch==ch))[0]
        else:
            idx = None
        ret.append(idx)
    return ret


class _cached_data(object):
    def __init__(self, data, idx_data, data2=None):
        self.data = data
        self.data2 = data2
        self.idx_data = idx_data
        self.cache = {}

    def get_time(self, ch, key_name='time'):
        key = (key_name, ch)
        if key in self.cache:
            return self.cache[key]
        res = self.data[self.idx_data[ch]]
        self.cache[key] = res
        return res

    def get_dtime(self, ch):
        return self.get_time(ch, 'dtime')

    def get_nsync(self, ch):
        key = ('nsync', ch)
        if key in self.cache:
            return self.cache[key]
        res = self.data2[self.idx_data[ch]]
        self.cache[key] = res
        return res

    def get_t2_1ch_diff(self, ch):
        key = ('diff21', ch)
        res = self.get_result(key)
        if res is None:
            t = self.get_time(ch)
            diff_t = np.diff(t)
            if len(t) > 0:
                first_time = t[0]
                end_time = t[-1]
            else:
                first_time = end_time = None
            res = diff_t, first_time, end_time
            self.set_result(key, res)
        return res

    def get_t3_1ch_diff(self, ch, sync_period_bin):
        key = ('diff31', ch, sync_period_bin)
        res = self.get_result(key)
        if res is None:
            dtime = self.get_dtime(ch)
            nsync = self.get_nsync(ch)
            diff_dtime = np.diff(dtime)
            diff_nsync = np.diff(nsync)
            diff_t = diff_nsync * sync_period_bin + diff_dtime
            if len(dtime) > 0:
                pre_meas_dtime = dtime[0]
                pre_meas_nsync = nsync[0]
                end_sync_dtime = dtime[-1]
                end_sync_nsync = nsync[-1]
            else:
                pre_meas_dtime = pre_meas_nsync = end_sync_dtime = end_sync_nsync = None
            res = diff_t, pre_meas_dtime, pre_meas_nsync, end_sync_dtime, end_sync_nsync
            self.set_result(key, res)
        return res

    def get_t2_2ch_diff(self, meas_ch, sync_ch):
        key = ('diff22', meas_ch, sync_ch)
        res = self.get_result(key)
        if res is None:
            synci = self.idx_data[sync_ch]
            measi = self.idx_data[meas_ch]
            # returns the index of where measi[i] can be included in synci
            # the value to the left is the sync to use for every meas
            idxs = np.searchsorted(synci, measi)
            # skip idxs = 0 which mean we got a meas before a sync
            first = np.searchsorted(idxs, 1)
            tmeas = self.get_time(meas_ch)
            pre_meas = tmeas[:first]
            meas = tmeas[first:]
            # We can get all the sync data now and index into that
            # or use the synci index instead
            ## first option
            #tsync = self.get_time(sync_ch)
            #tsync = tsync[idxs[first:]-1]
            ## second option
            synci_meas = synci[idxs[first:] - 1]
            tsync = self.data[synci_meas]
            diff_t = meas - tsync
            if len(synci) > 0:
                # end_sync_time = tsync[-1]
                end_sync_time = self.data[synci[-1]]
            else:
                end_sync_time = None
            res = diff_t, pre_meas, end_sync_time
            self.set_result(key, res)
        return res

    def get_t3_2ch_diff(self, meas_ch, sync_ch, sync_period_bin):
        key = ('diff32', meas_ch, sync_ch, sync_period_bin)
        res = self.get_result(key)
        if res is None:
            synci = self.idx_data[sync_ch]
            measi = self.idx_data[meas_ch]
            # returns the index of where measi[i] can be included in synci
            # the value to the left is the sync to use for every meas
            idxs = np.searchsorted(synci, measi)
            # skip idxs = 0 which mean we got a meas before a sync
            first = np.searchsorted(idxs, 1)
            meas_dtimes = self.get_dtime(meas_ch)
            meas_nsyncs = self.get_nsync(meas_ch)
            pre_meas_nsync = meas_nsyncs[:first]
            pre_meas_dtime = meas_dtimes[:first]
            meas_dtime = meas_dtimes[first:]
            meas_nsync = meas_nsyncs[first:]
            # We can get all the sync data now and index into that
            # or use the synci index instead
            ## first option
            # sync_dtimes = self.get_dtime(sync_ch)
            # sync_nsyncs = self.get_nsync(sync_ch)
            # sync_dtime = sync_dtimes[idxs[first:]-1]
            # sync_nsync = sync_nsyncs[idxs[first:]-1]
            ## second option
            synci_meas = synci[idxs[first:] - 1]
            sync_dtime = self.data[synci_meas]
            sync_nsync = self.data2[synci_meas]
            diff_t = (meas_nsync - sync_nsync) * sync_period_bin + (meas_dtime - sync_dtime)
            if len(synci) > 0:
                # end_sync_dtime = sync_dtimes[-1]
                # end_sync_nsync = sync_dtimes[-1]
                end_synci = synci[-1]
                end_sync_dtime = self.data[end_synci]
                end_sync_nsync = self.data2[end_synci]
            else:
                end_sync_dtime = end_sync_nsync = None
            res = diff_t, pre_meas_dtime, pre_meas_nsync, end_sync_dtime, end_sync_nsync
            self.set_result(key, res)
        return res

    def set_result(self, key, result):
        #print('set', key, list(self.cache.keys()))
        self.cache[key] = result

    def get_result(self, key):
        #print('get', key, list(self.cache.keys()))
        if key in self.cache:
            return self.cache[key]
        return None


def Simple_Fast_Histo_T2(data, ch_histo=1, sync=1, t0=0, t1=5000, dt=5, resolution=10e-12, exclude_of_uf=True, reuse=None):
    """
    Will calculate the histogram of time differences between ch_histo and sync.
    t0, t1 and dt are to calculate the bins. They are in instrument bin numbers.
    ch_histo is the channel to do the histo on can be 0 for sync channel
    sync is channel to do the histo with respect to. can also be 0 for sync channel.
    resolution is the time resolution for the acquisition bins
    exclude_of_uf specify if the overflow and underflow are calculated and kept
    reuse can be used to extend a calculation with new data, in the the incoming stream
      is broken into blocks. When reuse is not None, all other keyword parameters are unused.
    returns
      histo, bins, times, reuse
    where bins are the starting value of the bin and times is that value converted to
      actual time in s. reuse is the value to pass into reuse to add to a previous call.
    Note that the algorithm assumes that the incoming data time_tag are always increasing.
    You can check that with Verify_time_increases.
    If multiple events arrive at the same time it takes them in the order they show up.
    So if sync=2 and ch_histo=1 and the event are always in ch order, then
    1 shows up before 2, then delta t will never be 0. In the opposite order,
    sync=1 and ch_histo=2 then delta t will be 0. Therefore 0 time event will depend on
    the stream order and can be totally absent. Negative time event are not possible.
    """
    if reuse is None:
        t0 = int(t0)
        t1 = int(t1)
        dt = int(dt)
        if t1 <= t0:
            raise ValueError('t1 needs to be greater than t0')
        if dt <= 0 or (t1-t0)//dt < 2:
            raise ValueError('dt needs to be positive and create at least 2 points between t1 and t0')
        bins = np.arange(t0-dt, t1+2*dt, dt) #-dt, +dt to count under/over flows
        t00 = bins[0]
        N = len(bins)
        histo = np.zeros(N, dtype=np.int64)
        last_sync = None
    else:
        histo, bins, t00, dt, N, last_sync, ch_histo, sync, resolution, exclude_of_uf = reuse
    d = MH_T2_data(data)
    times = d.time_tag.astype(np.int64)
    overi = np.nonzero(d.is_overflow)[0]
    over = times[overi]
    over = over.cumsum() * d.WRAP_ARROUND
    # Assuming over are not too frequent
    Nover = len(overi)
    for i in range(Nover):
        start = overi[i]
        if i+1 >= Nover:
            stop = None
        else:
            stop = overi[i+1]
        times[start:stop] += over[i]
    if sync == ch_histo:
        # Same channels for sync reference and measured channel
        if sync == 0:
            # according to some tests casting to bool is faster
            #t = d[d.is_sync.astype(bool)].time_tag
            # other options
            # t = d[np.nonzero(d.is_sync)].time_tag
            # t = d[np.where(d.is_sync)].time_tag
            # But I need the indexes
            ti = np.nonzero(d.is_sync)[0]
        else:
            ch = sync - 1
            ti = np.nonzero(d.is_normal * (d.ch==ch))[0]
        t = times[ti]
        diff_t = np.diff(t)
        _increment_histo(histo, diff_t, t00, dt, N)
        if last_sync is not None and len(t) > 0:
            diff_t_pre = np.array([t[0] - last_sync])
            _increment_histo(histo, diff_t_pre, t00, dt, N)
        if len(t) > 0:
            last_sync = t[-1]
    else:
        # different channels for measure and sync
        # This algorithm assumes time_tag always increases (event between channels)
        # and that for equal time, meas occurs after sync.
        # This second one is not True.
        if sync == 0:
            synci = np.nonzero(d.is_sync)[0]
        else:
            ch = sync - 1
            synci = np.nonzero(d.is_normal * (d.ch==ch))[0]
        if ch_histo == 0:
            measi = np.nonzero(d.is_sync)[0]
        else:
            ch = ch_histo - 1
            measi = np.nonzero(d.is_normal * (d.ch==ch))[0]
        # returns the index of where measi[i] can be included in synci
        # the value to the left is the sync to use for every meas
        idxs = np.searchsorted(synci, measi)
        # skip idxs = 0 which mean we got a meas before a sync
        first = np.searchsorted(idxs, 1)
        pre_measi = measi[:first]
        measi = measi[first:]
        tsync = times[synci[idxs[first:]-1]]
        meas = times[measi]
        diff_t = meas - tsync
        _increment_histo(histo, diff_t, t00, dt, N)
        if last_sync is not None and first != 0:
            diff_t_pre = times[pre_measi]-last_sync
            _increment_histo(histo, diff_t_pre, t00, dt, N)
        if len(synci) > 0:
            last_sync = times[synci[-1]]
    if len(over) > 0 and last_sync is not None:
        last_sync -= over[-1]
    reuse = histo, bins, t00, dt, N, last_sync, ch_histo, sync, resolution, exclude_of_uf
    if exclude_of_uf:
        histo = histo[1:-1]
        bins = bins[1:-1]
    times = bins*resolution
    return histo, bins, times, reuse


def Full_Fast_Histo_T2(data, ch_histo=1, sync=1, t0=0, t1=5000, dt=5, resolution=10e-12, exclude_of_uf=True, time_is_bin=False, max_N=100e5, reuse=None):
    """
    Will calculate the histogram of time differences between ch_histo and sync.
    Most parameters can be list to allow multiple histograms (see _parse_histo_param)
    t0, t1 and dt are to calculate the bins. They are in instrument bin numbers.
    ch_histo is the channel to do the histo on can be 0 for sync channel
    sync is channel to do the histo with respect to. can also be 0 for sync channel.
    resolution is the time resolution for the acquisition bins
    exclude_of_uf specify if the overflow and underflow are calculated and kept
    reuse can be used to extend a calculation with new data, in the the incoming stream
      is broken into blocks. When reuse is not None, all other keyword parameters are unused.
    returns
      histo, bins, times, reuse
    where bins are the starting value of the bin and times is that value converted to
      actual time in s. reuse is the value to pass into reuse to add to a previous call.
    Note that the algorithm assumes that the incoming data time_tag are always increasing.
    You can check that with Verify_time_increases.
    If multiple events arrive at the same time it takes them in the order they show up.
    So if sync=2 and ch_histo=1 and the event are always in ch order, then
    1 shows up before 2, then delta t will never be 0. In the opposite order,
    sync=1 and ch_histo=2 then delta t will be 0. Therefore 0 time event will depend on
    the stream order and can be totally absent. Negative time event are not possible.
    """
    if reuse is None:
        params = _parse_histo_param(ch_histo, sync, t0, t1, dt, resolution, exclude_of_uf, time_is_bin, max_N)
        ch_histos, syncs, bins_list, t00s, dts, Ns, histos, exclude_of_ufs = params
        last_syncs = [None]*len(ch_histos)
    else:
        histos, bins_list, t00s, dts, Ns, last_syncs, ch_histos, syncs, resolution, exclude_of_ufs = reuse
    d = MH_T2_data(data)
    times = d.time_tag.astype(np.int64)
    overi = np.nonzero(d.is_overflow)[0]
    over = times[overi]
    over = over.cumsum() * d.WRAP_ARROUND
    # Assuming over are not too frequent
    Nover = len(overi)
    for i in range(Nover):
        start = overi[i]
        if i+1 >= Nover:
            stop = None
        else:
            stop = overi[i+1]
        times[start:stop] += over[i]
    idx_data = _extract_ch_data(d, ch_histos, syncs, is_t3=False)
    cache = _cached_data(times, idx_data)
    histos_out = []
    bins_out = []
    times_out = []
    last_syncs_out = []
    variables = zip(histos, ch_histos, syncs, bins_list, t00s, dts, Ns, last_syncs, exclude_of_ufs)
    for histo, ch_histo, sync, bins, t00, dt, N, last_sync, exclude_of_uf in variables:
        big_key = ('full_result', ch_histo, sync, t00, dt, N, last_sync, exclude_of_uf)
        prev = cache.get_result(big_key)
        if prev is not None:
            histo, last_sync = prev
        elif sync == ch_histo:
            # Same channels for sync reference and measured channel
            diff_t, first_time, end_time = cache.get_t2_1ch_diff(sync)
            _increment_histo(histo, diff_t, t00, dt, N)
            if last_sync is not None and first_time is not None:
                diff_t_pre = np.array([first_time - last_sync])
                _increment_histo(histo, diff_t_pre, t00, dt, N)
            if end_time is not None:
                last_sync = end_time
        else:
            # different channels for measure and sync
            # This algorithm assumes time_tag always increases (event between channels).
            # For equal time, the data seems to come in ch order, so
            # for some ch combination it might be impossible to get diff_t of 0.
            diff_t, pre_meas, end_sync_time = cache.get_t2_2ch_diff(ch_histo, sync)
            _increment_histo(histo, diff_t, t00, dt, N)
            if last_sync is not None and len(pre_meas) != 0:
                diff_t_pre = pre_meas-last_sync
                _increment_histo(histo, diff_t_pre, t00, dt, N)
            if end_sync_time is not None:
                last_sync = end_sync_time
        if prev is None:
            cache.set_result(big_key, (histo, last_sync))
        if len(over) > 0 and last_sync is not None:
            last_sync -= over[-1]
        last_syncs_out.append(last_sync)
        if exclude_of_uf:
            histo = histo[1:-1]
            bins = bins[1:-1]
        times_x = bins*resolution
        histos_out.append(histo)
        bins_out.append(bins)
        times_out.append(times_x)
    reuses = histos, bins_list, t00s, dts, Ns, last_syncs_out, ch_histos, syncs, resolution, exclude_of_ufs
    return histos_out, bins_out, times_out, reuses


def Simple_Fast_Histo_T3(data, ch_histo=1, sync=0, t0=0, t1=5000, dt=5, resolution=10e-12, exclude_of_uf=True, sync_period=None, reuse=None):
    """
    Will calculate the histogram of time differences between ch_histo and sync.
    t0, t1 and dt are to calculate the bins. They are in instrument bin numbers.
    ch_histo is the channel to do the histo on can not be 0 for sync channel (T3 does
    not keep track of sync events).
    sync is channel to do the histo with respect to. Can be 0 for sync channel.
    resolution is the time resolution for the acquisition bins in s.
    exclude_of_uf specify if the overflow and underflow are calculated and kept
    sync_period is required when sync is not 0. It is in s.
    reuse can be used to extend a calculation with new data, in the the incoming stream
      is broken into blocks. When reuse is not None, all other keyword parameters are unused.
    returns
      histo, bins, times, reuse
    where bins are the starting value of the bin and times is that value converted to
      actual time in s. reuse is the value to pass into reuse to add to a previous call.
    Note that the algorithm assumes that the incoming data nsync and dtime are always increasing.
    You can check that with Verify_time_increases.
    If multiple events arrive at the same time it takes them in the order they show up.
    So if sync=2 and ch_histo=1 and the event are always in ch order, then
    1 shows up before 2, then delta t will never be 0. In the opposite order,
    sync=1 and ch_histo=2 then delta t will be 0. Therefore 0 time event will depend on
    the stream order and can be totally absent. Negative time event are not possible.
    """
    if reuse is None:
        t0 = int(t0)
        t1 = int(t1)
        dt = int(dt)
        if t1 <= t0:
            raise ValueError('t1 needs to be greater than t0')
        if dt <= 0 or (t1-t0)//dt < 2:
            raise ValueError('dt needs to be positive and create at least 2 points between t1 and t0')
        bins = np.arange(t0-dt, t1+2*dt, dt) #-dt, +dt to count under/over flows
        t00 = bins[0]
        N = len(bins)
        histo = np.zeros(N, dtype=np.int64)
        last_sync = None
        if sync != -1 and sync_period is None:
            raise ValueError('When sync != 0, sync_period needs to be given.')
        if ch_histo == -1:
            raise ValueError('ch_histo can not be 0 for T3.')
    else:
        histo, bins, t00, dt, N, last_sync, ch_histo, sync, resolution, exclude_of_uf, sync_period = reuse
    d = MH_T3_data(data)
    if sync != 0:
        sync_is_ch = True
        sync_period_bin = sync_period/(resolution)
    else:
        sync_is_ch = False
        last_sync = 0
    syncs = d.nsync.astype(np.int64)
    dtimes = d.dtime.astype(np.int64)
    overi = np.nonzero(d.is_overflow)[0]
    over = syncs[overi]
    over = over.cumsum() * d.WRAP_ARROUND
    if len(over) > 1:
        over_last = over[-1]
    else:
        over_last = 0
    # Assuming over are not too frequent
    Nover = len(overi)
    for i in range(Nover):
        start = overi[i]
        if i+1 >= Nover:
            stop = None
        else:
            stop = overi[i+1]
        syncs[start:stop] += over[i]
    if not sync_is_ch:
        # Reference is sync, simple
        ch = ch_histo - 1
        ti = np.nonzero(d.is_normal * (d.ch==ch))[0]
        diff_t = d[ti].dtime
        _increment_histo(histo, diff_t, t00, dt, N)
    elif sync == ch_histo:
        # Reference is sync, simple
        ch = ch_histo - 1
        ti = np.nonzero(d.is_normal * (d.ch==ch))[0]
        diff_nsync = np.diff(syncs[ti])
        diff_dtime = np.diff(dtimes[ti])
        diff_t = diff_nsync * sync_period_bin + diff_dtime
        _increment_histo(histo, diff_t, t00, dt, N)
        if last_sync is not None and len(ti) > 0:
            diff_nsync = syncs[ti[0]] - last_sync[1]
            diff_dtime = dtimes[ti[0]] - last_sync[0]
            diff_t_pre = diff_nsync * sync_period_bin + diff_dtime
            diff_t_pre = np.array([diff_t_pre])
            _increment_histo(histo, diff_t_pre, t00, dt, N)
        if len(ti) > 0:
            last_sync = dtimes[ti[-1]], syncs[ti[-1]] - over_last
    else:
        # full analysis
        ch = sync - 1
        synci = np.nonzero(d.is_normal * (d.ch==ch))[0]
        ch = ch_histo - 1
        measi = np.nonzero(d.is_normal * (d.ch==ch))[0]
        # returns the index of where measi[i] can be included in synci
        # the value to the left is the sync to use for every meas
        idxs = np.searchsorted(synci, measi)
        # skip idxs = 0 which mean we got a meas before a sync
        first = np.searchsorted(idxs, 1)
        pre_measi = measi[:first]
        measi = measi[first:]
        sync_dtime = dtimes[synci[idxs[first:]-1]]
        meas_dtime = dtimes[measi]
        sync_nsync = syncs[synci[idxs[first:]-1]]
        meas_nsync = syncs[measi]
        diff_t = (meas_nsync - sync_nsync) * sync_period_bin + (meas_dtime - sync_dtime)
        _increment_histo(histo, diff_t, t00, dt, N)
        if last_sync is not None and first != 0:
            diff_nsync = syncs[pre_measi] - last_sync[1]
            diff_dtime = dtimes[pre_measi] - last_sync[0]
            diff_t_pre = diff_nsync * sync_period_bin + diff_dtime
            _increment_histo(histo, diff_t_pre, t00, dt, N)
        if len(synci) > 0:
            last_sync = dtimes[synci[-1]], syncs[synci[-1]] - over_last
    reuse = histo, bins, t00, dt, N, last_sync, ch_histo, sync, resolution, exclude_of_uf, sync_period
    if exclude_of_uf:
        histo = histo[1:-1]
        bins = bins[1:-1]
    times = bins*resolution
    return histo, bins, times, reuse


def Full_Fast_Histo_T3(data, ch_histo=1, sync=1, t0=0, t1=5000, dt=5, resolution=10e-12, exclude_of_uf=True, time_is_bin=False, max_N=100e5, sync_period=None, reuse=None):
    """
    Will calculate the histogram of time differences between ch_histo and sync.
    Most parameters can be list to allow multiple histograms (see _parse_histo_param)
    t0, t1 and dt are to calculate the bins. They are in instrument bin numbers.
    ch_histo is the channel to do the histo on can not be 0 for sync channel (T3 does
    not keep track of sync events).
    sync is channel to do the histo with respect to. Can be 0 for sync channel.
    resolution is the time resolution for the acquisition bins in s.
    exclude_of_uf specify if the overflow and underflow are calculated and kept
    sync_period is required when sync is not 0. It is in s.
    reuse can be used to extend a calculation with new data, in the the incoming stream
      is broken into blocks. When reuse is not None, all other keyword parameters are unused.
    returns
      histo, bins, times, reuse
    where bins are the starting value of the bin and times is that value converted to
      actual time in s. reuse is the value to pass into reuse to add to a previous call.
    Note that the algorithm assumes that the incoming data nsync and dtime are always increasing.
    You can check that with Verify_time_increases.
    If multiple events arrive at the same time it takes them in the order they show up.
    So if sync=2 and ch_histo=1 and the event are always in ch order, then
    1 shows up before 2, then delta t will never be 0. In the opposite order,
    sync=1 and ch_histo=2 then delta t will be 0. Therefore 0 time event will depend on
    the stream order and can be totally absent. Negative time event are not possible.
    """
    if reuse is None:
        params = _parse_histo_param(ch_histo, sync, t0, t1, dt, resolution, exclude_of_uf, time_is_bin, max_N)
        ch_histos, syncs, bins_list, t00s, dts, Ns, histos, exclude_of_ufs = params
        if any(np.array(syncs) != 0) and sync_period is None:
            raise ValueError('When sync != 0, sync_period needs to be given.')
        if any(np.array(ch_histos) == 0):
            raise ValueError('ch_histo can not be 0 for T3.')
        last_syncs = [None]*len(ch_histos)
        if sync_period is None:
            sync_period = 0.
    else:
        histos, bins_list, t00s, dts, Ns, last_syncs, ch_histos, syncs, resolution, exclude_of_ufs, sync_period = reuse
    d = MH_T3_data(data)
    nsyncs = d.nsync.astype(np.int64)
    dtimes = d.dtime.astype(np.int64)
    overi = np.nonzero(d.is_overflow)[0]
    over = nsyncs[overi]
    over = over.cumsum() * d.WRAP_ARROUND
    if len(over) > 1:
        over_last = over[-1]
    else:
        over_last = 0
    # Assuming over are not too frequent
    Nover = len(overi)
    for i in range(Nover):
        start = overi[i]
        if i+1 >= Nover:
            stop = None
        else:
            stop = overi[i+1]
        nsyncs[start:stop] += over[i]
    idx_data = _extract_ch_data(d, ch_histos, syncs, is_t3=True)
    cache = _cached_data(dtimes, idx_data, nsyncs)
    sync_period_bin = sync_period/resolution
    histos_out = []
    bins_out = []
    times_out = []
    last_syncs_out = []
    variables = zip(histos, ch_histos, syncs, bins_list, t00s, dts, Ns, last_syncs, exclude_of_ufs)
    for histo, ch_histo, sync, bins, t00, dt, N, last_sync, exclude_of_uf in variables:
        big_key = ('full_result', ch_histo, sync, t00, dt, N, last_sync, exclude_of_uf)
        prev = cache.get_result(big_key)
        if prev is not None:
            histo, last_sync = prev
        if sync == 0:
            # Reference is sync, simple
            last_sync = None
            diff_t = cache.get_time(ch_histo)
            _increment_histo(histo, diff_t, t00, dt, N)
        elif sync == ch_histo:
            diff_t, pre_meas_dtime, pre_meas_nsync, end_sync_dtime, end_sync_nsync = \
                        cache.get_t3_1ch_diff(ch_histo, sync_period_bin)
            _increment_histo(histo, diff_t, t00, dt, N)
            if last_sync is not None and pre_meas_dtime is not None:
                diff_dtime = pre_meas_dtime - last_sync[0]
                diff_nsync = pre_meas_nsync - last_sync[1]
                diff_t_pre = diff_nsync * sync_period_bin + diff_dtime
                diff_t_pre = np.array([diff_t_pre])
                _increment_histo(histo, diff_t_pre, t00, dt, N)
            if  end_sync_dtime is not None:
                last_sync = end_sync_dtime, end_sync_nsync
        else:
            # full analysis
            diff_t, pre_meas_dtime, pre_meas_nsync, end_sync_dtime, end_sync_nsync = \
                        cache.get_t3_2ch_diff(ch_histo, sync, sync_period_bin)
            _increment_histo(histo, diff_t, t00, dt, N)
            if last_sync is not None and len(pre_meas_nsync) != 0:
                diff_nsync = pre_meas_nsync - last_sync[1]
                diff_dtime = pre_meas_dtime - last_sync[0]
                diff_t_pre = diff_nsync * sync_period_bin + diff_dtime
                _increment_histo(histo, diff_t_pre, t00, dt, N)
            if  end_sync_dtime is not None:
                last_sync = end_sync_dtime, end_sync_nsync

        if prev is None:
            cache.set_result(big_key, (histo, last_sync))
        if last_sync is not None:
            last_sync = last_sync[0], last_sync[1] - over_last
        last_syncs_out.append(last_sync)
        if exclude_of_uf:
            histo = histo[1:-1]
            bins = bins[1:-1]
        times_x = bins*resolution
        histos_out.append(histo)
        bins_out.append(bins)
        times_out.append(times_x)
    reuses = histos, bins_list, t00s, dts, Ns, last_syncs_out, ch_histos, syncs, resolution, exclude_of_ufs, sync_period
    return histos_out, bins_out, times_out, reuses


#######################################################
##    PicoQuant MultiHarp 150 snAPI driver
#######################################################

snAPI = None
def load_snAPI():
    global snAPI
    try:
        import snAPI
        import snAPI.Main # this also import snAPI.Constants and snAPI.Utils
    except ImportError:
        raise RuntimeError("Package snAPI is required for this driver but it is currently missing. It can be installed with: pip install snAPI")
    return snAPI

def _generate_initAPI_wrapper(console_log=False, keep_temp_file=False):
    def initAPI_wrapper(self, systemIni='system.ini'):
        if console_log in [False, True]:
            if is_py2:
                from ConfigParser import SafeConfigParser as ConfigParser
            else:
                from configparser import ConfigParser
            cp = ConfigParser()
            cp.optionxform = lambda s: s # make writing conf case sensitive (defaults to lower case)
            filenames = cp.read([systemIni])
            if len(filenames) == 0:
                raise RuntimeError('Unable to open original package system ini file')
            if not cp.has_option('Log', 'Console'):
                raise RuntimeError('Unable to extract the Log/Console value')
            if console_log:
                cp.set('Log', 'Console', 'true')
            else:
                cp.set('Log', 'Console', 'false')
            try:
                fn, system_ini = tempfile.mkstemp(suffix='.ini', prefix='saAPI_pyHegel_modified_system', text=True)
                os.close(fn)
                with open(system_ini, 'wt') as configfile:
                    cp.write(configfile)
                self._orig_initAPI(system_ini)
            finally:
                if not keep_temp_file:
                    try:
                        os.remove(system_ini)
                    except Exception:
                        pass
        else:
            self._orig_initAPI(systemIni)
    return initAPI_wrapper

# running initAPI without closing it first generates a crash.
# generating the snAPI objects automatically call initAPI
# exitAPI can be run multiple times.
# So to avoid the crash, use a class as a single instance.
# always access api with snAPI_instance.api
# and obtain snAPI_instance with snAPI_instance.get
class snAPI_instance(object):
    api = None
    @classmethod
    def init(cls, console_log=False, keep_temp_file=False):
        cls.console_log = console_log
        cls.keep_temp_file = keep_temp_file
        snapi = load_snAPI()
        if not hasattr(snapi.Main.snAPI, '_orig_initAPI'):
            # duck type a fix to allow changing console logging level
            # required for at aleast version 1.1.2 of snAPI
            orig_initAPI = snapi.Main.snAPI.initAPI
            snapi.Main.snAPI._orig_initAPI = orig_initAPI
        snapi.Main.snAPI.initAPI = _generate_initAPI_wrapper(console_log=console_log, keep_temp_file=keep_temp_file)
        cls.api = snapi.Main.snAPI()
        return cls
    @classmethod
    def get(cls, console_log=False, keep_temp_file=False, reload=False):
        if cls.api is not None:
            if reload:
                cls.api.exitAPI()
                cls.api = None
            else:
                return cls
        return snAPI_instance.init(console_log=console_log, keep_temp_file=keep_temp_file)


def locked_calling_with_dev(func):
    @functools.wraps(func)
    def locked_call_with_dev_wrapped(self, *args, **kwargs):
        self._update_dev()
        return func(self, *args, **kwargs)
    # This is needed in python 2
    locked_call_with_dev_wrapped.__wrapped__ = func
    return locked_calling(locked_call_with_dev_wrapped)


@add_to_instruments
#@register_instrument('PicoQuant', 'MultiHarp')
class PicoQuant_MultiHarp_snAPI(BaseInstrument):
    """
    This controls the picoQuant instruments using the snAPI interface.
    You can use any of the snAPI trought the ._snapi attribute.
    The snAPI constants are available through the ._snc attribute.
    Only a minimal interface is currently implemented on top of it.
    Useful devices:
        count_rate_all
        fetch
        readval
    Useful methods:
        discover (static method)
        conf
        conf_meas
        set_mode_refsrc
    Useful attribute:
        device # to call the snAPI.device methods
        measurement # to call the methods of the currently configured meas (conf_meas)
    """
    @property
    def _snapi(self):
        return self._sn.api

    @property
    def _snc(self):
        return snAPI.Constants

    @property
    @locked_calling_with_dev
    def device(self):
        return self._snapi.device

    @property
    @locked_calling_with_dev
    def measurement(self):
        try:
            mode, args, kwargs, corr_type = self._get_meas_conf()
        except RuntimeError:
            return None
        return mode

    def __init__(self, dev_num_name=0, console_log=False, mode='Histogram', ref_src='Internal', keep_temp_file=False, reload=False, **kwargs):
        """
        dev_num_name can be a number, which selects that device discovered.
                It can also be a serial number string to select one
                You can use the static method discover to list devices.
        mode see set_mode_refsrc for the possible mode (after first initialization)
        ref_src also see set_mode_refsrc
        console_log when False (default) disables the default console log that snAPI normally generates
                    True will forcefully enable it. None will keep the current system default.
        keep_temp_file default to False. When True, usually for debugging, it keeps the temporary file generated when
                console_log is False.
        reload when True is to force exiting and reinit of the snAPI. Otherwise console_log and keep_temp_file
            will only be effecting on the first init.
        WARNING: like for the dll interface, if two object refering to the same instrument are loaded
        and one of them closes, the other will also be in a closed state. This will happen if
        you reload an instrument with the same python variable name.
        """
        self._sn = snAPI_instance.get(console_log=console_log, keep_temp_file=keep_temp_file, reload=reload)
        self._snapi_cache = self._snapi
        self._dev = None
        self._serial_num = None
        self._meas_conf = None
        self._choices_mode = Choice_Enum(self._snc.MeasMode)
        self._choices_rfsrc = Choice_Enum(self._snc.RefSource)
        doc = PicoQuant_MultiHarp_snAPI.set_mode_refsrc.__doc__
        if '%r' in doc:
            doc = doc%(self._choices_mode, self._choices_rfsrc)
            PicoQuant_MultiHarp_snAPI.set_mode_refsrc.__doc__ = doc
        super(PicoQuant_MultiHarp_snAPI, self).__init__(**kwargs)
        self.open(dev_num_name)
        self.set_mode_refsrc(mode, ref_src, _init=True)
        self._async_mode = 'poll' # not wait
        self.async_wait.set(.1) # async wait time when fetching count by default.

    @staticmethod
    def discover(console_log=False, keep_temp_file=False, reload=False):
        """
        returns a list of names (serial number)
        """
        sn = snAPI_instance.get(console_log=console_log, keep_temp_file=keep_temp_file, reload=reload)
        sn.api.getDeviceIDs()
        return sn.api.deviceIDs

    @locked_calling
    def open(self, dev_num_name=0):
        if not self._snapi.getDevice(dev_num_name):
            raise RuntimeError("Unable to open the device.")
        # when getDevice succeeds it does getDeviceConfig
        # which saves the result in deviceConfig
        serial = self._snapi.deviceConfig["ID"]
        dev = self._snapi.deviceConfig["Index"]
        self._serial_num = serial
        self._dev = dev

    @locked_calling_with_dev
    def close(self):
        if hasattr(self, '_dev') and self._dev is not None:
            self._snapi.closeDevice(False)
            self._snapi.getDeviceConfig()
        self._dev = None

    def __del__(self):
        self.close()
        super(PicoQuant_MultiHarp_snAPI, self).__del__()

    def idn(self):
        conf = self.conf()
        model = conf['Model']
        version = conf['Version']
        #partno = conf['PartNo']
        if sys.platform.startswith('win'):
            import win32api
            # see doc for VerQueryValue
            #  https://learn.microsoft.com/en-us/windows/win32/api/winver/nf-winver-verqueryvaluea
            # note that 0409 means en_US language and 04b0 means 1200 code page
            # the list of codepages can be obtained from
            # win32api.GetFileVersionInfo(self._snapi.dll._name, r'\VarFileInfo\Translation')
            libversion = win32api.GetFileVersionInfo(self._snapi.dll._name, r'\StringFileInfo\040904b0\ProductVersion')
            # could also use
            # s = win32api.GetFileVersionInfo(self._snapi.dll._name, '\\')
            # l = s['FileVersionLS']; m = s['FileVersionMS']
            # libversion = '%d.%d.%d.%d'%(m>>16, m&0xffff, l>>16, l&0xffff)
            if libversion is None or libversion == '':
                libversion = '-1'
        else:
            libversion = '-1'
        serial = conf['ID']
        ver = 'hw:%s_lib:%s'%(version, libversion)
        return "PicoQuant,%s,%s,%s"%(model, serial, ver)

    def _async_select(self, devs):
        self._async_mode = 'wait'
        for dev in devs:
            if isinstance(dev, tuple):
                d = dev[0]
                p = dev[1]
            else:
                d = dev
                p = {}
            if d in [self.fetch, self.readval]:
                count = p.get('count', False)
                if not count:
                    self._async_mode = 'poll'

    @locked_calling
    def _async_trig(self):
        super(PicoQuant_MultiHarp_snAPI, self)._async_trig()
        if self._async_mode == 'wait':
            return
        # make sure previous one is stopped
        self.stop_measurement()
        self.clear_measurement()
        # clear status
        self.start_measurement()

    def _async_detect(self, max_time=.5):
        if self._async_mode not in ['wait', 'poll']:
            raise RuntimeError('Invalid async_mode selected')
        if self._async_mode == 'wait':
            return super(PicoQuant_MultiHarp_snAPI, self)._async_detect(max_time)
        mode, args, kwargs, corr_type = self._get_meas_conf()
        if _retry_wait(mode.isFinished, max_time, delay=0.05):
            return True
        return False

    def _async_cleanup_after(self):
        if self._async_mode == 'poll':
            self.stop_measurement()
        super(PicoQuant_MultiHarp_snAPI, self)._async_cleanup_after()


    def _update_dev(self):
        # This is used by locked_calling_with_dev
        # This is required to be call before any api, so that we talk
        # to the correct device (in case another device is also loaded).
        # The api seems to be using serial numbers directly, so use that
        # instead of the device number
        self._snapi.getDevice(self._serial_num)

    @locked_calling_with_dev
    def set_mode_refsrc(self, mode=None, ref_src=None, _init=False):
        """ set the mode and refsrc
            if both are None, return the current one.
            Otherwise changes one or both
            mode must be one of %r
            ref_src must be one of %r
        """
        if mode is None and ref_src is None:
            return dict_improved(mode=self._init_mode, ref_src=self._init_refsrc)
        if mode is None:
            mode = self._init_mode
        elif mode not in self._choices_mode:
            raise ValueError(self.perror('Invalid mode. Needs to be one of %r'%self._choices_mode))
        if ref_src is None:
            ref_src = self._init_refsrc
        elif ref_src not in self._choices_rfsrc:
            raise ValueError(self.perror('Invalid ref_src. Needs to be one of %r'%self._choices_rfsrc))
        self._snapi.initDevice(self._choices_mode.tostr(mode), self._choices_rfsrc.tostr(ref_src))
        self._init_mode = mode
        self._init_refsrc = ref_src

    @locked_calling_with_dev
    def _current_config(self, dev_obj=None, options={}):
        opts = ['conf=%r'%self.conf()]
        return opts + self._conf_helper(options)

    def _get_meas_conf(self):
        if self._meas_conf is None:
            raise RuntimeError(self.perror('You need to initialize the measurement with the conf_meas method'))
        return self._meas_conf

    @locked_calling_with_dev
    def start_measurement(self):
        mode, args, kwargs, corr_type = self._get_meas_conf()
        mode.measure(*args, **kwargs)

    @locked_calling_with_dev
    def clear_measurement(self):
        mode, args, kwargs, corr_type = self._get_meas_conf()
        mode.clearMeasure()

    @locked_calling_with_dev
    def stop_measurement(self):
        mode, args, kwargs, corr_type = self._get_meas_conf()
        mode.stopMeasure()

    @locked_calling_with_dev
    def conf(self):
        # make sure the deviceConfig is up to date.
        self._snapi.getDeviceConfig()
        return self._snapi.deviceConfig

    def _count_rate_all_getformat(self, **kwarg):
        num_ch = self.conf()['NumChans']
        cnt_titles = ['sync'] + ['ch%d'%i for i in range(1, num_ch+1)]
        fmt = self.count_rate_all._format
        fmt.update(multi=cnt_titles)
        return BaseDevice.getformat(self.count_rate_all, **kwarg)

    def _count_rate_all_getdev(self):
        if getattr(self._snapi, 'getCountRates'):
            return self._snapi.getCountRates()
        else:
            # this is for v 1.2.1
            return self._snapi.device.getCountRates()

    def _active_channels_getdev(self):
        enabled = []
        for i, ch in enumerate(self.conf()['ChansCfg']):
            if ch['ChanEna']:
                enabled.append(i+1)
        return enabled

    def conf_meas(self, mode, *args, **kwargs):
        """ select the measurement mode as well as the parameters that will be passed
        to the measure methode of the mode """
        if hasattr(self, 'histogram2d'):
            modes = ['raw', 'unfold', 'histogram', 'histogram2d', 'timeTrace', 'correlation_g2', 'correlation_fcs']
        else:
            modes = ['raw', 'unfold', 'histogram', 'timeTrace', 'correlation_g2', 'correlation_fcs']
        if mode not in modes:
            raise ValueError('mode needs to be one of %r'%modes)
        mode_split = mode.split('_')
        if len(mode_split) == 1:
            mode_split.append('')
        mode, corr_type = mode_split
        kwargs['waitFinished'] = False
        self._meas_conf = getattr(self._snapi, mode), args, kwargs, corr_type

    def _fetch_ch_helper(self, chs, count=False):
        if chs is None:
            chs = self.active_channels.get()
            if count:
                chs = [0] + chs
        if not isinstance(chs, (list, tuple, np.ndarray)):
            chs = [chs]
        for c in chs:
            all_chs = list(range(0, self.conf()['NumChans']+1))
            if c not in all_chs:
                raise ValueError(self.perror('Invalid chs selection in fetch'))
        return chs

    def _fetch_getformat(self, **kwarg):
        chs = kwarg.get('chs', None)
        count = kwarg.get('count', False)
        xaxis = kwarg.get('xaxis', True)
        graph = []
        if count:
            chs = self._fetch_ch_helper(chs, count)
            xaxis = False
            multi = []
            graph = list(range(len(chs)))
            for c in chs:
                if c == 0:
                    multi.append('sync')
                else:
                    multi.append('ch%i'%c)
        else:
            mode, args, kwargs, corr_type = self._get_meas_conf()
            if mode == self._snapi.histogram:
                chs = self._fetch_ch_helper(chs)
                if xaxis:
                    multi = ['time(s)']
                else:
                    multi = []
                for c in chs:
                    multi.append('ch%i'%c)
            else:
                xaxis = False
                multi = ['data']
            multi = tuple(multi)
        fmt = self.fetch._format
        fmt.update(multi=multi, graph=graph, xaxis=xaxis)
        return BaseDevice.getformat(self.fetch, **kwarg)

    def _fetch_getdev(self, chs=None, count=False, xaxis=True):
        """ options are:
            count: to return count_rate instead of data selected with conf_meas.
            chs: only for histogram or counts.
                 to select which channels to return.
                 when None, returns all active chs
                 otherwise can be a single ch or a list
                 of ch. if ch=0 it means the sync ch (it can be used for
                  count and for T2 histograms)
            xaxis: only for histogram
        """
        bins = None
        if count:
            data = self.count_rate_all.get()
        else:
            mode, args, kwargs, corr_type = self._get_meas_conf()
            if corr_type == 'g2':
                data, bins = mode.getG2Data()
            elif corr_type == 'fcs':
                data, bins = mode.getFCSData()
            else:
                data = mode.getData()
                if mode == self._snapi.histogram:
                    # bins are in ps, make it s
                    data, bins = data
                    bins = bins*1e-12
                elif mode == self._snapi.timeTrace:
                    data, bins = data
        if count or mode == self._snapi.histogram:
            chs = self._fetch_ch_helper(chs, count)
            data = data[chs]
        if bins is not None:
            if len(bins) == 0:
                raise RuntimeError('No data is present. Use readval instead.')
            if xaxis:
                if data.ndim == 1:
                    data = np.array([bins, data])
                else:
                    data = np.concatenate([[bins], data], axis=0)
        return data

    def _create_devs(self):
        self._devwrap('count_rate_all', autoinit=False)
        self._devwrap('active_channels', autoinit=False)
        self._devwrap('fetch', autoinit=False, trig=True)
        self.readval = ReadvalDev(self.fetch)
        # This needs to be last to complete creation
        super(PicoQuant_MultiHarp_snAPI, self)._create_devs()
