import os
import re
import time
from contextlib import asynccontextmanager

from bson import ObjectId
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from motor.motor_asyncio import AsyncIOMotorClient

# NOTE: sip_bridge (Twilio) intentionally NOT wired in for this local test run,
# per instruction to exclude Twilio setup. Re-add once numbers/Twilio are configured:
# from sip_bridge import router as twilio_sip_router
# app.include_router(twilio_sip_router)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")  # optional

URDU_RANGE_RE = re.compile(r"[\u0600-\u06FF]")


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client["voice_agent_db"]
    calls = db["calls"]

    await calls.create_index("created_at")
    await calls.create_index("status")
    await calls.create_index("caller_number")

    app.state.mongo_client = client
    app.state.calls = calls
    try:
        yield
    finally:
        client.close()


app = FastAPI(title="AI Voice Calling Agent - Approval Dashboard", lifespan=lifespan)


def notify_slack(call_id: str, summary: dict):
    """Optional: pings Slack when a new call summary lands. Safe no-op if not configured."""
    if not SLACK_WEBHOOK_URL:
        return
    try:
        import json
        import urllib.request

        text = (
            f"New call awaiting review (id: {call_id})\n"
            f"From: {summary.get('caller_number', 'unknown')}\n"
            f"Project: {summary.get('project_type')}\n"
            f"Agreed price: {summary.get('agreed_price')}\n"
            f"Review here: /"
        )
        data = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        # Never let a notification failure break the webhook itself
        pass


@app.post("/webhook/call-summary")
async def receive_call_summary(request: Request):
    """
    The agent's submit_call_summary tool POSTs here with a structured JSON
    summary at the end of a call. Expected shape:
    {
        "caller_number": "+15105550100",   # or SIP identity / "unknown" locally
        "project_type": "custom_software",
        "agreed_price": "2000 USD",
        "timeline": "6-8 weeks",
        "notes": "client wants Next.js frontend",
        "transcript_summary": "short human-readable recap"
    }
    """
    payload = await request.json()

    doc = {
        "caller_number": payload.get("caller_number", "unknown"),
        "project_type": payload.get("project_type", ""),
        "agreed_price": payload.get("agreed_price", ""),
        "timeline": payload.get("timeline", ""),
        "notes": payload.get("notes", ""),
        "transcript_summary": payload.get("transcript_summary", ""),
        "raw_json": payload,
        "status": "pending",
        "created_at": time.time(),
    }

    result = await request.app.state.calls.insert_one(doc)
    call_id = str(result.inserted_id)

    notify_slack(call_id, payload)
    return {"status": "received", "call_id": call_id}


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

STATUS_META = {
    "pending":     {"label": "Pending",     "class": "st-pending"},
    "approved":    {"label": "Approved",    "class": "st-approved"},
    "rejected":    {"label": "Rejected",    "class": "st-rejected"},
    "renegotiate": {"label": "Renegotiate", "class": "st-renegotiate"},
}


def _text_dir_attrs(text: str) -> str:
    """Right-align + Nastaliq font when the field is actually Urdu script."""
    if text and URDU_RANGE_RE.search(text):
        return 'dir="rtl" lang="ur" class="urdu-text"'
    return 'dir="ltr"'


