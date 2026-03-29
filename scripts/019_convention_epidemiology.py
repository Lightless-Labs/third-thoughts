"""
Experiment 019: Convention Epidemiology
========================================
Apply epidemiological (SIR) modeling to trace how conventions spread
through the project portfolio. Fit SIR models, logistic adoption curves,
classify transmission mechanisms, and assess convention mortality.

NOTE: This script uses hardcoded convention adoption timeline data from
the Banade-a-Bonnot portfolio (original research data). It does not read
from the corpus directly -- it models that pre-collected data.

Adapted for Third Thoughts output directory.
"""

import json
import numpy as np
from scipy.integrate import odeint
from scipy.optimize import minimize, curve_fit
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from collections import OrderedDict
import os

OUTPUT_DIR = os.environ.get("MIDDENS_OUTPUT", "experiments/")

# ============================================================================
# DATA: Convention adoption timelines from diff-convention-propagation-waves.md
# ============================================================================

TOTAL_PROJECTS = 10

SSH_AUTH_SOCK_TIMELINE = OrderedDict([
    ("infinidash",       datetime(2026, 2, 19)),
    ("kumbaya",          datetime(2026, 2, 20)),
    ("phil-connors",     datetime(2026, 2, 22)),
    ("ten-a-day",        datetime(2026, 2, 23)),
    ("weatherby",        datetime(2026, 2, 24)),
    ("parsiweb-previews",datetime(2026, 3, 1)),
    ("JASONETTE-Reborn", datetime(2026, 3, 6)),
])

UUIDV7_TIMELINE = OrderedDict([
    ("phil-connors",     datetime(2026, 1, 31)),
    ("kumbaya",          datetime(2026, 1, 31)),
    ("ten-a-day",        datetime(2026, 1, 31)),
    ("weatherby",        datetime(2026, 2, 11)),
    ("ergon",            datetime(2026, 2, 27)),
    ("JASONETTE-Reborn", datetime(2026, 2, 28)),
    ("parsiweb-previews",datetime(2026, 3, 1)),
])

PROCESS_RULES_TIMELINE = OrderedDict([
    ("infinidash",       datetime(2026, 1, 28)),
    ("phil-connors",     datetime(2026, 1, 30)),
    ("ten-a-day",        datetime(2026, 1, 30)),
    ("converge-refinery",datetime(2026, 2, 11)),
    ("weatherby",        datetime(2026, 2, 11)),
    ("parsiweb-previews",datetime(2026, 3, 1)),
])

ADDENDUM_TIMELINE = OrderedDict([
    ("infinidash",       datetime(2026, 2, 7)),
    ("converge-refinery",datetime(2026, 2, 11)),
])

SEED_CONVENTIONS = OrderedDict([
    ("infinidash",       datetime(2026, 1, 24)),
    ("kumbaya",          datetime(2026, 1, 26)),
    ("ten-a-day",        datetime(2026, 1, 27)),
    ("phil-connors",     datetime(2026, 1, 28)),
    ("weatherby",        datetime(2026, 2, 11)),
    ("converge-refinery",datetime(2026, 2, 11)),
    ("ergon",            datetime(2026, 2, 27)),
    ("JASONETTE-Reborn", datetime(2026, 2, 28)),
    ("parsiweb-previews",datetime(2026, 3, 1)),
    ("pocket-claw",      datetime(2026, 2, 20)),
])


def days_from_origin(timeline):
    origin = min(timeline.values())
    days = []
    for project, date in timeline.items():
        days.append((date - origin).days)
    days.sort()
    counts = list(range(1, len(days) + 1))
    return np.array(days, dtype=float), np.array(counts, dtype=float), origin


# ============================================================================
# Analysis 1: SIR Model Fitting
# ============================================================================

def sir_model(y, t, beta, gamma, N):
    S, I, R = y
    dSdt = -beta * S * I / N
    dIdt = beta * S * I / N - gamma * I
    dRdt = gamma * I
    return [dSdt, dIdt, dRdt]


