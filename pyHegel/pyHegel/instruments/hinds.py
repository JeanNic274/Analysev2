# -*- coding: utf-8 -*-

########################## Copyrights and license ############################
#                                                                            #
# Copyright 2025-2025  Christian Lupien <christian.lupien@usherbrooke.ca>    #
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


from ..instruments_base import visaInstrument, scpiDevice, decode_float64, visa_wrap,\
                                locked_calling, float_as_fixed
from ..instruments_registry import register_instrument

nm_float = float_as_fixed('%.6e') # needs to be <=10 in configuration I tested

@register_instrument("Hinds", "PEM controller CSC")
class Hinds_PEM_CSC(visaInstrument):
    """
    This controls the Hinds PhotoElastic Modulator Controller (PEM-CSC)
    Useful devices:
        Get/Set devices :
            modulator_drive_voltage
            modulator_retardance_nm
        Get device :
            modulator_freq
    Useful method:
            set_output_en
    The usb connection acts as a serial one, so the address should look like:
         ASRL4
    """

    def __init__(self, visa_address, **kwargs):
        cnsts = visa_wrap.constants
        baud_rate = kwargs.pop('baud_rate', 115200)
        parity = kwargs.pop('parity', cnsts.Parity.none)
        data_bits = kwargs.pop('data_bits', 8)
        stop_bits = kwargs.pop('stop_bits', visa_wrap.constants.StopBits.one)
        kwargs['baud_rate'] = baud_rate
        kwargs['parity'] = parity
        kwargs['data_bits'] = data_bits
        kwargs['stop_bits'] = stop_bits
        kwargs['write_termination'] = '\n'
        kwargs['read_termination'] = '\n'
        self._write_top_level = True
        super(Hinds_PEM_CSC, self).__init__(visa_address, **kwargs)

    # Careful. The commands need to be in the exact same capitalization as the manual
    #  and scientific numbers need to use lower case e
    def idn(self):
        res = self.ask('*IDN?')
        vendor = "Hinds"
        if res.upper().startswith(vendor.upper()):
            model, version = res[len(vendor):].strip().rsplit(' ', 1)
            return ','.join([vendor, model, 'no-serial', version])
        return res

    def _current_config(self, dev_obj=None, options={}):
        return self._conf_helper('modulator_retardance_nm', 'modulator_freq',
                                 'modulator_is_stable', 'modulator_retardance_range_nm', options)

    @locked_calling
    def write(self, cmd, termination='default', encoding=None):
        if self._write_top_level:
            try:
                self._write_top_level = False
                self.ask(cmd, encoding=encoding)
            finally:
                self._write_top_level = True
        else:
            super(Hinds_PEM_CSC, self).write(cmd, termination=termination, encoding=encoding)

    @locked_calling
    def ask(self, cmd, raw=False, encoding=None, chunk_size=None):
        if self._write_top_level:
            try:
                self._write_top_level = False
                res = super(Hinds_PEM_CSC, self).ask(cmd, encoding=encoding)
            finally:
                self._write_top_level = True
        else:
            res = super(Hinds_PEM_CSC, self).ask(cmd, encoding=encoding)
        return res

    def read(self, raw=False, encoding=None, count=None, chunk_size=None):
        ret = super(Hinds_PEM_CSC, self).read(raw=raw, encoding=encoding, count=count, chunk_size=chunk_size)
        if ret.startswith('[') and ']' in ret:
            d = ret.split(']', maxsplit=1)[1]
            if d[0] == '(' and d[-1] == ')':
                return d[1:-1]
        elif ret.startswith('<SCPINOP>('):
            raise  RuntimeError(self.perror('Bad command: %s'%ret))
        raise RuntimeError(self.perror('Invalid read stings: %s'%ret))

    def set_output_en(self, val):
        if val:
            extra='1'
        else:
            extra='0'
        self.write(':SYS:PEMO '+extra)

    def _create_devs(self):
        # self.idn = scpiDevice(getstr="*IDN?", str_type=str)
        self.modulator_drive_voltage = scpiDevice(":MOD:DRV", str_type=nm_float, min=0, max=1)
        self.modulator_retardance_nm = scpiDevice(":MOD:AMP", str_type=nm_float, setget=True)
        self.modulator_retardance_range_nm = scpiDevice(getstr=":MOD:AMPR?", str_type=decode_float64)
        self.modulator_freq = scpiDevice(getstr=":MOD:FREQ?", str_type=nm_float)
        self.modulator_is_stable = scpiDevice(getstr=":MOD:STABLE?", str_type=bool)
        return super()._create_devs()
