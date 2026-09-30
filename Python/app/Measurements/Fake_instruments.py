
import time
import numpy as np







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
    
    
    
    
    
    
    
    
class Fake_NanoPositionner():
    def __init__(self):
        pass
    

        
    

























