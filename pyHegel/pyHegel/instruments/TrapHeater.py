# -*- coding: utf-8 -*-
########################## Copyrights and license ############################
#                                                                            #
# Copyright 2016-2023  Gabriel Laliberté <Gabriel.Laliberte@usherbrooke.ca>  #
#                      Christian Lupien <christian.lupien@usherbrooke.ca>    #
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
                            BaseDevice, Dict_SubDevice, ChoiceMultiple,\
                            visa_wrap, _fromstr_helper, _tostr_helper, locked_calling
from ..instruments_registry import register_instrument

#######################################################
##    Trap Heater V1
#######################################################
class Float_2dec(object):
    def __call__(self, from_str):
        return float(from_str)
    def tostr(self, val):
        return '%.2f'%val
float_2dec = Float_2dec()

class string_with_header(object):
    def __init__(self, header, str_type):
        self.header = header+':'
        self.str_type = str_type
    def __call__(self, from_str):
        if from_str.startswith(self.header):
            from_str = from_str[len(self.header):]
        else:
            raise ValueError('Missing header "%s" in value read'%self.header[:-1])
        return _fromstr_helper(from_str, self.str_type)
    def tostr(self, val):
        return _tostr_helper(val, self.str_type)

class Trap_Dev(BaseDevice):
    def __init__(self, name_type, question, command=False, single=None, *args, **kwargs):
        """
        name_type is a list of tuples of (name, type, dict_entry_name, lims)
        where lims can be None, (min, max) or a list (min or max can also be None)
        single True returns the first value, False returns the whole dictionnary
               None is automatic (is True when there is onlt one name_type entry)
        """
        if single is None:
            single = True if len(name_type)==1 else False
        self._single = single
        field_names = [e[2] for e in name_type]
        ch_kwargs = {}
        if not single:
            kwargs['allow_kw_as_dict'] = True
            kwargs['allow_missing_dict'] = True
            kwargs['multi'] = field_names
            ch_kwargs['ending_sep'] = True
        else:
            ch_kwargs['ending_sep'] = False  # for set
            ch_kwargs['ending_sep_get'] = True
        lims = [(string_with_header(e[0], e[1]), e[3]) for e in name_type]
        choices = ChoiceMultiple(field_names, lims, sep=';', **ch_kwargs)
        kwargs['choices'] = choices
        super(Trap_Dev, self).__init__(*args, **kwargs)
        if command:
            self._setdev_p = question
        self._getdev_p = question
        self._name_type = name_type
        self.type = choices
    def _parse_answer(self, answer):
        ret = self.choices(answer)
        if self._single:
            ret = ret[0]
        return ret
    def _checkdev(self, val):
        if self._single:
            val = {self._name_type[0][2]: val}
        self._check_cache['val'] = val
        super(Trap_Dev, self)._checkdev(val)
    def _getdev(self):
        getdev_p = self._getdev_p
        answer = self.instr.ask(getdev_p)
        return self._parse_answer(answer)
    def _setdev(self, val):
        quest = self._setdev_p
        if quest is None:
            raise NotImplementedError('This device does not have setdev')
        val= self._check_cache['val']
        answer = self.instr.ask(quest + self.choices.tostr(val))
        self._set_delayed_cache = self._parse_answer(answer)

class Trap_Redirect_Dev(Trap_Dev):
    def __init__(self, command_str, subdev, subdev_entry, name, data_type, lims, *args, **kwargs):
        name_type = [(name, data_type, 'foo', lims)]
        kwargs['command'] = True
        super(Trap_Redirect_Dev, self).__init__(name_type, command_str, *args, **kwargs)
        self._getdev_p = (subdev, subdev_entry)
    def _getdev(self):
        subdev, subdev_entry = self._getdev_p
        return subdev.get()[subdev_entry]

#@register_instrument('Reulet Lab','TH01','1.0')
@register_instrument('Reulet Lab','TH01','2.1')
class Trap_Heater(visaInstrument):
    """
    This controls the Trap Heater module
    Useful device:
        status
        setpoint
        heat_time
        pid
    Useful methods:
        start
        stop
    This only handles serial address connections (like ASRL1)
    """
    def __init__(self, address):
        cnsts = visa_wrap.constants
        super(Trap_Heater, self).__init__(address, parity=cnsts.Parity.none, flow_control=cnsts.VI_ASRL_FLOW_NONE,
                                            baud_rate=9600, data_bits=8, stop_bits=cnsts.StopBits.one, write_termination='\n')
    def idn(self):
        return self.ask('*idn?')
    @locked_calling
    def _current_config(self, dev_obj=None, options={}):
        return self._conf_helper('status', 'pid', 'heat_time', options)
    def start(self):
        st = self.ask('STHT')
        if st == 'STHT':
            print('Heating Started')
        else:
            raise NotImplementedError('Start Failed')
    def stop(self):
        st = self.ask('SPHT')
        if st == 'SPHT':
            print('Heating Stopped')
        else:
            raise NotImplementedError('Stop Failed')
    def _create_devs(self):
        self._devwrap('setpoint')
        self.status = Trap_Dev([('TC1', float, 'temp_tc1', None), ('TC2', float, 'temp_tc2', None),
                                 ('HTR', float, 'heat_power', None), ('STP', float, 'setpoint', None),
                                 ('HTL', float, 'time_left', None)], 'RDST', doc='time in seconds, heat_power in percent')
        self.setpoint = Trap_Redirect_Dev('STSP', self.status, 'setpoint', 'SP', float_2dec, (0., None))
        self.heat_time = Trap_Dev([('HD', int, 'foo', (0, 500))], 'STHD', command=True, doc='time in minutes')
        self.pid = Trap_Dev([('P', float_2dec, 'p', (0, None)), ('I', float_2dec, 'i', (0, None)), ('D', float_2dec, 'd', (0, None))], 'SPID', command=True)
        self.pid_p = Dict_SubDevice(self.pid, 'p', force_default=False) # force_default=False means use the cache for the others
        self.pid_i = Dict_SubDevice(self.pid, 'i', force_default=False)
        self.pid_d = Dict_SubDevice(self.pid, 'd', force_default=False)
        self.temp1 = Dict_SubDevice(self.status, 'temp_tc1', force_default=False, doc='units are Celsius')
        self.temp2 = Dict_SubDevice(self.status, 'temp_tc2', force_default=False)
        self.alias = self.temp1
        # This needs to be last to complete creation
        super(Trap_Heater, self)._create_devs()
