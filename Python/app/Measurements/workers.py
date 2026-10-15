import time
import sys
import traceback
def temp_msg(msg):
    sys.stdout.write(f'\r\033[K{msg}')
    sys.stdout.flush()
    
from PySide6.QtCore import QThread, QObject, Signal
import numpy as np

from Python.app.Processing.io import create_file_header

temp_msg('starting pyHegel')
from pyHegel.pyHegel import commands as cmds # pyright: ignore[reportMissingImports]


        
class CommWorker(QObject):
    finished = Signal()  
    error = Signal(str)
    value_error = Signal(list)
    
    def __init__(self, device, set_fn):
        super().__init__()
        self.device = device
        self.set_fn = set_fn
        self.kwargs = {}

    def run(self):
        try:
            val = self.set_fn(device = self.device, **self.kwargs)
            if val:
                self.value_error.emit(val)
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            self.finished.emit() 
        
        
class MeasureWorker(QObject):
    completed = Signal(object)  
    finished = Signal()  
    error = Signal(str)

    def __init__(self, meas_fn):
        super().__init__()
        self.meas_fn = meas_fn
        self.kwargs = {}

    def run(self):
        try:
            val = self.meas_fn()
            self.completed.emit(val)
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            self.finished.emit()
                   
            
class ContinuousReadWorker(QObject):
    reading = Signal(object)   
    error = Signal(str)
    finished = Signal()

    def __init__(self, measure_fn, interval_ms=500, graph = None):
        super().__init__()
        self.measure_fn = measure_fn
        self.interval_ms = interval_ms
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            while self._running:
                value = self.measure_fn()
                self.reading.emit(value)

                # sleep in small chunks so it feels less laggy
                slept = 0
                chunk = 100  # ms
                while slept < self.interval_ms and self._running:
                    QThread.msleep(chunk)
                    slept += chunk
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            self.finished.emit()        
            
            
class ScanWorker(QObject): 
    point_measured = Signal(tuple, dict, object)
    finished = Signal()
    completed = Signal(float)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, axes, move_fns, measure_fn, sess_nb="" ,meas_nb = "", file_path = 'ScanError.txt', save_points = False, value_idx = -1, slice_idx = slice(100), meas_names = range(10)):
        super().__init__()
        self.axes = axes
        self.meas_nb = meas_nb
        self.sess_nb = sess_nb
        self.save_points = save_points
        self.move_fns = move_fns
        self.measure_fn = measure_fn
        self.meas_names = meas_names
        self._stop_requested = False
        self.value_idx = value_idx
        self.slice_idx = slice_idx
        self._file_path = file_path
        
        self._stop_msg = None

        self.axis_names = list(reversed(axes.keys()))
        self.axis_values = []
        try:
            for name in self.axis_names:
                start, stop, step = axes[name]
                if (start>stop and step >0) or (start<stop and step <0):
                    start, stop = stop, start
                start, stop, step = 1000*int(start), 1000*int(stop), 1000*int(step)
                values = np.arange(start, stop + step / 2, step, dtype= int)
                self.axis_values.append(values)
        except Exception as e:
            self._stop_requested = True
            self._stop_msg = str(e)
            traceback.print_exc()
            return None

        self.shape = tuple(len(v) for v in self.axis_values)
        if len(axes) == 1:
            self.data = np.full(self.shape, np.nan, dtype = object)
        else:
            self.data = np.full(self.shape, np.nan)
        
    def _boustrophedon_scan(self, index_ranges): # snake like order
        n = len(index_ranges)

        def recurse(level, parity):
            seq = list(index_ranges[level])
            if parity % 2 == 1:
                seq.reverse()

            if level == n - 1:
                for i in seq:
                    yield (i,)
            else:
                for k, i in enumerate(seq):
                    # every outer step flips the inner axes
                    for rest in recurse(level + 1, parity + k):
                        yield (i,) + rest

        yield from recurse(0, 0)
        
    def request_stop(self):
        self._stop_requested = True
        self._stop_msg = "Manual stop requested"

    def run(self):
        try:
            with open(self._file_path,'a') as file:
                index_ranges = [range(len(v)) for v in self.axis_values]
                
                combos = list(self._boustrophedon_scan(index_ranges))
                total = len(combos)
                file.write('#')
                for name in self.axis_names[::-1]:
                    file.write(name+'.ReqPosition(um)'+'\t')
                    file.write(name+'.DetPos(um)'+'\t')
                for name in self.meas_names:
                    file.write(name+'\t')
                file.write('\n')
                
                last_coords = {name: None for name in self.axis_names}
                det_coords = {name: None for name in self.axis_names}
                t_start = time.time()
                for i, idx in enumerate(combos):
                    t_point = time.time()
                    save_data = []
                    
                    if self._stop_requested:
                        raise Exception(self._stop_msg)

                    coords = {
                        name: self.axis_values[a][idx[a]]
                        for a, name in enumerate(self.axis_names)
                    }
                    
                    # only move relevant axes
                    for name in self.axis_names[::-1]:
                        if coords[name] != last_coords[name]:
                            det_coords[name] = self.move_fns[name](coords[name])/1000
                            last_coords[name] = coords[name]
                        save_data.append(str(coords[name]/1000))
                        save_data.append(str(det_coords[name]))

                    value_raw = self.measure_fn()
                    value = value_raw[self.slice_idx]
                    self.data[idx] = value[self.value_idx] # used by _on_point_measured, dont remove
                    values_str = [str(val) for val in value]
                    save_data += values_str
                    file.write('\t'.join(save_data) + '\n')
                    file.flush()
                    self.point_measured.emit(idx, coords, value[self.value_idx])
                    if self.save_points:
                        self.save_point(value_raw[-1],idx)
                        
                    self.progress.emit(time.strftime('%H:%M:%S', time.gmtime((total-i)*( time.time()-t_start)/(i+1))))

                self.completed.emit(time.time()-t_start)
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            self.finished.emit()
            
    def save_point(self,val,idx):
        file_path = create_file_header(devices = [], sess_nb=self.sess_nb,meas_nb = self.meas_nb, idx = idx,sub_level = True)
        columns = ["IdusCam.Pixel(Num)","IdusCam.Wavelenght(nm)","IdusCam.Y Pix Track 1(Cnt)"]
        fmts = ["%d", "%.4f", "%d"]
        if len(val)>3:
            columns.append("IdusCam.Bckgnd Y Pix Row 1(Cnt)")
            columns.append("IdusCam.Corr Y Pix Row 1(Cnt)")
            fmts.append("%d")
            fmts.append("%d")
        if len(val) != len(columns):
            columns = [str(x) for x in range(len(val))]
            fmts = len(val) * ["%.4f"]
        np.savetxt(
                file_path,
                np.column_stack(val),
                delimiter="\t",
                header="\t".join(columns),
                comments="#",          
                fmt=fmts,   
            )

class MoveWorker(QObject):
    finished = Signal(int)  
    error = Signal(str)
    
    def __init__(self, device, axe, coords, absolute = True):
        super().__init__()
        self.device = device
        self.axe = axe
        self.coords = coords
        self.absolute = absolute

    def run(self):
        val = 0
        try:
            if not self.absolute:
                self.coords += round(self.device.move.getPosition(self.axe),-1)
            self.device.move.setControlTargetPosition(self.axe,self.coords)
            self.device.wait_until_stable(self.axe)
            val = self.device.move.getPosition(self.axe)
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            self.finished.emit(val) 