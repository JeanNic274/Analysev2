from matplotlib.colors import LinearSegmentedColormap, ListedColormap
import matplotlib.pyplot as plt

def wavelength_to_rgb(wavelength, gamma=0.8):

    '''This converts a given wavelength of light to an 
    approximate RGB color value. The wavelength must be given
    in nanometers in the range from 380 nm through 750 nm
    (789 THz through 400 THz).
    Based on code by Dan Bruton
    http://www.physics.sfasu.edu/astro/color/spectra.html
    '''

    wavelength = float(wavelength)
    if wavelength >= 380 and wavelength <= 440:
        attenuation = 0.3 + 0.7 * (wavelength - 380) / (440 - 380)
        R = ((-(wavelength - 440) / (440 - 380)) * attenuation) ** gamma
        G = 0.0
        B = (1.0 * attenuation) ** gamma
    elif wavelength >= 440 and wavelength <= 490:
        R = 0.0
        G = ((wavelength - 440) / (490 - 440)) ** gamma
        B = 1.0
    elif wavelength >= 490 and wavelength <= 510:
        R = 0.0
        G = 1.0
        B = (-(wavelength - 510) / (510 - 490)) ** gamma
    elif wavelength >= 510 and wavelength <= 580:
        R = ((wavelength - 510) / (580 - 510)) ** gamma
        G = 1.0
        B = 0.0
    elif wavelength >= 580 and wavelength <= 645:
        R = 1.0
        G = (-(wavelength - 645) / (645 - 580)) ** gamma
        B = 0.0
    elif wavelength >= 645 and wavelength <= 750:
        attenuation = 0.3 + 0.7 * (750 - wavelength) / (750 - 645)
        R = (1.0 * attenuation) ** gamma
        G = 0.0
        B = 0.0
    else:
        R = 0.0
        G = 0.0
        B = 0.0
    # R *= 255
    # G *= 255
    # B *= 255
    return (R, G, B)


# Define the colors and their positions (fractions of the 0.0 to 1.0 range).
# Positions must be monotonically increasing.
color_nodes = [
    (0.0, 'white'),   
    (0.02, 'blue'),     
    (0.3, 'lime'),   
    (0.55, 'yellow'),  
    (0.8, 'orange'),      
    (1.0, 'red')
] 

custom_low_counts = LinearSegmentedColormap.from_list(
    'CustomLC',
    color_nodes,       
    N=256              
)

plt.colormaps.register(custom_low_counts)


wavelength_colors = [
    (480, (0.0, 0.4, 1.0)),   # blue
    (500, (0.0, 0.8, 1.0)),   # cyan
    (520, (0.0, 1.0, 0.3)),   # green
    (540, (0.6, 1.0, 0.0)),   # yellow-green
    (560, (1.0, 1.0, 0.0)),   # yellow
    (580, (1.0, 0.6, 0.0)),   # orange
    (600, (1.0, 0.2, 0.0)),   # red-orange
]

# Normalize wavelength positions (0–1)
wavelength_min, wavelength_max = 480, 600
color_nodes = [
    ((wl - wavelength_min) / (wavelength_max - wavelength_min), color)
    for wl, color in wavelength_colors
]

# Create the colormap
spectrum_cmap = LinearSegmentedColormap.from_list("visible_480_600", color_nodes, N=256)

plt.colormaps.register(spectrum_cmap, force=True)


nm_to_rgb = [(i, wavelength_to_rgb(i)) for i in range(400,750,10)]

nm_to_rgb = [
    (400,'#8300b5'),   
    (450, '#0046ff'),   
    (500, '#00ff92'),   
    (550, '#a3ff00'),   
    (600, '#ffbe00'),   
    (650, '#ff0000'),   
    (650, '#ff0000'),   
    (750, '#a10000'),   
]


# Normalize wavelength positions (0–1)
wavelength_min, wavelength_max = 400, 750
color_nodes = [
    ((wl - wavelength_min) / (wavelength_max - wavelength_min), color)
    for wl, color in nm_to_rgb
]


# Create the colormap
visible_cmap = LinearSegmentedColormap.from_list("visible", color_nodes, N=256)

plt.colormaps.register(visible_cmap, force=True)

color_nodes_transp = [
    (0.0, (1,0,0,0)),   
    (1.0, (1,0,0,1))
] 

red_transp = LinearSegmentedColormap.from_list(
    'red_transp',
    color_nodes_transp,       
    N=256              
)

plt.colormaps.register(red_transp)


#------------ test cmap -------------#

# fig, ax = plt.subplots(figsize=(6, 1))
# fig.subplots_adjust(bottom=0.5)

# cb = plt.colorbar(
#     plt.cm.ScalarMappable(cmap=red_transp),
#     cax=ax,
#     orientation='horizontal',
#     label='Wavelength (nm)'
# )
# cb.set_ticks([0, 0.25, 0.5, 0.75, 1])
# cb.set_ticklabels(['400', '487.5', '575', '662.5', '750'])
# plt.show()





