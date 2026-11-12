import asyncio, json, os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from settfex.services.set import get_corporate_actions

ROOT=Path(__file__).resolve().parents[1]; WATCH=ROOT/"config/watchlist.json"; DATA=ROOT/"data/dividends.json"; TZ=ZoneInfo("Asia/Bangkok")
def as_date(v):
    if v is None:return None
    try:return v.date() if hasattr(v,"date") else date.fromisoformat(str(v)[:10])
    except (ValueError,TypeError):return None
async def thai(ticker):
    actions=await get_corporate_actions(ticker,lang="en"); today=datetime.now(TZ).date(); rows=[]
    for a in actions:
        typ=str(getattr(a,"ca_type","")).upper()
        if typ not in ("XD","CASH DIVIDEND","DIVIDEND"):continue
        ex=as_date(getattr(a,"x_date",None))
        if ex and ex>=today:rows.append((ex,a))
    if not rows:return {"status":"no_upcoming","ex_date":None,"payment_date":None,"dividend":None,"currency":"บาท/หุ้น","message":"ไม่พบกำหนด XD รอบถัดไป"}
    ex,a=min(rows,key=lambda x:x[0]); pay=as_date(getattr(a,"payment_date",None)); amount=getattr(a,"dividend",None)
    return {"status":"ok","ex_date":ex.isoformat(),"payment_date":pay.isoformat() if pay else None,"dividend":float(amount) if amount is not None else None,"currency":"บาท/หุ้น","source":"SET Corporate Actions"}
def us(ticker):
    # Endpoint/schema will be validated in the first scheduled workflow run; failures are surfaced, never treated as no dividend.
    r=requests.get("https://smarterdividends.com/api/v1/stocks/"+ticker,headers={"User-Agent":"DividendAlert/1.0"},timeout=25);r.raise_for_status();p=r.json()
    if not isinstance(p,dict):raise ValueError("SmarterDividends response ไม่ใช่ object")
    ex=p.get("next_ex_date"); pay=p.get("next_pay_date"); amount=p.get("next_dividend_amount") or p.get("next_dividend_per_share")
    if isinstance(amount,dict):amount=amount.get("amount") or amount.get("value")
    if not ex:return {"status":"no_upcoming","ex_date":None,"payment_date":None,"dividend":None,"currency":"USD/share"}
    return {"status":"ok","ex_date":str(ex)[:10],"payment_date":str(pay)[:10] if pay else None,"dividend":float(amount) if amount is not None else None,"currency":"USD/share","source":"SmarterDividends","source_url":"https://smarterdividends.com/dividend-api"}
def notify(items):
    topic=os.getenv("NTFY_TOPIC","").strip()
    if not topic or not items:return
    h={"Title":"Dividend Alert · XD พรุ่งนี้","Priority":"high","Tags":"bell"}; token=os.getenv("NTFY_TOKEN","").strip()
    if token:h["Authorization"]="Bearer "+token
    r=requests.post("https://ntfy.sh/"+topic,data="\n\n".join(items).encode(),headers=h,timeout=20);r.raise_for_status()
async def main():
    stocks=json.loads(WATCH.read_text()).get("stocks",[]); old=json.loads(DATA.read_text()) if DATA.exists() else {}; today=datetime.now(TZ).date(); tomorrow=today+timedelta(days=1)
    out={"updated_at":datetime.now(TZ).isoformat(timespec="seconds"),"source":"SET Corporate Actions / SmarterDividends","stocks":{},"source_status":{}}; alerts=[]
    for s in stocks:
        ticker=s["ticker"].upper(); market=s["market"].upper(); key=market+":"+ticker
        try:
            d=await thai(ticker) if market=="TH" else us(ticker) if market=="US" else (_ for _ in ()).throw(ValueError("Unsupported market "+market))
            d["market"]=market;out["stocks"][key]=d;out["source_status"][market]={"status":"ok","message":"เชื่อมต่อและประมวลผลสำเร็จ"}
            if d.get("ex_date")==tomorrow.isoformat():
                unit="บาท/หุ้น" if market=="TH" else "USD/share";alerts.append(f"{ticker}\nXD: {d['ex_date']}\nวันจ่าย: {d.get('payment_date') or 'ยังไม่ประกาศ'}\nปันผล: {d.get('dividend') if d.get('dividend') is not None else 'ไม่ระบุ'} {unit}")
        except Exception as e:
            print(f"[ERROR] {key}: {type(e).__name__}: {e}"); previous=old.get("stocks",{}).get(key,{})
            d={"status":"error","message":f"{type(e).__name__}: {e}","market":market}
            for f in ("ex_date","payment_date","dividend","currency"):
                if f in previous:d[f]=previous[f]
            out["stocks"][key]=d;out["source_status"][market]={"status":"error","message":str(e)[:250]}
    DATA.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n");notify(alerts);print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=="__main__":asyncio.run(main())