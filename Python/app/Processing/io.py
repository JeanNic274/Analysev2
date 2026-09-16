import json
import re
from pathlib import Path
from datetime import datetime

from app.Processing.data_import import Data_Set_Import

def save_exp(plot_area_widget,filename = 'test'):
    save_path = Path('data','experiments',filename)
    prevent_overwrite_file(save_path)
    save_dict = {}
    if plot_area_widget.spectrum:
        attributes = ['xlim','ylim','title','vlines','hlines','yaxis','groups','x_lab','y_lab','labels','toggles','fit_params']
        line = plot_area_widget.spectrum
        save_dict['spectrum'] = {'attributes':{}}
        for attr in attributes:
            save_dict['spectrum']['attributes'][attr] = getattr(line,attr,attr+'--- key error ---')
        save_dict['spectrum']['filepaths'] = list(line.lines.keys())
        
    if plot_area_widget.trpl:
        attributes = ['xlim','ylim','title','vlines','hlines','yaxis','x_lab','y_lab','labels','toggles','fit_params']
        line = plot_area_widget.trpl
        save_dict['trpl'] = {'attributes':{}}
        for attr in attributes:
            save_dict['trpl']['attributes'][attr] = getattr(line,attr,attr+'--- key error ---')
        save_dict['trpl']['filepaths'] = list(line.lines.keys())
        
    if plot_area_widget.maps:
        attributes = ['xlim','ylim','title','vlines','hlines','yaxis','x_lab','y_lab','labels','toggles']
        line = plot_area_widget.maps
        save_dict['maps'] = {'attributes':{}}
        for attr in attributes:
            save_dict['maps']['attributes'][attr] = getattr(line,attr,attr+'--- key error ---')
        save_dict['maps']['filepaths'] = list(line.lines.keys())
        
    with open(save_path, 'w') as file:
        file.write(json.dumps(save_dict, indent = 4))
    print('Saved experiment at: ', save_path)
    

def load_exp(plot_area_widget,plot_area_index,filename = "test    2026-09-08 14-20-41"):
    print('Loading experiment: ', filename)
    plot_area_widget.main.sidebar._clear_selection()
    
    with open(Path('data','experiments',filename), 'r') as file:
        experiment = json.load(file)
    
    for lines in experiment:
        plot_area_widget._get_or_create(lines)
        for attr in experiment[lines]['attributes']:
            setattr(getattr(plot_area_widget,lines),attr,experiment[lines]['attributes'][attr])
        for filepath in experiment[lines]['filepaths']:
            path=Path(filepath)
            if path.is_file():
                dataset = Data_Set_Import(path)
                plot_area_widget.main.selected_files[plot_area_index].append(filepath)
                plot_area_widget.main.datasets[filepath] = dataset
                plot_area_widget.manager.add(dataset)
                plot_area_widget.add(filepath,dataset,plot_now=False)
            else:
                for group_path in experiment[lines]['attributes']['groups'][filepath]:
                    path = Path(group_path)
                    dataset = Data_Set_Import(path)
                    plot_area_widget.main.selected_files[plot_area_index].append(group_path)
                    plot_area_widget.main.datasets[group_path] = dataset
                    plot_area_widget.manager.add(dataset)
                    plot_area_widget.add(group_path,dataset,plot_now=False)
        # getattr(plot_area_widget,lines)._refresh_full()
        if lines =='spectrum':
            plot_area_widget.spectrum.update_groups()
        else:
            getattr(plot_area_widget,lines)._refresh()
            
            

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
    
    
def save_figure_export(
    figure,
    filename,
    transp = True,
    width=6.4,
    height=4.8,
    dpi=200,
    font_size=10,
    legend_font_size=9,
):
    """
    Save an existing Matplotlib figure using a fixed export style.

    The original figure size and font sizes are restored afterwards.
    """
    filename = Path(filename)

    original_size = figure.get_size_inches().copy()

    text_sizes = {}

    for artist in figure.findobj(
        match=lambda artist: hasattr(artist, "get_fontsize")
    ):
        try:
            text_sizes[artist] = artist.get_fontsize()
        except Exception:
            pass

    try:

        figure.set_size_inches(
            width,
            height,
            forward=False
        )

        for artist in text_sizes:
            artist.set_fontsize(font_size)

        for ax in figure.axes:
            legend = ax.get_legend()
            if legend is not None:
                for text in legend.get_texts():
                    text.set_fontsize(legend_font_size)
        figure.savefig(
            filename,
            dpi=dpi,
            bbox_inches="tight",
            transparent = transp
        )

    finally:
        for artist, size in text_sizes.items():
            try:
                artist.set_fontsize(size)
            except Exception:
                pass
        figure.set_size_inches(
            original_size,
            forward=False
        )

        
def save_fit(graph,filename=""): 

    save_path = Path('data','fit results')
    save_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if filename =="":
        filename =  f"fit results {timestamp}.txt"
    else:
        filename+=".txt"
    save_file = Path(save_path,filename)
    prevent_overwrite_file(save_file)
    
    
  
    combined = {
            param: [graph.fit_params['fit_results'][name][param] for name in graph.fit_params['fit_results']]
            for param in next(iter(graph.fit_params['fit_results'].values()))
    }
    
    
    with open(save_file, 'w') as f:
        for name in graph.fit_params['fit_results']:
            pname = Path(name)
            f.write(pname.stem+' = [ '+',  \t'.join(str(x) for x in graph.fit_params['fit_results'][name].values())+"\t]\n")
        f.write('\n')
        for param, values in combined.items():
            while len(param)<10:
                param+=" "
            f.write(f"{param}  \t= {values}\n")

    print('Saved fit at: ', save_file)
           
        
        
        
        
        
        
        
        
        