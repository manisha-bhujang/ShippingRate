"""
Shipping Cost Comparison Tool
-----------------------------
A Streamlit app that compares shipping costs across carriers and modes
(truck, rail, intermodal, air) for a chosen route, shipment weight,
and fuel surcharge, then recommends a carrier based on the user's priorities.

Run locally:   streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# 1. Page setup (must be the first Streamlit command)
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Shipping Cost Comparison", page_icon="🚚", layout="wide")

# One fixed color per carrier, so a carrier keeps its color on every chart
# even when filters remove other carriers.
CARRIER_COLORS = {
    "SwiftHaul Freight": "#2a78d6",
    "Summit Trucking": "#eb6834",
    "IronLine Rail": "#1baf7a",
    "CrossCountry Intermodal": "#eda100",
    "JetStream Air Cargo": "#e87ba4",
    "SkyBridge Express": "#4a3aa7",
}


# ---------------------------------------------------------------------------
# 2. Load data (cached so the CSV is read once, not on every rerun)
# ---------------------------------------------------------------------------
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# 3. Business logic: plain pandas functions, no Streamlit involved
# ---------------------------------------------------------------------------
def calculate_costs(lane: pd.DataFrame, weight_lbs: float, fuel_pct: float) -> pd.DataFrame:
    """Return the lane's carriers with a cost breakdown for this shipment."""
    df = lane.copy()

    # Linehaul = the distance-and-weight part of the price
    df["linehaul_usd"] = df["rate_per_lb_per_100mi"] * weight_lbs * df["distance_miles"] / 100

    # Fuel surcharge applies to linehaul; some modes feel fuel prices more (air > truck > rail)
    df["fuel_usd"] = df["linehaul_usd"] * (fuel_pct / 100) * df["fuel_sensitivity"]

    df["total_cost_usd"] = df["base_fee_usd"] + df["linehaul_usd"] + df["fuel_usd"]
    df["cost_per_lb_usd"] = df["total_cost_usd"] / weight_lbs

    # Edge case: rail and intermodal won't take small shipments
    df["eligible"] = weight_lbs >= df["min_weight_lbs"]
    return df


def scale_0_to_1(values: pd.Series, higher_is_better: bool) -> pd.Series:
    """Rescale a column to 0-1 so cost ($), speed (days) and reliability (%) are comparable."""
    spread = values.max() - values.min()
    if spread == 0:  # edge case: every carrier is identical -> nobody wins or loses on this factor
        return pd.Series(1.0, index=values.index)
    scaled = (values - values.min()) / spread
    return scaled if higher_is_better else 1 - scaled


def add_value_score(df: pd.DataFrame, w_cost: int, w_speed: int, w_reliability: int) -> pd.DataFrame:
    """Combine cost, speed and reliability into one 0-100 'best value' score."""
    df = df.copy()
    total_weight = w_cost + w_speed + w_reliability
    if total_weight == 0:  # edge case: all sliders at 0 -> treat all factors equally
        w_cost = w_speed = w_reliability = total_weight = 1

    df["score"] = 100 * (
        w_cost * scale_0_to_1(df["total_cost_usd"], higher_is_better=False)
        + w_speed * scale_0_to_1(df["transit_days"], higher_is_better=False)
        + w_reliability * scale_0_to_1(df["on_time_pct"], higher_is_better=True)
    ) / total_weight
    return df


def efficient_options(df: pd.DataFrame) -> pd.DataFrame:
    """Carriers that no other carrier beats on BOTH cost and speed (the 'efficient frontier')."""
    keep = []
    for _, row in df.iterrows():
        beaten = (
            (df["total_cost_usd"] <= row["total_cost_usd"])
            & (df["transit_days"] <= row["transit_days"])
            & ((df["total_cost_usd"] < row["total_cost_usd"]) | (df["transit_days"] < row["transit_days"]))
        ).any()
        keep.append(not beaten)
    return df[keep].sort_values("transit_days")


df = load_data("shipping_rates.csv")

# ---------------------------------------------------------------------------
# 4. Sidebar inputs: every widget returns a normal Python value
# ---------------------------------------------------------------------------
st.sidebar.header("Shipment details")

origins = sorted(df["origin"].unique())
origin = st.sidebar.selectbox("Origin", origins, index=origins.index("Phoenix"))

destinations = sorted(df.loc[df["origin"] == origin, "destination"].unique())
destination = st.sidebar.selectbox(
    "Destination", destinations, index=destinations.index("Chicago") if "Chicago" in destinations else 0
)

