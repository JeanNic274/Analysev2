import numpy as np
import os
import pandas as pd
import re
from scipy.interpolate import interp1d
from lmfit import Model, Parameters
from lmfit import models
import pathlib

col_names = {
    'Unknown' :                 [str(i) for i in range(20)],
    'spectre w/o bg' :          ['pixel','nm','count_cor_raw'],
    'spectre w/ bg' :           ['pixel','nm','count_raw','countbg','count_cor_raw'],
    'map APD MH' :              ["x","detx","y","dety","count1","count2","count_raw"],
    'map APD DAQ' :             ["x","detx","y","dety","count1","count2","count_raw"],
    'plmap' :                   ["x","y","detx","dety","count1","count2","count_raw"],
    'focus scan MH' :           ["f","detf","count1","count2","count_raw"],
    'focus scan DAQ' :          ["f","detf","count1","count2","count_raw"],
    'trpl APD MH' :             ["ns","count1","count2"],
    'polarisation spectre' :    ["deg","detdeg","pixel","max_count_raw","max_wl","count"],
    'polarisation APD' :        ["deg","detdeg","count1","count2","count_raw"],
    'spectre c2n' :             ["ev","count_cor","bugged_col"],
}
col_merged = {
    'spectre w/o bg':          ['count_cor_raw'],
    'spectre w/ bg' :          ['count_cor_raw','count_raw'],
}
def reset_idx():
    global idx_tracker
    idx_tracker={}
idx_tracker={}

class Data_Set_Import:

    def make_label(self,labels):
        if labels=="":
            return self.name
        labels = re.split(', ', labels)
        label=""
        for lab in labels:
            if lab in self.attrs:
                label+=self.attrs[lab]+", "
            else:
                label+=lab+", "
        return label[:-2]


    def import_data(self): # Imports data from file path, if spectrum, allows merging of multiple wavelength range
        data_sets={}
        for scan_nb,file_path in enumerate(self.file_paths):
            if self.attrs['file_type'] == 'spectre w/o bg' or self.attrs['file_type'] == 'spectre w/ bg':
                data_sets[f'set_{scan_nb}']=pd.read_csv(file_path,comment="#",sep="\t",encoding="latin-1",names=col_names[self.attrs['file_type']]).fillna(0)
            else:
                self.data=pd.read_csv(file_path,comment="#",sep="\t",encoding="latin-1",names=col_names[self.attrs['file_type']]).fillna(0)
        if self.attrs['file_type'] == 'spectre w/o bg' or self.attrs['file_type'] == 'spectre w/ bg':
            self.data_sets=data_sets
            self.data=merge_spectra(data_sets.values(),axis=col_merged[self.attrs['file_type']])
        if self.attrs['measure_type']=='spectrum':
            if 'nm' in self.data.columns:
                self.data['ev']=1239.8/self.data['nm']
            else:
                self.data['nm']=1239.8/self.data['ev']
        if 'count_raw' in self.data.columns:
            self.data['count']=self.data['count_raw']/self.attrs['int_time']
        if 'count_cor_raw' in self.data.columns:
            self.data['count_cor']=self.data['count_cor_raw']/self.attrs['int_time']
        if 'count1' in self.data.columns:
            self.data['count']=(self.data['count1']+self.data['count2'])/self.attrs['int_time']
        

    
    def fit(self,fitOptions,graphOptions,fit_idx):
        self.data_fit={'xfit':0,'yfit':0,'yfit_init':0}
        self.fit_params=fit_data(self,fitOptions,graphOptions,fit_idx)
        # if self.attrs['measure_type']=='spectrum':
        #     self.fit_params=fit_spectrum(self,fitOptions,graphOptions,fit_idx)
        # elif self.attrs['measure_type']=='trpl':
        #     self.fit_params=fit_trpl(self,fitOptions,graphOptions,fit_idx)
        # else:
        #     print('No fit model for ',self.attrs['measure_type'])
    
    def __init__(self,file_paths):
        # if type(file_paths)==str:
        #     file_paths=[file_paths]
        self.name=os.path.basename(file_paths[0])[:-4]
        if self.name.startswith('Data_'):
            self.name=self.name[5:]
        if self.name.startswith('300gr-325nm_0-1pourcent_x74_10sx1_'):
            self.name=self.name[34:]
        if self.name.startswith('plmap_data_'):
            self.name=self.name[10:20]
            
        self.file_paths=file_paths
        self.attrs={**header_extract(file_paths[0])}
        self.import_data()
        # print(self.attrs['file_type'])
        if self.attrs['file_type']=='Unknown':
                print("Unknown Data File Type for "+self.name)
    def __str__(self):
        return self.name
    def __repr__(self):
        return self.name
            

