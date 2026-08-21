
import numpy as np
import pandas as pd
import re
from scipy.interpolate import interp1d

def normalize_lines(lines, original_d,xlim=None,xaxis='count',yaxis='nm'):
    if not xlim:
        xlim=[-np.inf,np.inf]
    for filepath, line in lines.items():
        y=original_d[filepath][yaxis]
        y_cut=np.array(original_d[filepath].loc[(original_d[filepath][xaxis] >= xlim[0]) & (original_d[filepath][xaxis] <= xlim[1]), yaxis])
        if y_cut.max() != 0 and line.get_ydata().max()!=1:
            line.set_ydata(y / y_cut.max())
        else:
            line.set_ydata(y)
            
def evnm_swap(lines):
    for filepath, line in lines.items():
        line.set_xdata(1239.8/line.get_xdata())         
            
def fetch_label(data,labels):
    labels=data.text+labels
    if labels=="":
        return data.name
    labels = re.split(', ', labels)
    label=""
    for lab in labels:
        label+=getattr(data,lab,lab)+", "
    return label[:-2]

            
            
            
def set_fig_title(fig,title,df):
    if "," in title:
        titlec=title.split(', ')
        title=getattr(df,titlec[0],titlec[0])
        for attribut in titlec[1:]:
            title+=', '+getattr(df,attribut,attribut)
    else:
        title=getattr(df,title,title)
    fig.suptitle(title)
            
def set_ax_lim(ax,lim,x=False,y=False):
    if type(lim)==str:
        limits=[i for i in lim.split(',')]
    elif type(lim)==tuple:
        limits=lim
    if len(limits)==2:
        if limits[0]:
            lim=[float(limits[0]),float(limits[1])]
        else:
            lim=[None,float(limits[1])]
    else:
        lim=[float(limits[0]),None]
    if x:
        ax.set_xlim(lim)
    if y:
        ax.set_ylim(lim)
            
              
def merge_spectra(dfs,axis=['count','count_cor'],x_axis='nm',step=0.05):
    min_wl,max_wl=2000,0
    for df in dfs:
        min_wl = min(df.data['nm'].min(),min_wl) 
        max_wl = max(df.data['nm'].max(),max_wl) 

    target_wavelengths = np.arange(min_wl, max_wl, step) 
    target_df = pd.DataFrame({'nm':target_wavelengths})

    def interpolate_spectrum(df, target_wls,yaxis, kind='slinear'):
        f = interp1d(df[x_axis].values, df[yaxis].values, kind=kind, 
                    bounds_error=False, fill_value=np.nan)
        return pd.Series(f(target_wls))
    for df_nb,df in enumerate(dfs):
        target_df[f'{df_nb}'] = interpolate_spectrum(df.data, target_wavelengths,yaxis=axis[0])
        if len(axis)-1:
            target_df[f'{df_nb}_cor'] = interpolate_spectrum(df.data, target_wavelengths,yaxis=axis[1])

    target_df[axis[0]] = target_df[[f'{nb}' for nb in range(df_nb+1)]].mean(axis=1)
    if len(axis)>1:
        target_df[axis[0]] = target_df[[f'{nb}' for nb in range(df_nb+1)]].mean(axis=1)
        target_df[axis[1]] = target_df[[f'{nb}_cor' for nb in range(df_nb+1)]].mean(axis=1)

        final_spectrum = target_df[[x_axis,axis[0],axis[1]]]
    else:
        final_spectrum = target_df[[x_axis,axis[0]]]
    return final_spectrum 
                     