def render_card(doc) -> str:
    call_id = str(doc["_id"])
    ts = time.strftime("%b %d, %H:%M", time.localtime(doc.get("created_at", 0)))
    status = doc.get("status", "pending")
    meta = STATUS_META.get(status, STATUS_META["pending"])

    summary_text = doc.get("transcript_summary") or doc.get("notes") or "No summary provided."
    summary_attrs = _text_dir_attrs(summary_text)

    pulse = (
        '<span class="pulse" aria-hidden="true">'
        '<span></span><span></span><span></span><span></span>'
        "</span>"
        if status == "pending"
        else ""
    )

    actions = ""
    if status in ("pending", "renegotiate"):
        actions = f"""
        <div class="actions">
            <form method="post" action="/decision/{call_id}">
                <input type="hidden" name="action" value="approve">
                <button type="submit" class="btn btn-approve">Accept</button>
            </form>
            <form method="post" action="/decision/{call_id}">
                <input type="hidden" name="action" value="renegotiate">
                <button type="submit" class="btn btn-renegotiate">Renegotiate</button>
            </form>
            <form method="post" action="/decision/{call_id}">
                <input type="hidden" name="action" value="reject">
                <button type="submit" class="btn btn-reject">Reject</button>
            </form>
        </div>
        """

    project = doc.get("project_type") or "\u2014"
    price = doc.get("agreed_price") or "\u2014"
    timeline = doc.get("timeline") or "\u2014"
    caller = doc.get("caller_number") or "\u2014"

    return f"""
    <article class="card" data-status="{status}">
        <header class="card-head">
            <div class="card-head-left">
                <span class="status-pill {meta['class']}">{pulse}{meta['label']}</span>
                <time class="card-time">{ts}</time>
            </div>
            <span class="caller" title="Caller">{caller}</span>
        </header>

        <div class="card-body">
            <dl class="deal-terms">
                <div>
                    <dt>Project</dt>
                    <dd>{project}</dd>
                </div>
                <div>
                    <dt>Price</dt>
                    <dd class="mono">{price}</dd>
                </div>
                <div>
                    <dt>Timeline</dt>
                    <dd class="mono">{timeline}</dd>
                </div>
            </dl>
            <p class="summary" {summary_attrs}>{summary_text}</p>
        </div>

        {actions}
    </article>
    """


