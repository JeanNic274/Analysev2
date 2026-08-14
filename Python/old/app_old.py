from flask import Flask, render_template, jsonify, request
from pathlib import Path
import base64
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import io
from matplotlib.patches import Rectangle, Circle
import matplotlib.patheffects as path_effects
import matplotlib.colors as mcolors
from bokeh.plotting import figure, show
from bokeh.embed import json_item
from bokeh.models import LogAxis, LinearAxis, HoverTool, ColorBar, LogColorMapper, LinearColorMapper, CustomJSTransform, Range1d, CustomJSTicker, CustomJS, FixedTicker, CustomJSTickFormatter, Legend, Span
from bokeh.transform import linear_cmap
from bokeh.palettes import Viridis256, Set3_10, Bokeh8
import bokeh.io as bio
import itertools
import json
import os
import re
from selenium import webdriver
from Process import *
from datetime import datetime
import csv
import cmaps #Custom cmaps do not remove

#Default parameters
# New plot type : data_types, fig_layout (ctrl f _fig), color_palettes and index.html init params
def data_types_init():
    """Initializes data_types to default values at scipt start or user input

    Returns:
        dict: Dictionnary of all data_types with their default values
    """
    data_types={
        'spectrum':{ #Bokeh keys
            'x_axis':'nm',
            'axis':'count_cor',
            'axis_renorm':1,
            "top_axis_label":"Energy (eV)",
            "leg_loc":"top_right",
            'fig_layout' : {#"title": "Emission Spectrum" ,
                            "x_axis_label":"Wavelength (nm)",
                            "y_axis_label": "Counts/s",
                            "y_axis_type":"linear",
                            'background_fill_color':None,
                            'border_fill_color':None,
                            # 'x_range':None,
                            },
            'data':[],
        },
        
        'trpl':{ #Bokeh keys
            'x_axis':'ns',
            'axis':'count',
            'axis_renorm':0,
            "leg_loc":"top_right",
            'fig_layout' : {#"title": "Time Resolved Photoluminescence" ,
                            "x_axis_label": "Time (ns)",
                            "y_axis_label": "Counts/s",
                            "y_axis_type":"linear",
                            'background_fill_color':None,
                            'border_fill_color':None,
                            # 'x_range':None,
                            },
            'data':[],
            
        },
        'focus':{ #Bokeh keys
            'x_axis':'f',
            'axis':'count',
            'axis_renorm':0,
            "leg_loc":"top_right",
            'fig_layout' : {"title": "Focus Sweep" ,
                            "x_axis_label":"Focus (μm)",
                            "y_axis_label": "Counts/s",
                            "y_axis_type":"linear",
                            'background_fill_color':None,
                            'border_fill_color':None,
                            # 'x_range':None,
                            },
            'data':[],
        },
        'lineplot':{ #Bokeh keys
            'x_axis':'1',
            'axis':'2',
            "leg_loc":"top_right",
            'fig_layout' : {"title": "Line Plot" ,
                            "x_axis_label":"1",
                            "y_axis_label": "2",
                            "y_axis_type":"linear",
                            'background_fill_color':None,
                            'border_fill_color':None,
                            # 'x_range':None,
                            },
            'data':[],
        },
        
        
        'maps':{ #MPL keys
            'x_axis':'x',
            'y_axis':'y',
            'z_axis':'count',
            'fig_layout' : {#"title": "PL map" ,
                            "xlabel": "x (μm)",
                            "ylabel": "y (μm)",
                            "label": "Counts/s",
                            # 'xlim':[0,0],
                            # 'ylim':[0,0],
                            },
            'data':[],
            
        },
        
        
        'polars':{ #MPL keys
            'x_axis':'deg',
            'axis':'count',
            'factor':'1',
            'fig_layout' : {
                #"title": "Polarisation" ,
                "xlabel": 'Degree (°)',
                "ylabel": "Counts/s",
                # 'xlim':[0,0],
                # 'ylim':[0,0],
                            },
            'data':[],
            
        },
        
    }
    return data_types

data_types = data_types_init()
global_fit_parameters={} # Keep in memory to avoid recalculating fit if no change in parameters
data_sets={} # Keep in memeory to avoid re importing data sets if no change
global_curr_files=[]
global_curr_fit={}


def sort_key(filename):
    """Sorts key by number

    Args:
        filename (list): List of file names to be sorted

    Returns:
        list: Sorted list
    """
    numbers = re.findall(r'\d+', filename)
    return [int(n) for n in numbers]


