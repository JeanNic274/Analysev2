from pathlib import Path
import os
import re
import csv
import sys

from Python.config import WHITELIST_EXTENSIONS


class curve_number():
    def __init__(self):
        self.idx = {}
        
        
    def add(self,dataset):
        temp = self.idx.get(dataset.measure_type,[])
        temp.append(dataset)
        dataset.number = len(temp)
        self.idx[dataset.measure_type] = temp
    
    def remove(self,dataset):
        temp = self.idx.get(dataset.measure_type)
        if not temp:
            return
        index = int(dataset.number)-1
        if index >= len(temp):
            print('curve_number pop, index > len(list)')
            return
        temp.pop(index)
        for i in range(index,len(temp)):
            temp[i].number = i+1
    def _reset(self):
        self.idx={}


measure_type_index = {
    "#IdusCam.Pixel(Num)"       : "spectrum",
    "#AttoX.ReqPosition(um)"    : "maps",
    "#AttoY.ReqPosition(um)"    : "maps",
    "#AttoFocus.ReqPosition(um)": "focus",
    "#AttoZ.ReqPosition(um)"    : "focus",
    "#MH150.Time(ns)"           : "trpl",
    "#ThorKDC101.ReqPos(deg)"   : "polars",
}

def meastxt(directory_path):
    print('Generating measurements.txt file:')
    print("")
    files_type,csv_save=[],[]
    spectre,polarisation,carte,cartespec,lifetime,focus=[],[],[],[],[],[]
    # directory_path=os.path.join("Data","micro-PL",directory)
    directory_path=Path(directory_path)
    
    # Sort numerically for easier reading
    if directory_path.name[0:2]=="20":
        files_sorted = [p.name for p in sorted((p for p in directory_path.iterdir() if (p.name.startswith("plmap") and not p.name.endswith("f.txt"))),key=lambda p: tuple(map(int, p.stem.split('_')[-2:])))] #py
        filestart="plmap"
    else:
        files_sorted = [p.name for p in sorted((p for p in directory_path.iterdir() if (p.name.startswith("Data_") and not p.name.endswith("f.txt"))),key=lambda p: tuple(map(int, p.stem.split('_')[-2:])))]
        filestart="Data_"
    # print(files_sorted)
    for file in files_sorted:
        with_bg=" bg?"
        file_type="Undefined"
        filter= 'Not Found'
        int_time= '1'
        pos, power="\t","\t"
        filename = os.fsdecode(file)
        # if filename.endswith(".txt") and filename.startswith("Data_") and "Req" not in filename:
        if filename.endswith(".txt") and filename.startswith(filestart) and "Req" not in filename:
            file_path=os.path.join(directory_path,filename)
            header=[]
    
            with open(file_path) as f:
                comment_lines=0
                check_line=0
                for line in f:
                    
                    if line.startswith('#'):
                        column=line
                        header.append(line)
                        comment_lines+=1
                        
                    else:
                        if line[0].isdigit() or line[0]=='-':
                            header.append(line)
                            check_line=1
                            break
                        
                nb_data= sum(1 for _ in f)+check_line
                f.close()
                if nb_data>1:
                    power=fetchpower(header)
                    filter=fetchfilter(header)
                    pos=fetchpos(header)   
                    
                    col_names = header[-2].split("\t")
                    col_names = [s.strip() for s in col_names]
                    
                    measure_type = measure_type_index.get(col_names[0],"Unknown")
                    
                    n_col=len(col_names)
                    
                    if measure_type == "spectrum":
                        file_type="spectre"
                        with_bg = ""
                        if n_col==5:
                            with_bg=" w/ bg"
                        elif n_col==3:
                            with_bg=" w/o bg"
                                
                        file_type+=with_bg
                        
                    elif measure_type == "maps":
                        if "Idus" in col_names[4]:
                            file_type="map spectre"
                        elif 'MH15' in col_names[4]:
                            file_type="map APD MH"
                            
                        elif 'DAQ' in col_names[4]:
                            file_type="map APD DAQ"
                            
                    elif measure_type == "focus":
                        if 'MH15' in col_names[2]:
                            file_type="focus scan MH"
                            
                        elif 'DAQ' in col_names[2]:
                            file_type="focus scan DAQ"
                        
                    elif measure_type=="polars":
                        if 'MH15' in col_names[2]:
                            file_type="polarisation MH"
                        elif 'DAQ' in col_names[2]:
                            file_type="polarisation DAQ"
                            
                    elif measure_type=="trpl":
                        file_type="trpl APD MH"
                    elif column[1:5]==" x_r":
                        continue #???
                    int_time=fetchinttime(header,file_type)
                else:
                    file_type='Empty file'
                    sys.stdout.write("\r")
                    sys.stdout.flush()
                    print(filename + ' is empty.')
            sys.stdout.write("\r"+filename+' done.')
            sys.stdout.flush()
            if len(pos)<10:
                pos+="    "
            if len(filter)<15:
                filter+="       "
                
            files_type.append(filename+"\t"+file_type+"\t"+str(nb_data)+"\t"+pos+"\t"+power + "\t" + filter+ "\t" +int_time)
    with open(os.path.join(directory_path,f'{directory_path.name} measurements.txt'), 'w') as f:
        f.write("#file \t\t\ttype \t\tsize \tpos (um) \t\tpower (W) \tfilter\t\t\tInt time(ms)\n")
        f.write('\n'.join(files_type))
        f.close()
        
    # dic={'bg_spectre':[],'spectre':spectre,'polarisation':polarisation,'map':carte,'lifetime':lifetime,'map_spec':cartespec,'focus':focus,'folder':directory}
    print('\n\n',f"\b{len(files_type)} file types saved in "+directory_path.name+f" as {directory_path.name} measurements.txt'")
    return 0