def fit_sir(timeline, N=TOTAL_PROJECTS, convention_name=""):
    days, cumulative, origin = days_from_origin(timeline)
    t_max = max(days) + 5
    t_span = np.linspace(0, t_max, 500)

    def sir_objective(params):
        beta, gamma = params
        if beta <= 0 or gamma <= 0 or beta > 10 or gamma > 10:
            return 1e10
        y0 = [N - 1, 1, 0]
        try:
            solution = odeint(sir_model, y0, t_span, args=(beta, gamma, N))
            S, I, R = solution.T
            cumulative_model = N - S
            model_at_data = np.interp(days, t_span, cumulative_model)
            return np.sum((cumulative - model_at_data) ** 2)
        except Exception:
            return 1e10

    best_result = None
    best_cost = 1e10
    for beta_init in [0.1, 0.3, 0.5, 1.0, 2.0]:
        for gamma_init in [0.1, 0.3, 0.5, 1.0, 2.0]:
            result = minimize(sir_objective, [beta_init, gamma_init],
                            method='Nelder-Mead',
                            options={'maxiter': 10000})
            if result.fun < best_cost:
                best_cost = result.fun
                best_result = result

    beta_fit, gamma_fit = best_result.x
    R0 = beta_fit / gamma_fit

    y0 = [N - 1, 1, 0]
    solution = odeint(sir_model, y0, t_span, args=(beta_fit, gamma_fit, N))
    S_fit, I_fit, R_fit = solution.T
    cumulative_fit = N - S_fit

    return {
        'convention': convention_name,
        'beta': beta_fit,
        'gamma': gamma_fit,
        'R0': R0,
        'N': N,
        'days': days,
        'cumulative': cumulative,
        'origin': origin,
        't_span': t_span,
        'S_fit': S_fit,
        'I_fit': I_fit,
        'R_fit': R_fit,
        'cumulative_fit': cumulative_fit,
        'residual': best_cost,
        'num_adopted': len(timeline),
        'total_days': max(days),
    }


# ============================================================================
# Analysis 2: Logistic S-curve Fitting
# ============================================================================

def logistic(t, L, k, t0):
    return L / (1 + np.exp(-k * (t - t0)))