def prevent_overwrite_file(filepath):
    """Prevents new file from overwriting existing file with same name. New file will keep its name and older file will have (n) at the end of their name.

    Args:
        filepath (path): New file's path

    """
    filepath = Path(filepath)

    if not filepath.exists(): # If no file with same name, exits
        return 0

    parent = filepath.parent # File parent directory
    stem = filepath.stem     # File name
    suffix = filepath.suffix # File suffix

    existing_versions = [] # Initialization of list of existing files with same name

    for f in parent.iterdir(): # Search for all files with same name and (n)
        if f.is_file():
            match = re.match(
                rf"^{re.escape(stem)} \((\d+)\){re.escape(suffix)}$",
                f.name
            )
            if match:
                existing_versions.append(int(match.group(1)))

    next_number = max(existing_versions, default=0) + 1 # New max n

    for number in range(next_number, 0, -1): # Rename every file to filename (n+1)
        old = parent / f"{stem} ({number}){suffix}"
        new = parent / f"{stem} ({number + 1}){suffix}"

        if old.exists():
            old.rename(new)

    filepath.rename(parent / f"{stem} (1){suffix}")




app = Flask(__name__)

@app.route("/")
def index(): # Initializes UI
    return render_template("index.html")


@app.route("/data_types_reset", methods=["POST"])
def data_types_reset():  # User input to reset data (mostly in case of bug to avoid reload)
    global data_types
    data_types=data_types_init()
    return data_types

@app.route("/fetchdata", methods=["POST"])
def fetch_data(files=0):
    """Imports data sets from user selected files

    Args:
        files (int, optional): Boolean to request file paths for first import. Defaults to 0.

    Returns:
        _type_: _description_
    """
    if not files: # Request files if not already in memory
        files = request.json.get("files", [])
    global data_sets
    reset_idx() # Reset files number index
    data_sets={}
    plot_type={}
    for file_path in files:
        
        data=Data_Set_Import(file_path)
        print('Fetched file[0]:',data.name)
        if data.attrs['measure_type'] not in data_sets: # Initialize new type of data to be plotted
            data_sets[data.attrs['measure_type']]=[]
            plot_type[data.attrs['measure_type']]=1
        data_sets[data.attrs['measure_type']].append(data)
    return jsonify(plot_type) # Return every types of plotted data (spectrum, trpl, maps, ...)