def header_extract(file_path,map=False):
    header=[]
    with open(file_path) as f:
        comment_lines=0
        check_line = 0
        for line in f:
            
            if line.startswith('#'):
                header.append(line)
                comment_lines+=1
                
            else:
                if line[:2].replace('.','',1).replace('-','',1).replace('E','',1).isdigit():
                    header.append(line)
                    check_line=1
                    break
                        
        nb_data = sum(1 for _ in f)+check_line
    info={}
    if nb_data<2:
        info['file_type'],info['measure_type']= 'Empty file','Empty file'
    else:
        info['file_type'],info['measure_type']=fetchtype(header)
    
    info['name']=os.path.basename(file_path)[:-4]
    if info['name'].startswith('Data_'):
        info['name']=info['name'][5:]
    if info['name'].startswith('300gr-325nm_0-1pourcent_x74_10sx1_'):
        info['name']=info['name'][34:]
    if info['name'].startswith('plmap_data'):
        info['name']=info['name'][10:20]
    
    col_name=''.join(header[-2:])
    if 'MH' in col_name:
        file_type='MH'
    elif 'DAQ' in col_name:
        file_type='DAQ'
    elif 'Idus' in col_name:
        file_type='spectre'
    elif '#Acq. time (s)' in header[0]:
        file_type='spectre c2n'
    else:
        file_type=0
    
    if map:
        info['pos'] = '( '+fetchmap(header)+' )'
    else:
        x,y,z=fetchpos(header).split(',')
        info['pos'] = '('+x+', '+y+')'
        info['posf'] = '('+x+', '+y+', '+z+')'

    power=fetchpower(header)
    info['power_raw']=power
    if power == 'Out of range':
        info['power'] = power
    else:
        power = float(power)
            
        if power < 1:
            info['power'] = f"{1e3 * power:.4}" + ' mW'
        if power < 1e-3:
            info['power'] = f"{1e6 * power:.4}" + r' μW'
        if power < 1e-6:
            info['power'] = f"{1e9 * power:.4}" + r' nW'
            
    info['filter'] = fetchfilter(header)
    info['x_offset'] = 0
    info['y_offset'] = 0
    info['cmap'] = 'viridis'
    info['text'] = ""
    info['skip_fit'] = False
    info['fitted'] = False
    if file_type:
        info['int_time'] = int(fetchinttime(header,file_type=file_type).replace(' ',''))/1000
    return info  


def fetchpos(header):
    pos="Not found,,"
    attox = next((line for line in header if line.startswith("#Instrument: AttoX") or line.startswith("##Instrument: AttoX")), None)
    attoy = next((line for line in header if line.startswith("#Instrument: AttoY")), None)
    
    attof = next((line for line in header if line.startswith("#Instrument: AttoF")), None)
    if attox and attoy and attof:
        matchx = re.search(r'Act\.Pos\(um\):\s*([-+]?\d*\.\d+|\d+)', attox)
        matchy = re.search(r'Act\.Pos\(um\):\s*([-+]?\d*\.\d+|\d+)', attoy)
        matchf = re.search(r'Act\.Pos\(um\):\s*([-+]?\d*\.\d+|\d+)', attof)

        if matchx and matchy:
            # print(type(matchx.group(1)))
            pos=matchx.group(1)[:-2]+', '+matchy.group(1)[:-2]+', '+matchf.group(1)[:-2]
    return pos

def fetchpower(header):
    power="Out of range"
    thor = next((line for line in header if line.startswith("#Instrument: ThorPM100A")), None)
    if thor:
        power_search = re.search(r'Act\s*Power:\s*([-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?)', thor)
        if power_search:
            power=power_search.group(1)
    return power

