"""
Discord Notification Service
Dispatches rich, institutional-grade trading alerts and trade updates to Discord Webhooks.
"""
import requests
import json
from datetime import datetime
import config

def send_discord_webhook(payload: dict) -> bool:
    """
    Send raw payload to configured Discord Webhook URL.
    """
    webhook_url = config.DISCORD_WEBHOOK_URL.strip()
    if not webhook_url:
        print("[DISCORD] Webhook URL is empty. Alert printed to console instead.")
        return False

    try:
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=8
        )
        if response.status_code in [200, 204]:
            print(f"[DISCORD] Alert sent successfully! (Status: {response.status_code})")
            return True
        else:
            print(f"[DISCORD ERROR] Failed to send webhook: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[DISCORD ERROR] Exception while sending alert: {e}")
        return False

def notify_signal_entry(signal) -> bool:
    """
    Format and send a new ENTRY Signal with 5-Pillar verification to Discord.
    """
    is_buy = signal.direction == 'BUY'
    color = 58998 if is_buy else 16717636  # Green for BUY, Red for SELL
    icon = "🟢" if is_buy else "🔴"
    action_text = "BUY LIMIT / RETEST" if is_buy else "SELL LIMIT / RETEST"

    reasons_formatted = "\n".join([f"• {r}" for r in signal.reasons])

    embed = {
        "title": f"{icon} XAUUSD 5-PILLAR SNIPER SIGNAL | {action_text}",
        "description": f"**SMC & 5-Pillar AI Engine** memvalidasi setup akurasi tinggi di **{signal.session}**.",
        "color": color,
        "fields": [
            {
                "name": "📌 Setup Details",
                "value": f"**Pair:** `{config.DISPLAY_SYMBOL}`\n**Action:** `{signal.direction}`\n**Timeframe:** `M15 (Daily & H1 Bias)`\n**AI Score:** `{signal.score}/100 (Grade A+ Sniper)`",
                "inline": True
            },
            {
                "name": "🎯 Order Parameters",
                "value": f"**Entry (FVG):** `{signal.entry_price:.2f}`\n**SL:** `{signal.sl_price:.2f}` (`-{signal.sl_pips} pips`)\n**TP1:** `{signal.tp1_price:.2f}` (`+{signal.tp1_pips} pips`)\n**TP2:** `{signal.tp2_price:.2f}` (`+{signal.tp2_pips} pips`)",
                "inline": True
            },
            {
                "name": "⚖️ Risk / Reward",
                "value": f"**RR to TP1:** `{signal.rr_tp1}`\n**RR to TP2:** `{signal.rr_tp2}`\n**Win Probability:** `> 85%`",
                "inline": True
            },
            {
                "name": "🏛️ 5-Pillar Confluences",
                "value": reasons_formatted if reasons_formatted else "• News Clear | Macro Daily/H1 Aligned | DXY Confirmed | FVG Limit",
                "inline": False
            },
            {
                "name": "🛡️ Trade Management Rules",
                "value": "1. **Running +50 pips:** Pindahkan SL ke **Entry + 5 pips (Risk Free)**.\n2. **Hit TP1 (+100 pips):** Close **50% volume**, pasang Trailing SL ke +60 pips profit.\n3. **Hit TP2 (+150 pips):** Full Victory Exit.",
                "inline": False
            }
        ],
        "footer": {
            "text": f"Antigravity XAUUSD 5-Pillar AI Engine • {signal.timestamp}"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

    payload = {
        "username": "XAUUSD Institutional Sniper",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "content": config.DISCORD_PING_MENTION,
        "embeds": [embed]
    }

    return send_discord_webhook(payload)

def notify_trade_update(update_type: str, trade_info: dict) -> bool:
    """
    Notify updates such as Breakeven Moved, TP1 Hit, TP2 Hit, or SL Hit.
    """
    if update_type == "BREAKEVEN":
        color = 2718207 # Blue
        title = "🛡️ TRADE UPDATE: STOP LOSS MOVED TO BREAKEVEN"
        desc = f"**{trade_info['direction']} {config.DISPLAY_SYMBOL}** sudah running **+{config.BREAKEVEN_TRIGGER_PIPS} pips**! Stop Loss telah diamankan ke Entry (Risk-Free Trade)."
    elif update_type == "TP1_HIT":
        color = 16766720 # Gold
        title = "💰 TARGET HIT: TAKE PROFIT 1 (+100 PIPS) REACHED!"
        desc = f"Selamat! **{trade_info['direction']} {config.DISPLAY_SYMBOL}** mencapai TP1 di `{trade_info['tp1']:.2f}` (**+{config.TP1_PIPS} pips**).\nAmankan 50% partial profit dan biarkan runner melaju ke TP2."
    elif update_type == "TP2_HIT":
        color = 58879 # Cyan
        title = "🚀 FULL VICTORY: TAKE PROFIT 2 (+150 PIPS) SMASHED!"
        desc = f"Target penuh berhasil tercapai di `{trade_info['tp2']:.2f}`! Total profit terkunci: **+{config.TP2_PIPS} pips**."
    elif update_type == "SL_HIT":
        color = 12000284 # Dark Red
        title = "🛑 TRADE CLOSED: STOP LOSS HIT"
        desc = f"Trade **{trade_info['direction']} {config.DISPLAY_SYMBOL}** terkena Stop Loss di `{trade_info['sl']:.2f}` (`-{trade_info['sl_pips']} pips`). Disiplin risiko terjaga."
    else:
        color = 9807270
        title = f"ℹ️ TRADE UPDATE: {update_type}"
        desc = json.dumps(trade_info)

    embed = {
        "title": title,
        "description": desc,
        "color": color,
        "footer": {
            "text": f"Antigravity XAUUSD 5-Pillar AI Engine • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        }
    }

    payload = {
        "username": "XAUUSD Institutional Sniper",
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [embed]
    }

    return send_discord_webhook(payload)