@app.route("/plot", methods=["POST"])
def plot():
    """
    Plots normal line dataset (spectrum, trpl, ...) with Bokeh

    :return: json dump for javascript
    """
    
    
    global global_fit_parameters
    global data_sets
    global global_curr_fit
    
    global_fit_parameters={}
    # User selected parameters sent from UI
    graphOptions    = request.json.get("graphOptions", [])
    fitOptions      = request.json.get("fitOptions", [])
    files           = request.json.get("files", [])
    
    if not data_sets: # Fetch data if not already in memory
        fetch_data(files)
    
    graphTypes=['spectrum','trpl','focus','lineplot'] # Types of graph plotted by this function (Bokeh, 2d lines)
    
    for graphType in graphOptions: # Setting graph parameters selected in UI
        if graphType not in graphTypes:
            continue
        if 'log' in graphOptions[graphType]: # Log scale
            if graphOptions[graphType]['log']:
                data_types[graphType]['fig_layout']['y_axis_type']='log'
            else:
                data_types[graphType]['fig_layout']['y_axis_type']='linear'
                
        if 'ev' in graphOptions[graphType]: # Spectrum eV/nm scale
            if graphOptions[graphType]['ev']:
                data_types[graphType]['x_axis']='ev'
                data_types[graphType]['fig_layout']['x_axis_label']='Energy (eV)'
                data_types[graphType]['top_axis_label']='Wavelength (nm)'
            else:
                data_types[graphType]['x_axis']='nm'
                data_types[graphType]['fig_layout']['x_axis_label']='Wavelength (nm)'
                data_types[graphType]['top_axis_label']='Energy (eV)'
                
        if 'axis_renorm' in graphOptions[graphType]: # Renormalize to 1
            if graphOptions[graphType]['axis_renorm']:
                data_types[graphType]['axis_renorm']=1
            else:
                data_types[graphType]['axis_renorm']=0
        if 'leg_loc' in graphOptions[graphType]: # Legend location
            data_types[graphType]['leg_loc']=graphOptions[graphType]['leg_loc']
    
    fig_layout = { #Initializes figure layouts
    'spectrum_fig' : figure(**data_types['spectrum']['fig_layout'],
        tools="box_zoom,pan,wheel_zoom,reset,save,hover",
        width=600, height=500
    ),
    'trpl_fig' : figure(**data_types['trpl']['fig_layout'],
        tools="box_zoom,pan,wheel_zoom,reset,save,hover",
        width=600, height=500
    ),
    'focus_fig' : figure(**data_types['focus']['fig_layout'],
        tools="box_zoom,pan,wheel_zoom,reset,save,hover",
        width=600, height=500
    ),
    'lineplot_fig' : figure(**data_types['lineplot']['fig_layout'],
        tools="box_zoom,pan,wheel_zoom,reset,save,hover",
        width=600, height=500
    ),
    }
    color_palettes = { # Default Bokeh color cycles
        'spectrum':itertools.cycle(Bokeh8),
        'trpl':itertools.cycle(Bokeh8),
        'focus':itertools.cycle(Bokeh8),
        'lineplot':itertools.cycle(Bokeh8),
    }
    
    
    
    fig_data = {}
    plots={}
    fit_idx={
        'trpl':0,
        'spectrum':0,
    }
    lines=[]
    for d_type in graphTypes:
        if d_type in data_sets:
            lines+=data_sets[d_type]
    for data in lines:
        if data.attrs['measure_type'] not in fig_data:
            fig_data[data.attrs['measure_type']]=fig_layout[data.attrs['measure_type']+"_fig"] # Initialize figure
            fig_data[data.attrs['measure_type']].xaxis.axis_label_text_font_style = "normal"
            fig_data[data.attrs['measure_type']].xaxis.axis_label_text_color = "black"
            fig_data[data.attrs['measure_type']].xaxis.major_label_text_color = "black"
            fig_data[data.attrs['measure_type']].yaxis.axis_label_text_font_style = "normal"
            fig_data[data.attrs['measure_type']].yaxis.axis_label_text_color = "black"
            fig_data[data.attrs['measure_type']].yaxis.major_label_text_color = "black"
            fig_data[data.attrs['measure_type']].toolbar.logo = None
            if data.attrs['measure_type']=='spectrum': # Second x axis for spectrum (eV/nm)
                nm_ticker = CustomJSTicker(major_code="""
                                            return ticks;
                                        """)
                
                nm_axis = LinearAxis(
                    axis_label=data_types['spectrum']['top_axis_label'],
                    ticker=fig_data[data.attrs['measure_type']].xaxis.ticker,  
                    axis_label_text_font_style="normal",
                    axis_label_text_color="black",
                    formatter=CustomJSTickFormatter(code="""
                            const span = Math.abs((1240/ticks[ticks.length - 1]) - (1240/ticks[0]));
                            let decimals;
                            if (span > 5)       decimals = 0;
                            else if (span > 0.5) decimals = 2;
                            else if (span > 0.05) decimals = 3;
                            else                 decimals = 4;
                            return (1240 / tick).toFixed(decimals);
                    """)
                )
                fig_data[data.attrs['measure_type']].add_layout(nm_axis, 'above')
                blank_axis=LinearAxis()
                fig_data[data.attrs['measure_type']].add_layout(blank_axis, 'right')
                
            # -------------------------------- spans ------------------------------------------ #
            if graphOptions[data.attrs['measure_type']]['spanx']:
                spanx=[float(i) for i in graphOptions[data.attrs['measure_type']]['spanx'].split(',')]
                for hline in spanx: 
                    fig_data[data.attrs['measure_type']].add_layout(Span(location=hline, dimension='width',
                line_color="#292929A8", line_width=1))
            if graphOptions[data.attrs['measure_type']]['spany']:
                spany=[float(i) for i in graphOptions[data.attrs['measure_type']]['spany'].split(',')]
                for vline in spany: 
                    fig_data[data.attrs['measure_type']].add_layout(Span(location=vline, dimension='height',
                line_color="#292929A8", line_width=1))
            
        # Fit data range filter
        if 'fit' in graphOptions[data.attrs['measure_type']]:
            if graphOptions[data.attrs['measure_type']]['fit']:
                ydata=np.array(data.data.loc[(data.data[data_types[data.attrs['measure_type']]['x_axis']] >= fitOptions[data.attrs['measure_type']]['p0'][fit_idx[data.attrs['measure_type']]][0]) & (data.data[data_types[data.attrs['measure_type']]['x_axis']] <= fitOptions[data.attrs['measure_type']]['p0'][fit_idx[data.attrs['measure_type']]][1]), data_types[data.attrs['measure_type']]['axis']])
                renorm_fact=ydata.max() if data_types[data.attrs['measure_type']]['axis_renorm'] else 1
        if 'fit' not in graphOptions[data.attrs['measure_type']] or not graphOptions[data.attrs['measure_type']]['fit']:
            if 'x_range' in data_types[data.attrs['measure_type']]['fig_layout']:
                x_data_plotted=np.array(data.data.loc[(data.data[data_types[data.attrs['measure_type']]['x_axis']] >= data_types[data.attrs['measure_type']]['fig_layout']['x_range'][0]) & (data.data[data_types[data.attrs['measure_type']]['x_axis']] <= data_types[data.attrs['measure_type']]['fig_layout']['x_range'][1]), data_types[data.attrs['measure_type']]['axis']])
                renorm_fact=(x_data_plotted.max() if data_types[data.attrs['measure_type']]['axis_renorm'] else 1)
            else:
                renorm_fact=(data.data[data_types[data.attrs['measure_type']]['axis']].max() if data_types[data.attrs['measure_type']]['axis_renorm'] else 1)
            
        # -------------------------------- line plot -------------------------------------- #
        graphOptions['labels'].append(data.name)
        fig_data[data.attrs['measure_type']].line( # Plots data
            data.data[data_types[data.attrs['measure_type']]['x_axis']],
            data.data[data_types[data.attrs['measure_type']]['axis']]/renorm_fact,
            legend_label=data.make_label((graphOptions['labels']).pop(0)),
            line_color=next(color_palettes[data.attrs['measure_type']]),
            line_width=1.5,
        )
        
        # Turn off default range padding
        if not 'x_range' in data_types[data.attrs['measure_type']]['fig_layout']:
            fig_data[data.attrs['measure_type']].x_range.range_padding = 0
        if not 'y_range' in data_types[data.attrs['measure_type']]['fig_layout']:
            fig_data[data.attrs['measure_type']].y_range.range_padding = 0
            
        # Legend location
        fig_data[data.attrs['measure_type']].legend.location = data_types[data.attrs['measure_type']]['leg_loc']
        
        # Draw fit results if applicable
        if 'fit' in graphOptions[data.attrs['measure_type']]:
            if graphOptions[data.attrs['measure_type']]['fit']:
                if fitOptions[data.attrs['measure_type']]['fit_legend']:
                    fit_init_line_kwargs={'legend_label':data.name+'_fit_init','line_color':'red','line_width':1.5}
                    fit_line_kwargs={'legend_label':data.name+'_fit','line_color':'black','line_width':1.5}
                else:
                    fit_init_line_kwargs={'line_color':'red','line_width':1.5}
                    fit_line_kwargs={'line_color':'black','line_width':1.5}
                
                if global_curr_fit!=fitOptions:
                    data.fit(fitOptions[data.attrs['measure_type']],graphOptions[data.attrs['measure_type']],fit_idx[data.attrs['measure_type']]) # Data fit call
                global_fit_parameters[data.name]=data.fit_params
                fit_idx[data.attrs['measure_type']]+=1
                fig_data[data.attrs['measure_type']].line(
                    data.data_fit['xfit'],
                    data.data_fit['yfit']/(data.data_fit['yfit'].max() if data_types[data.attrs['measure_type']]['axis_renorm'] else 1),
                    **fit_line_kwargs
                    )
                if fitOptions[data.attrs['measure_type']]['fit_init']:
                    fig_data[data.attrs['measure_type']].line(
                        data.data_fit['xfit'],
                        data.data_fit['yfit_init']/(data.data_fit['yfit_init'].max() if data_types[data.attrs['measure_type']]['axis_renorm'] else 1),
                        **fit_init_line_kwargs
                        )
            combined = {
                param: [global_fit_parameters[name][param].value for name in global_fit_parameters]
                for param in next(iter(global_fit_parameters.values()))
                        }
            print("\n")
            print("------------------  fit results  ------------------")
            for name in global_fit_parameters:
                print(name+' = [ '+',\t'.join(str(x) for x in global_fit_parameters[name].valuesdict().values())+" ]")
            print('\n')
            for param, values in combined.items():
                print(f"{param}\t= {values}")
              
    # Save graph through web (reallllly slow)      
    saving=0
    for graphType in graphTypes:
        if graphOptions[graphType]['save']:
            driver = webdriver.Firefox()
            saving=1
            break
    if saving:
        try:
            for graphType in graphTypes:
                if graphOptions[graphType]['save']:
                    fig_data[graphType].background_fill_color = None
                    fig_data[graphType].border_fill_color = None
                    fig_data[graphType].toolbar_location = None
                    save_path=Path(graphOptions['savedir']+"\\"+graphOptions[graphType]['save_p']['Name']+graphOptions[graphType]['save_p']['fmt'])
                    save_path.parent.absolute().mkdir(parents=True, exist_ok=True)
                    if graphOptions[graphType]['save_p']['fmt']=='.pdf' or graphOptions[graphType]['save_p']['fmt']=='.svg': 
                        prevent_overwrite_file(save_path.with_suffix('.svg'))        
                        print('Saved at: ',bio.export_svg(fig_data[graphType],filename=save_path.with_suffix('.svg'), webdriver=driver))               
                    elif graphOptions[graphType]['save_p']['fmt']=='.png':
                        prevent_overwrite_file(save_path.with_suffix('.png'))        
                        print('Saved at: ',bio.export_png(fig_data[graphType],filename=save_path.with_suffix('.png'),scale_factor=1 ,webdriver=driver))   
                        fig_data[graphType].toolbar_location = 'right'
        finally:         
            driver.quit()  # always runs
                
        # show(fig_data[data.attrs['measure_type']])
    global_curr_fit=fitOptions

    for key in fig_data: #jsonify to send to UI
        plots[key]=json_item(fig_data[key])    
    
    return json.dumps(plots)


