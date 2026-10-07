
import time
import numpy as np
import sys

class Fake_laser():
    def __init__(self):

        self.softlock_en = FakeParameter(f"softlock_en", initial=None)
        self.laser_mode = FakeParameter(f"laser_mode", initial=None)
        self.cw_power_permille = FakeParameter(f"cw_power_permille", initial=0)
        self.freq = FakeParameter(f"freq", initial=0)


    def set(self, *value, **kwarg):
        return self.set(*value, **kwarg)

    def get(self, *args, **kwarg):
        return self.get(*args, **kwarg)



class Fake_spectrometer():
    def __init__(self):
        self.X = np.linspace(1,1024,1024)
        self.readval = FakeSpectrumMeasurement()
        self.val = np.array(100*np.exp( - (self.X - 500+300*(np.random.rand()-0.5))**2 / (2 * 100**2) ) +0.5*self.X+10*np.random.rand(1024))
    def get(self):
        time.sleep(2)
        self.val = np.array(100*np.exp( - (self.X - 500+300*(np.random.rand()-0.5))**2 / (2 * 50**2) ) +0.1*self.X+10*np.random.rand(1024))
        return self.X, self.val

class FakeSpectrumMeasurement():
    def __init__(self):
        self.X = np.linspace(1,1024,1024)
        self.val = np.random.rand(1024)
        
    def get(self, *args, **kwarg):
        self.val = np.array(100*np.exp( - (self.X - 500+300*(np.random.rand()-0.5))**2 / (2 * 50**2) ) +0.1*self.X+10*np.random.rand(1024))
        return self.X, self.val




class Fake_MH150():
    def __init__(self):
        pass
    
    
    def getCountRates(self):
        return (1000*np.random.randint(1,100), 1000*np.random.randint(1,100))
    
    
    
class Fake_ESP300():
    def __init__(self):
        pass
    
    
    
    
class Fake_NanoPositionner():
    def __init__(self):
        self.move = move_nano()    
        self.status = status_nano()
        # if self.NanoPos.status.getStatusMoving(axis) == 0 and self.NanoPos.status.getStatusTargetRange(axis):
        #     break
        # self.NanoPos.control.setControlOutput(axis, True)
        # self.NanoPos.control.setControlMove(axis, True)
class move_nano():
    def __init__(self):
        pass
    
    def setControlTargetPosition(self,axis,pos):
        sys.stdout.write("\r"+f"Going: {axis}, {pos}")
        sys.stdout.flush()
        time.sleep(0.11)
    
    def getPosition(self,axis):
        return np.random.randint(1000,100000)/10
    
class status_nano():
    def __init__(self):
        pass
    def getStatusMoving(self,axis):
        return 0
    def getStatusTargetRange(self,axis):
        return 1


class FakeParameter:
    def __init__(self, name, initial=None, validator=None):
        self.name = name
        self._value = initial
        self.validator = validator

    def set(self, *value, **kwarg):
        v = value[0] if value else kwarg.get('value')
        if self.validator is not None:
            v = self.validator(v)
        self._value = v
        print(f"[FAKE] {self.name} -> {v!r} (kwarg={kwarg})")
        return self._value

    def get(self, *args, **kwarg):
        print(f"[FAKE] {self.name} read -> {self._value!r}")
        return self._value

    def __repr__(self):
        return f"<FakeParameter {self.name}={self._value!r}>"


