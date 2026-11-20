# -*- coding: utf-8 -*-
try:
    from PyQt6.QtGui import QIcon
    from PyQt6.QtDesigner import QPyDesignerCustomWidgetPlugin
except:
    from PyQt5.QtGui import QIcon
    from PyQt5.QtDesigner import QPyDesignerCustomWidgetPlugin
from pyHegel.gui.ScientificSpinBox import PyScientificSpinBox

# need to place this in the search path or adjust the environment variable:
#    PYQTDESIGNERPATH
# default paths are:
#   QtCore.QCoreApplication.libraryPaths()  :: [u'/usr/lib64/qt5/plugins', u'/usr/bin']
#     That list can be augmented (prepend) with entries in QT_PLUGIN_PATH environment variable
#   (Obtaining just the plugins path can be done with:
#        QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.PluginsPath)
#      which is: u'/usr/lib64/qt5/plugins' )
#    with /designer/python appended
# Also:
#   QtCore.QDir.homePath()
#    with /.designer/plugins/python appended
#
# On linux can start with:
#  PYQTDESIGNERPATH=~/codes/pyHegel/pyHegel/gui/designer/python: /usr/lib/qt6/bin/designer
# On windows can start with:
#  set PYQTDESIGNERPATH=\Codes\pyHegel\pyHegel\gui\designer\python;
#  \Anaconda3\envs\py311qt6\Library\bin\Designer6.exe

class PyScientificSpinBoxPlugin(QPyDesignerCustomWidgetPlugin):
    def __init__(self, parent=None):
        super(PyScientificSpinBoxPlugin, self).__init__(parent)
        self._initialized = False

    def initialize(self, core):
        if self._initialized:
            return
        self._initialized = True

    def isInitialized(self):
        return self._initialized

    def isContainer(self):
        return False

    def createWidget(self, parent):
        return PyScientificSpinBox(parent)

    def group(self):
        return 'UdeS custom'
    def name(self):
        return 'PyScientificSpinBox'

    def icon(self):
        return QIcon()

    def toolTip(self):
        return 'A generalized DoubleSpinBox using exponents.'

    def whatsThis(self):
        return """A generalized DoubleSpinBox that allows the use of varying precision, logarithmic increase,
                  and MKS multiplier unit"""

    def includeFile(self):
        return 'pyHegel.gui.ScientificSpinBox'

    def domXml(self):
        return """
<widget class="PyScientificSpinBox" name="spinScientific">
</widget>
"""

# defaulting with a changed value for a property, add (within <widget>):
# <property name="precision">
#    <number>5</number>
# </property>