@app.route("/plotmap", methods=["POST"])
def plot_map():
    """Plots 2d map with MPL.

    Returns:
        str: base64 encoded image
    """
    # User selected parameters sent from UI
    graphOptions = request.json.get("graphOptions", [])
    # Types of graphs
    graphTypes=['maps']
    
    # Check valid colormap
    if graphOptions['maps']['cmap'] not in plt.colormaps():
        print('cmap must be one of:\n',[c for c in plt.colormaps() if not c.endswith('_r')])
        print('Unknown cmap, defaults to viridis')
        graphOptions['maps']['cmap'] = 'viridis'
        
    circs = request.json.get("fitOptions", [])['maps'] # Circles
    global data_sets
    fig,ax=plt.subplots()
    xma,xmi,yma,ymi,zma,zmi=-np.inf,np.inf,-np.inf,np.inf,-np.inf,np.inf # Initialize max/min for x,y,z
    # print(maps[0][axis].max(),"at ",maps[0].loc[maps[0][axis].idxmax(), 'x'],maps[0].loc[maps[0][axis].idxmax(), 'y']) #Prints highest count pixel coordinates
    
    axis=data_types['maps']['z_axis'] 
    
    maps=[]
    for d_type in graphTypes:
        if d_type in data_sets:
            maps+=data_sets[d_type]
    for data in maps:
        axis='count'
        
        if "xlim" in data_types[data.attrs['measure_type']]['fig_layout'] and "ylim" in data_types[data.attrs['measure_type']]['fig_layout'] :
            z_data=np.array(data.data.loc[(data.data['x'] >= data_types[data.attrs['measure_type']]['fig_layout']['xlim'][0]) & 
                                          (data.data['x'] <= data_types[data.attrs['measure_type']]['fig_layout']['xlim'][1]) &
                                          (data.data['y'] >= data_types[data.attrs['measure_type']]['fig_layout']['ylim'][0]) &
                                          (data.data['y'] <= data_types[data.attrs['measure_type']]['fig_layout']['ylim'][1]) 
                                          , axis])
        elif "xlim" in data_types[data.attrs['measure_type']]['fig_layout']:
            z_data=np.array(data.data.loc[(data.data['x'] >= data_types[data.attrs['measure_type']]['fig_layout']['xlim'][0]) & 
                                          (data.data['x'] <= data_types[data.attrs['measure_type']]['fig_layout']['xlim'][1]), axis])
        elif "ylim" in data_types[data.attrs['measure_type']]['fig_layout']:
            z_data=np.array(data.data.loc[(data.data['y'] >= data_types[data.attrs['measure_type']]['fig_layout']['ylim'][0]) & 
                                          (data.data['y'] <= data_types[data.attrs['measure_type']]['fig_layout']['ylim'][1]), axis])
            
        if "xlim" in data_types[data.attrs['measure_type']]['fig_layout'] or "ylim" in data_types[data.attrs['measure_type']]['fig_layout'] :
            zma=max(z_data.max(),zma)
            zmi=min(z_data.min(),zmi)
        else:
            zma=max(data.data[axis].max(),zma)
            zmi=min(data.data[axis].min(),zmi)
            
    for graphType in graphTypes:
        if 'log' in graphOptions[graphType]: # Log scale
            if graphOptions[graphType]['log']:
                print(zmi,zma)
                norm=mcolors.LogNorm(zmi+1,zma)
            else:
                norm=mcolors.Normalize(zmi,zma)
        
    for data in maps: #Plots maps
        z_grid = data.data.pivot(index='y', columns='x', values=axis)
        x_unique = np.sort(data.data['x'].unique())
        y_unique = np.sort(data.data['y'].unique())
        pcolormesh=ax.pcolormesh(x_unique, y_unique, z_grid.values, shading='nearest', cmap=graphOptions[data.attrs['measure_type']]['cmap'],norm=norm,edgecolors='none',linewidth=0,rasterized=True)
        pcolormesh.set_edgecolor('face')
        
    dx,dy=0,0 # DEPRECATED moves circle's center to match sent coordinates
    
    if 'fit' in graphOptions[data.attrs['measure_type']]:
        if graphOptions[data.attrs['measure_type']]['fit']:
            for color_id,circ_coord in enumerate(circs['p0']):
                if circ_coord[2]>0:
                    circ_patch=Circle(([circ_coord[0]+dx,circ_coord[1]+dy]),circ_coord[2],fc=(0,0,0,0),ec='r',lw=2.5,clip_on=False)
                    
                    circ_patch_b1=Circle(([circ_coord[0]+dx,circ_coord[1]+dy]),1.05*circ_coord[2],fc=(0,0,0,0),ec='k',lw=2.5,clip_on=False)
                    
                    circ_patch_b2=Circle(([circ_coord[0]+dx,circ_coord[1]+dy]),0.95*circ_coord[2],fc=(0,0,0,0),ec='k',lw=2.5,clip_on=False)
                    
                    ax.add_patch(circ_patch_b1)
                    ax.add_patch(circ_patch_b2)
                    ax.add_patch(circ_patch)
                    
                    text=ax.text(circ_coord[0]+1*circ_coord[2],circ_coord[1]+1*circ_coord[2],f"{color_id+1}",color='r',fontsize=15)
                    
                    text.set_path_effects([path_effects.Stroke(linewidth=1, foreground='k'),path_effects.Normal()])
                
        
        
    plt.locator_params(nbins=5)
        
    ax.set_aspect('equal')
    fig.colorbar(pcolormesh,label=data_types[data.attrs['measure_type']]['fig_layout']['label'])
    # if "y_range" in data_types[data.attrs['measure_type']]['fig_layout']:
    #     data_types[data.attrs['measure_type']]['fig_layout']['ylim']=data_types[data.attrs['measure_type']]['fig_layout'].pop('y_range')
    # else:
    #     if 'ylim' in data_types[data.attrs['measure_type']]['fig_layout']:  
    #         del data_types[data.attrs['measure_type']]['fig_layout']['ylim']
    # if "x_range" in data_types[data.attrs['measure_type']]['fig_layout']:
    #     data_types[data.attrs['measure_type']]['fig_layout']['xlim']=data_types[data.attrs['measure_type']]['fig_layout'].pop('x_range')
    # else:
    #     if 'xlim' in data_types[data.attrs['measure_type']]['fig_layout']:  
    #         del data_types[data.attrs['measure_type']]['fig_layout']['xlim']
    ax.set(**data_types[data.attrs['measure_type']]['fig_layout'])

    plt.tight_layout()
    
    # Encode image into base64 and send to UI
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=115, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    
    for graphType in graphTypes:
        if graphOptions[graphType]['save']:
            save_path=Path(graphOptions['savedir']+"\\"+graphOptions[graphType]['save_p']['Name']+graphOptions[graphType]['save_p']['fmt'])
            save_path.parent.absolute().mkdir(parents=True, exist_ok=True)  
            prevent_overwrite_file(save_path)        
            if graphOptions[graphType]['save_p']['fmt']=='.png':
                fig.savefig(save_path.with_suffix('.png'), bbox_inches='tight',transparent=True)
                print('Saved at: ',save_path)   
    
    plt.close(fig)
    return jsonify({"maps": img_base64})


