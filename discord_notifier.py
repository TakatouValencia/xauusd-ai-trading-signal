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
    Supports both MARKET (Instant Entry) and LIMIT (Retest) modes.
    """
    is_buy = signal.direction == 'BUY'
    order_type = getattr(signal, 'order_type', f"{signal.direction} MARKET")
    is_limit = "LIMIT" in order_type

    color = 58998 if is_buy else 16717636  # Green for BUY, Red for SELL
    icon = "🟢" if is_buy else "🔴"

    if is_limit:
        action_text = f"{signal.direction} LIMIT / RETEST"
        entry_label = "Limit Entry"
        status_note = f"⏳ **Status:** Pasang **Pending Order {action_text}** di `{signal.entry_price:.2f}` (Tunggu retest dari `{signal.market_price:.2f}`)."
    else:
        action_text = f"{signal.direction} NOW (MARKET EXECUTION)"
        entry_label = "Market Entry"
        status_note = f"⚡ **Status:** **Eksekusi Instan (Market Order)** di `{signal.entry_price:.2f}` pada penutupan M15."

    reasons_formatted = "\n".join([f"• {r}" for r in signal.reasons])

    embed = {
        "title": f"{icon} {config.BOT_NAME} | {action_text}",
        "description": f"**{config.BOT_NAME} 5-Pillar Engine** memvalidasi setup akurasi tinggi di **{signal.session}**.\n{status_note}",
        "color": color,
        "fields": [
            {
                "name": "📌 Setup Details",
                "value": f"**Pair:** `{config.DISPLAY_SYMBOL}`\n**Action:** `{action_text}`\n**Timeframe:** `M15 (Daily & H1 Bias)`\n**AI Score:** `{signal.score}/100 (Grade A+ Sniper)`",
                "inline": True
            },
            {
                "name": "🎯 Order Parameters",
                "value": f"**{entry_label}:** `{signal.entry_price:.2f}`\n**SL:** `{signal.sl_price:.2f}` (`-{signal.sl_pips} pips`)\n**TP1:** `{signal.tp1_price:.2f}` (`+{signal.tp1_pips} pips`)\n**TP2:** `{signal.tp2_price:.2f}` (`+{signal.tp2_pips} pips`)",
                "inline": True
            },
            {
                "name": "🏛️ Fresh Institutional Area (SMC / SND / OB / FVG)",
                "value": f"**Zone:** `{getattr(signal, 'zone_type', 'Fresh Institutional Area')}`\n**Range:** `{getattr(signal, 'zone_range', '-')}`\n**RR to TP1:** `1:{signal.rr_tp1}` | **TP2:** `1:{signal.rr_tp2}`",
                "inline": False
            },
            {
                "name": "⚡ 5-Pillar Confluences",
                "value": reasons_formatted if reasons_formatted else "• Fresh Institutional Area | Macro Aligned | DXY Confirmed",
                "inline": False
            },
            {
                "name": "🛡️ Trade Management Rules",
                "value": "1. **Running +50 pips:** Pindahkan SL ke **Entry + 5 pips (Risk Free)**.\n2. **Hit TP1 (+100 pips):** Close **50% volume**, pasang Trailing SL ke +60 pips profit.\n3. **Hit TP2 (+150 pips):** Full Victory Exit.",
                "inline": False
            }
        ],
        "footer": {
            "text": f"{config.BOT_NAME} • {signal.timestamp}"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

    payload = {
        "username": config.BOT_NAME,
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "content": config.DISCORD_PING_MENTION,
        "embeds": [embed]
    }

    return send_discord_webhook(payload)

def notify_trade_update(update_type: str, trade_info: dict) -> bool:
    """
    Notify updates such as Limit Order Filled, Limit Expired, Breakeven Moved, TP1 Hit, TP2 Hit, or SL Hit.
    """
    if update_type == "ORDER_FILLED":
        color = 3066993  # Teal
        title = f"🎯 {config.BOT_NAME}: PENDING LIMIT ORDER FILLED"
        desc = f"Pending **{trade_info['direction']} LIMIT** di `{trade_info['entry_price']:.2f}` berhasil terjemput! Posisi trading kini **AKTIF**."
    elif update_type == "ORDER_EXPIRED":
        color = 9807270  # Grey
        title = f"⏱️ {config.BOT_NAME}: PENDING LIMIT CANCELLED (EXPIRED)"
        desc = f"Pending order **{trade_info['direction']} LIMIT** di `{trade_info['entry_price']:.2f}` dibatalkan karena tidak terjemput dalam batas waktu ({config.LIMIT_MAX_WAIT_BARS} bar M15)."
    elif update_type == "BREAKEVEN":
        color = 2718207 # Blue
        title = f"🛡️ {config.BOT_NAME}: STOP LOSS MOVED TO BREAKEVEN"
        desc = f"**{trade_info['direction']} {config.DISPLAY_SYMBOL}** sudah running **+{config.BREAKEVEN_TRIGGER_PIPS} pips**! Stop Loss telah diamankan ke Entry (Risk-Free Trade)."
    elif update_type == "TP1_HIT":
        color = 16766720 # Gold
        title = f"💰 {config.BOT_NAME}: TAKE PROFIT 1 (+100 PIPS) REACHED!"
        desc = f"Selamat! **{trade_info['direction']} {config.DISPLAY_SYMBOL}** mencapai TP1 di `{trade_info['tp1']:.2f}` (**+{config.TP1_PIPS} pips**).\nAmankan 50% partial profit dan biarkan runner melaju ke TP2."
    elif update_type == "TP2_HIT":
        color = 58879 # Cyan
        title = f"🚀 {config.BOT_NAME}: TAKE PROFIT 2 (+150 PIPS) SMASHED!"
        desc = f"Target penuh berhasil tercapai di `{trade_info['tp2']:.2f}`! Total profit terkunci: **+{config.TP2_PIPS} pips**."
    elif update_type == "SL_HIT":
        color = 12000284 # Dark Red
        title = f"🛑 {config.BOT_NAME}: STOP LOSS HIT"
        desc = f"Trade **{trade_info['direction']} {config.DISPLAY_SYMBOL}** terkena Stop Loss di `{trade_info['sl']:.2f}` (`-{trade_info['sl_pips']} pips`). Disiplin risiko terjaga."
    elif update_type == "CIRCUIT_BREAKER":
        color = 16711680 # Bright Red
        losses = trade_info.get('consecutive_losses', config.MAX_CONSECUTIVE_LOSSES_PER_DAY)
        date_str = trade_info.get('date', datetime.utcnow().strftime('%Y-%m-%d'))
        title = f"🛑 {config.BOT_NAME}: DAILY CIRCUIT BREAKER ACTIVATED"
        desc = (
            f"⚠️ **Proteksi Modal Aktif!** Terdeteksi **{losses}x Loss Beruntun** pada hari ini ({date_str}).\n\n"
            f"Demi mengamankan modal dan menjaga psikologi trading, sistem **OTOMATIS BERHENTI TRADING HARI INI**.\n\n"
            f"🔄 Bot akan aktif kembali secara otomatis besok pada sesi berikutnya."
        )
    else:
        color = 9807270
        title = f"ℹ️ {config.BOT_NAME}: {update_type}"
        desc = json.dumps(trade_info)

    embed = {
        "title": title,
        "description": desc,
        "color": color,
        "footer": {
            "text": f"{config.BOT_NAME} • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        }
    }

    payload = {
        "username": config.BOT_NAME,
        "avatar_url": "https://i.imgur.com/4M34hi2.png",
        "embeds": [embed]
    }

    return send_discord_webhook(payload)
