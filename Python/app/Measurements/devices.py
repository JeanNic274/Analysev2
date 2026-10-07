import time

import Python.app.Measurements.Fake_instruments as FAKE
# from Python.app.Measurements.detection import start_apds, start_apds_trpl, start_spectro
from Python.app.Measurements.Fake_instruments import *
from pyHegel.pyHegel import commands as cmds

def close_device_all(sn=None, amc=None,showcmd=True, daq=None, t_ch1=None, t_ch2=None, spectro=None, camera=None,laser=None):
    try:
        if amc:
            amc.close()
            if showcmd:
                print("AMC closed.")
        if sn:
            sn.closeDevice(allDevices=True)
            sn.exitAPI()
            time.sleep(3)
            if showcmd:
                print("MH150 closed.")
        if daq:
            if t_ch1:
                t_ch1.stop()
            if t_ch2:
                t_ch2.stop()
            if showcmd:
                print("DAQ closed.") 
        if camera:
            unload(camera)
        if spectro:
            unload(spectro)
        if laser:
            unload(laser)
    except:
        print("Nothing to close.")
        return None


def start_default_devices(spectro=True):
    if spectro:
        spectro_device = start_spectro()
    return spectro_device



class Scanner():
    def __init__(self,axes,detection):
        self.axes = axes
        self.name_detection = detection[0]
        self.dev_detection = detection[1]
        self.NanoPos = None
        
    def move_fns(self):
        fns = {}
        for axe in self.axes:
            if axe =='AttoX':
                if self.NanoPos is None:
                    self.NanoPos = Fake_NanoPositionner()
                fns[axe] = lambda v: piezoMove(0,v)
            if axe =='AttoY':
                if self.NanoPos is None:
                    self.NanoPos = Fake_NanoPositionner()
                fns[axe] = lambda v: piezoMove(1,v)
            if axe =='AttoZ':
                if self.NanoPos is None:
                    self.NanoPos = Fake_NanoPositionner()
                fns[axe] = lambda v: piezoMove(2,v)
            
            def piezoMove(axe,coord):
                self.NanoPos.move.setControlTargetPosition(axe,coord)
                self.wait_until_stable(axe)
                return self.NanoPos.move.getPosition(axe)
                # amc.move.setControlTargetPosition(2, int(y * 1000)); wait_until_stable(amc, 2)       
            
        return fns

    
    
    def wait_until_stable(self, axis):
        timeout = 10
        start = time.time()
        while True:
            if self.NanoPos.status.getStatusMoving(axis) == 0 and self.NanoPos.status.getStatusTargetRange(axis):
                break
            self.NanoPos.control.setControlOutput(axis, True)
            self.NanoPos.control.setControlMove(axis, True)
            if time.time() - start > timeout:
                print(f"Timeout waiting for stage axis {axis}")
                break
            time.sleep(0.01)
    
    def meas_fns(self):
        if self.name_detection == 'MH150':
            return self.dev_detection.getCountRates
        elif self.name_detection == 'DAQ':
            print('WIP')
            return self.WIP
        elif self.name_detection == 'Spec':
            return lambda: cmds.get(self.dev_detection.readval)
        else:
            raise Exception(f'Could not find detection for {self.name_detection}')
        