"""Shared typography, palette and signed labels for publication figures."""
import matplotlib

# Nature-style conventions after SciencePlots (garrettj403/SciencePlots, nature.mplstyle);
# colors from the ggsci NPG palette. No LaTeX dependency.
FONT = ['Arial', 'Helvetica', 'DejaVu Sans']
INK = '#000000'
MUTED = '#555555'
ZERO = '#8c8c8c'
BASELINE = '#3C5488'    # B1 / XGBoost (NPG navy)
MODEL = '#E64B35'       # S0 / GRU (NPG red)
BASELINE_LIGHT = '#A7B2C9'  # B1 secondary components, e.g. costs (NPG navy at 45% on white)
MODEL_LIGHT = '#F39B7F'     # S0 secondary components, e.g. costs (NPG salmon)
DIFF = '#4D4D4D'        # S0-B1 differences (neutral dark gray)
DIFF_LIGHT = '#8491B4'  # secondary non-model category (NPG gray-blue)
CATEGORY_A = '#7E6148'  # non-model contrast, first group (NPG brown)
CATEGORY_B = '#B09C85'  # non-model contrast, second group (NPG taupe)
GAIN = '#4DBBD5'        # gross edge (NPG cyan)
COST = '#F39B7F'        # half-spread costs (NPG salmon)
NET = '#4D4D4D'         # net result
LINEAR_LIGHT = '#AFE0EC'  # Linear secondary components (NPG cyan at 45% on white)
LINEAR = '#4DBBD5'      # Linear model (NPG cyan)
HISTGB = '#7E6148'      # HistGradientBoosting (NPG brown)
STOCKS = {'KGHM': '#7E6148', 'PEKAO': '#B09C85', 'PKNORLEN': '#4DBBD5', 'PKOBP': '#8491B4', 'PZU': '#91D1C2'}
COHORT_A = CATEGORY_A   # first cohort/period, e.g. Apr/Jun/Sep/Nov monthly
COHORT_B = CATEGORY_B   # second cohort/period, e.g. Dec 27–29 later check
WIDTH_DOUBLE = 7.2      # Nature double-column width, inches (183 mm)


def apply():
    """Apply the shared figure style without changing plotted data."""
    matplotlib.rcParams.update({
        'font.family': 'sans-serif', 'font.sans-serif': FONT, 'font.size': 8,
        'text.color': INK,
        'axes.titlesize': 8, 'axes.titleweight': 'normal',
        'axes.titlelocation': 'left', 'axes.titlecolor': INK,
        'axes.labelcolor': INK, 'axes.labelsize': 8,
        'xtick.color': INK, 'ytick.color': INK,
        'xtick.labelsize': 8, 'ytick.labelsize': 8, 'legend.fontsize': 8,
        'axes.linewidth': 0.5, 'axes.edgecolor': INK,
        'axes.spines.top': True, 'axes.spines.right': True,
        'axes.spines.left': True, 'axes.spines.bottom': True,
        'xtick.direction': 'in', 'ytick.direction': 'in',
        'xtick.top': True, 'ytick.right': True,
        'xtick.major.size': 3, 'ytick.major.size': 3,
        'xtick.major.width': 0.5, 'ytick.major.width': 0.5,
        'xtick.minor.size': 1.5, 'ytick.minor.size': 1.5,
        'xtick.minor.width': 0.5, 'ytick.minor.width': 0.5,
        'ytick.minor.visible': True, 'xtick.minor.visible': False,
        'axes.grid': False, 'axes.axisbelow': True,
        'lines.linewidth': 1.0, 'lines.markersize': 3,
        'legend.frameon': False, 'axes.unicode_minus': True,
        'text.usetex': False, 'mathtext.fontset': 'dejavusans',
        'figure.facecolor': 'white', 'savefig.dpi': 300,
    })


def panel_label(ax, letter):
    """Place a Nature-style panel letter outside the top-left axes corner."""
    ax.annotate(letter.lower(), xy=(0, 1), xycoords='axes fraction',
                xytext=(-14, 14), textcoords='offset points',
                ha='left', va='baseline', fontsize=9, weight='bold',
                color=INK, annotation_clip=False)


def fmt_signed(v, nd):
    """Format an explicit sign, using the typographic minus sign."""
    return f'{v:+.{nd}f}'.replace('-', '−')
