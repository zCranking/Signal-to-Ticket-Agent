"""Signal-to-Ticket | Streamlit demo UI."""
import json
import sys
import time
from pathlib import Path

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
                if k not in ("error", "fallback", "skipped"):
                    snippets.append(f"{k}: {v}")
            if snippets:
                detail = f" — {', '.join(snippets[:3])}"
        elif state in ("warning", "error", "killed") and data.get("error"):
            detail = f" — {data['error']}"
        elif state == "killed" and data.get("reason"):
            detail = f" — {data['reason']}"

        st.markdown(
            f'<div class="step-box {css}">{icon}  {label}{detail}</div>',
            unsafe_allow_html=True,
        )


def render_ticket(ticket: dict):
    direction = ticket.get("direction", "HOLD")
    badge_class = {"BUY": "badge-buy", "SELL": "badge-sell"}.get(direction, "badge-hold")
    confidence = ticket.get("confidence_score", 0)

    st.markdown('<div class="ticket-box">', unsafe_allow_html=True)

    col_dir, col_ticker, col_conf = st.columns([1, 2, 2])
    with col_dir:
        st.markdown(f'<span class="{badge_class}">{direction}</span>', unsafe_allow_html=True)
    with col_ticker:
        st.markdown(
            f'<div class="metric-label">Ticker</div>'
            f'<div class="metric-value">{ticket["ticker"]}</div>',
            unsafe_allow_html=True,
        )
    with col_conf:
        conf_color = "#00d48a" if confidence >= 65 else ("#ffd700" if confidence >= 45 else "#ff4444")
        st.markdown(
            f'<div class="metric-label">Confidence</div>'
            f'<div class="metric-value" style="color:{conf_color}">{confidence}/100</div>',
            unsafe_allow_html=True,
        )

    st.progress(confidence / 100)

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
    if analogue_summary.get("sample_size", 0) > 0:
        st.markdown("**Analogue Baseline**")
        ac1, ac2, ac3, ac4 = st.columns(4)
        ac1.metric("Sample Size", analogue_summary.get("sample_size", 0))
        ac2.metric("Median +1d", analogue_summary.get("median_1d_return", "—"))
        ac3.metric("Median +5d", analogue_summary.get("median_5d_return", "—"))
        ac4.metric("Median +20d", analogue_summary.get("median_20d_return", "—"))

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
    st.caption("Partners: Crusoe · Vultr · SEC EDGAR")

# ── Main panel ───────────────────────────────────────────────────────────────

st.markdown('<div class="main-title">Signal-to-Ticket</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Event-driven trade agent · 8-K → compliance → ticket</div>', unsafe_allow_html=True)
st.divider()

col_pipeline, col_result = st.columns([1, 1.6], gap="large")

with col_pipeline:
    st.markdown("#### Agent Pipeline")
    pipeline_placeholder = st.empty()

with col_result:
    st.markdown("#### Result")
    result_placeholder = st.empty()

# Initialize step display
if "step_states" not in st.session_state:
    st.session_state.step_states = {s: "pending" for s in PIPELINE_STEPS}
    st.session_state.step_data = {s: {} for s in PIPELINE_STEPS}
    st.session_state.result = None

with pipeline_placeholder.container():
    render_steps(st.session_state.step_states, st.session_state.step_data)

if st.session_state.result:
    with result_placeholder.container():
        r = st.session_state.result
        if r["status"] == "TICKET":
            render_ticket(r["ticket"])
        elif r["status"] == "KILLED":
            render_kill(r)
        elif r["status"] == "SKIPPED":
            st.info(f"Skipped: {r.get('reason', '')}")
        else:
            st.error(f"Error: {r.get('reason', '')}")

# ── Agent execution ───────────────────────────────────────────────────────────

if run_btn:
    # Reset state
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
        # Inject pre-loaded text so we don't need live EDGAR for demo events
        if selected_event.get("use_pre_loaded_text") and selected_event.get("pre_loaded_text"):
            filing_arg["_pre_loaded_text"] = selected_event["pre_loaded_text"]

    def on_step(name: str, status: str, data: dict):
        st.session_state.step_states[name] = status
        st.session_state.step_data[name] = data
        with pipeline_placeholder.container():
            render_steps(st.session_state.step_states, st.session_state.step_data)

    result = run_agent(ticker=ticker_input, filing=filing_arg, on_step=on_step)

    st.session_state.result = result

    with result_placeholder.container():
        if result["status"] == "TICKET":
            render_ticket(result["ticket"])
        elif result["status"] == "KILLED":
            render_kill(result)
        elif result["status"] == "SKIPPED":
            st.info(f"Skipped: {result.get('reason', '')}")
        else:
            st.error(f"Error: {result.get('reason', '')}")
