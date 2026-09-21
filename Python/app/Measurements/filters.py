import time
import serial


try: from pylablib.devices import Thorlabs
except ImportError as e: print(e)


def send_cmd(drive, command, delay=0.05):
    """Sends a command and reads the response, with a small safety delay."""
    drive.write(f"{command}\r".encode('ascii'))
    time.sleep(delay)
    return drive.read_until(b'\r').decode('ascii').strip()

def power_apds(drive, state):
    """Robust APD power toggle. Sends command twice to ensure it registers."""
    cmd = "IL1" if state else "IH1"
    send_cmd(drive, cmd)
    time.sleep(0.1)
    send_cmd(drive, cmd) # Double-send for hardware robustness

def power_whitelight(drive, state):
    """Toggles white light without accidentally triggering APD commands."""
    if state:
        send_cmd(drive, "IL2")
    else:
        send_cmd(drive, "IH2")

def seek_home_precise(drive):
    """Micro-steps to the sensor edge and sets it as absolute zero (SP0)."""
    send_cmd(drive, "SK")
    time.sleep(0.1)
    send_cmd(drive, "VE10.0")
    
    while True:
        bits = send_cmd(drive, "IS").replace("IS=", "")
        if len(bits) >= 4 and bits[3] == '0':
            break
        send_cmd(drive, "DI10")
        send_cmd(drive, "FL")
        time.sleep(0.01)
        
    send_cmd(drive, "SP0")
    time.sleep(0.1)

def filterwheel(slot, offset=11.224, home_first=False, apd_final_state=False, wlight_final_state=False):
    """Moves the filter wheel and returns a state dictionary."""
    if slot < 0 or slot > 14:
        return {"status": "Error", "msg": "Invalid slot"}
        
    target_steps = int(-(slot + offset) * 1400)
    
    try:
        with serial.Serial(port='COM4', baudrate=38400, timeout=1) as drive:
            # Power down sensitive equipment during move
            power_whitelight(drive, False)
            power_apds(drive, False)
            
            if home_first:
                seek_home_precise(drive)

            send_cmd(drive, "VE1.0") 
            send_cmd(drive, f"FP{target_steps}")
            
            time.sleep(0.2)
            while True:
                if "0009" in send_cmd(drive, "SC", delay=0.1):
                    break
            
            # Restore desired states after move
            power_apds(drive, apd_final_state)
            if not apd_final_state:
                power_whitelight(drive, wlight_final_state)
                
            return {
                "Slot": slot,
                "APD_Power": "ON" if apd_final_state else "OFF",
                "White_Light": "ON" if (wlight_final_state and not apd_final_state) else "OFF"
            }
            
    except serial.SerialException as e:
        print(f"Serial connection failed: {e}")
        return {"Slot": "Unknown", "APD_Power": "Unknown", "White_Light": "Unknown"}

def move_esp_axis(esp, axis, target_pos, axis_name, showcmd=False):
    """Smart polling function that moves an axis and waits exactly until it arrives."""
    try:
        if showcmd:
            print(f"{axis_name} axis moving to {target_pos}mm...")
        
        esp.write(f"{axis}PA{target_pos}")
        
        # Smart Polling Loop instead of time.sleep(5)
        timeout = 15.0 
        start_time = time.time()
        pos_now = 0.0
        
        while time.time() - start_time < timeout:
            response = esp.query(f"{axis}TP?").strip()
            if response:
                pos_now = float(response)
                # If we are within 0.01mm of target, we have arrived
                if abs(pos_now - target_pos) < 0.01:
                    break
            time.sleep(0.2) # Check 5 times a second
            
        if showcmd:
            print(f"{axis_name} axis arrived at: {pos_now} mm")
        return pos_now
        
    except Exception as e:
        print(f"ESP communication error on {axis_name}: {e}")
        return "Error"

def detector_switch(esp, moveto='camera', showcmd=False):
    targets = {'apd': 0.0, 'spectro': -49.0, 'camera': 47.5}
    if moveto not in targets: return "Invalid"
    return move_esp_axis(esp, axis=3, target_pos=targets[moveto], axis_name="Detection", showcmd=showcmd)

def filter_switch(esp, moveto='no', showcmd=False):
    targets = {'no': -24.0, 'n405': 0.0, 'n533': 25.0}
    if moveto not in targets: return "Invalid"
    return move_esp_axis(esp, axis=2, target_pos=targets[moveto], axis_name="Filter", showcmd=showcmd)


