
def normalize_lines(lines, original_y):
    for filepath, line in lines.items():
        y=original_y[filepath]
        if y.max() != 0 and line.get_ydata().max()!=1:
            line.set_ydata(y / y.max())
        else:
            line.set_ydata(y)