def merge_spectra(dfs,axis=['count_cor_raw','count_raw'],x_axis='nm',step=0.05):
    min_wl,max_wl=2000,0
    for df in dfs:
        min_wl = min(df['nm'].min(),min_wl) 
        max_wl = max(df['nm'].max(),max_wl) 

    target_wavelengths = np.arange(min_wl, max_wl, step) 
    target_df = pd.DataFrame({'nm':target_wavelengths})

    def interpolate_spectrum(df, target_wls,yaxis, kind='slinear'):
        f = interp1d(df[x_axis].values, df[yaxis].values, kind=kind, 
                    bounds_error=False, fill_value=np.nan)
        return pd.Series(f(target_wls))
    for df_nb,df in enumerate(dfs):
        target_df[f'{df_nb}'] = interpolate_spectrum(df, target_wavelengths,yaxis=axis[0])
        if len(axis)-1:
            target_df[f'{df_nb}_cor'] = interpolate_spectrum(df, target_wavelengths,yaxis=axis[1])

    target_df[axis[0]] = target_df[[f'{nb}' for nb in range(df_nb+1)]].mean(axis=1)
    if len(axis)-1:
        target_df[axis[1]] = target_df[[f'{nb}' for nb in range(df_nb+1)]].mean(axis=1)
        target_df['count_cor'] = target_df[[f'{nb}_cor' for nb in range(df_nb+1)]].mean(axis=1)

        final_spectrum = target_df[[x_axis,axis[0],axis[1]]]
    else:
        final_spectrum = target_df[[x_axis,axis[0]]]
    return final_spectrum 
                     
            
def header_extract(file_path,map=False):
    header=[]
    with open(file_path) as f:
        comment_lines=0
        for line in f:
            
            if line.startswith('#'):
                header.append(line)
                comment_lines+=1
                
            else:
                if line[:2].replace('.','',1).replace('-','',1).replace('E','',1).isdigit():
                    header.append(line)
                    break
    info={}
    info['file_type'],info['measure_type']=fetchtype(header)
    if info['measure_type'] in idx_tracker:
        print('idx_tracker',idx_tracker)
        idx_tracker[info['measure_type']]+=1
    else:
        idx_tracker[info['measure_type']]=1
    info['number'] = str(idx_tracker[info['measure_type']])
    
    if len(header)<10:
        info['int_time']=1
        return info
    
    
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
    
    
    if int_time>9999:
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
    file_type="Unknown"
    measure_type="Unknown"
    if len(header)<10:
        return 'plmap', 'maps'
    column=header[-2]
    if header[0][:10]=='#Acq. time':
        file_type='spectre c2n'
        measure_type='spectrum'
    if column[1:5]=="Idus":
        measure_type="spectrum"
        file_type="spectre"
        header_len=len(column)
        if header_len==157:
            with_bg=" w/ bg"
        elif header_len==94:
            with_bg=" w/o bg"
                
        file_type+=with_bg
    elif column[1:6]=="AttoX":
        measure_type="maps"
        if "Idus" in column:
            file_type="map spectre"
        elif 'MH15' in column:
            file_type="map APD MH"
            
        elif 'DAQ' in column:
            file_type="map APD DAQ"
    elif column[1:6]=="AttoF":
        measure_type="focus"
        if column[63:67]=='MH15' and column[5:10]=='Focus':
            file_type="focus scan MH"
            
        elif column[63:67]=='DAQ6'and column[5:10]=='Focus':
            file_type="focus scan DAQ"
        
    elif column[1:5]=="Thor":
        measure_type="polars"
        if 'MH150' in column:
            file_type="polarisation APD"
        elif 'Idus' in column:
            file_type="polarisation spectre"
    elif column[1:5]=="MH15":
        measure_type="trpl"
        file_type="trpl APD MH"
    return file_type,measure_type


