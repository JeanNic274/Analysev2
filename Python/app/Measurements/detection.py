import time
from pathlib import Path
import pyvisa

from pyHegel.pyHegel import commands, instruments
from app.Measurements.devices import *

try: from snAPI.Main import *
except ImportError as e: print(e)

try: import nidaqmx; from nidaqmx.constants import Edge
except ImportError as e: print(e)

from thorlabs_tsi_sdk.tl_camera import TLCameraSDK
from thorlabs_tsi_sdk.tl_camera_enums import OPERATION_MODE


from Python.app.Measurements.filters import filterwheel, filter_switch, detector_switch



def set_detection(state, home_first=False, apd_final_state=False, wlight_final_state=False, offset=11.224):
    """
    Coordinates all hardware and prints a complete state output table.
    """
    print(f"\n--- Initiating Hardware Shift to: [{state.upper()}] ---")
    
    # 1. Manage Serial Filter Wheel & Lights
    configs = {
        "camera":  {"slot": 0,  "filter": "no",   "detector": "camera"},
        "apd":     {"slot": 10, "filter": "n405", "detector": "apd"},
        "spectro": {"slot": 1,  "filter": "n405", "detector": "spectro"},
        "apd-435": {"slot": 5, "filter": "n405", "detector": "apd"}
    }
    
    if state not in configs:
        print("Error: Unknown detection state requested.")
        return
        
    cfg = configs[state]
    
    serial_status = filterwheel(
        slot=cfg["slot"], 
        offset=offset, 
        home_first=home_first, 
        apd_final_state=apd_final_state, 
        wlight_final_state=wlight_final_state
    )
    
    # 2. Manage ESP Axes
    det_pos, filt_pos = "Unknown", "Unknown"
    
    try:
        rm = pyvisa.ResourceManager()
        esp = rm.open_resource("GPIB1::7::INSTR")
        esp.timeout = 2000 # Set 2s timeout for reliable queries
        
        filt_pos = filter_switch(esp, moveto=cfg["filter"], showcmd=False)
        det_pos = detector_switch(esp, moveto=cfg["detector"], showcmd=False)
        
        esp.close()
    except Exception as e:
        print(f"Warning: Could not connect to ESP Controller. {e}")

    # 3. Output Final Hardware State
    print("\n" + "="*45)
    print("      CURRENT HARDWARE SYSTEM STATE      ")
    print("="*45)
    print(f" Target Mode        : {state.upper()}")
    print(f" Filter Wheel Slot  : {serial_status['Slot']}")
    print(f" Filter Axis Pos    : {filt_pos} mm")
    print(f" Detection Axis Pos : {det_pos} mm")
    print(f" APD Power State    : {serial_status['APD_Power']}")
    print(f" White Light State  : {serial_status['White_Light']}")
    print("="*45 + "\n")









def start_apds(detector_config=2, trpl=False, read_counts=True, graph_counts=False):
    """
    Initializes the MH150. Validates that total count rates > 200 cps before 
    returning the device handle. Retries up to 3 times, polling for 10 seconds 
    per attempt.
    """
    config_path_1_det = Path("data","settings","instruments_configs","Exciletas_MH.ini")#r"C:\Codes\Picoquant\snAPI_configs\Exciletas_MH.ini"
    config_path_2_det = Path("data","settings","instruments_configs","MPDs_MH.ini")#r"C:\Codes\Picoquant\snAPI_configs\MPDs_MH.ini"
    config_path_3_det = Path("data","settings","instruments_configs","MPDs_MH_TRPL.ini")#r"C:\Codes\Picoquant\snAPI_configs\MPDs_MH_TRPL.ini"

    d0 = 0  # Sync channel is standardly 0

    for attempt in range(3):
        sn = None  
        d1, d2 = None, None
        
        try:
            print(f"\n--- APD Initialization Attempt {attempt + 1}/3 ---")
            
            # --- 1. Initialize snAPI Detector ---
            sn = snAPI()
            sn.getDevice("1043897") 
            
            if not sn.initDevice():
                raise ConnectionError('MH150 device initialization failed.')

            # --- 2. Configuration Routing ---
            if detector_config == 1:
                d1, d2 = 1, 2
                sn.loadIniConfig(config_path_1_det)
                print(f'Using Exciletas: {sn.deviceConfig["ID"]}')
                
            elif detector_config == 2:
                d1, d2 = 3, 4
                if trpl:
                    sn.loadIniConfig(config_path_3_det)
                    print(f'Using MPDs for TRPL: {sn.deviceConfig["ID"]}')
                else:
                    sn.loadIniConfig(config_path_2_det)
                    print(f'Using MPDs (Standard): {sn.deviceConfig["ID"]}')
                    
            elif detector_config == 3:
                d1, d2 = 3, 4
                sn.loadIniConfig(config_path_3_det)
                print(f'Using MPDs for TRPL (Config 3 direct): {sn.deviceConfig["ID"]}')
                trpl = True 
            else:
                raise ValueError(f"Invalid detector_config: {detector_config}")

            # --- 3. Verification: Poll for 10 seconds ensuring Total > 200 ---
            counts_passed = False
            print("Polling APD count rates for up to 10 seconds (Requires Total > 200 cps)...")
            
            for sec in range(1, 11): # 1 to 10 seconds
                time.sleep(1) # Let hardware accumulate
                cnts = sn.getCountRates()

                c1, c2 = int(cnts[d1]), int(cnts[d2])
                total = c1 + c2
                
                if read_counts:
                    print(f"  [T+{sec}s] Ch {d1}: {c1} | Ch {d2}: {c2} | Total: {total} cps")
                    
                if total > 200:
                    counts_passed = True
                    print("Verification passed! Handing over instrument.")
                    break # Exit the polling loop early
            
            if not counts_passed:
                print("Verification failed: Total counts did not exceed 200 cps within 10 seconds.")
                print("Closing device and triggering restart...")
                close_device_all(sn=sn)
                time.sleep(1.5) # Brief cooldown before the next attempt
                continue # Jump to the next iteration of the 3-attempt loop


            # --- 5. Successful Standard Return ---
            if trpl:
                return sn, d0, d1, d2
            else:
                return sn, d1, d2

        except Exception as e:
            print(f"An error occurred during attempt {attempt + 1}: {e}")
            if sn is not None:
                try: close_device_all(sn=sn)
                except: pass
            time.sleep(1.5) # Cooldown before next attempt

    # --- Exhausted all 3 attempts ---
    print("\nCritical Error: Failed to start APDs with > 200 cps after 3 attempts.")
    return (None, None, None, None) if trpl else (None, None, None)