@app.route("/plotpolar", methods=["POST"])
def plot_polar():
    """Plots polar graph with MPL

    Returns:
        str: base64 encoded image
    """
    
    # User selected parameters sent from UI
    graphOptions = request.json.get("graphOptions", [])
    
    graphTypes=['polars']
    
    global data_sets
    fig,ax=plt.subplots()
    
    polars=[]
    for d_type in graphTypes:
        if d_type in data_sets:
            polars+=data_sets[d_type]
    axis='count'
        
    # Figure initialization
    fig = plt.figure(figsize=(12.8,4.8),dpi=100)
    gs = gridspec.GridSpec(1, 2)  # Top:2x, Bottom:1x

    # Left = polar plot
    ax1 = fig.add_subplot(gs[0], projection='polar')
    ax2 = fig.add_subplot(gs[1])

    for graphType in graphOptions:
        if graphType not in graphTypes:
            continue
        if 'log' in graphOptions[graphType]: # Log scale
            if graphOptions[graphType]['log']:
                ax1.set_yscale('log')
                ax2.set_yscale('log')
                
        if 'axis_renorm' in graphOptions[graphType]: # Renormalize to 1
            if graphOptions[graphType]['axis_renorm']:
                data_types[graphType]['axis_renorm']=1
            else:
                data_types[graphType]['axis_renorm']=0
        if 'leg_loc' in graphOptions[graphType]: # Legend location
            data_types[graphType]['leg_loc']=graphOptions[graphType]['leg_loc']
            
    for data in polars:
        if 'xlim' in data_types[data.attrs['measure_type']]['fig_layout']:
            x_data_plotted=np.array(data.data.loc[(data.data[data_types[data.attrs['measure_type']]['x_axis']] >= data_types[data.attrs['measure_type']]['fig_layout']['x_range'][0]) & (data.data[data_types[data.attrs['measure_type']]['x_axis']] <= data_types[data.attrs['measure_type']]['fig_layout']['x_range'][1]), data_types[data.attrs['measure_type']]['axis']])
            renorm_fact=(x_data_plotted.max() if data_types[data.attrs['measure_type']]['axis_renorm'] else 1)
        else:
            renorm_fact=(data.data[data_types[data.attrs['measure_type']]['axis']].max() if data_types[data.attrs['measure_type']]['axis_renorm'] else 1)
        ax1.scatter(
            float(graphOptions[data.attrs['measure_type']]['factor']) * data.data[data_types[data.attrs['measure_type']]['x_axis']]/(180/np.pi),
            data.data[data_types[data.attrs['measure_type']]['axis']]/renorm_fact,
            s=10,
            )
        ax2.plot(
            data.data[data_types[data.attrs['measure_type']]['x_axis']],
            data.data[data_types[data.attrs['measure_type']]['axis']]/renorm_fact,
            )

        
    ax1.set_aspect('equal')
        
    ax2.set(**data_types[data.attrs['measure_type']]['fig_layout'])        

    plt.tight_layout()
    
    # Encoding in base64 to send to UI
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=115, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    
    # Save graph
    for graphType in graphTypes:
        if graphOptions[graphType]['save']:
            save_path=Path(graphOptions['savedir']+"\\"+graphOptions[graphType]['save_p']['Name']+graphOptions[graphType]['save_p']['fmt'])
            save_path.parent.absolute().mkdir(parents=True, exist_ok=True)          
            prevent_overwrite_file(save_path)        
            if graphOptions[graphType]['save_p']['fmt']=='.png':
                fig.savefig(save_path.with_suffix('.png'), bbox_inches='tight',transparent=True)
                print('Saved at: ',save_path)   
    
    plt.close(fig)
    return jsonify({"polars": img_base64})