def fit_data(df,parameters,graph,fit_idx):
    xaxis=graph['x_axis']
    axis=graph['axis']
    
    yfit=np.array(df.data.loc[(df.data[xaxis] >= parameters['p0'][fit_idx][0]) & (df.data[xaxis] <= parameters['p0'][fit_idx][1]), axis])
    xfit=np.array(df.data.loc[(df.data[xaxis] >= parameters['p0'][fit_idx][0]) & (df.data[xaxis] <= parameters['p0'][fit_idx][1]), xaxis])
    p0=parameters['p0'][fit_idx][2:]
    
    xfit0=0
    
    if parameters['fit_model']=='Gaussian':
        nb_func=len(p0)//3
        cstmodel=len(p0)%3
        s=['a{}_'.format(i) for i in range(1, nb_func)]
        model=models.GaussianModel(prefix="a0_")
        pars=Parameters()
        pars.add_many(
            ('a0_amplitude',p0[0],True,0,None),
            ('a0_center',p0[1],True,1,None),
            ('a0_sigma',p0[2],True,0,None),
            )
        for p_idx,pref in enumerate(s):
            model+=models.GaussianModel(prefix=pref)

            pars.add_many(
                (pref+"amplitude",p0[3*p_idx+3],True,0,None),
                (pref+'center',p0[3*p_idx+4],True,1,None),
                (pref+'sigma',p0[3*p_idx+5],True,0,None),
                )
    
    if parameters['fit_model']=='Lorentzian':
        nb_func=len(p0)//3
        cstmodel=len(p0)%3
        s=['a{}_'.format(i) for i in range(1, nb_func)]
        model=models.LorentzianModel(prefix="a0_")
        pars=Parameters()
        pars.add_many(
            ('a0_amplitude',p0[0],True,0,None),
            ('a0_center',p0[1],True,1,None),
            ('a0_sigma',p0[2],True,0,None),
            )
        for p_idx,pref in enumerate(s):
            model+=models.LorentzianModel(prefix=pref)

            pars.add_many(
                (pref+"amplitude",p0[3*p_idx+3],True,0,None),
                (pref+'center',p0[3*p_idx+4],True,1,None),
                (pref+'sigma',p0[3*p_idx+5],True,0,None),
                )
            
    if parameters['fit_model']=='PseudoVoigt':
        nb_func=len(p0)//4
        cstmodel=len(p0)%4
        s=['a{}_'.format(i) for i in range(1, nb_func)]
        model=models.PseudoVoigtModel(prefix="a0_")
        pars=Parameters()
        pars.add_many(
            ('a0_amplitude',p0[0],True,0,None),
            ('a0_center',p0[1],True,1,None),
            ('a0_sigma',p0[2],True,0,None),
            ('a0_fraction',p0[3],True,0,1),
            )
        for p_idx,pref in enumerate(s):
            model+=models.PseudoVoigtModel(prefix=pref)

            pars.add_many(
                (pref+"amplitude",p0[4*p_idx+4],True,0,None),
                (pref+'center',p0[4*p_idx+5],True,1,None),
                (pref+'sigma',p0[4*p_idx+6],True,0,None),
                (pref+'fraction',p0[4*p_idx+7],True,0,1),
                )
        
    if parameters['fit_model']=='Exponential':
        
        xfit-=parameters['p0'][fit_idx][0]
        xfit0=1
        
        nb_func=len(p0)//2
        cstmodel=len(p0)%2
        s=['a{}_'.format(i) for i in range(1, nb_func)]
        model=models.ExponentialModel(prefix="a0_")
        pars=Parameters()
        pars.add_many(
            ('a0_amplitude',p0[0],True,0,None),
            ('a0_decay',p0[1],True,0,None),
            )
        for p_idx,pref in enumerate(s):
            model+=models.ExponentialModel(prefix=pref)

            pars.add_many(
                (pref+"amplitude",p0[2*p_idx+3],True,0,None),
                (pref+'decay',p0[2*p_idx+4],True,0,None),
                )
    
    if parameters['fit_model']=='Stretched':
        
        xfit-=parameters['p0'][fit_idx][0]
        xfit0=1
        
        def StretchedExpModel(x,amplitude,decay,beta):
            return amplitude*((np.exp(-x/decay))**beta)
        cstmodel=len(p0)%3
        model=Model(StretchedExpModel)
        pars=Parameters()
        pars.add_many(
            ('amplitude',p0[0],True,0,None),
            ('decay',p0[1],True,0,None),
            ('beta',p0[2],True,0,1),
            )
        
            
    if cstmodel:
        model+=models.ConstantModel()
        pars.add('c',p0[-1],True,0,None)
    
    result = model.fit(yfit, pars, x=xfit,weights=1/np.sqrt(yfit))

    if xfit0:
        xfit+=parameters['p0'][fit_idx][0]

    print(result.fit_report(show_correl=0))
    df.data_fit['xfit']=xfit
    df.data_fit['yfit']=result.best_fit
    df.data_fit['yfit_init']=result.init_fit
    print('---------------- ',df.attrs['measure_type'],' #',df.attrs['number'],'   ',df.attrs['name'], 'fit done -----------------')
    return result.params