PAGE_SHELL_HEAD = """
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Deal Approvals \u2014 Voice Agent</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Noto+Nastaliq+Urdu:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #F3F5F8;
            --surface: #FFFFFF;
            --ink: #10233D;
            --ink-soft: #55647A;
            --line: #E3E8EF;
            --brand: #1B3A5C;
            --approve: #1E7F5C;
            --approve-bg: #E7F5EF;
            --renegotiate: #B7791F;
            --renegotiate-bg: #FCF3E1;
            --reject: #B3372C;
            --reject-bg: #FBEAE8;
            --pending: #8A6D00;
            --pending-bg: #FBF4DD;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            background: var(--bg);
            color: var(--ink);
            font-family: "IBM Plex Sans", -apple-system, sans-serif;
            -webkit-font-smoothing: antialiased;
        }
        .mono { font-family: "IBM Plex Mono", monospace; font-size: 13.5px; }

        header.top {
            position: sticky;
            top: 0;
            z-index: 10;
            background: var(--surface);
            border-bottom: 1px solid var(--line);
            padding: 18px 20px 14px;
        }
        .top-inner { max-width: 880px; margin: 0 auto; }
        h1 {
            font-family: "Fraunces", serif;
            font-weight: 600;
            font-size: 22px;
            margin: 0 0 2px;
            letter-spacing: -0.01em;
        }
        .tagline { color: var(--ink-soft); font-size: 13.5px; margin: 0 0 14px; }

        .filters {
            display: flex;
            gap: 6px;
            overflow-x: auto;
            padding-bottom: 2px;
        }
        .filter-pill {
            flex: 0 0 auto;
            border: 1px solid var(--line);
            background: var(--bg);
            color: var(--ink-soft);
            font-size: 13px;
            font-weight: 500;
            padding: 7px 13px;
            border-radius: 999px;
            cursor: pointer;
            white-space: nowrap;
            transition: background 0.15s, color 0.15s, border-color 0.15s;
        }
        .filter-pill.active {
            background: var(--brand);
            border-color: var(--brand);
            color: #fff;
        }
        .filter-pill .count { opacity: 0.7; margin-left: 4px; }

        main { max-width: 880px; margin: 0 auto; padding: 18px 16px 60px; }

        .card {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 16px 18px;
            margin-bottom: 12px;
            box-shadow: 0 1px 2px rgba(16, 35, 61, 0.04);
        }
        .card-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 12px;
        }
        .card-head-left { display: flex; align-items: center; gap: 10px; }
        .card-time { color: var(--ink-soft); font-size: 12.5px; font-family: "IBM Plex Mono", monospace; }
        .caller { font-family: "IBM Plex Mono", monospace; font-size: 13px; color: var(--ink-soft); }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11.5px;
            font-weight: 600;
            letter-spacing: 0.03em;
            text-transform: uppercase;
            padding: 4px 9px;
            border-radius: 999px;
        }
        .st-pending { background: var(--pending-bg); color: var(--pending); }
        .st-approved { background: var(--approve-bg); color: var(--approve); }
        .st-rejected { background: var(--reject-bg); color: var(--reject); }
        .st-renegotiate { background: var(--renegotiate-bg); color: var(--renegotiate); }

        /* Signature element: small waveform pulse for calls awaiting a decision */
        .pulse { display: inline-flex; align-items: flex-end; gap: 2px; height: 9px; }
        .pulse span {
            width: 2px;
            background: var(--pending);
            border-radius: 1px;
            animation: wave 0.9s ease-in-out infinite;
        }
        .pulse span:nth-child(1) { height: 4px; animation-delay: 0s; }
        .pulse span:nth-child(2) { height: 9px; animation-delay: 0.15s; }
        .pulse span:nth-child(3) { height: 6px; animation-delay: 0.3s; }
        .pulse span:nth-child(4) { height: 8px; animation-delay: 0.45s; }
        @keyframes wave {
            0%, 100% { transform: scaleY(0.5); }
            50% { transform: scaleY(1); }
        }
        @media (prefers-reduced-motion: reduce) {
            .pulse span { animation: none; }
        }

        .deal-terms {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin: 0 0 12px;
            padding: 12px;
            background: var(--bg);
            border-radius: 10px;
        }
        .deal-terms dt {
            font-size: 11px;
            color: var(--ink-soft);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 3px;
        }
        .deal-terms dd { margin: 0; font-size: 14px; font-weight: 500; }

        .summary {
            font-size: 14px;
            line-height: 1.55;
            color: var(--ink);
            margin: 0;
        }
        .summary.urdu-text {
            font-family: "Noto Nastaliq Urdu", serif;
            font-size: 17px;
            line-height: 2;
            text-align: right;
        }

        .actions {
            display: flex;
            gap: 8px;
            margin-top: 14px;
            padding-top: 14px;
            border-top: 1px solid var(--line);
        }
        .actions form { flex: 1; }
        .btn {
            width: 100%;
            border: none;
            border-radius: 9px;
            padding: 11px 10px;
            font-size: 13.5px;
            font-weight: 600;
            cursor: pointer;
            transition: filter 0.15s, transform 0.1s;
        }
        .btn:active { transform: scale(0.97); }
        .btn-approve { background: var(--approve); color: #fff; }
        .btn-renegotiate { background: var(--renegotiate); color: #fff; }
        .btn-reject { background: transparent; color: var(--reject); border: 1px solid var(--reject-bg); }
        .btn:hover { filter: brightness(1.08); }
        .btn:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }

        .empty {
            text-align: center;
            padding: 60px 20px;
            color: var(--ink-soft);
        }
        .empty .pulse { justify-content: center; margin-bottom: 10px; }

        @media (min-width: 640px) {
            main { padding: 24px 24px 70px; }
            h1 { font-size: 25px; }
        }
    </style>
</head>
"""

FILTER_BAR = """
<div class="filters" role="tablist" aria-label="Filter deals by status">
    <button class="filter-pill active" data-filter="all" role="tab">All <span class="count" id="count-all"></span></button>
    <button class="filter-pill" data-filter="pending" role="tab">Pending <span class="count" id="count-pending"></span></button>
    <button class="filter-pill" data-filter="renegotiate" role="tab">Renegotiate <span class="count" id="count-renegotiate"></span></button>
    <button class="filter-pill" data-filter="approved" role="tab">Approved <span class="count" id="count-approved"></span></button>
    <button class="filter-pill" data-filter="rejected" role="tab">Rejected <span class="count" id="count-rejected"></span></button>
</div>
"""

