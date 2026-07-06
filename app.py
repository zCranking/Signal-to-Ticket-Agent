"""Signal-to-Ticket | Streamlit demo UI."""
import json
import sys
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from signal_to_ticket.agent import run_agent, PIPELINE_STEPS
from signal_to_ticket.config import DEMO_EVENTS_PATH

st.set_page_config(
    page_title="Signal-to-Ticket",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .main-title { font-size: 2rem; font-weight: 800; letter-spacing: -0.5px; }
  .sub-title  { color: #888; font-size: 0.9rem; margin-top: -12px; }
  .step-box   { border-radius: 6px; padding: 10px 14px; margin: 6px 0; font-size: 0.88rem; }
  .step-wait  { background: #1e1e2e; color: #666; }
  .step-run   { background: #1a2a1a; color: #ffd700; border-left: 3px solid #ffd700; }
  .step-done  { background: #0d1f18; color: #00d48a; border-left: 3px solid #00d48a; }
  .step-warn  { background: #1f1a0d; color: #ffa500; border-left: 3px solid #ffa500; }
  .step-kill  { background: #1f0d0d; color: #ff4444; border-left: 3px solid #ff4444; }
  .step-time  { color: #667; font-size: 0.78rem; float: right; }
  .ticket-box { border: 1.5px solid #00d48a; border-radius: 10px; padding: 22px; background: #0a0f0a; }
  .kill-box   { border: 1.5px solid #ff4444; border-radius: 10px; padding: 22px; background: #1a0505; }
  .badge-buy  { background: #00d48a22; color: #00d48a; padding: 4px 14px; border-radius: 20px;
                font-weight: 800; font-size: 1.1rem; border: 1px solid #00d48a; }
  .badge-sell { background: #ff444422; color: #ff4444; padding: 4px 14px; border-radius: 20px;
                font-weight: 800; font-size: 1.1rem; border: 1px solid #ff4444; }
  .badge-hold { background: #ffd70022; color: #ffd700; padding: 4px 14px; border-radius: 20px;
                font-weight: 800; font-size: 1.1rem; border: 1px solid #ffd700; }
  .metric-label { color: #888; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.5px; }
  .metric-value { font-size: 1.4rem; font-weight: 700; margin-top: 2px; }
  .citation    { background: #12181f; border-left: 3px solid #4488cc; padding: 8px 12px;
                 margin: 5px 0; border-radius: 0 6px 6px 0; font-size: 0.83rem; }
  .peer-up   { color: #00d48a; font-weight: 600; }
  .peer-down { color: #ff4444; font-weight: 600; }
  .peer-chip { background: #12181f; border-radius: 6px; padding: 6px 12px; margin: 3px;
               display: inline-block; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

STEP_LABELS = {
    "fetch_filing":        "1  Fetch Filing from EDGAR",
    "classify_event":      "2  Classify Event (LLM)",
    "retrieval_analogues": "3  Retrieve Historical Analogues",
    "retrieval_mandate":   "4  Load Governing Documents",
    "size_position":       "5  Size Position (Kelly + HV20)",
    "compliance_gate":     "6  Compliance Gate",
    "freshness_check":     "7  Freshness Check (Recent Filings)",
    "generate_ticket":     "8  Generate Trade Ticket",
}

STEP_ICONS = {
    "pending": "○",
    "running": "◎",
    "done":    "✓",
    "warning": "△",
    "killed":  "✕",
    "error":   "✕",
}

STEP_CLASSES = {
    "pending": "step-wait",
    "running": "step-run",
    "done":    "step-done",
    "warning": "step-warn",
    "killed":  "step-kill",
    "error":   "step-kill",
}

CONF_BANDS = [(65, "#00d48a"), (45, "#ffd700"), (0, "#ff4444")]


def conf_color(score: float) -> str:
    for floor, color in CONF_BANDS:
        if score >= floor:
            return color
    return CONF_BANDS[-1][1]


def load_demo_events() -> list[dict]:
    with open(DEMO_EVENTS_PATH) as f:
        return json.load(f)


def render_steps(step_states: dict, step_data: dict):
    for step in PIPELINE_STEPS:
        state = step_states.get(step, "pending")
        label = STEP_LABELS[step]
        icon = STEP_ICONS.get(state, "○")
        css = STEP_CLASSES.get(state, "step-wait")
        data = step_data.get(step, {})

        detail = ""
        if state == "done" and data:
            snippets = []
            for k, v in data.items():
                if k not in ("error", "fallback", "skipped", "elapsed_s"):
                    snippets.append(f"{k}: {v}")
            if snippets:
                detail = f" — {', '.join(snippets[:3])}"
        elif state in ("warning", "error", "killed") and data.get("error"):
            detail = f" — {data['error']}"
        elif state == "killed" and data.get("reason"):
            detail = f" — {data['reason']}"

        timing = ""
        if data.get("elapsed_s") is not None and state != "running":
            timing = f'<span class="step-time">{data["elapsed_s"]:.1f}s</span>'

        st.markdown(
            f'<div class="step-box {css}">{timing}{icon}  {label}{detail}</div>',
            unsafe_allow_html=True,
        )


def render_confidence_gauge(confidence: int):
    color = conf_color(confidence)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=confidence,
        number={"font": {"color": "#e8e8e8", "size": 40}, "suffix": "/100"},
        gauge={
            "axis": {
                "range": [0, 100],
                "tickcolor": "#556",
                "tickfont": {"color": "#889", "size": 10},
            },
            "bar": {"color": color, "thickness": 0.35},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            # Low-alpha threshold bands; the printed number carries the value,
            # color is a redundant status cue.
            "steps": [
                {"range": [0, 45], "color": "rgba(255, 68, 68, 0.10)"},
                {"range": [45, 65], "color": "rgba(255, 215, 0, 0.10)"},
                {"range": [65, 100], "color": "rgba(0, 212, 138, 0.10)"},
            ],
        },
    ))
    fig.update_layout(
        height=170,
        margin=dict(t=24, b=6, l=24, r=24),
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e8e8e8"},
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_peer_ripple(top_analogues: list[dict]):
    """Average 1-day peer reactions across the matched analogues."""
    peer_sums: dict[str, list[float]] = {}
    for a in top_analogues:
        for peer, reaction in (a.get("peer_reaction_1d") or {}).items():
            peer_sums.setdefault(peer, []).append(float(reaction))
    if not peer_sums:
        return

    st.markdown("**Peer Ripple Effect** — avg next-day peer moves in analogue events")
    chips = []
    for peer, vals in sorted(peer_sums.items(), key=lambda kv: -abs(sum(kv[1]) / len(kv[1]))):
        avg = sum(vals) / len(vals)
        cls = "peer-up" if avg >= 0 else "peer-down"
        arrow = "▲" if avg >= 0 else "▼"
        chips.append(
            f'<span class="peer-chip">{peer} <span class="{cls}">{arrow} {avg:+.1%}</span></span>'
        )
    st.markdown(" ".join(chips), unsafe_allow_html=True)


def render_ticket(ticket: dict):
    direction = ticket.get("direction", "HOLD")
    badge_class = {"BUY": "badge-buy", "SELL": "badge-sell"}.get(direction, "badge-hold")
    confidence = ticket.get("confidence_score", 0)

    st.markdown('<div class="ticket-box">', unsafe_allow_html=True)

    col_dir, col_ticker, col_gauge = st.columns([1, 1.2, 2])
    with col_dir:
        st.markdown(f'<span class="{badge_class}">{direction}</span>', unsafe_allow_html=True)
    with col_ticker:
        st.markdown(
            f'<div class="metric-label">Ticker</div>'
            f'<div class="metric-value">{ticket["ticker"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="metric-label" style="margin-top:8px">Confidence</div>',
            unsafe_allow_html=True,
        )
    with col_gauge:
        render_confidence_gauge(confidence)

    st.markdown("**Thesis**")
    st.info(ticket.get("thesis", ""))

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Entry Price", f"${ticket.get('entry_price', 0):,.2f}")
    with m2:
        st.metric("Shares", f"{ticket.get('shares', 0):,}")
    with m3:
        st.metric("Position", f"${ticket.get('position_value_usd', 0):,.0f}")
    with m4:
        st.metric("Stop Loss", f"${ticket.get('stop_loss', 0):,.2f}")
    with m5:
        st.metric("Target", f"${ticket.get('price_target', 0):,.2f}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**HV20 (annualized):** {ticket.get('hv20', 0):.1%}")
        st.markdown(f"**Kelly fraction:** {ticket.get('kelly_fraction', 0):.1%}")
        st.markdown(f"**Mandate:** {ticket.get('mandate_status', '—')}")
        st.markdown(f"**Freshness:** {ticket.get('freshness_status', '—')}")
    with col_b:
        st.markdown("**Risk Factors**")
        for rf in ticket.get("risk_factors", []):
            st.markdown(f"- {rf}")

    analogue_summary = ticket.get("analogue_summary", {})
    top_analogues = analogue_summary.get("top_analogues", [])
    if analogue_summary.get("sample_size", 0) > 0:
        st.markdown("**Analogue Baseline**")
        ac1, ac2, ac3, ac4 = st.columns(4)
        ac1.metric("Sample Size", analogue_summary.get("sample_size", 0))
        ac2.metric("Median +1d", analogue_summary.get("median_1d_return", "—"))
        ac3.metric("Median +5d", analogue_summary.get("median_5d_return", "—"))
        ac4.metric("Median +20d", analogue_summary.get("median_20d_return", "—"))

        if top_analogues:
            st.dataframe(
                [
                    {
                        "Event": a.get("event", ""),
                        "Ticker": a.get("ticker", ""),
                        "Date": a.get("date", ""),
                        "Similarity": a.get("similarity", 0),
                        "+1d": a.get("1d_return", "—"),
                        "+5d": a.get("5d_return", "—"),
                    }
                    for a in top_analogues
                ],
                use_container_width=True,
                hide_index=True,
            )
            render_peer_ripple(top_analogues)

    if ticket.get("citations"):
        with st.expander("Citation Trail", expanded=True):
            for cite in ticket["citations"]:
                st.markdown(
                    f'<div class="citation">'
                    f'<strong>{cite.get("source", "")}</strong><br>{cite.get("excerpt", "")}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    st.markdown(
        f'<div style="color:#666;font-size:0.75rem;margin-top:12px">'
        f'Filing: {ticket.get("accession_number", "")} | '
        f'Filed: {ticket.get("filing_date", "")} | '
        f'Generated: {ticket.get("generated_at", "")[:19]}Z'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.download_button(
        "⬇ Export Ticket JSON",
        data=json.dumps(ticket, indent=2),
        file_name=f"{ticket['ticker']}_{ticket.get('filing_date', 'ticket')}.json",
        mime="application/json",
    )


def render_kill(result: dict):
    st.markdown(
        f'<div class="kill-box">'
        f'<span style="color:#ff4444;font-size:1.2rem;font-weight:800">TRADE KILLED</span><br><br>'
        f'<strong>Stage:</strong> {result.get("stage", "unknown")}<br>'
        f'<strong>Reason:</strong> {result.get("reason", "")}'
        + (f'<br><br><em>Mandate rule: {result["mandate_excerpt"]}</em>' if result.get("mandate_excerpt") else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def render_result(result: dict):
    if result["status"] == "TICKET":
        render_ticket(result["ticket"])
    elif result["status"] == "KILLED":
        render_kill(result)
    elif result["status"] == "SKIPPED":
        st.info(f"Skipped: {result.get('reason', '')}")
    else:
        st.error(f"Error: {result.get('reason', '')}")


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## Signal-to-Ticket")
    st.markdown("*Event-driven quant agent*")
    st.divider()

    mode = st.radio("Trigger mode", ["Demo event", "Live ticker"], index=0)

    demo_events = load_demo_events()

    if mode == "Demo event":
        demo_labels = [e["label"] for e in demo_events]
        selected_label = st.selectbox("Select event", demo_labels)
        selected_event = next(e for e in demo_events if e["label"] == selected_label)
        ticker_input = selected_event["ticker"]
        st.caption(f"**{selected_event['event_type'].replace('_', ' ').title()}** · {selected_event['filing_date']}")
        st.caption(selected_event["description"])
    else:
        ticker_input = st.text_input("Ticker", value="NVDA", max_chars=10).upper()
        selected_event = None
        st.caption("Fetches the most recent 8-K from EDGAR live.")

    run_btn = st.button("Run Agent", type="primary", use_container_width=True)

    st.divider()
    with st.expander("How the agent works"):
        st.markdown(
            "The agent treats an 8-K filing as a trading signal and runs it through "
            "an 8-step gauntlet before any ticket is issued.\n\n"
            "**Sizing** uses the Kelly criterion at half strength — full Kelly is "
            "growth-optimal but punishing when win-rate estimates are off, so "
            "half-Kelly is the institutional norm. Size is then scaled down when "
            "20-day realized volatility (HV20) runs above a 20% baseline.\n\n"
            "**Analogues** come from a vector search over historical filing events "
            "with known price reactions — the median 5-day move of the closest "
            "matches anchors the expected return.\n\n"
            "**Compliance** is a hard gate: an LLM reads the fund mandate and kills "
            "any trade violating a hard rule, no matter how strong the signal."
        )
    st.caption("Data: SEC EDGAR · LLM: Vultr Serverless Inference · Vectors: ChromaDB")

# ── Main panel ───────────────────────────────────────────────────────────────

st.markdown('<div class="main-title">Signal-to-Ticket</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Event-driven trade agent · 8-K → compliance → ticket</div>', unsafe_allow_html=True)
st.divider()

if "step_states" not in st.session_state:
    st.session_state.step_states = {s: "pending" for s in PIPELINE_STEPS}
    st.session_state.step_data = {s: {} for s in PIPELINE_STEPS}
    st.session_state.result = None
    st.session_state.history = []

tab_run, tab_history = st.tabs(["Agent Run", f"History ({len(st.session_state.history)})"])

with tab_run:
    col_pipeline, col_result = st.columns([1, 1.6], gap="large")

    with col_pipeline:
        st.markdown("#### Agent Pipeline")
        pipeline_placeholder = st.empty()

    with col_result:
        st.markdown("#### Result")
        result_placeholder = st.empty()

    with pipeline_placeholder.container():
        render_steps(st.session_state.step_states, st.session_state.step_data)

    if st.session_state.result and not run_btn:
        with result_placeholder.container():
            render_result(st.session_state.result)

with tab_history:
    if not st.session_state.history:
        st.caption("No runs yet this session.")
    else:
        st.dataframe(
            [
                {
                    "Time": h["time"],
                    "Ticker": h["ticker"],
                    "Event": h["event_type"],
                    "Outcome": h["outcome"],
                    "Direction": h["direction"],
                    "Confidence": h["confidence"],
                    "Position": h["position"],
                }
                for h in reversed(st.session_state.history)
            ],
            use_container_width=True,
            hide_index=True,
        )

# ── Agent execution ───────────────────────────────────────────────────────────

if run_btn:
    st.session_state.step_states = {s: "pending" for s in PIPELINE_STEPS}
    st.session_state.step_data = {s: {} for s in PIPELINE_STEPS}
    st.session_state.result = None

    with result_placeholder.container():
        st.markdown("*Running agent...*")

    filing_arg = None
    if mode == "Demo event" and selected_event:
        filing_arg = {
            "ticker": selected_event["ticker"],
            "cik": selected_event["cik"],
            "filing_date": selected_event["filing_date"],
            "accession": selected_event["accession"],
            "primary_document": selected_event.get("primary_document", ""),
            "items": selected_event.get("items", ""),
        }
        # Inject pre-loaded text so demo events never depend on live EDGAR
        if selected_event.get("use_pre_loaded_text") and selected_event.get("pre_loaded_text"):
            filing_arg["_pre_loaded_text"] = selected_event["pre_loaded_text"]

    def on_step(name: str, status: str, data: dict):
        st.session_state.step_states[name] = status
        st.session_state.step_data[name] = data
        with pipeline_placeholder.container():
            render_steps(st.session_state.step_states, st.session_state.step_data)

    result = run_agent(ticker=ticker_input, filing=filing_arg, on_step=on_step)

    st.session_state.result = result

    ticket = result.get("ticket", {})
    st.session_state.history.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "ticker": ticker_input,
        "event_type": st.session_state.step_data.get("classify_event", {}).get("event_type", "—"),
        "outcome": result["status"],
        "direction": ticket.get("direction", "—"),
        "confidence": ticket.get("confidence_score", "—"),
        "position": f"${ticket.get('position_value_usd', 0):,.0f}" if ticket else "—",
    })
    st.session_state.history = st.session_state.history[-8:]

    with result_placeholder.container():
        render_result(result)
