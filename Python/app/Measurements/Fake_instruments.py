
import time
import numpy as np
import sys






class Fake_spectrometer():
    def __init__(self):
        self.X = np.linspace(1,1024,1024)
        self.readval = np.random.rand(1024)
        self.val = np.array(100*np.exp( - (self.X - 500+300*(np.random.rand()-0.5))**2 / (2 * 100**2) ) +0.5*self.X+10*np.random.rand(1024))
    def get(self):
        time.sleep(2)
        self.val = np.array(100*np.exp( - (self.X - 500+300*(np.random.rand()-0.5))**2 / (2 * 50**2) ) +0.1*self.X+10*np.random.rand(1024))
        return self.X, self.val





class Fake_MH150():
    def __init__(self):
        pass
    
    
    def getCountRates(self):
        return 1000*np.random.randint(1,100), 1000*np.random.randint(1,100)
    
    
    
    
    
    
class Fake_NanoPositionner():
    def __init__(self):
        self.move = move_nano()    
        
class move_nano():
    def __init__(self):
        pass
    
    def setControlTargetPosition(self,axis,pos):
        sys.stdout.write("\r"+f"Going: {axis}, {pos}")
        sys.stdout.flush()
        time.sleep(0.11)
    

