weight = st.sidebar.slider("Shipment weight (lbs)", min_value=50, max_value=10_000, value=800, step=50)
fuel = st.sidebar.slider("Fuel surcharge (%)", min_value=0, max_value=60, value=15, step=5)

all_modes = sorted(df["mode"].unique())
modes = st.sidebar.multiselect("Modes to include", all_modes, default=all_modes)

st.sidebar.header("Decision rules")
deadline = st.sidebar.slider("Must arrive within (days)", min_value=1, max_value=10, value=5)

st.sidebar.caption("How much does each factor matter to you? (0 = not at all)")
w_cost = st.sidebar.slider("Cost", 0, 10, 6)
w_speed = st.sidebar.slider("Speed", 0, 10, 3)
w_reliability = st.sidebar.slider("Reliability (on-time rate)", 0, 10, 1)

# ---------------------------------------------------------------------------
# 5. Filter + compute (the script reruns top to bottom on every widget change)
# ---------------------------------------------------------------------------
lane = df[(df["origin"] == origin) & (df["destination"] == destination) & (df["mode"].isin(modes))]
results = calculate_costs(lane, weight, fuel)

eligible = results[results["eligible"]]
excluded = results[~results["eligible"]]

eligible = add_value_score(eligible, w_cost, w_speed, w_reliability) if not eligible.empty else eligible
eligible = eligible.assign(meets_deadline=eligible["transit_days"] <= deadline)
eligible = eligible.sort_values("score", ascending=False).reset_index(drop=True)

on_time_options = eligible[eligible["meets_deadline"]]

# ---------------------------------------------------------------------------
# 6. Page header and headline numbers
# ---------------------------------------------------------------------------
st.title("🚚 Shipping Cost Comparison")
distance = int(df.loc[(df["origin"] == origin) & (df["destination"] == destination), "distance_miles"].iloc[0])
st.caption(
    f"{origin} → {destination} · {distance:,} miles · {weight:,} lbs · "
    f"{fuel}% fuel surcharge · deadline {deadline} day(s)"
)

if eligible.empty:
    st.warning("No carriers match these settings. Try adding more modes or increasing the weight.")
    st.stop()

cheapest_overall = eligible.loc[eligible["total_cost_usd"].idxmin()]

k1, k2, k3, k4 = st.columns(4)
if on_time_options.empty:
    # Edge case: nobody can meet the deadline -> say so instead of recommending a late carrier
    recommended = None
    fastest = eligible.sort_values(["transit_days", "total_cost_usd"]).iloc[0]
    k1.metric("Recommended carrier", "None")
    k1.caption(f"No carrier delivers within {deadline} day(s). Fastest is {fastest['transit_days']} days.")
    k2.metric("Cheapest on time", "—")
    k3.metric("Extra cost to meet deadline", "—")
else:
    recommended = on_time_options.iloc[0]  # already sorted by score
    cheapest_on_time = on_time_options.loc[on_time_options["total_cost_usd"].idxmin()]
    extra_cost = cheapest_on_time["total_cost_usd"] - cheapest_overall["total_cost_usd"]

    # st.metric truncates long names, so show the carrier with plain markdown instead
    k1.markdown(f"<small>Recommended carrier</small><br><span style='font-size:1.6rem'>"
                f"{recommended['carrier']}</span>", unsafe_allow_html=True)
    k1.caption(f"Value score {recommended['score']:.0f}/100 · ${recommended['total_cost_usd']:,.0f} · "
               f"{recommended['transit_days']} day(s)")
    k2.metric("Cheapest on time", f"${cheapest_on_time['total_cost_usd']:,.0f}")
    k2.caption(f"{cheapest_on_time['carrier']} · {cheapest_on_time['transit_days']} day(s)")
    k3.metric("Extra cost to meet deadline", f"${extra_cost:,.0f}")
    k3.caption("$0 means the cheapest carrier is already fast enough"
               if extra_cost == 0 else f"vs. {cheapest_overall['carrier']} ({cheapest_overall['transit_days']} days)")

k4.metric("Cheapest overall", f"${cheapest_overall['total_cost_usd']:,.0f}")
k4.caption(f"{cheapest_overall['carrier']} · {cheapest_overall['transit_days']} day(s)")

# ---------------------------------------------------------------------------
# 7. Tabs keep the page organized instead of one long scroll
# ---------------------------------------------------------------------------
tab_compare, tab_tradeoff, tab_whatif, tab_scenarios = st.tabs(
    ["📊 Compare", "⚖️ Cost vs. speed", "📈 What-if: weight", "💾 Saved scenarios"]
)

