import numpy as np
import re
from scipy.interpolate import interp1d

def normalize_lines(lines,original_d,xlim=None,xaxis='nm',yaxis='count',toggle=1):
    if xlim is None:
        xlim = [-np.inf, np.inf]
    for filepath, line in lines.items():
        data = original_d[filepath]
        y = data[yaxis]
        mask = ((data[xaxis] >= xlim[0]) &(data[xaxis] <= xlim[1]))
        y_cut = y[mask]
        if y_cut.size == 0:
            continue
        if y_cut.max() != 0 and toggle:
            line.set_ydata(y / y_cut.max())
        else:
            line.set_ydata(y)
            
            
def offset_lines(GraphClass,xoffset=0,yoffset=0,xaxis='nm',yaxis='count'):
    for filepath, line in GraphClass.lines.items():
        data = GraphClass.original_d[filepath]
        y = data[yaxis]
        x = data[xaxis]
        line.set_ydata(y+(float(GraphClass.main.datasets[filepath].number)-1)*np.float64(yoffset))
        line.set_xdata(x+(float(GraphClass.main.datasets[filepath].number)-1)*np.float64(xoffset))
            
def evnm_swap(lines):
    for filepath, line in lines.items():
        line.set_xdata(1239.8/line.get_xdata())         
            
def fetch_label(data,labels='',toggles={}):
    labels=data.text+labels
    _check_if=0
    for (k,v) in toggles.items():
        if v:
            labels+=k+', '
            _check_if=1
    if _check_if:
        labels=labels[:-2]
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
            
def merge_spectra(dfs,axis=('count', 'count_cor'),x_axis='nm',step=0.05):
    dfs = list(dfs)

    if not dfs:
        return None

    min_wl = min(df.data[x_axis].min() for df in dfs)
    max_wl = max(df.data[x_axis].max() for df in dfs)

    target_wavelengths = np.arange(min_wl,max_wl,step)

    spectra = []
    spectra_cor = []

    for df in dfs:

        x = df.data[x_axis]
        y = df.data[axis[0]]

        f = interp1d(x,y,kind='slinear',bounds_error=False,fill_value=np.nan)

        spectra.append(f(target_wavelengths))

        if len(axis) > 1:

            y_cor = df.data[axis[1]]
            f_cor = interp1d(x,y_cor,kind='slinear',bounds_error=False,fill_value=np.nan)

            spectra_cor.append(f_cor(target_wavelengths))

    spectra = np.array(spectra)

    merged = np.nanmean(spectra,axis=0)

    if len(axis) > 1:

        spectra_cor = np.array(spectra_cor)
        merged_cor = np.nanmean(spectra_cor,axis=0)

        result = np.empty(
            len(target_wavelengths),
            dtype=[
                (x_axis, 'f8'),
                (axis[0], 'f8'),
                (axis[1], 'f8')
            ])

        result[x_axis] = target_wavelengths
        result[axis[0]] = merged
        result[axis[1]] = merged_cor

    else:

        result = np.empty(
            len(target_wavelengths),
            dtype=[
                (x_axis, 'f8'),
                (axis[0], 'f8')
            ])

        result[x_axis] = target_wavelengths
        result[axis[0]] = merged

    return result



import matplotlib.pyplot as plt


def save_figure_export(
    figure,
    filename,
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
            bbox_inches="tight"
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


          