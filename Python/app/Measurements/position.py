import time


try: from amc_api_python import AMC
except ImportError as e: print(e)

def start_attocube(amc_address='amc100num-a01-0248.local',showcmd=False):
    """
    Initializes and connects to an AMC positioner.
    Args:
        amc_address (str): The network address of the AMC controller.
    Returns:
        AMC.Device or None: The connected AMC device object on success, 
                            otherwise returns None on failure.
    """
    amc = None
    try:
        # --- AMC Positioner Init ---
        amc = AMC.Device(amc_address)
        amc.connect()
        
        # Configure axes for control and movement
        for axis in [0, 1, 2]:
            amc.control.setControlOutput(axis, True)
            amc.control.setControlMove(axis, True)
            
        if showcmd: 
            print(f"Using AMC : {amc_address}")
        # Return the connected device object so it can be used later
        return amc
    

    except Exception as e:
        print(f"ERROR: Failed to connect or initialize AMC controller: {e}")
        # Clean up by closing the connection if an error occurs
        if amc:
            amc.close()
        return None
    
def amc_disable():
    amc= start_attocube()
    for axis in [0, 1, 2]:
        #amc.control.setControlOutput(axis, False)
        amc.control.setControlMove(axis, False)
        print(f"Disabled: Axis {axis}")
    amc.close()



def wait_until_stable(amc_dev, axis):
    """Waits for the specified AMC axis to become stable."""
    timeout = 10
    start = time.time()
    while True:
        if amc_dev.status.getStatusMoving(axis) == 0 and \
            amc_dev.status.getStatusTargetRange(axis):
            break
        amc_dev.control.setControlOutput(axis, True)
        amc_dev.control.setControlMove(axis, True)
        if time.time() - start > timeout:
            print(f"Timeout waiting for stage axis {axis}")
            break
        time.sleep(0.01)
        
        
def amc_move(amc=None, axis=None, d=None):
    if amc is None:
        amc = start_attocube()
    amc.move.setControlTargetPosition(axis, int(d * 1000));wait_until_stable(amc, axis)
    
def amc_movexyz(x,y,f,amc=None):
    if amc is None:
        amc = start_attocube()
    amc.move.setControlTargetPosition(0, int(x * 1000));wait_until_stable(amc, 0)
    amc.move.setControlTargetPosition(1, int(f * 1000));wait_until_stable(amc, 1)
    amc.move.setControlTargetPosition(2, int(y * 1000));wait_until_stable(amc, 2)      
    
def gohome(amc=None):
    if amc is None:
        amc = start_attocube()
    for ax in [0,1,2]:
        amc_move(amc=amc,axis=ax,d=0)