def meastxt(directory_path):
    files_type,csv_save=[],[]
    spectre,polarisation,carte,cartespec,lifetime,focus=[],[],[],[],[],[]
    # directory_path=os.path.join("Data","micro-PL",directory)
    directory_path=pathlib.Path(directory_path)
    
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
        pos, power="\t","\t"
        filename = os.fsdecode(file)
        int_time="1"
        # if filename.endswith(".txt") and filename.startswith("Data_") and "Req" not in filename:
        if filename.endswith(".txt") and filename.startswith(filestart) and "Req" not in filename:
            file_path=os.path.join(directory_path,filename)
            header=[]
            print(filename)
    
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
                    # print(filename, nb_data, column[1:5], column[125:129])
                    if column[1:5]=="Idus":
                        file_type="spectre"
                        header_len=len(column)
                        int_time=fetchinttime(header,file_type)
                        if header_len==157:
                            with_bg=" w/ bg"
                        elif header_len==94:
                            with_bg=" w/o bg"
                                
                        file_type+=with_bg
                    elif column[1:6]=="AttoX":
                        # print(header)
                        if column[125:129]=="Idus":
                            file_type="map spectre"
                            int_time=fetchinttime(header,file_type)
                        elif column[125:129]=='MH15':
                            file_type="map APD MH"
                            int_time=fetchinttime(header,file_type)
                            
                        elif column[125:129]=='DAQ6':
                            file_type="map APD DAQ"
                            int_time=fetchinttime(header,file_type)
                    elif column[1:6]=="AttoF":
                        if column[63:67]=='MH15' and column[5:10]=='Focus':
                            file_type="focus scan MH"
                            int_time=fetchinttime(header,file_type)
                            
                        elif column[63:67]=='DAQ6'and column[5:10]=='Focus':
                            file_type="focus scan DAQ"
                            int_time=fetchinttime(header,file_type)
                        
                    elif column[1:5]=="Thor":
                        file_type="polarisation"
                        int_time=fetchinttime(header,file_type+"MH")
                    elif column[1:5]=="MH15":
                        file_type="trpl APD MH"
                        int_time=fetchinttime(header,file_type)
                    elif column[1:5]==" x_r":
                        continue #???
                else:
                    file_type='Empty file'
                    print(filename + ' is empty.')
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
    print(len(files_type), "file types saved in "+directory_path.name+f" as {directory_path.name} measurements.txt'")
    return 0






