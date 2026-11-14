import asyncio
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from settfex.services.set import get_corporate_actions

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "config/watchlist.json"
DATA = ROOT / "data/dividends.json"
TZ = ZoneInfo("Asia/Bangkok")


def as_date(value):
    if value is None:
        return None
    try:
        return value.date() if hasattr(value, "date") else date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


async def thai(ticker):
    actions = await get_corporate_actions(ticker, lang="en")
    today = datetime.now(TZ).date()
    rows = []

    for action in actions:
        action_type = str(getattr(action, "ca_type", "")).upper()
        if action_type not in ("XD", "CASH DIVIDEND", "DIVIDEND"):
            continue

        ex_date = as_date(getattr(action, "x_date", None))
        if ex_date and ex_date >= today:
            rows.append((ex_date, action))

    if not rows:
        return {
            "status": "no_upcoming",
            "ex_date": None,
            "payment_date": None,
            "dividend": None,
            "currency": "บาท/หุ้น",
            "message": "ไม่พบกำหนด XD รอบถัดไป",
        }

    ex_date, action = min(rows, key=lambda item: item[0])
    payment_date = as_date(getattr(action, "payment_date", None))
    amount = getattr(action, "dividend", None)

    return {
        "status": "ok",
        "ex_date": ex_date.isoformat(),
        "payment_date": payment_date.isoformat() if payment_date else None,
        "dividend": float(amount) if amount is not None else None,
        "currency": "บาท/หุ้น",
        "source": "SET Corporate Actions",
    }


def us(ticker):
    url = "https://smarterdividends.com/api/v1/stocks/" + ticker
    response = requests.get(
        url,
        headers={"User-Agent": "DividendAlert/1.0"},
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("SmarterDividends response ไม่ใช่ object")

    # SmarterDividends places next_ex_date inside the nested "dividend" object.
    dividend_info = payload.get("dividend") or {}
    if not isinstance(dividend_info, dict):
        raise ValueError("SmarterDividends field 'dividend' ไม่ใช่ object")

    ex_date = dividend_info.get("next_ex_date")
    if not ex_date:
        return {
            "status": "no_upcoming",
            "ex_date": None,
            "payment_date": None,
            "dividend": None,
            "currency": "USD/share",
        }

    return {
        "status": "ok",
        "ex_date": str(ex_date)[:10],
        "payment_date": None,
        "dividend": None,
        "currency": "USD/share",
        "source": "SmarterDividends",
        "source_url": payload.get("url") or "https://smarterdividends.com/stocks/" + ticker,
    }


def notify(items):
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        print("[NTFY] SKIPPED: NTFY_TOPIC secret is missing or empty")
        return

    if not items:
        print("[NTFY] No XD tomorrow; no alert is expected.")
        return

    headers = {"Title": "Dividend Alert", "Priority": "high", "Tags": "bell"}
    token = os.getenv("NTFY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token

    try:
        response = requests.post(
            "https://ntfy.sh/" + topic,
            data="\n\n".join(items).encode("utf-8"),
            headers=headers,
            timeout=20,
        )
        if response.status_code == 429:
            print("[NTFY] WARNING: rate limited (HTTP 429); data update will continue.")
            return
        response.raise_for_status()
        print("[NTFY] Notification sent successfully.")
    except requests.RequestException as error:
        print(f"[NTFY] WARNING: notification failed: {type(error).__name__}: {error}")
        print("[NTFY] Data update will continue; notification can be retried later.")

async def main():
    stocks = json.loads(WATCH.read_text(encoding="utf-8")).get("stocks", [])
    old = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    today = datetime.now(TZ).date()
    tomorrow = today + timedelta(days=1)

    output = {
        "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "source": "SET Corporate Actions / SmarterDividends",
        "stocks": {},
        "source_status": {},
    }
    alerts = []

    for stock in stocks:
        ticker = stock["ticker"].upper()
        market = stock["market"].upper()
        key = market + ":" + ticker

        output["source_status"].setdefault(
            market,
            {"status": "ok", "message": "เชื่อมต่อและประมวลผลสำเร็จ"},
        )

        try:
            if market == "TH":
                dividend_data = await thai(ticker)
            elif market == "US":
                dividend_data = us(ticker)
            else:
                raise ValueError("Unsupported market " + market)

            dividend_data["market"] = market
            output["stocks"][key] = dividend_data

            if dividend_data.get("ex_date") == tomorrow.isoformat():
                unit = "บาท/หุ้น" if market == "TH" else "USD/share"
                amount = dividend_data.get("dividend")
                alerts.append(
                    f"{ticker}\n"
                    f"XD: {dividend_data['ex_date']}\n"
                    f"วันจ่าย: {dividend_data.get('payment_date') or 'ยังไม่ประกาศ'}\n"
                    f"ปันผล: {amount if amount is not None else 'ไม่ระบุ'} {unit}"
                )

        except Exception as error:
            print(f"[ERROR] {key}: {type(error).__name__}: {error}")
            previous = old.get("stocks", {}).get(key, {})
            dividend_data = {
                "status": "error",
                "message": f"{type(error).__name__}: {error}",
                "market": market,
            }
            for field in ("ex_date", "payment_date", "dividend", "currency"):
                if field in previous:
                    dividend_data[field] = previous[field]
            output["stocks"][key] = dividend_data
            output["source_status"][market] = {
                "status": "error",
                "message": str(error)[:250],
            }

    if os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch":
        alerts.append(
            "Dividend Alert: ทดสอบระบบ ntfy สำเร็จ\n"
            "ข้อความนี้เกิดจากการกด Run workflow ด้วยตนเอง"
        )

    DATA.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    notify(alerts)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
