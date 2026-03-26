"""
Baltimore City Health & Economic Dashboard (Streamlit)
Tract-level indicators: ACS (health + economic) and CDC PLACES where available.
"""

from typing import Optional

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import os

# Page config
st.set_page_config(
    page_title="Baltimore City Dashboard",
    page_icon="B",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .metric-card {
        background: #f7fafc;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-left: 4px solid #667eea;
    }
    .stMetric {
        background: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# Columns that are IDs / geometry / UI helpers — not plottable indicators
_ID_META_COLS = frozenset({
    "tract", "state", "county", "NAME", "NAME_additional", "NAME_health", "NAME_econ",
    "tract_str", "tract_display", "lat", "lon",
})


def _humanize_column(col: str) -> str:
    s = col.replace("places_", "", 1) if col.startswith("places_") else col
    return s.replace("_", " ").strip().title()


def _numeric_indicator_columns(df: pd.DataFrame) -> list[str]:
    """All numeric columns suitable for maps and charts (excludes tract/NAME helpers)."""
    out = []
    for c in df.columns:
        if c in _ID_META_COLS:
            continue
        if c.startswith("flag_"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        out.append(c)
    return sorted(out, key=lambda x: _humanize_column(x).lower())


def _indicator_labels(df: pd.DataFrame) -> dict[str, str]:
    return {c: _humanize_column(c) for c in _numeric_indicator_columns(df)}


def _build_city_overview_categories(df: pd.DataFrame) -> dict[str, dict[str, str]]:
    """Full indicator picklists: CDC PLACES vs all ACS / integrated metrics."""
    labels = _indicator_labels(df)
    places = {c: labels[c] for c in df.columns if c.startswith("places_") and c in labels}
    acs_rest = {c: labels[c] for c in labels if not c.startswith("places_")}
    cats: dict[str, dict[str, str]] = {}
    if places:
        cats["Clinical Outcomes (CDC PLACES)"] = places
    if acs_rest:
        cats["Health, Economic & Social (ACS integrated)"] = acs_rest
    return cats


def _first_existing(*paths: str) -> Optional[str]:
    """Resolve first path that exists (do not cache — cwd must be fresh each run)."""
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def load_data():
    """Load the expanded integrated dataset.

    Supports both layouts: packaged under ``data/integrated/`` or CSVs in repo
    root (common when uploading directly to GitHub).
    """
    places_candidates = (
        "data/integrated/baltimore_integrated_with_places_2022.csv",
        "baltimore_integrated_with_places_2022.csv",
    )
    legacy_candidates = (
        "data/integrated/baltimore_integrated_expanded_2022.csv",
        "baltimore_integrated_expanded_2022.csv",
    )
    try:
        p = _first_existing(*places_candidates)
        if p:
            return pd.read_csv(p)
        p = _first_existing(*legacy_candidates)
        if p:
            return pd.read_csv(p)
        st.error(
            "Data file not found. Add one of:\n"
            "- `baltimore_integrated_with_places_2022.csv` (PLACES merge), or\n"
            "- `baltimore_integrated_expanded_2022.csv`\n"
            "either in the repo root or under `data/integrated/`."
        )
        return None
    except Exception as e:
        st.error(f"Failed to load CSV: {e}")
        return None

def main():
    # Header
    st.markdown('<h1 class="main-header">Baltimore City Health & Economic Dashboard</h1>', unsafe_allow_html=True)
    st.markdown("**Tract-level health and economic indicators for Baltimore City**")
    st.markdown("---")
    
    # Load data
    df = load_data()
    if df is None:
        return
    
    # Sidebar
    st.sidebar.title("Dashboard Controls")
    st.sidebar.markdown("---")
    
    # View selection (no emojis)
    view_mode = st.sidebar.radio(
        "Select View",
        ["City Overview (Map & Data)", "Neighborhood Explorer", "Indicator Analysis", "About"]
    )
    
    if view_mode == "City Overview (Map & Data)":
        show_city_overview(df)
    elif view_mode == "Neighborhood Explorer":
        show_neighborhood_explorer(df)
    elif view_mode == "Indicator Analysis":
        show_indicator_analysis(df)
    else:
        show_about(df)

def show_city_overview(df):
    """Show city-level overview: map and data in one view."""
    st.header("City Overview: Map & Data")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Census Tracts", f"{len(df):,}", help="Total tracts in Baltimore City")
    with col2:
        st.metric("Avg Poverty Rate", f"{df['poverty_rate'].mean():.1f}%", help="Average across tracts")
    with col3:
        st.metric("Avg Unemployment", f"{df['unemployment_rate'].mean():.1f}%", help="Average across tracts")
    with col4:
        st.metric("Median Income", f"${df['median_household_income_econ'].median():,.0f}", help="Median across tracts")
    
    st.markdown("---")

    indicator_categories = _build_city_overview_categories(df)
    n_ind = len(_numeric_indicator_columns(df))
    st.sidebar.caption(f"{n_ind} numeric indicators in this dataset (all available below).")

    if not indicator_categories:
        st.error("No numeric indicator columns found.")
        return

    category = st.sidebar.selectbox("Indicator category", list(indicator_categories.keys()))
    indicator = st.sidebar.selectbox("Indicator", list(indicator_categories[category].keys()),
                                    format_func=lambda x: indicator_categories[category][x])
    
    # Single merged view: map (scatter) + data table + distribution
    tract_col = 'tract' if 'tract' in df.columns else df.columns[0]
    df_display = df.copy()
    df_display['tract_str'] = df_display['tract'].astype(str).str.zfill(6)
    
    # Approximate coordinates for Baltimore City (center + jitter by tract index for spread)
    np.random.seed(42)
    n = len(df_display)
    df_display['lat'] = 39.29 + (np.arange(n) % 10 - 5) * 0.02 + np.random.randn(n) * 0.01
    df_display['lon'] = -76.61 + (np.arange(n) // 10 - 5) * 0.02 + np.random.randn(n) * 0.01
    
    col_map, col_data = st.columns([1, 1])
    
    with col_map:
        st.subheader("Map")
        fig_map = px.scatter_mapbox(
            df_display,
            lat='lat',
            lon='lon',
            color=indicator,
            hover_name='tract_str',
            hover_data={indicator: ':.2f', 'lat': False, 'lon': False},
            color_continuous_scale='Viridis',
            mapbox_style='open-street-map',
            center=dict(lat=39.29, lon=-76.61),
            zoom=10,
            height=400,
        )
        fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig_map, use_container_width=True)
    
    with col_data:
        st.subheader("Data (selected indicator)")
        vals = df_display[['tract_str', indicator]].dropna()
        vals = vals.sort_values(indicator, ascending=False).head(50)
        vals = vals.rename(columns={'tract_str': 'Tract', indicator: indicator_categories[category][indicator]})
        st.dataframe(vals, use_container_width=True, height=400)
    
    st.markdown("---")
    st.subheader("Distribution")
    col1, col2 = st.columns(2)
    with col1:
        fig_hist = px.histogram(
            df, x=indicator, nbins=30,
            labels={indicator: indicator_categories[category][indicator]},
            color_discrete_sequence=['#667eea']
        )
        fig_hist.update_layout(showlegend=False, height=300, plot_bgcolor='white')
        st.plotly_chart(fig_hist, use_container_width=True)
    with col2:
        fig_box = px.box(
            df, y=indicator,
            labels={indicator: indicator_categories[category][indicator]},
            color_discrete_sequence=['#764ba2']
        )
        fig_box.update_layout(showlegend=False, height=300, plot_bgcolor='white')
        st.plotly_chart(fig_box, use_container_width=True)
    
    # Statistics (compact)
    values = df[indicator].dropna()
    if len(values) == 0:
        st.caption("No numeric values for this indicator (all missing).")
    else:
        st.caption(
            f"Min: {values.min():.2f}  |  Median: {values.median():.2f}  |  "
            f"Max: {values.max():.2f}  |  Std: {values.std():.2f}"
        )

def show_neighborhood_explorer(df):
    """Show neighborhood-level drill-down."""
    st.header("Neighborhood Explorer")
    
    # Prepare tract selection
    df['tract_str'] = df['tract'].astype(str).str.zfill(6)
    df['tract_display'] = 'Tract ' + df['tract_str']
    
    # Select tract
    selected_tract = st.selectbox(
        "Select Census Tract",
        df['tract_display'].tolist(),
        help="Choose a census tract to view detailed information"
    )
    
    tract_data = df[df['tract_display'] == selected_tract].iloc[0]
    
    st.markdown("---")
    
    # Key indicators
    st.subheader("Key Indicators")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        poverty = tract_data['poverty_rate']
        city_avg = df['poverty_rate'].mean()
        delta = poverty - city_avg
        st.metric(
            "Poverty Rate",
            f"{poverty:.1f}%",
            f"{delta:+.1f}% vs city avg",
            delta_color="inverse"
        )
    
    with col2:
        unemployment = tract_data['unemployment_rate']
        city_avg = df['unemployment_rate'].mean()
        delta = unemployment - city_avg
        st.metric(
            "Unemployment Rate",
            f"{unemployment:.1f}%",
            f"{delta:+.1f}% vs city avg",
            delta_color="inverse"
        )
    
    with col3:
        income = tract_data['median_household_income_econ']
        city_avg = df['median_household_income_econ'].median()
        delta = income - city_avg
        st.metric(
            "Median Income",
            f"${income:,.0f}",
            f"${delta:+,.0f} vs city median"
        )
    
    with col4:
        gini = tract_data['gini_index']
        city_avg = df['gini_index'].mean()
        delta = gini - city_avg
        st.metric(
            "Gini Index",
            f"{gini:.3f}",
            f"{delta:+.3f} vs city avg",
            delta_color="inverse"
        )
    
    st.markdown("---")
    
    # Detailed metrics
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Housing & Economic")
        
        metrics = [
            ('housing_cost_burden_rate', 'Housing Cost Burden', '%'),
            ('snap_participation_rate', 'SNAP Participation', '%'),
            ('public_assistance_rate', 'Public Assistance', '%'),
            ('home_ownership_rate', 'Home Ownership', '%'),
            ('vacancy_rate', 'Vacancy Rate', '%'),
        ]
        
        for key, label, unit in metrics:
            if key in tract_data.index and pd.notna(tract_data[key]):
                value = tract_data[key]
                city_avg = df[key].mean()
                diff_pct = ((value - city_avg) / city_avg * 100) if city_avg != 0 else 0
                
                st.write(f"**{label}:** {value:.1f}{unit}")
                st.progress(min(value / 100, 1.0) if unit == '%' else 0.5)
                st.caption(f"{diff_pct:+.1f}% vs city average")
                st.markdown("")
    
    with col2:
        st.subheader("Health & Education")

        # CDC PLACES (clinical outcomes) fields are prefixed with `places_`.
        # We include a stable subset when the enriched dataset is available.
        cdc_metrics = []
        if 'places_no_health_insurance_pct' in df.columns:
            cdc_metrics.append(('places_no_health_insurance_pct', 'No Health Insurance (CDC PLACES)', '%'))
        if 'places_obesity_pct' in df.columns:
            cdc_metrics.append(('places_obesity_pct', 'Obesity (CDC PLACES)', '%'))
        if 'places_diabetes_pct' in df.columns:
            cdc_metrics.append(('places_diabetes_pct', 'Diabetes (CDC PLACES)', '%'))
        if 'places_high_blood_pressure_pct' in df.columns:
            cdc_metrics.append(('places_high_blood_pressure_pct', 'High Blood Pressure (CDC PLACES)', '%'))
        if 'places_depression_pct' in df.columns:
            cdc_metrics.append(('places_depression_pct', 'Depression (CDC PLACES)', '%'))

        metrics = [
            # Keep core ACS-based social determinants / education context.
            ('disability_rate', 'Disability Rate', '%'),
            ('college_degree_rate', 'College Degree Rate', '%'),
            ('long_commute_rate', 'Long Commute Rate (60+ min)', '%'),
        ] + cdc_metrics
        
        for key, label, unit in metrics:
            if key in tract_data.index and pd.notna(tract_data[key]):
                value = tract_data[key]
                city_avg = df[key].mean()
                diff_pct = ((value - city_avg) / city_avg * 100) if city_avg != 0 else 0
                
                st.write(f"**{label}:** {value:.1f}{unit}")
                st.progress(min(value / 100, 1.0) if unit == '%' else 0.5)
                st.caption(f"{diff_pct:+.1f}% vs city average")
                st.markdown("")
    
    # Comparison radar chart
    st.markdown("---")
    st.subheader("Neighborhood vs City Average")
    
    places_labels = {
        'places_no_health_insurance_pct': 'No Health Insurance (CDC)',
        'places_obesity_pct': 'Obesity (CDC)',
        'places_diabetes_pct': 'Diabetes (CDC)',
        'places_high_blood_pressure_pct': 'High BP (CDC)',
        'places_depression_pct': 'Depression (CDC)',
        'places_current_smoking_pct': 'Current Smoking (CDC)',
    }

    comparison_indicators = [
        'poverty_rate',
        'unemployment_rate',
        'housing_cost_burden_rate',
        'places_no_health_insurance_pct',
        'places_obesity_pct',
        'college_degree_rate',
    ]
    
    tract_values = []
    city_values = []
    labels = []
    
    for ind in comparison_indicators:
        if ind in tract_data.index and pd.notna(tract_data[ind]):
            tract_val = tract_data[ind]
            city_val = df[ind].mean()
            
            # Normalize to percentage of city average
            normalized = (tract_val / city_val * 100) if city_val != 0 else 100
            
            tract_values.append(normalized)
            city_values.append(100)
            labels.append(places_labels.get(ind, ind.replace('_', ' ').title()))
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=tract_values,
        theta=labels,
        fill='toself',
        name=selected_tract,
        line_color='#667eea'
    ))
    
    fig.add_trace(go.Scatterpolar(
        r=city_values,
        theta=labels,
        fill='toself',
        name='City Average (100%)',
        line_color='#764ba2',
        line_dash='dash'
    ))
    
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 150])),
        showlegend=True,
        height=500
    )
    
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Radar uses a fixed subset of indicators for readability. "
        "Use the lookup below for any column in the dataset."
    )

    lab = _indicator_labels(df)
    keys_ne = sorted(lab.keys(), key=lambda k: lab[k].lower())
    with st.expander("Look up any indicator for this tract"):
        pick = st.selectbox(
            "Indicator",
            keys_ne,
            format_func=lambda k: lab[k],
            key="neighborhood_lookup_indicator",
        )
        if pick in tract_data.index:
            raw = tract_data[pick]
            if pd.isna(raw):
                st.write("**Value:** missing for this tract")
            else:
                st.write(f"**Value:** {raw:.4g}")
            city_m = df[pick].mean()
            if pd.notna(city_m) and pd.notna(raw):
                st.caption(f"City mean: {city_m:.4g}")

