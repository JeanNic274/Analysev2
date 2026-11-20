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

from ..instruments_base import visaInstrument, scpiDevice,\
                            visa_wrap, locked_calling
from ..instruments_registry import register_instrument


#@register_instrument('UdeS_IQ', 'Watchdog_communication', 'V1.1.1')
@register_instrument('UdeS_IQ', 'Watchdog_communication')
class iq_watchdog(visaInstrument):
    """
    This controls the UdeS_IQ Watchdog_communication device
    Useful devices:
        watchdog
        time_left
        relay
        temperature
    This only handles serial address connections (like ASRL1)
    """
    def __init__(self, address, baud_rate=115200, quiet_empty=True, **kwargs):
        """
        baud_rate is probably 115200 or 9600.
        """
        self._doing_ask = False
        self._quiet_empty = quiet_empty
        cnsts = visa_wrap.constants
        super(iq_watchdog, self).__init__(address, parity=cnsts.Parity.none, flow_control=cnsts.VI_ASRL_FLOW_NONE,
                                            baud_rate=baud_rate, data_bits=8, stop_bits=cnsts.StopBits.one, write_termination='\r\n',
                                            read_termination='\r\n', **kwargs)

    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        return self._conf_helper('watchdog', 'relay', 'time_left', options)

    @locked_calling
    def write(self, val, termination='default', encoding=None, skip_read=False):
        if self._doing_ask or skip_read:
            super(iq_watchdog, self).write(val, termination=termination, encoding=encoding)
        else:
            ret = self.ask(val, encoding=encoding)
            if ret != 'ok':
            #if ret.startswith('Error:'):
                raise RuntimeError(self.perror('The device returned an error: %s'%ret))

    @locked_calling
    def ask(self, question, raw=False, encoding=None, chunk_size=None):
        try:
            self._doing_ask = True
            return super(iq_watchdog, self).ask(question, raw=raw, encoding=encoding, chunk_size=chunk_size)
        finally:
            self._doing_ask = False

    def reset_poweron(self, quiet=True):
        self.write('reset', skip_read=True)
        self.empty_buf(quiet=quiet)

    def empty_buf(self, quiet=True):
        prev_timeout = self.set_timeout
        try:
            self.set_timeout = 0.1
            while True:
                r = self.read()
                if not quiet:
                    print(r)
        except visa_wrap.VisaIOError:
            pass
        finally:
            self.set_timeout = prev_timeout

    def _create_devs(self):
        # if the connection happens immediately after a reset of the chip
        # it returns a bunch of text. Clean it up
        self.empty_buf(quiet=self._quiet_empty)
        self.watchdog = scpiDevice('watchdog', str_type=int, min=0, max=3600, doc='read or set watchdog time in s')
        self.time_left = scpiDevice(getstr='time_left?', str_type=float)
        self.temperature = scpiDevice(getstr='temperature?', str_type=float)
        self.relay = scpiDevice('relay', str_type=bool)

        # This needs to be last to complete creation
        super(iq_watchdog, self)._create_devs()
