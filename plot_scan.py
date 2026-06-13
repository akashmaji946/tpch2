import numpy as np
import matplotlib.pyplot as plt
import re
from pathlib import Path

# ============================================================
# Publication-quality settings
# ============================================================
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Helvetica', 'DejaVu Sans']
plt.rcParams['mathtext.fontset'] = 'stix'

plt.rcParams['axes.linewidth'] = 1.5
plt.rcParams['xtick.major.width'] = 1.5
plt.rcParams['ytick.major.width'] = 1.5
plt.rcParams['xtick.major.size'] = 7
plt.rcParams['ytick.major.size'] = 7

# ============================================================
# Data
# ============================================================
DATA_FILE = Path(__file__).with_name("scan_threads_50.txt")

THREAD_RE = re.compile(r"USE_RDB_PARALLEL_SCAN_THREADS=(\d+)")
RASTERDB_RE = re.compile(r"^\s*(Q\d+)\s+\S+.*?GPU OK \(\s*([0-9.]+)ms\)")


def load_rasterdb_times(path):
    current_thread = None
    thread_values = []
    query_values = {}

    for line in path.read_text().splitlines():
        thread_match = THREAD_RE.search(line)
        if thread_match:
            current_thread = int(thread_match.group(1))
            thread_values.append(current_thread)
            continue

        if current_thread is None:
            continue

        rasterdb_match = RASTERDB_RE.search(line)
        if rasterdb_match:
            query, time_ms = rasterdb_match.groups()
            query_values.setdefault(query, {})[current_thread] = float(time_ms)

    threads = sorted(dict.fromkeys(thread_values))
    data = {
        query: [values.get(thread, np.nan) for thread in threads]
        for query, values in query_values.items()
    }

    return threads, data


threads, data = load_rasterdb_times(DATA_FILE)
max_runtime = np.nanmax([time for times in data.values() for time in times])

# ============================================================
# Styling
# ============================================================
academic_colors = [
    '#1f77b4', '#e377c2', '#2ca02c', '#d62728',
    '#9467bd', '#8c564b', '#ff7f0e', '#17becf',
    '#bcbd22', '#7f7f7f', '#111111'
]

markers = ['o', '^', 's', 'D', 'v', 'p', '*', 'h', '<', '>', 'X']
linestyles = ['-', '--', '-.', ':']

# ============================================================
# FIGURE 1 : Runtime Plot
# ============================================================
fig1, ax1 = plt.subplots(figsize=(18, 18))

for i, (query, times) in enumerate(data.items()):
    ax1.plot(
        threads,
        times,
        marker=markers[i],
        linestyle=linestyles[i % len(linestyles)],
        color=academic_colors[i],
        linewidth=3.0,
        markersize=10,
        markeredgewidth=1.2,
        label=query
    )

ax1.set_xlabel(
    "Number of Scan Threads",
    fontsize=22,
    fontweight='bold'
)

ax1.set_ylabel(
    "Runtime (ms)",
    fontsize=22,
    fontweight='bold'
)

ax1.set_title(
    "RasterDB Runtime vs Scan Threads [SF=50]",
    fontsize=24,
    fontweight='bold',
    pad=15
)

ax1.set_xlim(0, 25)
ax1.set_xticks(threads)

runtime_tick_step = 1000
runtime_ymax = int(np.ceil(max_runtime / runtime_tick_step) * runtime_tick_step)
ax1.set_ylim(0, runtime_ymax)
runtime_ticks = np.arange(0, runtime_ymax + runtime_tick_step, runtime_tick_step)
ax1.set_yticks(runtime_ticks)

ax1.tick_params(
    axis='both',
    which='both',
    direction='in',
    top=True,
    right=True,
    labelsize=18,
    width=1.5,
    length=7
)

ax1.grid(
    True,
    which='both',
    linestyle=':',
    linewidth=0.8,
    alpha=0.7
)

ax1.legend(
    loc='upper right',
    fontsize=14,
    frameon=True,
    edgecolor='black',
    fancybox=False,
    ncol=2
)

for spine in ax1.spines.values():
    spine.set_linewidth(1.5)

ax1.set_box_aspect(0.75)

plt.tight_layout()

plt.savefig(
    "runtime_plot.png",
    dpi=300,
    bbox_inches='tight'
)

plt.show()

# ============================================================
# FIGURE 2 : Speedup Plot
# ============================================================
fig2, ax2 = plt.subplots(figsize=(16, 18))

for i, (query, times) in enumerate(data.items()):
    speedup = np.array(times[0]) / np.array(times)
    ax2.plot(
        threads,
        speedup,
        marker=markers[i],
        linestyle=linestyles[i % len(linestyles)],
        color=academic_colors[i],
        linewidth=3.0,
        markersize=10,
        markeredgewidth=1.2,
        label=query
    )

ax2.plot(
    [0, 25],
    [0, 25],
    color='black',
    linestyle=':',
    linewidth=2.5,
    label='Ideal Speedup'
)

ax2.set_xlabel(
    "Number of Scan Threads",
    fontsize=22,
    fontweight='bold'
)

ax2.set_ylabel(
    "Speedup",
    fontsize=22,
    fontweight='bold'
)

ax2.set_title(
    "Parallel Scaling Efficiency",
    fontsize=24,
    fontweight='bold',
    pad=15
)

ax2.set_xlim(0, 25)
ax2.set_ylim(0, 25)

ax2.set_xticks(threads)
ax2.set_yticks(np.arange(0, 26, 5))

ax2.tick_params(
    axis='both',
    which='both',
    direction='in',
    top=True,
    right=True,
    labelsize=18,
    width=1.5,
    length=7
)

ax2.grid(
    True,
    linestyle=':',
    linewidth=0.8,
    alpha=0.7
)

ax2.legend(
    loc='upper left',
    fontsize=14,
    frameon=True,
    edgecolor='black',
    fancybox=False,
    ncol=2
)

for spine in ax2.spines.values():
    spine.set_linewidth(1.5)

ax2.set_box_aspect(1.125)

plt.tight_layout()

plt.savefig(
    "speedup_plot.png",
    dpi=300,
    bbox_inches='tight'
)