def show_indicator_analysis(df):
    """Show indicator analysis and correlations."""
    st.header("Indicator Analysis")
    
    labels = _indicator_labels(df)
    keys_sorted = sorted(labels.keys(), key=lambda k: labels[k].lower())
    if len(keys_sorted) < 2:
        st.warning("Need at least two numeric indicators for correlation.")
        return

    st.markdown("Correlation between any two indicators (full list from the integrated dataset).")
    
    col1, col2 = st.columns(2)
    with col1:
        x_var = st.selectbox(
            "X-axis",
            keys_sorted,
            format_func=lambda k: labels[k],
        )
    with col2:
        y_idx = min(1, len(keys_sorted) - 1)
        if keys_sorted[y_idx] == x_var and len(keys_sorted) > y_idx + 1:
            y_idx += 1
        y_var = st.selectbox(
            "Y-axis",
            keys_sorted,
            index=y_idx,
            format_func=lambda k: labels[k],
        )
    
    # Scatter plot — manual trendline avoids statsmodels dependency
    pair = df[[x_var, y_var]].dropna()
    if len(pair) < 2:
        st.warning("Not enough paired observations.")
        return

    fig = px.scatter(
        pair,
        x=x_var,
        y=y_var,
        title=f"{labels[x_var]} vs {labels[y_var]}",
        labels={x_var: labels[x_var], y_var: labels[y_var]},
        color_discrete_sequence=['#667eea']
    )

    # Add trendline via numpy (no statsmodels needed)
    m, b = np.polyfit(pair[x_var], pair[y_var], 1)
    x_range = np.linspace(pair[x_var].min(), pair[x_var].max(), 100)
    fig.add_scatter(
        x=x_range, y=m * x_range + b,
        mode='lines', name='Trend',
        line=dict(color='#764ba2', dash='dash')
    )

    fig.update_layout(height=600, plot_bgcolor='white')
    st.plotly_chart(fig, use_container_width=True)

    corr = pair[x_var].corr(pair[y_var])
    st.metric("Correlation Coefficient", f"{corr:.3f}")

    if abs(corr) > 0.7:
        st.success("Strong correlation")
    elif abs(corr) > 0.4:
        st.info("Moderate correlation")
    else:
        st.warning("Weak correlation")

def show_about(df):
    """Show about page."""
    st.header("About This Dashboard")

    n_ind = len(_numeric_indicator_columns(df)) if df is not None else 0

    st.markdown(f"""
    **Baltimore City Health & Economic Dashboard**

    Census tract–level indicators for Baltimore City (199 tracts; **{n_ind}** numeric columns in the loaded file).
    Reference year: 2022 (ACS 5-year). Sources: U.S. Census ACS; CDC PLACES (where merged).

    **Views:** City Overview (map, table, distributions); Neighborhood Explorer (tract profile and indicator lookup);
    Indicator Analysis (scatter and correlation).

    Missing Census codes are represented as NaN. Last updated: March 2026.
    """)

if __name__ == "__main__":
    main()