def start_apds_trpl():
    """
    Initializes the MH150, and optionally reads or graphs count rates.

    Args:
        detector_config (int): Selects detector config 1 (Exciletas) or 2 (MPDs). Defaults to 2.
        read_counts (bool): If True, prints count rates once. Defaults to False.
        graph_counts (bool): If True, enters a blocking loop to plot live count rates.
                             This mode will automatically close the device upon exit.

    Returns:
        tuple: A tuple of (sn, d1, d2) if initialization is successful and graph_counts is False.
               Returns (None, None, None) on failure or after graph_counts is used.
    """
    # Define configuration paths
    config_path_3_det = Path("data","settings","instruments_configs","MPDs_MH_TRPL.ini")#r"C:\Codes\Picoquant\snAPI_configs\MPDs_MH_TRPL.ini"

    sn = None  # Initialize sn to None for robust error handling
    try:
        # --- Initialize snAPI Detector ---
        sn = snAPI()
        sn.getDevice("1043897") # Register the device by serial number.
        

        if not sn.initDevice(MeasMode.Histogram):
            raise ConnectionError('MH150 device initialization failed.')
    
        d0, d1, d2 =0, 3, 4
        sn.loadIniConfig(config_path_3_det)
        print(f'Using MPDs for TRPL: {sn.deviceConfig["ID"]}')

        return sn, d0, d1, d2

    except Exception as e:
        print(f"An error occurred in start_apds: {e}")
        # Ensure cleanup happens on any initialization error
        if sn is not None:
             close_device_all(sn=sn)
        return None, None, None 

def start_daq(device='Dev1',ch1='PFI8', ch2='PFI9',read_counts=False, graph_counts=False, bin=0.1):
    PFI_CH1 = f"/{device}/{ch1}"
    PFI_CH2 = f"/{device}/{ch2}"
    # Channel 2: ctr1 on PFI9
    daq=nidaqmx
    t_ch1=daq.Task()
    #t_ch1.channels.ci_count_edges_count_reset_reset_cnt()
    t_ch1.ci_channels.add_ci_count_edges_chan(
        counter=f"{device}/ctr0",
        edge=Edge.RISING,
        initial_count=0
    )
    t_ch1.ci_channels.all.ci_count_edges_term = PFI_CH1
    
    # Channel 2: ctr1 on PFI9
    t_ch2=daq.Task()
    t_ch2.ci_channels.add_ci_count_edges_chan(
        counter=f"{device}/ctr1",
        edge=Edge.RISING,
        initial_count=0
    )
    t_ch2.ci_channels.all.ci_count_edges_term = PFI_CH2
    print(f'Using MPD with DAQ')
    return daq, t_ch1, t_ch2 


def start_spectro(spectro_set_cw=484, shutter_init=True,waitfortemp=True,showrange=True):

    spectro = instruments.andor_kymera()
    commands.set(spectro.wavelength_nm, spectro_set_cw)
    time.sleep(1)
    camera = instruments.andor_iDus(spectro_instr=spectro,cooler_temp=-80,shutter_init=shutter_init)
    time.sleep(5)
    camera.conf(read_mode='full_vertical_binning',exposure_time=5,acq_mode="accumulate", acc_N=2)
    commands.set(camera.cosmic_filter_en, True)
    vbg=None
    if waitfortemp:
        camera.wait_for_cooler_stable(-80)
    minw = int(commands.get(spectro.sensor_wavelengths_nm)[0])
    maxw = int(commands.get(spectro.sensor_wavelengths_nm)[-1])
    if showrange:
        print(f"Current wavelength range : {minw}nm to {maxw}nm")
    return spectro, camera  
      
def close_spectro(spectro=None,camera=None):
    if camera is not None:
        unload(camera)
    if spectro is not None:
        unload(spectro)



def set_spectrum(
    camera=None,
    spectro=None,
    wl=None,
    grating=2,
    exposure_time=5,
    acq_mode="accumulate",
    acc_N=2,
    cosmic_filter=True,
):
  if spectro is not None and wl is not None:
    commands.set(spectro.active_grating, int(grating))
    commands.set(spectro.wavelength_nm, int(wl))
    minw = int(commands.get(spectro.sensor_wavelengths_nm)[0])
    maxw = int(commands.get(spectro.sensor_wavelengths_nm)[-1])
    print(f"Current wavelength range : {minw}nm to {maxw}nm")

  # Configure camera settings if provided
  if camera is not None:
    conf_args = {
        "read_mode": "full_vertical_binning",
        "exposure_time": exposure_time,
        "acq_mode": acq_mode,
    }
    if acq_mode == "accumulate" and acc_N is not None:
      conf_args["acc_N"] = acc_N

    camera.conf(**conf_args)
    commands.set(camera.cosmic_filter_en, cosmic_filter)
    print(camera.conf())





