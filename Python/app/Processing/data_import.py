import time
t=time.time()
import numpy as np
print('imported np', time.time()-t)
t=time.time()
import os
print('imported os', time.time()-t)
t=time.time()
import pandas as pd
print('imported pd', time.time()-t)
t=time.time()
import re
print('imported re', time.time()-t)
t=time.time()
from lmfit import Model, Parameters, models
print('imported lmfit', time.time()-t)
t=time.time()
from app.Processing.misc import header_extract
print('imported header_extract', time.time()-t)

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

class Data_Set_Import:

    def make_label(self,labels):
        if labels=="":
            return self.name
        labels = re.split(', ', labels)
        label=""
        for lab in labels:
            if hasattr(self,lab):
                label+=self.lab+", "
            else:
                label+=lab+", "
        return label[:-2]


    def import_data(self): # Imports data from file path, if spectrum, allows merging of multiple wavelength range
        # data_sets={}
        for scan_nb,file_path in enumerate(self.file_paths):
            # if self.file_type == 'spectre w/o bg' or self.file_type == 'spectre w/ bg':
            #     data_sets[f'set_{scan_nb}']=pd.read_csv(file_path,comment="#",sep="\t",encoding="latin-1",names=col_names[self.file_type]).fillna(0)
            # else:
                self.data=pd.read_csv(file_path,comment="#",sep="\t",encoding="latin-1",names=col_names[self.file_type]).fillna(0)
        # if self.file_type == 'spectre w/o bg' or self.file_type == 'spectre w/ bg':
        #     self.data_sets=data_sets
        #     self.data=merge_spectra(data_sets.values(),axis=col_merged[self.file_type])
        if self.measure_type=='spectrum':
            if 'nm' in self.data.columns:
                self.data['ev']=1239.8/self.data['nm']
            else:
                self.data['nm']=1239.8/self.data['ev']
        if 'count_raw' in self.data.columns:
            self.data['count']=self.data['count_raw']/self.int_time
        if 'count_cor_raw' in self.data.columns:
            self.data['count_cor']=self.data['count_cor_raw']/self.int_time
        if 'count1' in self.data.columns:
            self.data['count']=(self.data['count1']+self.data['count2'])/self.int_time
        

    
    def fit(self,fitOptions,graphOptions,fit_idx):
        self.data_fit={'xfit':0,'yfit':0,'yfit_init':0}
        self.fit_params=fit_data(self,fitOptions,graphOptions,fit_idx)
    
    def __init__(self,file_paths):
        # if type(file_paths)==str:
        #     file_paths=[file_paths]
        self.filepath = file_paths
        self.name=os.path.basename(file_paths[0])[:-4]
        if self.name.startswith('Data_'):
            self.name=self.name#[5:]
        if self.name.startswith('300gr-325nm_0-1pourcent_x74_10sx1_'):
            self.name=self.name[34:]
        if self.name.startswith('plmap_data_'):
            self.name=self.name[10:20]
        self.text = ""
        self.file_paths=file_paths
        for k, v in header_extract(file_paths[0]).items():
            setattr(self, k, v)
        self.import_data()
        if self.file_type=='Unknown':
                print("Unknown Data File Type for "+self.name)
    def __str__(self):
        return self.name
    def __repr__(self):
        return self.name
            


            



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
    print('---------------- ',df.measure_type,' #',df.number,'   ',df.name, 'fit done -----------------')
    return result.params