def fit_logistic(timeline, convention_name=""):
    days, cumulative, origin = days_from_origin(timeline)
    L_max = len(timeline)

    try:
        popt, pcov = curve_fit(
            logistic, days, cumulative,
            p0=[L_max, 0.2, np.median(days)],
            bounds=([L_max * 0.5, 0.001, -10], [TOTAL_PROJECTS + 1, 5, max(days) + 50]),
            maxfev=10000
        )
        L, k, t0 = popt
        time_to_50 = t0
        t_plot = np.linspace(min(days) - 2, max(days) + 10, 300)
        y_plot = logistic(t_plot, L, k, t0)

        y_pred = logistic(days, L, k, t0)
        ss_res = np.sum((cumulative - y_pred) ** 2)
        ss_tot = np.sum((cumulative - np.mean(cumulative)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        return {
            'convention': convention_name,
            'L': L,
            'k': k,
            't0': t0,
            'r_squared': r_squared,
            'days': days,
            'cumulative': cumulative,
            'origin': origin,
            't_plot': t_plot,
            'y_plot': y_plot,
            'time_to_50_pct': time_to_50,
            'doubling_time': np.log(2) / k if k > 0 else float('inf'),
        }
    except Exception as e:
        return {
            'convention': convention_name,
            'error': str(e),
            'days': days,
            'cumulative': cumulative,
            'origin': origin,
        }


# ============================================================================
# Analysis 3: Transmission Mechanism Classification
# ============================================================================

def classify_transmissions():
    classifications = []

    ssh_events = [
        {'convention': 'SSH_AUTH_SOCK', 'project': 'infinidash', 'date': '2026-02-19',
         'mechanism': 'independent_emergence', 'evidence': 'Patient zero. Agent git push failed.',
         'vector': 'failure-driven discovery'},
        {'convention': 'SSH_AUTH_SOCK', 'project': 'kumbaya', 'date': '2026-02-20',
         'mechanism': 'active_transmission', 'evidence': 'Added 1 day after infinidash.',
         'vector': 'human copy-paste after same bug'},
        {'convention': 'SSH_AUTH_SOCK', 'project': 'phil-connors', 'date': '2026-02-22',
         'mechanism': 'active_transmission', 'evidence': 'Part of large docs rewrite.',
         'vector': 'human proactive docs update (batch propagation)'},
        {'convention': 'SSH_AUTH_SOCK', 'project': 'ten-a-day', 'date': '2026-02-23',
         'mechanism': 'independent_emergence', 'evidence': 'Uses $HOME/.ssh/agent.sock instead.',
         'vector': 'same bug, independently resolved'},
        {'convention': 'SSH_AUTH_SOCK', 'project': 'weatherby', 'date': '2026-02-24',
         'mechanism': 'active_transmission', 'evidence': 'Dedicated commit.',
         'vector': 'human deliberate propagation'},
        {'convention': 'SSH_AUTH_SOCK', 'project': 'parsiweb-previews', 'date': '2026-03-01',
         'mechanism': 'active_transmission', 'evidence': 'Baked into initial commit.',
         'vector': 'template inheritance (initial commit)'},
        {'convention': 'SSH_AUTH_SOCK', 'project': 'JASONETTE-Reborn', 'date': '2026-03-06',
         'mechanism': 'independent_emergence', 'evidence': 'Dedicated commit 15 days after origin.',
         'vector': 'same bug triggered in new project'},
    ]

    uuid_events = [
        {'convention': 'UUIDv7/URN', 'project': 'phil-connors', 'date': '2026-01-31',
         'mechanism': 'independent_emergence', 'evidence': 'Co-origin with kumbaya.',
         'vector': 'architectural decision during development'},
        {'convention': 'UUIDv7/URN', 'project': 'kumbaya', 'date': '2026-01-31',
         'mechanism': 'active_transmission', 'evidence': 'Same day as phil-connors.',
         'vector': 'human cross-pollination in same session'},
        {'convention': 'UUIDv7/URN', 'project': 'ten-a-day', 'date': '2026-01-31',
         'mechanism': 'active_transmission', 'evidence': 'Same day, uses infinidash:: prefix.',
         'vector': 'human copy-paste (same session, wrong prefix)'},
        {'convention': 'UUIDv7/URN', 'project': 'weatherby', 'date': '2026-02-11',
         'mechanism': 'active_transmission', 'evidence': 'Uses infinidash:: prefix.',
         'vector': 'template inheritance with stale prefix'},
        {'convention': 'UUIDv7/URN', 'project': 'ergon', 'date': '2026-02-27',
         'mechanism': 'active_transmission', 'evidence': 'Shortened form.',
         'vector': 'evolved copy-paste (simplified wording)'},
        {'convention': 'UUIDv7/URN', 'project': 'JASONETTE-Reborn', 'date': '2026-02-28',
         'mechanism': 'active_transmission', 'evidence': 'Same shortened form as ergon.',
         'vector': 'human copy-paste from sibling project'},
        {'convention': 'UUIDv7/URN', 'project': 'parsiweb-previews', 'date': '2026-03-01',
         'mechanism': 'active_transmission', 'evidence': 'Uses bab::phil-connors:: prefix.',
         'vector': 'copy-paste from wrong source project'},
    ]

    process_events = [
        {'convention': 'Process/Plan Rules', 'project': 'infinidash', 'date': '2026-01-28',
         'mechanism': 'independent_emergence', 'evidence': 'Patient zero. 5 rules.',
         'vector': 'original authoring'},
        {'convention': 'Process/Plan Rules', 'project': 'phil-connors', 'date': '2026-01-30',
         'mechanism': 'active_transmission', 'evidence': '5 rules identical.',
         'vector': 'human copy-paste'},
        {'convention': 'Process/Plan Rules', 'project': 'ten-a-day', 'date': '2026-01-30',
         'mechanism': 'active_transmission', 'evidence': '4 rules (missing sub-agents).',
         'vector': 'selective human copy-paste'},
        {'convention': 'Process/Plan Rules', 'project': 'converge-refinery', 'date': '2026-02-11',
         'mechanism': 'active_transmission', 'evidence': '6 rules with addendum.',
         'vector': 'template inheritance from up-to-date source'},
        {'convention': 'Process/Plan Rules', 'project': 'weatherby', 'date': '2026-02-11',
         'mechanism': 'active_transmission', 'evidence': '5 rules without addendum.',
         'vector': 'template inheritance from stale source'},
        {'convention': 'Process/Plan Rules', 'project': 'parsiweb-previews', 'date': '2026-03-01',
         'mechanism': 'active_transmission', 'evidence': '5 rules + 2 new iterative lines.',
         'vector': 'copy-paste with local innovation'},
    ]

    return ssh_events + uuid_events + process_events


# ============================================================================
# Analysis 4: Convention Mortality
# ============================================================================

def analyze_mortality():
    conventions_tracked = [
        {'name': 'ast-grep preference', 'first_seen': '2026-01-24',
         'projects_adopted': 10, 'projects_still_have': 9,
         'removed_from': ['Tempered-Wax'], 'reason': 'Swift ecosystem, ast-grep less relevant',
         'survival_rate': 9/10, 'status': 'alive (domain-specific attrition)'},
        {'name': 'Atomic commits', 'first_seen': '2026-01-24',
         'projects_adopted': 10, 'projects_still_have': 10,
         'removed_from': [], 'reason': None,
         'survival_rate': 1.0, 'status': 'alive (universal)'},
        {'name': 'TDD approach', 'first_seen': '2026-01-24',
         'projects_adopted': 10, 'projects_still_have': 10,
         'removed_from': [], 'reason': None,
         'survival_rate': 1.0, 'status': 'alive (universal)'},
        {'name': 'SSH_AUTH_SOCK', 'first_seen': '2026-02-19',
         'projects_adopted': 7, 'projects_still_have': 7,
         'removed_from': [], 'reason': None,
         'survival_rate': 1.0, 'status': 'alive (operational necessity)'},
        {'name': 'UUIDv7/URN', 'first_seen': '2026-01-31',
         'projects_adopted': 7, 'projects_still_have': 7,
         'removed_from': [], 'reason': None,
         'survival_rate': 1.0, 'status': 'alive (but mutated)'},
        {'name': 'Process/Plan lifecycle (5 rules)', 'first_seen': '2026-01-28',
         'projects_adopted': 6, 'projects_still_have': 6,
         'removed_from': [], 'reason': None,
         'survival_rate': 1.0, 'status': 'alive (universal)'},
        {'name': 'Addendum rule', 'first_seen': '2026-02-07',
         'projects_adopted': 2, 'projects_still_have': 2,
         'removed_from': [], 'reason': None,
         'survival_rate': 1.0, 'status': 'alive but failed to spread (R0 < 1)'},
        {'name': 'Hexagonal architecture / DDD', 'first_seen': '2026-01-28',
         'projects_adopted': 5, 'projects_still_have': 5,
         'removed_from': [], 'reason': None,
         'survival_rate': 1.0, 'status': 'alive (domain-specific)'},
        {'name': 'DynamoDB defensive rules', 'first_seen': '2026-03-08',
         'projects_adopted': 1, 'projects_still_have': 1,
         'removed_from': [], 'reason': None,
         'survival_rate': 1.0, 'status': 'alive but endemic'},
        {'name': 'Conventional Commits spec', 'first_seen': '2026-02-10',
         'projects_adopted': 3, 'projects_still_have': 3,
         'removed_from': [], 'reason': None,
         'survival_rate': 1.0, 'status': 'alive (limited adoption)'},
        {'name': 'ANTHROPIC_API_KEY env var', 'first_seen': '2026-01-30',
         'projects_adopted': 1, 'projects_still_have': 0,
         'removed_from': ['infinidash'],
         'reason': 'Replaced by CLAUDE_CODE_OAUTH_TOKEN',
         'survival_rate': 0.0, 'status': 'dead (superseded)'},
        {'name': 'Bazel-only build system', 'first_seen': '2026-01-25',
         'projects_adopted': 6, 'projects_still_have': 5,
         'removed_from': [], 'reason': 'Newer projects use Cargo only',
         'survival_rate': 5/6, 'status': 'alive but receding'},
    ]
    return conventions_tracked


# ============================================================================
# Plotting
# ============================================================================

def plot_sir_results(results_list):
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    colors = ['#e74c3c', '#3498db', '#2ecc71']

    for idx, (result, color) in enumerate(zip(results_list, colors)):
        ax = axes[idx]
        ax.plot(result['t_span'], result['S_fit'], '--', color='gray', alpha=0.6, label='S (susceptible)')
        ax.plot(result['t_span'], result['I_fit'], '-', color='orange', alpha=0.7, label='I (adopting)')
        ax.plot(result['t_span'], result['R_fit'], '-', color=color, alpha=0.7, label='R (established)')
        ax.plot(result['t_span'], result['cumulative_fit'], '-', color='black', alpha=0.4, label='Cumulative (model)')
        ax.scatter(result['days'], result['cumulative'], color=color, s=80, zorder=5,
                  edgecolors='black', linewidth=1, label='Observed adoptions')
        ax.set_title(f"{result['convention']}\n$R_0$ = {result['R0']:.2f}, "
                     f"$\\beta$ = {result['beta']:.3f}, $\\gamma$ = {result['gamma']:.3f}",
                     fontsize=11)
        ax.set_xlabel('Days from origin')
        ax.set_ylabel('Projects')
        ax.set_ylim(-0.5, TOTAL_PROJECTS + 1)
        ax.legend(fontsize=8, loc='right')
        ax.grid(True, alpha=0.3)

    plt.suptitle('SIR Model Fits for Convention Propagation', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '019-sir-model-fits.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Saved: 019-sir-model-fits.png")


def plot_adoption_curves(logistic_results):
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    colors = ['#e74c3c', '#3498db', '#2ecc71']

    for idx, (result, color) in enumerate(zip(logistic_results, colors)):
        ax = axes[idx]
        if 'error' in result:
            ax.set_title(f"{result['convention']}\n(Logistic fit failed: {result['error'][:40]})")
            ax.scatter(result['days'], result['cumulative'], color=color, s=80, zorder=5)
            continue

        ax.plot(result['t_plot'], result['y_plot'], '-', color=color, linewidth=2,
               label=f'Logistic fit ($R^2$ = {result["r_squared"]:.3f})')
        ax.scatter(result['days'], result['cumulative'], color=color, s=80, zorder=5,
                  edgecolors='black', linewidth=1, label='Observed')

        if 't0' in result:
            y_50 = result['L'] / 2
            ax.axhline(y=y_50, color='gray', linestyle=':', alpha=0.5)
            ax.axvline(x=result['t0'], color='gray', linestyle=':', alpha=0.5)
            ax.annotate(f'50% at day {result["t0"]:.1f}',
                       xy=(result['t0'], y_50), fontsize=9,
                       xytext=(result['t0'] + 2, y_50 + 0.5),
                       arrowprops=dict(arrowstyle='->', color='gray'))

        ax.set_title(f"{result['convention']}\nL={result['L']:.1f}, k={result['k']:.3f}, "
                     f"t_{{50%}}={result['t0']:.1f}d", fontsize=11)
        ax.set_xlabel('Days from origin')
        ax.set_ylabel('Cumulative adoptions')
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)

    plt.suptitle('Logistic S-curve Fits for Convention Adoption', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '019-adoption-curves.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Saved: 019-adoption-curves.png")


def plot_transmission_mechanisms(classifications):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    conventions = ['SSH_AUTH_SOCK', 'UUIDv7/URN', 'Process/Plan Rules']
    data = {}
    for conv in conventions:
        data[conv] = {'active_transmission': 0, 'independent_emergence': 0}
    for event in classifications:
        conv = event['convention']
        mech = event['mechanism']
        if conv in data:
            data[conv][mech] += 1

    ax = axes[0]
    x = np.arange(len(conventions))
    width = 0.5
    active = [data[c]['active_transmission'] for c in conventions]
    independent = [data[c]['independent_emergence'] for c in conventions]

    bars1 = ax.bar(x, active, width, label='Active (human-mediated)', color='#3498db')
    bars2 = ax.bar(x, independent, width, bottom=active, label='Independent emergence', color='#e74c3c')

    ax.set_xlabel('Convention')
    ax.set_ylabel('Number of adoption events')
    ax.set_title('Transmission Mechanisms by Convention')
    ax.set_xticks(x)
    ax.set_xticklabels([c.replace('/', '/\n') for c in conventions], fontsize=9)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    for bar, val in zip(bars1, active):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height()/2,
                   str(val), ha='center', va='center', fontweight='bold', color='white')
    for bar, val, bottom in zip(bars2, independent, active):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bottom + val/2,
                   str(val), ha='center', va='center', fontweight='bold', color='white')

    ax2 = axes[1]
    vectors = {}
    for event in classifications:
        v = event['vector']
        if 'copy-paste' in v.lower() or 'template' in v.lower() or 'inheritance' in v.lower():
            key = 'Copy-paste / Template'
        elif 'cross-pollination' in v.lower() or 'same session' in v.lower():
            key = 'Same-session cross-pollination'
        elif 'proactive' in v.lower() or 'deliberate' in v.lower() or 'batch' in v.lower():
            key = 'Deliberate propagation'
        elif 'bug' in v.lower() or 'failure' in v.lower() or 'independently' in v.lower():
            key = 'Same bug, independent fix'
        elif 'discovery' in v.lower() or 'authoring' in v.lower() or 'decision' in v.lower():
            key = 'Original authoring'
        else:
            key = v
        vectors[key] = vectors.get(key, 0) + 1

    labels = list(vectors.keys())
    sizes = list(vectors.values())
    colors_pie = ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6', '#1abc9c']

    wedges, texts, autotexts = ax2.pie(sizes, labels=None, autopct='%1.0f%%',
                                        colors=colors_pie[:len(labels)],
                                        startangle=90, pctdistance=0.8)
    ax2.legend(labels, loc='center left', bbox_to_anchor=(-0.3, -0.15), fontsize=8)
    ax2.set_title('Transmission Vectors (All Conventions)')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '019-transmission-mechanisms.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Saved: 019-transmission-mechanisms.png")


def plot_mortality(mortality_data):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    sorted_data = sorted(mortality_data, key=lambda x: x['projects_adopted'], reverse=True)

    ax = axes[0]
    names = [d['name'][:20] for d in sorted_data]
    adopted = [d['projects_adopted'] for d in sorted_data]
    surviving = [d['projects_still_have'] for d in sorted_data]

    x = np.arange(len(names))
    width = 0.35

    bars1 = ax.barh(x, adopted, width, label='Projects adopted', color='#3498db', alpha=0.7)
    bars2 = ax.barh(x + width, surviving, width, label='Projects still have', color='#2ecc71', alpha=0.7)

    ax.set_xlabel('Number of projects')
    ax.set_title('Convention Adoption vs. Survival')
    ax.set_yticks(x + width/2)
    ax.set_yticklabels(names, fontsize=8)
    ax.legend(fontsize=9)
    ax.invert_yaxis()
    ax.grid(True, alpha=0.3, axis='x')

    ax2 = axes[1]
    survival_rates = [d['survival_rate'] for d in sorted_data]
    statuses = [d['status'] for d in sorted_data]

    colors_bar = []
    for s in survival_rates:
        if s >= 1.0:
            colors_bar.append('#2ecc71')
        elif s > 0.5:
            colors_bar.append('#f39c12')
        else:
            colors_bar.append('#e74c3c')

    bars = ax2.barh(x, survival_rates, 0.6, color=colors_bar, alpha=0.8)
    ax2.set_xlabel('Survival rate')
    ax2.set_title('Convention Survival Rate')
    ax2.set_yticks(x)
    ax2.set_yticklabels(names, fontsize=8)
    ax2.set_xlim(0, 1.1)
    ax2.axvline(x=1.0, color='gray', linestyle=':', alpha=0.5)
    ax2.invert_yaxis()
    ax2.grid(True, alpha=0.3, axis='x')

    for i, (bar, status) in enumerate(zip(bars, statuses)):
        short_status = status.split('(')[1].rstrip(')') if '(' in status else status
        ax2.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2,
                short_status[:30], va='center', fontsize=7, style='italic')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '019-convention-mortality.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Saved: 019-convention-mortality.png")


