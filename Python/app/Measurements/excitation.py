from pyHegel.pyHegel import commands, instruments
from app.Measurements.devices import *


def set_laser(power=None, pulsed=False, laser=None, freq_khz=10000, softlock=False, engaged=True):
    """
    Controls and manages a Taiko laser connection.
    Automatically disables the softlock (softlock=False) to allow emission.
    
    Args:
        power (float, optional): Sets CW/Pulsed power as a percentage (0-100). Defaults to None.
        pulsed (bool): If True, sets to pulsed mode. If False, sets to CW mode. Defaults to False.
        laser (object, optional): Existing laser object. Defaults to None.
        freq_khz (float): Pulse frequency in kHz. Defaults to 20000.
        softlock (bool): Enables the software lock. Defaults to False (unlocked).
        engaged (bool): If True, returns the connection. If False, returns None.
    """
    if laser is None:
        try:
            laser = instruments.picoQuant.PicoQuant_Taiko_PDL_M1()
        except Exception as e:
            print(f"Failed to connect to laser: {e}")
            return None

    # === 1. Unlock Laser ===
    if softlock is not None:
        commands.set(laser.softlock_en, softlock)
        print(f"\nLaser softlock state : {commands.get(laser.softlock_en)}")

    # === 2. Apply Power & Mode Settings ===
    if power is not None:
        pwr_permille = int(power * 10) # Convert % to permille (0-1000)
        
        if pulsed:
            print("Setting Pulsed mode...")
            commands.set(laser.laser_mode, "pulsed")
            
            freq_hz = int(freq_khz * 1000)
            print(f"Setting Frequency to {freq_hz} Hz ({freq_khz} kHz)...")
            commands.set(laser.pulse_burst_freq_Hz, freq_hz)
            
            print(f"Setting power to {power}%...")
            commands.set(laser.pulse_burst_power_permille, pwr_permille)
            
        else:
            print("Setting CW mode...")
            commands.set(laser.laser_mode, "cw")
            
            print(f"Setting power to {power}%...")
            commands.set(laser.cw_power_permille, pwr_permille)
        close_device_all(laser=laser)


def get_laser(laser=None):
    """
    Queries and prints current Taiko laser parameters.
    
    Returns:
        tuple: (mode, cw_power_permille, cw_power_W, pulse_power_permille, pulse_power_W, freq_hz)
    """
    laser_local = False
    if laser is None:
        try:
            laser = instruments.picoQuant.PicoQuant_Taiko_PDL_M1()
            laser_local = True
        except Exception as e:
            print(f"Failed to connect to laser: {e}")
            return None

    try:
        mode = commands.get(laser.laser_mode)
        pwr_cw_p = commands.get(laser.cw_power_permille) / 10.0      # Converted to %
        pwr_cw_w = commands.get(laser.cw_power_W)
        hz = commands.get(laser.pulse_burst_freq_Hz)
        pwr_pulse_p = commands.get(laser.pulse_burst_power_permille) / 10.0 # Converted to %
        pwr_pulse_w = commands.get(laser.pulse_burst_power_W)
        
        print("\n--- Taiko Laser Status ---")
        print(f"  Mode           : {mode}")
        print(f"  CW Power       : {pwr_cw_p}% ({pwr_cw_w} W)")
        print(f"  Pulse Power    : {pwr_pulse_p}% ({pwr_pulse_w} W)")
        print(f"  Frequency      : {hz} Hz ({hz / 1e6} MHz)")
        print("-" * 28)

    finally:
        if laser_local and laser:
            close_device_all(laser=laser)
            
    return mode, pwr_cw_p, pwr_cw_w, pwr_pulse_p, pwr_pulse_w, hz


def set_laser_softlock(laser=None, engaged=True):
    """
    Safely zeroes the laser power and enables the software lock.
    """
    if laser is None:
        try:
            laser = instruments.picoQuant.PicoQuant_Taiko_PDL_M1()
        except Exception as e:
            print(f"Failed to connect to laser for softlocking: {e}")
            return None
            
    print("\nEnabling Laser Softlock (Zeroing power)...")
    commands.set(laser.cw_power_permille, 0)
    commands.set(laser.pulse_burst_power_permille, 0)
    commands.set(laser.softlock_en, True)
    close_device_all(laser=laser)