def start_kdc(SN="27257399", kdc=None, force=True):
    """
    Initializes and connects to a Thorlabs Kinesis Motor (rotation mount).
    
    Args:
        SN (str): Serial number of the motor. Defaults to "27257399".
        kdc (Thorlabs.KinesisMotor, optional): Existing KDC motor instance.
        force (bool): If True, forces the motor to home upon starting. Defaults to False.
        
    Returns:
        Thorlabs.KinesisMotor: The connected motor object.
    """
    if kdc is not None:
        return kdc
    else:
        try:
            kdc = Thorlabs.KinesisMotor(SN)
            kdc.open()
            print(f"Homing KDC motor SN: {SN}...")
            kdc.home(force=force)
            print(f"Connected to KDC motor SN: {SN}")
            return kdc
        except Exception as e:
            print(f"ERROR: Failed to connect to KDC motor: {e}")
            return None


def kdc_position_deg(kdc=None):
    """
    Reads the current position of the Thorlabs KDC rotation mount in degrees.
    
    Args:
        kdc (Thorlabs.KinesisMotor, optional): Existing KDC motor instance.
        
    Returns:
        float: Current position in degrees.
    """
    kdc_local = False
    if kdc is None:
        kdc = start_kdc()
        kdc_local = True
        
    if kdc is None:
        print("ERROR: KDC motor is not initialized.")
        return 0.0

    current_steps = kdc.get_position()
    current_deg = current_steps / 1919.6418578623391
    
    if kdc_local and kdc:
        try:
            kdc.close()
        except Exception:
            pass
    return current_deg




def start_kdc(SN="27257399", kdc=None, force=False):
    if kdc is not None:
        return kdc
    else:
        try:
            kdc = Thorlabs.KinesisMotor(SN)
            kdc.open()
            if force:
                print(f"Homing KDC motor SN: {SN}...")
                # sync=False allows the script to continue running so we can poll
                kdc.home(force=True, sync=False) 
                time.sleep(0.2) # Give the motor a moment to start moving
                
                # Poll position while homing
                try:
                    while kdc.is_moving():
                        curr_deg = kdc.get_position() / 1919.6418578623391
                        print(f"Homing... Current Position: {curr_deg:.2f}°", end='\r')
                        time.sleep(0.05)
                    print("\nHoming complete.")
                except Exception:
                    # Fallback if is_moving behaves as a property
                    while getattr(kdc, 'is_moving', False):
                        curr_deg = kdc.get_position() / 1919.6418578623391
                        print(f"Homing... Current Position: {curr_deg:.2f}°", end='\r')
                        time.sleep(0.05)
                    print("\nHoming complete.")
                    
            print(f"Connected to KDC motor SN: {SN}")
            return kdc
        except Exception as e:
            print(f"ERROR: Failed to connect to KDC motor: {e}")
            return None



def kdc_move_deg(deg, kdc=None, showcmd=True):
    """
    Moves the Thorlabs KDC rotation mount to the specified angle in degrees.
    
    Args:
        deg (float): Target angle in degrees.
        kdc (Thorlabs.KinesisMotor, optional): Existing KDC motor instance.
        showcmd (bool): If True, prints polling status. If False, moves silently.
    """
    kdc_local = False
    if kdc is None:
        kdc = start_kdc()
        kdc_local = True
        
    if kdc is None:
        if showcmd: print("ERROR: KDC motor is not initialized.")
        return

    step = deg * 1919.6418578623391
    kdc.move_to(step)
    
    time.sleep(0.05)
    
    # Poll position while moving
    try:
        while kdc.is_moving():
            if showcmd:
                curr_deg = kdc.get_position() / 1919.6418578623391
                print(f"Moving... Current Angle: {curr_deg:.2f}° (Target: {deg:.2f}°)", end='\r')
            time.sleep(0.05)
            
        if showcmd:
            final_deg = kdc.get_position() / 1919.6418578623391
            print(f"\nMovement complete. Final Angle: {final_deg:.2f}°")
            
    except Exception:
        # Fallback if is_moving behaves as a property
        while getattr(kdc, 'is_moving', False):
            if showcmd:
                curr_deg = kdc.get_position() / 1919.6418578623391
                print(f"Moving... Current Angle: {curr_deg:.2f}° (Target: {deg:.2f}°)", end='\r')
            time.sleep(0.05)
            
        if showcmd:
            final_deg = kdc.get_position() / 1919.6418578623391
            print(f"\nMovement complete. Final Angle: {final_deg:.2f}°")

    if kdc_local and kdc:
        try:
            kdc.close()
        except Exception:
            pass

