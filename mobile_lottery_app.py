import json
import random
import re
import urllib.request
import streamlit as st

# --- PAGE CONFIGURATION (Mobile-First) ---
st.set_page_config(
    page_title="LotteryWheel Pro",
    page_icon="🎱",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom CSS for clean mobile buttons and number pills
st.markdown("""
    <style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .ticket-card {
        background-color: #1e2130;
        border: 1px solid #31364f;
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 10px;
        font-family: 'Courier New', monospace;
    }
    .ball-num {
        display: inline-block;
        background-color: #ffffff;
        color: #111111;
        font-weight: bold;
        border-radius: 50%;
        width: 32px;
        height: 32px;
        line-height: 32px;
        text-align: center;
        margin-right: 5px;
        font-size: 15px;
    }
    .bonus-num {
        display: inline-block;
        background-color: #e63946;
        color: #ffffff;
        font-weight: bold;
        border-radius: 50%;
        width: 32px;
        height: 32px;
        line-height: 32px;
        text-align: center;
        margin-left: 6px;
        font-size: 15px;
    }
    .meta-line {
        color: #a0a8c0;
        font-size: 12px;
        margin-top: 6px;
    }
    </style>
""", unsafe_allow_html=True)

# --- GAME CONFIGURATIONS (Exact Match to Desktop App) ---
GAME_CONFIGS = {
    "Powerball": {
        "total_balls": 69,
        "pick_count": 5,
        "bonus_balls": 26,
        "bonus_name": "PB",
        "default_window": 14,
        "default_tickets": 4,
        "default_hot": 6,
        "default_warm": 7,
        "default_cold": 3,
        "min_sum": 115,
        "max_sum": 235,
        "api_url": "https://data.ny.gov/resource/d6yy-54nr.json?$limit=150&$order=draw_date%20DESC",
        "field_numbers": "winning_numbers",
        "field_bonus": ""
    },
    "Mega Millions": {
        "total_balls": 70,
        "pick_count": 5,
        "bonus_balls": 25,
        "bonus_name": "MB",
        "default_window": 13,
        "default_tickets": 3,
        "default_hot": 5,
        "default_warm": 8,
        "default_cold": 3,
        "min_sum": 120,
        "max_sum": 240,
        "api_url": "https://data.ny.gov/resource/5xaw-6ayf.json?$limit=150&$order=draw_date%20DESC",
        "field_numbers": "winning_numbers",
        "field_bonus": "mega_ball"
    },
    "Florida Lotto": {
        "total_balls": 53,
        "pick_count": 6,
        "bonus_balls": 0,
        "bonus_name": "",
        "default_window": 13,
        "default_tickets": 3,
        "default_hot": 6,
        "default_warm": 7,
        "default_cold": 3,
        "min_sum": 115,
        "max_sum": 205,
        "api_url": "https://www.flalottery.com/exptkt/l6.htm",
        "field_numbers": "",
        "field_bonus": ""
    }
}


# --- DATA FETCHING (Cached for 15 minutes for fast mobile response) ---
@st.cache_data(ttl=900, show_spinner=False)
def fetch_live_draws(game_name):
    cfg = GAME_CONFIGS[game_name]
    try:
        req = urllib.request.Request(
            cfg["api_url"],
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            raw_text = resp.read().decode("utf-8", errors="ignore")
            new_draws = []

            if cfg["api_url"].endswith(".json") or "$limit=" in cfg["api_url"]:
                data = json.loads(raw_text)
                for item in data:
                    raw_nums = item.get(cfg["field_numbers"], "")
                    parts = [int(x) for x in raw_nums.split() if x.isdigit()]
                    bonus = None
                    b_field = cfg.get("field_bonus", "")
                    if b_field and b_field in item:
                        try:
                            bonus = int(str(item[b_field]).strip())
                        except Exception:
                            bonus = None
                    if bonus is None and len(parts) > cfg["pick_count"]:
                        bonus = parts[cfg["pick_count"]]
                    if len(parts) >= cfg["pick_count"]:
                        new_draws.append((sorted(parts[:cfg["pick_count"]]), bonus))
            else:
                lines = raw_text.splitlines()
                for line in reversed(lines):
                    matches = re.findall(r"\b\d{1,2}\b", line)
                    nums = [int(x) for x in matches if 1 <= int(x) <= cfg["total_balls"]]
                    if len(nums) >= 6:
                        cand = sorted(list(dict.fromkeys(nums[-6:])))
                        if len(cand) == 6:
                            new_draws.append((cand, None))
                            if len(new_draws) >= 120:
                                break

            if len(new_draws) >= 15:
                return new_draws, True
    except Exception:
        pass

    # Fallback data if offline
    rng = random.Random(101)
    fallback = []
    for _ in range(120):
        mb = sorted(rng.sample(range(1, cfg["total_balls"] + 1), cfg["pick_count"]))
        bb = rng.randint(1, cfg["bonus_balls"]) if cfg["bonus_balls"] > 0 else None
        fallback.append((mb, bb))
    return fallback, False


# --- CORE WHEELING & ANALYSIS ENGINE ---
def compute_pools_for_history(cfg, history_slice, window_size):
    active_draws = history_slice[:window_size]
    total_balls = cfg["total_balls"]

    freq = {i: 0 for i in range(1, total_balls + 1)}
    skips = {i: len(history_slice) for i in range(1, total_balls + 1)}

    for draw_idx, (main_balls, _) in enumerate(history_slice):
        for b in main_balls:
            if b in skips and skips[b] == len(history_slice):
                skips[b] = draw_idx

    for main_balls, _ in active_draws:
        for b in main_balls:
            if b in freq:
                freq[b] += 1

    expected_hits = (window_size * cfg["pick_count"]) / total_balls
    hot_thresh = max(2, int(round(expected_hits * 1.3)))
    cold_thresh = max(0, int(round(expected_hits * 0.7)))

    hot_pool = [b for b, cnt in freq.items() if cnt >= hot_thresh]
    warm_pool = [b for b, cnt in freq.items() if cold_thresh <= cnt < hot_thresh]
    cold_pool = [b for b, cnt in freq.items() if cnt < cold_thresh]

    hot_pool.sort(key=lambda x: (-freq[x], skips[x], x))
    warm_pool.sort(key=lambda x: (skips[x], x))
    cold_pool.sort(key=lambda x: (skips[x], x))

    return freq, skips, hot_pool, warm_pool, cold_pool


def has_three_consecutive(combo_s):
    for i in range(len(combo_s) - 2):
        if combo_s[i + 1] - combo_s[i] == 1 and combo_s[i + 2] - combo_s[i + 1] == 1:
            return True
    return False


def is_valid_combination(cfg, combo_s, strict=True):
    pick_count = cfg["pick_count"]
    half_val = cfg["total_balls"] // 2

    odds = sum(1 for x in combo_s if x % 2 != 0)
    if pick_count == 5 and odds not in [2, 3]:
        return False
    elif pick_count == 6 and odds not in [2, 3, 4]:
        return False

    lows = sum(1 for x in combo_s if x <= half_val)
    if pick_count == 5 and lows not in [2, 3]:
        return False
    elif pick_count == 6 and lows not in [2, 3, 4]:
        return False

    if not strict:
        return True

    l_sum = sum(combo_s)
    if not (cfg["min_sum"] <= l_sum <= cfg["max_sum"]):
        return False

    decs = [x // 10 for x in combo_s]
    if any(decs.count(d) > 2 for d in set(decs)):
        return False

    if has_three_consecutive(combo_s):
        return False

    return True


def build_wheeled_tickets(cfg, skips, hot_list, warm_list, cold_list, num_tickets):
    pick_count = cfg["pick_count"]
    h_pool = list(hot_list)
    w_pool = list(warm_list)
    c_pool = list(cold_list)

    combined_pool = list(dict.fromkeys(h_pool + w_pool + c_pool))
    if len(combined_pool) < pick_count + 4:
        extra = [
            b for b in sorted(skips.keys(), key=lambda x: skips[x])
            if b not in combined_pool
        ]
        combined_pool.extend(extra[:(16 - len(combined_pool))])

    total_req = max(1, len(h_pool) + len(w_pool) + len(c_pool))
    q_hot = min(len(h_pool), max(1, round(pick_count * len(h_pool) / total_req)))
    q_cold = min(len(c_pool), max(1 if len(c_pool) > 0 else 0, round(pick_count * len(c_pool) / total_req)))
    q_warm = pick_count - q_hot - q_cold

    while q_warm > len(w_pool) and q_hot < len(h_pool):
        q_warm -= 1
        q_hot += 1
    while q_warm < 0:
        if q_hot > 1:
            q_hot -= 1
        elif q_cold > 0:
            q_cold -= 1
        q_warm += 1

    usage_count = {b: 0 for b in combined_pool}
    used_pairs = set()
    valid_tickets = []
    rng = random.Random()

    for _ in range(num_tickets):
        best_candidate = None
        best_score = 999999

        for attempt in range(400):
            strict_mode = attempt < 300
            try:
                h_sorted = sorted(h_pool, key=lambda x: (usage_count.get(x, 0), rng.random()))
                w_sorted = sorted(w_pool, key=lambda x: (usage_count.get(x, 0), rng.random()))
                c_sorted = sorted(c_pool, key=lambda x: (usage_count.get(x, 0), rng.random()))

                h_slice = h_sorted[:max(q_hot + 2, len(h_sorted))]
                w_slice = w_sorted[:max(q_warm + 2, len(w_sorted))]
                c_slice = c_sorted[:max(q_cold + 1, len(c_sorted))]

                cand = (
                    rng.sample(h_slice, min(q_hot, len(h_slice))) +
                    rng.sample(w_slice, min(q_warm, len(w_slice))) +
                    rng.sample(c_slice, min(q_cold, len(c_slice)))
                )
                if len(cand) < pick_count:
                    rem = [b for b in combined_pool if b not in cand]
                    cand.extend(rng.sample(rem, pick_count - len(cand)))
            except ValueError:
                cand = rng.sample(combined_pool, pick_count)

            combo_s = sorted(cand)
            if combo_s in valid_tickets:
                continue

            if not is_valid_combination(cfg, combo_s, strict=strict_mode):
                continue

            u_score = sum(usage_count.get(x, 0) * 10 for x in combo_s)
            pair_overlap = 0
            for i in range(len(combo_s)):
                for j in range(i + 1, len(combo_s)):
                    if (combo_s[i], combo_s[j]) in used_pairs:
                        pair_overlap += 25

            total_score = u_score + pair_overlap
            if total_score < best_score:
                best_score = total_score
                best_candidate = combo_s
                if total_score == 0:
                    break

        if best_candidate is None:
            best_candidate = sorted(rng.sample(combined_pool, pick_count))

        valid_tickets.append(best_candidate)
        for b in best_candidate:
            usage_count[b] = usage_count.get(b, 0) + 1
        for i in range(len(best_candidate)):
            for j in range(i + 1, len(best_candidate)):
                used_pairs.add((best_candidate[i], best_candidate[j]))

    return valid_tickets, combined_pool, (q_hot, q_warm, q_cold)


# --- MOBILE UI ---
st.markdown("### 🎱 LotteryWheel Mobile")

# 1. Single-Game Selector (Replaces 3-column desktop view)
game_name = st.segmented_control(
    "Select Lottery",
    options=["Powerball", "Mega Millions", "Florida Lotto"],
    default="Powerball",
    label_visibility="collapsed"
)
if not game_name:
    game_name = "Powerball"

cfg = GAME_CONFIGS[game_name]

# Fetch data & handle manual override in session state
state_key = f"custom_draws_{game_name}"
if state_key not in st.session_state:
    st.session_state[state_key] = []

live_draws, is_live = fetch_live_draws(game_name)
draw_history = st.session_state[state_key] + live_draws

# Status Banner
latest_nums = " ".join(f"{x:02d}" for x in draw_history[0][0])
latest_b = f" [{draw_history[0][1]:02d}]" if draw_history[0][1] else ""
status_badge = "🟢 LIVE" if (is_live or st.session_state[state_key]) else "🟠 OFFLINE"
st.caption(f"{status_badge} | Latest: **{latest_nums}{latest_b}** ({len(draw_history)} draws)")

# 2. Quick Window Presets (13 / 26 / 52)
if f"win_{game_name}" not in st.session_state:
    st.session_state[f"win_{game_name}"] = cfg["default_window"]

p_col1, p_col2, p_col3, p_col4 = st.columns(4)
if p_col1.button("13 Draws", use_container_width=True):
    st.session_state[f"win_{game_name}"] = 13
if p_col2.button("26 Draws", use_container_width=True):
    st.session_state[f"win_{game_name}"] = 26
if p_col3.button("52 Draws", use_container_width=True):
    st.session_state[f"win_{game_name}"] = 52
if p_col4.button("🔄 Refresh", use_container_width=True):
    fetch_live_draws.clear()
    st.rerun()

# 3. Compact Controls (2-column mobile grid)
c1, c2 = st.columns(2)
window_size = c1.number_input("Window (Draws)", min_value=5, max_value=75, key=f"win_{game_name}")
num_tickets = c2.number_input("Tickets", min_value=1, max_value=50, value=cfg["default_tickets"], key=f"tkt_{game_name}")

p1, p2, p3 = st.columns(3)
h_req = p1.number_input("Hot", min_value=1, max_value=18, value=cfg["default_hot"], key=f"hot_{game_name}")
w_req = p2.number_input("Warm", min_value=1, max_value=18, value=cfg["default_warm"], key=f"warm_{game_name}")
c_req = p3.number_input("Cold", min_value=1, max_value=12, value=cfg["default_cold"], key=f"cold_{game_name}")

# Compute Pools
freq, skips, hot_pool, warm_pool, cold_pool = compute_pools_for_history(cfg, draw_history, window_size)
chosen_hot = hot_pool[:h_req]
chosen_warm = warm_pool[:w_req]
chosen_cold = cold_pool[:c_req]

# Bonus Ball Analysis
top_bonuses = []
if cfg["bonus_balls"] > 0:
    b_freq = {i: 0 for i in range(1, cfg["bonus_balls"] + 1)}
    b_skips = {i: len(draw_history) for i in range(1, cfg["bonus_balls"] + 1)}
    for idx, (_, bonus) in enumerate(draw_history):
        if bonus and bonus in b_skips and b_skips[bonus] == len(draw_history):
            b_skips[bonus] = idx
    for _, bonus in draw_history[:window_size]:
        if bonus and bonus in b_freq:
            b_freq[bonus] += 1
    ranked_bb = sorted(b_freq.keys(), key=lambda x: (-b_freq[x], b_skips[x]))
    top_bonuses = ranked_bb[:3]

# Collapsible Pool Details & Manual Draw Entry
with st.expander("📊 View Hot / Warm / Cold Pools & Manual Entry"):
    st.markdown(f"**Hot ({len(hot_pool)} avail):** `{chosen_hot}`")
    st.markdown(f"**Warm ({len(warm_pool)} avail):** `{chosen_warm}`")
    st.markdown(f"**Cold ({len(cold_pool)} avail):** `{chosen_cold}`")
    if top_bonuses:
        st.markdown(f"**Top {cfg['bonus_name']}:** `{top_bonuses}`")

    st.divider()
    raw_paste = st.text_area(
        "Paste Recent Draws (Newest first, one per line):",
        placeholder="e.g. 09 44 49 51 68 04",
        height=80,
        key=f"paste_{game_name}"
    )
    if st.button("Add Manual Draws", use_container_width=True):
        parsed = []
        for line in raw_paste.strip().splitlines():
            nums = [int(x) for x in re.findall(r"\b\d+\b", line)]
            if len(nums) >= cfg["pick_count"]:
                main = sorted(nums[:cfg["pick_count"]])
                if all(1 <= x <= cfg["total_balls"] for x in main):
                    bonus = None
                    if cfg["bonus_balls"] > 0 and len(nums) > cfg["pick_count"]:
                        b_cand = nums[cfg["pick_count"]]
                        if 1 <= b_cand <= cfg["bonus_balls"]:
                            bonus = b_cand
                    parsed.append((main, bonus))
        if parsed:
            st.session_state[state_key] = parsed + st.session_state[state_key]
            st.success(f"Added {len(parsed)} draws!")
            st.rerun()
        else:
            st.warning("No valid draws found.")

# 4. Primary Action Buttons
b1, b2 = st.columns(2)
gen_clicked = b1.button("🎟️ Generate Wheel", type="primary", use_container_width=True)
bt_clicked = b2.button("📈 Backtest 13", use_container_width=True)

# 5. Output Display
if gen_clicked or f"last_wheel_{game_name}" not in st.session_state:
    tickets, pool, quotas = build_wheeled_tickets(
        cfg, skips, chosen_hot, chosen_warm, chosen_cold, num_tickets
    )
    st.session_state[f"last_wheel_{game_name}"] = (tickets, pool, quotas)

if bt_clicked:
    bt_draws = 13
    if len(draw_history) < window_size + bt_draws:
        st.error(f"Need at least {window_size + bt_draws} draws to backtest.")
    else:
        st.subheader(f"📈 {bt_draws}-Draw Backtest ({game_name})")
        total_pool_hits = 0
        best_line_hits = []
        rows_md = []

        for test_idx in range(bt_draws - 1, -1, -1):
            actual_main, actual_bonus = draw_history[test_idx]
            prior_history = draw_history[test_idx + 1:]

            _, bt_skips, h_p, w_p, c_p = compute_pools_for_history(cfg, prior_history, window_size)
            c_h = h_p[:h_req]
            c_w = w_p[:w_req]
            c_c = c_p[:c_req]

            bt_tickets, bt_pool, _ = build_wheeled_tickets(cfg, bt_skips, c_h, c_w, c_c, num_tickets)

            pool_hits = len(set(actual_main).intersection(bt_pool))
            total_pool_hits += pool_hits
            max_tkt_hit = max(len(set(actual_main).intersection(t)) for t in bt_tickets)
            best_line_hits.append(max_tkt_hit)

            act_str = " ".join(f"{x:02d}" for x in actual_main)
            badge = "🔥" if max_tkt_hit >= 4 else ("✅" if max_tkt_hit == 3 else "")
            rows_md.append(f"| `-{test_idx+1:02d}` | `{act_str}` | {pool_hits}/{len(actual_main)} | **{max_tkt_hit}** {badge} |")

        m1, m2 = st.columns(2)
        m1.metric("Avg Pool Capture", f"{total_pool_hits / bt_draws:.1f} balls")
        m2.metric("3+ Number Hits", f"{sum(1 for h in best_line_hits if h >= 3)} / {bt_draws}")

        table_header = "| Draw | Winning Numbers | Pool | Best |\n| :--- | :--- | :---: | :---: |\n"
        st.markdown(table_header + "\n".join(rows_md))

else:
    tickets, pool, quotas = st.session_state[f"last_wheel_{game_name}"]
    covered = len({b for t in tickets for b in t})
    st.caption(f"Quota: **{quotas[0]}H / {quotas[1]}W / {quotas[2]}C** | Coverage: **{covered}/{len(pool)}** balls")

    for idx, t in enumerate(tickets, 1):
        balls_html = "".join(f'<span class="ball-num">{x:02d}</span>' for x in t)
        bonus_html = ""
        if cfg["bonus_balls"] > 0 and top_bonuses:
            bb = top_bonuses[(idx - 1) % len(top_bonuses)]
            bonus_html = f'<span class="bonus-num">{bb:02d}</span>'

        l_sum = sum(t)
        odds = sum(1 for x in t if x % 2 != 0)
        evens = len(t) - odds
        h_cnt = sum(1 for x in t if x in chosen_hot)
        w_cnt = sum(1 for x in t if x in chosen_warm)
        c_cnt = sum(1 for x in t if x in chosen_cold)

        st.markdown(f"""
        <div class="ticket-card">
            <div><strong style="color:#8d99ae; margin-right:8px;">#{idx:02d}</strong>{balls_html}{bonus_html}</div>
            <div class="meta-line">Sum: {l_sum:03d} &nbsp;|&nbsp; Odd/Even: {odds}/{evens} &nbsp;|&nbsp; H/W/C: {h_cnt}-{w_cnt}-{c_cnt}</div>
        </div>
        """, unsafe_allow_html=True)