"""Presentation-only layout for the archived aggregate figure renderers."""
import textwrap
from matplotlib.offsetbox import AnchoredOffsetbox, DrawingArea, HPacker, VPacker, TextArea
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
import figure_style as style


def finish(fig, path):
    """Arrange existing artists without changing their plotted quantities."""
    axes = [ax for ax in fig.axes if ax.get_label() != '<colorbar>']
    rows = max(ax.get_subplotspec().rowspan.stop for ax in axes)
    cols = max(ax.get_subplotspec().colspan.stop for ax in axes)
    categorical = path.name in {'event_time.png', 'paired_ic_delta.png', 'signal_sources.png', 'shuffle_controls.png', 'visible_costs.png'} or path.name.startswith(('01_', '02_', '03_', '04_'))
    event = path.name == 'event_time.png'
    height = 6.8 if rows > 1 else 4.7 if event else 4.1
    fig.set_layout_engine(None)
    fig.set_size_inches(style.WIDTH_DOUBLE, height)
    title = fig._suptitle.get_text() if fig._suptitle else ''
    if fig._suptitle:
        fig._suptitle.remove()
        fig._suptitle = None
    if not title and len(axes) == 1:
        title = axes[0].get_title() or axes[0].get_title(loc='left')
        axes[0].set_title('')
        axes[0].set_title('', loc='left')
    footnotes = []
    for text in list(fig.texts):
        footnotes.append(text.get_text())
        text.remove()
    entries = {}
    for i, ax in enumerate(axes):
        for text in list(ax.texts):
            if text.get_transform() == ax.transAxes and text.get_position()[1] < 0:
                footnotes.append(text.get_text())
                text.remove()
            elif text.get_gid() != 'model-heading':  # model headings keep their model color
                text.set_fontsize(8)
                text.set_color(style.NET)
        panel_title = ax.get_title() or ax.get_title(loc='left')
        ax.set_title('')
        ax.set_title(textwrap.fill(panel_title, 36 if cols == 2 else 28 if cols == 3 else 95),
                     loc='left', fontsize=8, weight='normal', pad=14)
        style.panel_label(ax, chr(97+i))
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(.5)
        ax.tick_params(direction='in', right=True, top=not categorical, labelsize=7 if event else 8)
        ax.xaxis.label.set_size(8)
        ax.yaxis.label.set_size(8)
        if cols == 3:
            ax.set_xlabel(textwrap.fill(ax.get_xlabel(), 25))
            ax.set_ylabel(textwrap.fill(ax.get_ylabel(), 31))
        handles, labels = ax.get_legend_handles_labels()
        for handle, label in zip(handles, labels):
            if label not in entries:
                if hasattr(handle, 'patches'):
                    handle = handle.patches[0]
                color = handle.get_color() if hasattr(handle, 'get_color') else handle.get_facecolor()
                if not isinstance(color, str) and hasattr(color, 'ndim') and color.ndim > 1:
                    color = color[0]
                entries[label] = (color, handle.get_linestyle() if isinstance(handle, Line2D) else None)
        if ax.get_legend():
            ax.get_legend().remove()
    for legend in list(fig.legends):
        legend.remove()
    fig.text(.035, .965, '\n'.join(textwrap.fill(line, 95) for line in title.split('\n')), ha='left', va='top', fontsize=10, weight='bold')
    if entries:
        packed = []
        for label, (color, line_style) in entries.items():
            square = DrawingArea(22 if line_style not in (None, 'None') else 6, 6, 0, 0)
            square.add_artist(Rectangle((0, 0), 6, 6, facecolor=color, edgecolor='none'))
            if line_style not in (None, 'None'):
                square.add_artist(Line2D([9, 22], [3, 3], color=color, linestyle=line_style, linewidth=1))
            packed.append(HPacker(children=[square, TextArea(label, textprops={'size':8, 'color':style.MUTED})], align='center', pad=0, sep=4))
        per_row = 3 if len(packed) > 4 else len(packed)
        key = VPacker(children=[HPacker(children=packed[j:j+per_row], align='center', pad=0, sep=18)
                                for j in range(0, len(packed), per_row)], align='left', pad=0, sep=5)
        fig.add_artist(AnchoredOffsetbox(loc='upper left', child=key, frameon=False,
                       bbox_to_anchor=(.035, .84), bbox_transform=fig.transFigure, borderpad=0, pad=0))
    bottom = .40 if event else .25 if footnotes else .18
    fig.subplots_adjust(left=.105, right=.97, bottom=bottom, top=.67 if entries else .77,
                        wspace=.48 if cols == 3 else .40, hspace=.75)
    # Keep the heatmap colorbar outside the last panel after resetting layout.
    for ax in fig.axes:
        if ax.get_label() == '<colorbar>':
            fig.subplots_adjust(right=.85, wspace=.16)
            for panel in axes[1:]:
                panel.tick_params(labelleft=False)
            ax.set_position([.88, bottom, .018, .67-bottom])
            ax.tick_params(labelsize=8)
            ax.yaxis.label.set_size(8)
    if footnotes:
        fig.text(.035, .10, '\n'.join(textwrap.fill(s, 112) for s in footnotes),
                 ha='left', va='top', fontsize=7, color=style.MUTED, linespacing=1.4)
    fig.savefig(path, dpi=300, facecolor='white', metadata={'Software': None})