@app.route("/browse", methods=["POST"])
def browse():
    """File browser function for UI

    Returns:
        str: json of folders and files in directory
    """
    directory = request.json.get("directory", "C:\\")
    
    meas_file={}
    if not os.path.exists(directory):
        return jsonify({"error": "Directory not found"}), 404
    if Path(os.path.join(directory,Path(directory).name+' measurements.txt')).is_file():
        with open(os.path.join(directory,Path(directory).name+' measurements.txt'),'r') as csvfile:
            f=csv.reader(csvfile,delimiter='\t')
            next(f,None)
            for line in f:
                meas_file[str(line[0])]=line[1][0]
            csvfile.close()
    items = []
    for name in os.listdir(directory):
        if name.endswith(".dat") or "measurements." in name or name.endswith(".l6s") or name.endswith(".png") or name.endswith(".db"): # blacklisted file extensions
            continue
        full_path = os.path.join(directory, name)
        
        name=meas_file.get(name,'')+" "+name
        
        items.append({
            "name": name,
            "path": full_path,
            "is_dir": os.path.isdir(full_path)
        })

    dirs  = sorted([i for i in items if     i["is_dir"]], key=lambda x: sort_key(x["name"]), reverse=True) # sort directories by reversed alphabetical order
    files = sorted([i for i in items if not i["is_dir"]], key=lambda x: sort_key(x["name"]), reverse=False) # sort files by alphabetical order

    return jsonify({"items": dirs + files, "current": directory})