# --- Tab 1: comparison ------------------------------------------------------
with tab_compare:
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Total cost by carrier")
        by_cost = eligible.sort_values("total_cost_usd")
        bar = px.bar(
            by_cost, x="total_cost_usd", y="carrier", orientation="h",
            color="carrier", color_discrete_map=CARRIER_COLORS,
            text=by_cost["total_cost_usd"].map("${:,.0f}".format),
            hover_data={"mode": True, "transit_days": True, "total_cost_usd": ":$,.0f", "carrier": False},
            labels={"total_cost_usd": "Total cost (USD)", "carrier": ""},
        )
        bar.update_traces(textposition="outside", cliponaxis=False)
        bar.update_layout(showlegend=False, height=340, margin=dict(l=0, r=40, t=10, b=0),
                          xaxis_tickprefix="$", yaxis={"categoryorder": "total descending"})
        st.plotly_chart(bar, width="stretch")

    with right:
        st.subheader("Where the money goes")
        breakdown = by_cost.melt(
            id_vars="carrier", value_vars=["base_fee_usd", "linehaul_usd", "fuel_usd"],
            var_name="component", value_name="usd",
        )
        breakdown["component"] = breakdown["component"].map(
            {"base_fee_usd": "Base fee", "linehaul_usd": "Linehaul", "fuel_usd": "Fuel surcharge"}
        )
        stack = px.bar(
            breakdown, x="usd", y="carrier", color="component", orientation="h",
            color_discrete_sequence=["#86b6ef", "#2a78d6", "#104281"],
            labels={"usd": "USD", "carrier": "", "component": ""},
        )
        stack.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), xaxis_tickprefix="$", xaxis_title=None,
                            legend=dict(orientation="h", y=-0.15),
                            yaxis={"categoryorder": "array", "categoryarray": list(by_cost["carrier"])[::-1]})
        st.plotly_chart(stack, width="stretch")

    st.subheader("Carrier ranking (best value first)")
    table = eligible[["carrier", "mode", "score", "total_cost_usd", "transit_days", "meets_deadline",
                      "on_time_pct", "cost_per_lb_usd"]]
    st.dataframe(
        table, hide_index=True, width="stretch",
        column_config={
            "carrier": "Carrier",
            "mode": "Mode",
            "score": st.column_config.ProgressColumn("Value score", min_value=0, max_value=100, format="%.0f"),
            "total_cost_usd": st.column_config.NumberColumn("Total cost", format="$%.2f"),
            "transit_days": st.column_config.NumberColumn("Transit (days)"),
            "meets_deadline": st.column_config.CheckboxColumn("Meets deadline"),
            "on_time_pct": st.column_config.NumberColumn("On-time rate", format="percent"),
            "cost_per_lb_usd": st.column_config.NumberColumn("Cost per lb", format="$%.3f"),
        },
    )
    st.caption("Value score = your weighted mix of cost, speed and reliability, rescaled so the best "
               "carrier on a factor gets full marks for it and the worst gets zero.")

    if not excluded.empty:
        names = ", ".join(f"{r.carrier} (min {r.min_weight_lbs:,} lbs)" for r in excluded.itertuples())
        st.info(f"Not shown because the shipment is below their minimum weight: {names}")

    st.download_button(
        "Download ranking as CSV",
        table.to_csv(index=False).encode("utf-8"),
        file_name=f"shipping_{origin}_{destination}.csv".replace(" ", "_"),
        mime="text/csv",
    )

# --- Tab 2: cost vs. speed trade-off ---------------------------------------
with tab_tradeoff:
    st.subheader("Cost vs. speed: which options are worth considering?")
    st.caption("Each dot is a carrier. The dashed line joins the efficient options: no other carrier is both "
               "cheaper and faster. Anything above the line is beaten on both. The shaded area is past your deadline.")

    frontier = efficient_options(eligible)

    scatter = px.scatter(
        eligible, x="transit_days", y="total_cost_usd", color="carrier",
        color_discrete_map=CARRIER_COLORS,
        hover_data={"mode": True, "on_time_pct": ":.0%", "total_cost_usd": ":$,.0f", "carrier": False},
        labels={"transit_days": "Transit time (days)", "total_cost_usd": "Total cost (USD)", "carrier": ""},
    )
    scatter.update_traces(marker=dict(size=14, line=dict(width=2, color="white")))
    scatter.add_trace(go.Scatter(
        x=frontier["transit_days"], y=frontier["total_cost_usd"], mode="lines",
        line=dict(dash="dash", color="gray", width=2), name="Efficient frontier", hoverinfo="skip",
    ))
    max_days = max(eligible["transit_days"].max(), deadline) + 1
    if deadline < max_days:
        scatter.add_vrect(x0=deadline + 0.5, x1=max_days, fillcolor="gray", opacity=0.12, line_width=0,
                          annotation_text="Misses deadline", annotation_position="top left")
    scatter.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0), yaxis_tickprefix="$",
                          xaxis=dict(dtick=1, range=[0.5, max_days]), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(scatter, width="stretch")

    dominated = sorted(set(eligible["carrier"]) - set(frontier["carrier"]))
    st.write("**Efficient options:** " + ", ".join(frontier["carrier"]))
    if dominated:
        st.write("**Never the right choice on cost or speed alone:** " + ", ".join(dominated))