PAGE_SCRIPT = """
<script>
(function () {
    const grid = document.getElementById('deal-grid');
    const pills = document.querySelectorAll('.filter-pill');
    let activeFilter = 'all';

    function applyFilter() {
        const cards = grid.querySelectorAll('.card');
        let visible = 0;
        cards.forEach(c => {
            const show = activeFilter === 'all' || c.dataset.status === activeFilter;
            c.style.display = show ? '' : 'none';
            if (show) visible++;
        });
        grid.querySelector('.empty')?.remove();
        if (visible === 0) {
            const empty = document.createElement('div');
            empty.className = 'empty';
            empty.innerHTML = '<div class="pulse"><span></span><span></span><span></span><span></span></div>No calls in this view yet.';
            grid.appendChild(empty);
        }
    }

    function updateCounts() {
        const cards = grid.querySelectorAll('.card');
        const counts = { all: cards.length, pending: 0, approved: 0, rejected: 0, renegotiate: 0 };
        cards.forEach(c => { counts[c.dataset.status] = (counts[c.dataset.status] || 0) + 1; });
        Object.keys(counts).forEach(k => {
            const el = document.getElementById('count-' + k);
            if (el) el.textContent = counts[k] ? '(' + counts[k] + ')' : '';
        });
    }

    pills.forEach(p => p.addEventListener('click', () => {
        pills.forEach(x => x.classList.remove('active'));
        p.classList.add('active');
        activeFilter = p.dataset.filter;
        applyFilter();
    }));

    updateCounts();
    applyFilter();

    // Poll for fresh data every 8s without a full page reload / lost scroll position.
    async function poll() {
        try {
            const res = await fetch('/api/deals');
            const data = await res.json();
            if (data.html !== grid.dataset.lastHtml) {
                grid.dataset.lastHtml = data.html;
                grid.innerHTML = data.html;
                updateCounts();
                applyFilter();
            }
        } catch (e) { /* silent: keep last known good state */ }
    }
    setInterval(poll, 8000);
})();
</script>
"""


def _render_cards_html(docs) -> str:
    return "".join(render_card(d) for d in docs) or (
        '<div class="empty">'
        '<div class="pulse"><span></span><span></span><span></span><span></span></div>'
        "No calls yet. They'll appear here the moment the agent logs one."
        "</div>"
    )


@app.get("/api/deals")
async def api_deals(request: Request):
    cursor = request.app.state.calls.find().sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return JSONResponse({"html": _render_cards_html(docs)})


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    cursor = request.app.state.calls.find().sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    cards_html = _render_cards_html(docs)

    return f"""
    <html>
    {PAGE_SHELL_HEAD}
    <body>
        <header class="top">
            <div class="top-inner">
                <h1>Deal Approvals</h1>
                <p class="tagline">No agreement reaches a client until you accept it here.</p>
                {FILTER_BAR}
            </div>
        </header>
        <main>
            <div id="deal-grid">{cards_html}</div>
        </main>
        {PAGE_SCRIPT}
    </body>
    </html>
    """


@app.post("/decision/{call_id}")
async def decide(call_id: str, request: Request, action: str = Form(...)):
    if action not in ("approve", "reject", "renegotiate"):
        return RedirectResponse(url="/", status_code=303)

    status = {"approve": "approved", "reject": "rejected", "renegotiate": "renegotiate"}[action]

    await request.app.state.calls.update_one(
        {"_id": ObjectId(call_id)}, {"$set": {"status": status}}
    )
    # TODO: once approved, trigger actual contract/email generation here.
    # TODO: once renegotiate, notify Talha's model/dashboard to re-open the deal terms.
    return RedirectResponse(url="/", status_code=303)


@app.get("/health")
async def health():
    return {"ok": True}
