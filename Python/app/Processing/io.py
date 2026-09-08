import json
from pathlib import Path
from datetime import datetime

from app.Processing.data_import import Data_Set_Import


def save_exp(plot_area_widget,filename = 'test'):
    filename += "    "+datetime.today().strftime('%Y-%m-%d %H-%M-%S')
    save_dict = {}
    if plot_area_widget.spectrum:
        attributes = ['xlim','ylim','title','vlines','hlines','yaxis','groups','x_lab','y_lab','labels','toggles']
        line = plot_area_widget.spectrum
        save_dict['spectrum'] = {'attributes':{}}
        for attr in attributes:
            save_dict['spectrum']['attributes'][attr] = getattr(line,attr,attr+'--- key error ---')
        save_dict['spectrum']['filepaths'] = list(line.lines.keys())
        
    if plot_area_widget.trpl:
        attributes = ['xlim','ylim','title','vlines','hlines','yaxis','x_lab','y_lab','labels','toggles']
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
        
    with open(Path('data','experiments',filename), 'w') as file:
        file.write(json.dumps(save_dict, indent = 4))
    

def load_exp(plot_area_widget,filename = "test    2026-09-08 14-20-41"):
    print('Loading experiment: ', filename)
    plot_area_widget.remove_all()
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
                plot_area_widget.main.selected_files.append(filepath)
                plot_area_widget.main.datasets[path] = dataset
                plot_area_widget.add(filepath,dataset)
            else:
                for group_path in experiment[lines]['attributes']['groups'][filepath]:
                    path = Path(group_path)
                    dataset = Data_Set_Import(path)
                    plot_area_widget.main.selected_files.append(group_path)
                    plot_area_widget.main.datasets[path] = dataset
                    plot_area_widget.add(group_path,dataset)
        # getattr(plot_area_widget,lines)._refresh_full()
        if lines =='spectrum':
            plot_area_widget.spectrum.update_groups()
        