def fetchinttime(header,file_type):
    int_time="1"
    line=0
    if "DAQ" in file_type:
        line = next((line for line in header if line.startswith("#Instrument: DAQ6363")), None)#AcqTime(ms):
    if 'c2n' in file_type:
        line= next((line for line in header if line.startswith("#Acq. time (s)=")), None)
    elif "spectre" in file_type:
        line = next((line for line in header if line.startswith("#Instrument: IdusCam")), None)#Acq. Time(s):
    if "MH" in file_type:
        line = next((line for line in header if line.startswith("#Instrument: MH150")), None)#Acqu. Time (ms):

    if line:
        int_search = re.search(r'Acq(u)?\.?\s*Time\s*\((ms|s)\):\s*([-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?)', line)
        if not int_search:
            int_time=1000*int(''.join(filter(str.isdigit, line)))
        if int_search:
            if int_search.group(2)=="s":
                int_time=1000*int(float(int_search.group(3)))
                if int_time==0:
                    int_time=int(1000*(float(int_search.group(3))-0.0527))
            else:
                int_time=int(int_search.group(3))
    
    
    if int(int_time)>9999:
        int_time='{:,}'.format(int_time).replace(',', ' ') 
    else:
        int_time=str(int_time)
    return int_time

        
def fetchmap(header):
    pos=header[-1].split()
    x=str(int(float(pos[0])))
    y=str(int(float(pos[2])))
    z="N.A."
    attof = next((line for line in header if line.startswith("#Instrument: AttoF")), None)
    if attof:
        z = re.search(r'Act\.Pos\(um\):\s*([-+]?\d*\.\d+|\d+)', attof)
    
    return "("+x+", "+y+", "+z+")"
         
def fetchfilter(header):
    filter = 11 * ''

    wheel = next((line for line in header if line.startswith("#Instrument: FilterWheel")), None)
    
    if wheel:
        filter_search = re.search(r'Filter\s*Desc:\s*([^\s;]+)', wheel)
        if filter_search:
            filter=filter_search.group(1)
    
    return filter



def fetchtype(header):
    col_names = header[-2].split("\t")
    col_names = [s.strip() for s in col_names]
    
    file_type="Unknown"
    measure_type = measure_type_index.get(col_names[0],"Unknown")
    if header[0][:12]=='# PL Mapping':
        file_type='plmap'
        measure_type='maps'
    if header[0][:10]=='#Acq. time':
        file_type='spectre c2n'
        measure_type='spectrum'
        
    
    n_col=len(col_names)
    
    if measure_type == "spectrum":
        file_type="spectre"
        with_bg = ""
        if n_col==5:
            with_bg=" w/ bg"
        elif n_col==3:
            with_bg=" w/o bg"
                
        file_type+=with_bg
        
    elif measure_type == "maps":
        if "Idus" in col_names[4]:
            file_type="map spectre"
        elif 'MH15' in col_names[4]:
            file_type="map APD MH"
            
        elif 'DAQ' in col_names[4]:
            file_type="map APD DAQ"
            
    elif measure_type == "focus":
        if 'MH15' in col_names[2]:
            file_type="focus scan MH"
            
        elif 'DAQ' in col_names[2]:
            file_type="focus scan DAQ"
        
    elif measure_type=="polars":
        if 'MH15' in col_names[2]:
            file_type="polarisation MH"
        elif 'DAQ' in col_names[2]:
            file_type="polarisation DAQ"
            
    elif measure_type=="trpl":
        file_type="trpl APD MH"
        
    return file_type,measure_type


    
def browse(directory="C:"):
    directory = Path(directory)
    
    meas_file={}
    if not directory.exists():
        print('404 error directory not found.')
        directory = Path("C:\\")
    if directory.joinpath(str(directory.name)+' measurements.txt').is_file():
        with open(directory.joinpath(str(directory.name)+' measurements.txt'),'r') as csvfile:
            f=csv.reader(csvfile,delimiter='\t')
            next(f,None)
            for line in f:
                meas_file[str(line[0])]=line[1][0]
            csvfile.close()
    items = []
    for name in directory.iterdir():
        if (name.suffix not in WHITELIST_EXTENSIONS or 'measurement' in name.name) and not name.is_dir(): # blacklisted file extensions
            continue
        
        name_type="📁 "+name.name if name.is_dir() else '📄'+meas_file.get(name.name,'')+"  "+name.name
        items.append({
            "name": name_type,
            "path": name,
            "is_dir": name.is_dir()
        })

    dirs  = sorted([i for i in items if     i["is_dir"]], key=lambda x: sort_key(x["name"]), reverse=True) # sort directories by reversed alphabetical order
    files = sorted([i for i in items if not i["is_dir"]], key=lambda x: sort_key(x["name"]), reverse=False) # sort files by alphabetical order

    # print(dirs+files)
    return dirs+files


def sort_key(filename):
    """Sorts key by number

    Args:
        filename (list): List of file names to be sorted

    Returns:
        list: Sorted list
    """
    numbers = re.findall(r'\d+', filename)
    return [int(n) for n in numbers]




