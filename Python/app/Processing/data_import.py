import time
# t=time.time()
import numpy as np
from numpy.lib import recfunctions as rfn
# print('imported np', time.time()-t)
# t=time.time()
import os
# print('imported os', time.time()-t)
# t=time.time()
# from lmfit import Model, Parameters, models
# print('imported lmfit', time.time()-t)
# t=time.time()
from app.Processing.misc import header_extract
# print('imported header_extract', time.time()-t)

col_names = {
    'Unknown' :                 [str(i) for i in range(20)],
    'spectre w/o bg' :          ['pixel','nm','count_cor_raw'],
    'spectre w/ bg' :           ['pixel','nm','count_raw','countbg','count_cor_raw'],
    'map APD MH' :              ["x","detx","y","dety","count1_raw","count2_raw","count_raw"],
    'map APD DAQ' :             ["x","detx","y","dety","count1_raw","count2_raw","count_raw"],
    'plmap' :                   ["x","y","detx","dety","count1_raw","count2_raw","count_raw"],
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

    def import_data(self,file_path):
        
        self.data=np.genfromtxt(file_path,comments="#",delimiter="\t",encoding="latin-1",names=col_names[self.file_type])
        self.data = np.nan_to_num(self.data, nan=0)
    def init_data(self):
        new_names = []
        new_values = []
        if 'ev' in self.data.dtype.names:
            new_names.append('nm')
            new_values.append(1239.8/self.data['ev'])
        if 'count_raw' in self.data.dtype.names:
            new_names.append('count')
            new_values.append(self.data['count_raw'] / self.int_time)

        if 'count_cor_raw' in self.data.dtype.names:
            new_names.append('count_cor')
            new_values.append(self.data['count_cor_raw'] / self.int_time)
            
        if 'count1' in self.data.dtype.names:
            new_names.append('count')
            new_values.append((self.data['count1']+self.data['count2'])/self.int_time)

        if new_names:
            self.data = rfn.append_fields(
                self.data,
                new_names,
                new_values,
                usemask=False
            ) 

    
    def fit(self,graph,fit_idx):
        self.data_fit={'xfit':0,'yfit':0,'yfit_init':0}
        self.fit_result=fit_data(self,graph,fit_idx)
        self.fitted = True
    
    def __init__(self,file_path=0,attrs=None,dataset=None,name=None):
        # if type(file_paths)==str:
        #     file_paths=[file_paths]
        if file_path:
            self.name=os.path.basename(file_path)[:-4]
        else:
            self.name=name
        if self.name.startswith('Data_'):
            self.name=self.name#[5:]
        if self.name.startswith('300gr-325nm_0-1pourcent_x74_10sx1_'):
            self.name=self.name[34:]
        if self.name.startswith('plmap_data_'):
            self.name=self.name[10:20]
        if file_path:
            self.attrs=header_extract(file_path)
        elif attrs:
            self.attrs=attrs
            self.data=dataset
        else:
            print('Missing either filepath or attrs')
        for k, v in self.attrs.items():
            setattr(self, k, v)
        if file_path:
            self.import_data(file_path)
        if self.file_type=='Unknown':
                print("Unknown Data File Type for "+self.name)
        self.init_data()
                
    def __str__(self):
        return self.name
    def __repr__(self):
        return self.name
            


            



def fit_data(df,graph,fit_idx):
    parameters = graph.fit_params
    xaxis=graph.xaxis
    yaxis=graph.yaxis
    
    mask = ((df.data[xaxis] >= parameters['p0s'][fit_idx][0]) & (df.data[xaxis] <= parameters['p0s'][fit_idx][1]))
    yfit=df.data[yaxis][mask]
    xfit=df.data[xaxis][mask] + df.x_offset
    p0=parameters['p0s'][fit_idx][2:]
    
    xfit0=0
    
    t=time.time()
    print('-- importing lmfit --')
    from lmfit import Model, Parameters, models
    print('imported lmfit', time.time()-t)
    
    if parameters['model']=='Gaussian':
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
    
    if parameters['model']=='Cauchy':
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
            
    if parameters['model']=='PseudoVoigt':
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
        
    if parameters['model']=='Exponential':
        
        xfit-=parameters['p0s'][fit_idx][0]
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
    
    if parameters['model']=='Stretched':
        
        xfit-=parameters['p0s'][fit_idx][0]
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
        xfit+=parameters['p0s'][fit_idx][0]

    print(result.fit_report(show_correl=0))
    df.data_fit['xfit']=xfit
    df.data_fit['yfit']=result.best_fit
    df.data_fit['yfit_init']=result.init_fit
    print('---------------- ',df.measure_type,' #',df.number,'   ',df.name, 'fit done -----------------')
    return result.params











