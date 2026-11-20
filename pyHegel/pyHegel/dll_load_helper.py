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

usb_core = None
usb_util = None

def delayed_libusb_import():
    global usb_core, usb_util
    if usb_core is None or usb_util is None:
        try:
            import usb.core as usb_core
            import usb.util as usb_util
        except ImportError as exc:
            raise RuntimeError('Unable to import usb.core usb.util because of: %s.\n'%exc+
                               'Can be installed with (only for python>=3.9):\n'+
                               ' pip install pyusb')
    return usb_core, usb_util
