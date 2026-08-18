
import numpy as np

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
            
              
         