def plot_combined_timeline():
    fig, ax = plt.subplots(figsize=(16, 8))

    timelines = [
        ('SSH_AUTH_SOCK', SSH_AUTH_SOCK_TIMELINE, '#e74c3c'),
        ('UUIDv7/URN', UUIDV7_TIMELINE, '#3498db'),
        ('Process/Plan Rules', PROCESS_RULES_TIMELINE, '#2ecc71'),
        ('Addendum Rule', ADDENDUM_TIMELINE, '#9b59b6'),
        ('Seed Conventions', SEED_CONVENTIONS, '#f39c12'),
    ]

    all_dates = []
    for name, timeline, color in timelines:
        all_dates.extend(timeline.values())
    min_date = min(all_dates)
    max_date = max(all_dates)

    for i, (name, timeline, color) in enumerate(timelines):
        y_base = i * 1.5
        for j, (project, date) in enumerate(timeline.items()):
            days = (date - min_date).days
            ax.scatter(days, y_base, s=120, color=color, edgecolors='black',
                      linewidth=1, zorder=5)
            ax.annotate(project, (days, y_base),
                       xytext=(5, 10 if j % 2 == 0 else -15),
                       textcoords='offset points', fontsize=7,
                       rotation=30, ha='left')

        dates_sorted = sorted([(date - min_date).days for date in timeline.values()])
        ax.plot(dates_sorted, [y_base] * len(dates_sorted), '-', color=color, alpha=0.5, linewidth=2)
        ax.text(-3, y_base, name, fontsize=10, fontweight='bold', ha='right', va='center', color=color)

    date_range = (max_date - min_date).days
    tick_days = list(range(0, date_range + 1, 7))
    tick_labels = [(min_date + timedelta(days=d)).strftime('%b %d') for d in tick_days]
    ax.set_xticks(tick_days)
    ax.set_xticklabels(tick_labels, rotation=45, fontsize=9)

    ax.set_yticks([])
    ax.set_xlabel('Date (2026)')
    ax.set_title('Convention Propagation Timeline Across Project Portfolio', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.2, axis='x')

    template_day = (datetime(2026, 2, 19) - min_date).days
    ax.axvline(x=template_day, color='gray', linestyle='--', alpha=0.5, linewidth=2)
    ax.text(template_day + 1, len(timelines) * 1.5 - 0.5, 'Template\ncreated',
            fontsize=9, color='gray', style='italic')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '019-combined-timeline.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print("  Saved: 019-combined-timeline.png")


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 70)
    print("Experiment 019: Convention Epidemiology")
    print("=" * 70)

    print("\n--- Analysis 1: SIR Model Fitting ---")
    sir_ssh = fit_sir(SSH_AUTH_SOCK_TIMELINE, N=TOTAL_PROJECTS, convention_name="SSH_AUTH_SOCK")
    sir_uuid = fit_sir(UUIDV7_TIMELINE, N=TOTAL_PROJECTS, convention_name="UUIDv7/URN")
    sir_process = fit_sir(PROCESS_RULES_TIMELINE, N=TOTAL_PROJECTS, convention_name="Process/Plan Rules")
    sir_results = [sir_ssh, sir_uuid, sir_process]

    for r in sir_results:
        print(f"\n  {r['convention']}:")
        print(f"    beta (transmission rate) = {r['beta']:.4f}")
        print(f"    gamma (recovery rate)    = {r['gamma']:.4f}")
        print(f"    R0 (reproduction number) = {r['R0']:.2f}")
        print(f"    Adopted: {r['num_adopted']}/{r['N']} projects in {r['total_days']} days")
        print(f"    Residual (SSE): {r['residual']:.4f}")

    plot_sir_results(sir_results)

    print("\n--- Analysis 2: Logistic S-curve Fitting ---")
    log_ssh = fit_logistic(SSH_AUTH_SOCK_TIMELINE, convention_name="SSH_AUTH_SOCK")
    log_uuid = fit_logistic(UUIDV7_TIMELINE, convention_name="UUIDv7/URN")
    log_process = fit_logistic(PROCESS_RULES_TIMELINE, convention_name="Process/Plan Rules")
    logistic_results = [log_ssh, log_uuid, log_process]

    for r in logistic_results:
        if 'error' in r:
            print(f"\n  {r['convention']}: FIT FAILED - {r['error']}")
        else:
            print(f"\n  {r['convention']}:")
            print(f"    Carrying capacity (L)    = {r['L']:.2f} projects")
            print(f"    Growth rate (k)          = {r['k']:.4f} per day")
            print(f"    Time to 50% (t0)         = {r['t0']:.1f} days from origin")
            print(f"    Doubling time            = {r['doubling_time']:.1f} days")
            print(f"    R-squared                = {r['r_squared']:.4f}")

    plot_adoption_curves(logistic_results)

    print("\n--- Analysis 3: Transmission Mechanisms ---")
    classifications = classify_transmissions()
    mechanism_counts = {}
    for event in classifications:
        m = event['mechanism']
        mechanism_counts[m] = mechanism_counts.get(m, 0) + 1

    print(f"\n  Total adoption events classified: {len(classifications)}")
    for mech, count in sorted(mechanism_counts.items()):
        pct = count / len(classifications) * 100
        print(f"    {mech}: {count} ({pct:.0f}%)")

    for conv in ['SSH_AUTH_SOCK', 'UUIDv7/URN', 'Process/Plan Rules']:
        events = [e for e in classifications if e['convention'] == conv]
        active = sum(1 for e in events if e['mechanism'] == 'active_transmission')
        independent = sum(1 for e in events if e['mechanism'] == 'independent_emergence')
        print(f"\n  {conv}: {active} active / {independent} independent ({len(events)} total)")

    plot_transmission_mechanisms(classifications)

    print("\n--- Analysis 4: Convention Mortality ---")
    mortality_data = analyze_mortality()

    alive = sum(1 for d in mortality_data if d['survival_rate'] >= 1.0)
    attenuated = sum(1 for d in mortality_data if 0 < d['survival_rate'] < 1.0)
    dead = sum(1 for d in mortality_data if d['survival_rate'] == 0)

    print(f"\n  Conventions tracked: {len(mortality_data)}")
    print(f"  Fully alive (100% survival): {alive}")
    print(f"  Attenuated (partial survival): {attenuated}")
    print(f"  Dead (0% survival): {dead}")

    for d in mortality_data:
        if d['survival_rate'] < 1.0:
            print(f"\n  MORTALITY EVENT: {d['name']}")
            print(f"    Status: {d['status']}")
            print(f"    Reason: {d['reason']}")

    plot_mortality(mortality_data)

    print("\n--- Combined Timeline Plot ---")
    plot_combined_timeline()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    summary = {
        'sir_models': {},
        'logistic_fits': {},
        'transmission_mechanisms': mechanism_counts,
        'mortality': {
            'total_tracked': len(mortality_data),
            'fully_alive': alive,
            'attenuated': attenuated,
            'dead': dead,
        },
        'key_findings': [],
    }

    for r in sir_results:
        summary['sir_models'][r['convention']] = {
            'R0': round(r['R0'], 2),
            'beta': round(r['beta'], 4),
            'gamma': round(r['gamma'], 4),
            'days_to_saturation': int(r['total_days']),
            'projects_reached': r['num_adopted'],
        }

    for r in logistic_results:
        if 'error' not in r:
            summary['logistic_fits'][r['convention']] = {
                'carrying_capacity': round(r['L'], 2),
                'growth_rate': round(r['k'], 4),
                'time_to_50_pct': round(r['t0'], 1),
                'doubling_time': round(r['doubling_time'], 1),
                'r_squared': round(r['r_squared'], 4),
            }

    ssh_r0 = sir_ssh['R0']
    uuid_r0 = sir_uuid['R0']
    process_r0 = sir_process['R0']

    summary['key_findings'] = [
        f"SSH_AUTH_SOCK R0={ssh_r0:.2f}: {'Epidemic' if ssh_r0 > 1 else 'Sub-epidemic'} spread",
        f"UUIDv7/URN R0={uuid_r0:.2f}: {'Epidemic' if uuid_r0 > 1 else 'Sub-epidemic'} spread",
        f"Process Rules R0={process_r0:.2f}: {'Epidemic' if process_r0 > 1 else 'Sub-epidemic'} spread",
        f"Dominant transmission: {max(mechanism_counts, key=mechanism_counts.get)}",
        f"Convention mortality is extremely low: {dead}/{len(mortality_data)} conventions died",
        f"Addendum rule has lowest effective R0 -- adopted by only 2/10 projects",
    ]

    for finding in summary['key_findings']:
        print(f"  * {finding}")

    json_path = os.path.join(OUTPUT_DIR, '019-epidemiology-results.json')
    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n  Saved: 019-epidemiology-results.json")

    return summary


if __name__ == '__main__':
    main()