# --- Tab 3: what-if on weight ----------------------------------------------
with tab_whatif:
    st.subheader("How cost changes with weight")
    st.caption("Lines cross where a different carrier becomes cheapest. The dashed line is your current weight.")

    show_air = st.checkbox("Include air carriers (they cost far more and flatten the other lines)", value=False)

    weights = range(50, 5_001, 50)
    curve = pd.concat([calculate_costs(lane, w, fuel).assign(weight_lbs=w) for w in weights], ignore_index=True)
    curve = curve[curve["eligible"]]
    if not show_air:
        curve = curve[curve["mode"] != "Air"]

    line = px.line(
        curve, x="weight_lbs", y="total_cost_usd", color="carrier", color_discrete_map=CARRIER_COLORS,
        labels={"weight_lbs": "Shipment weight (lbs)", "total_cost_usd": "Total cost (USD)", "carrier": ""},
    )
    line.update_traces(line_width=2, hovertemplate="%{x:,} lbs: $%{y:,.0f}")
    line.add_vline(x=weight, line_dash="dash", line_color="gray")
    line.update_layout(height=420, hovermode="x unified", yaxis_tickprefix="$",
                       margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(line, width="stretch")

# --- Tab 4: saved scenarios (st.session_state) ------------------------------
# PITFALL: a normal Python list would be recreated empty on every rerun, so saved
# scenarios would vanish the moment you touched a slider. st.session_state is a
# dictionary that survives reruns for as long as the browser tab stays open.
if "scenarios" not in st.session_state:
    st.session_state["scenarios"] = []

with tab_scenarios:
    st.subheader("Save and compare scenarios")
    st.caption("Change the sidebar settings, save each version, then compare them side by side.")

    save_col, clear_col, _ = st.columns([1, 1, 3])
    if save_col.button("💾 Save current scenario", type="primary"):
        st.session_state["scenarios"].append({
            "Scenario": f"#{len(st.session_state['scenarios']) + 1}",
            "Route": f"{origin} → {destination}",
            "Weight (lbs)": weight,
            "Fuel %": fuel,
            "Deadline (days)": deadline,
            "Priorities (cost/speed/rel.)": f"{w_cost}/{w_speed}/{w_reliability}",
            "Recommended": recommended["carrier"] if recommended is not None else "None meets deadline",
            "Recommended cost": recommended["total_cost_usd"] if recommended is not None else None,
            "Cheapest overall": cheapest_overall["total_cost_usd"],
        })
    if clear_col.button("Clear all"):
        st.session_state["scenarios"] = []

    if not st.session_state["scenarios"]:
        st.info("No scenarios saved yet. Try saving one, raising the fuel surcharge, and saving again.")
    else:
        saved = pd.DataFrame(st.session_state["scenarios"])
        st.dataframe(
            saved, hide_index=True, width="stretch",
            column_config={
                "Recommended cost": st.column_config.NumberColumn(format="$%.0f"),
                "Cheapest overall": st.column_config.NumberColumn(format="$%.0f"),
            },
        )
        compare = saved.dropna(subset=["Recommended cost"])
        if len(compare) >= 2:
            fig = px.bar(
                compare, x="Scenario", y="Recommended cost", color="Recommended",
                color_discrete_map=CARRIER_COLORS,
                text=compare["Recommended cost"].map("${:,.0f}".format),
                labels={"Recommended cost": "Cost of recommended carrier (USD)", "Recommended": ""},
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_layout(height=360, margin=dict(l=0, r=0, t=20, b=0), yaxis_tickprefix="$",
                              xaxis_type="category", bargap=0.5,
                              legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig, width="stretch")