@app.route("/save_fit", methods=["POST"])
def save_fit(save_path=r"C:\\Users\\jnich\\OneDrive - USherbrooke\\Uni\\PhD\Data\\micro-PL\\fit"): # Save fitted parameters TODO: allow new save path
    """Save fit results to disk

    Args:
        save_path (path, optional): Path to folder. Defaults to r"C:\\Users\\jnich\\OneDrive - USherbrooke\\Uni\\PhD\\Data\\micro-PL\\fit".
    """
    fit_results=[]
    os.makedirs(save_path, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = os.path.join(save_path, f"fit results {timestamp}.txt")
    
    combined = {
            param: [global_fit_parameters[name][param].value for name in global_fit_parameters]
            for param in next(iter(global_fit_parameters.values()))
    }
    
    with open(filename, 'w') as f:
        for name in global_fit_parameters:
            f.write(name+' = [ '+',\t'.join(str(x) for x in global_fit_parameters[name].valuesdict().values())+" ]\n")
        f.write('\n')
        for param, values in combined.items():
            f.write(f"{param}\t= {values}\n")
    return "Saved"


@app.route("/setxrange", methods=["POST"])
def set_xrange(): 
    global data_types
    new_xrange = request.json.get("xrange", [])
    x_range=new_xrange['range'].split(',')
    key='x_range'
    if new_xrange['plotId']=='maps':
        key='xlim'
    if x_range ==['']:
        if key in data_types[new_xrange['plotId']]['fig_layout']:
            del data_types[new_xrange['plotId']]['fig_layout'][key]
    else:
        data_types[new_xrange['plotId']]['fig_layout'][key]=[float(i) for i in x_range]
    return ""


@app.route("/setyrange", methods=["POST"])
def set_yrange(): 
    global data_types
    new_yrange = request.json.get("yrange", [])
    y_range=new_yrange['range'].split(',')
    key='y_range'
    if new_yrange['plotId']=='maps':
        key='ylim'
    if y_range ==['']:
        if key in data_types[new_yrange['plotId']]['fig_layout']:
            del data_types[new_yrange['plotId']]['fig_layout'][key]
    else:
        data_types[new_yrange['plotId']]['fig_layout'][key]=[float(i) for i in y_range]
    return ""


@app.route("/settitle", methods=["POST"])
def set_title(): 
    global data_types
    new_title = request.json.get("title", [])
    data_types[new_title['plotId']]['fig_layout']['title']=new_title['title']
    return ""


@app.route('/saveexp', methods=['POST'])
def save_exp():
    payload = request.get_json()
    filename = payload['file_name']
    data = payload['data']
    file_path=os.path.join('Experiments',filename+datetime.now().strftime("%Y-%m-%d_%H-%M-%S")+'.json')
    with open(file_path, 'w') as f:
        json.dump(data, f)
    return jsonify({"success": True})


DEFAULT_FOLDER = "Experiments"

@app.route('/list_json', methods=['GET'])
def list_json():
    files = [f for f in os.listdir(DEFAULT_FOLDER) if f.endswith('.json')]
    return jsonify(files)

@app.route('/load_json', methods=['POST'])
def load_json():
    filename = request.get_json()['filename']
    filepath = os.path.join(DEFAULT_FOLDER, os.path.basename(filename))
    with open(filepath, 'r') as f:
        data = json.load(f)
    return jsonify(data)

@app.route('/gen_meastxt', methods=['POST'])
def gen_meastxt():
    directory = request.get_json()['directory']
    meastxt(directory)
    return jsonify(0)




if __name__ == "__main__":
    app.run(debug=True)