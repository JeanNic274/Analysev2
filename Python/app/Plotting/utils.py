
def normalize_lines(lines, original_y):
    for filepath, line in lines.items():
        y=original_y[filepath]
        if y.max() != 0 and line.get_ydata().max()!=1:
            line.set_ydata(y / y.max())
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
    fig.suptitle(title)
       
         