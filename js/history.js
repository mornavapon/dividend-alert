const RAW="https://raw.githubusercontent.com/mornavapon/dividend-alert/main/";
const params=new URLSearchParams(location.search);
const ticker=(params.get("ticker")||"").toUpperCase();
const $=id=>document.getElementById(id);
function fmtDate(value){if(!value)return"—";const d=new Date(value+"T00:00:00");return d.toLocaleDateString("th-TH",{day:"numeric",month:"short",year:"numeric"})}
function esc(value){return String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
async function load(){
 if(!/^[A-Z0-9.-]{1,20}\.BK$/.test(ticker))throw Error("หน้านี้รองรับประวัติหุ้นไทยในระยะแรก");
 $("historyTicker").textContent=ticker;
 const response=await fetch(RAW+"data/dividends.json?t="+Date.now());
 if(!response.ok)throw Error("โหลดข้อมูลไม่สำเร็จ ("+response.status+")");
 const data=await response.json(),stock=data.stocks?.["TH:"+ticker];
 if(!stock)throw Error("ไม่พบหุ้นนี้ในข้อมูลล่าสุด");
 const rows=Array.isArray(stock.history)?stock.history:[];
 const oldest=rows.length?rows[rows.length-1].ex_date:null, newest=rows.length?rows[0].ex_date:null;
 $("historyMeta").innerHTML="<span>จำนวนรายการ: <b>"+rows.length+"</b></span><span>ช่วงข้อมูล: <b>"+(oldest?fmtDate(oldest)+" – "+fmtDate(newest):"ไม่มีข้อมูล")+"</b></span><span>อัปเดต: <b>"+fmtDate((data.updated_at||"").slice(0,10))+"</b></span>";
 $("historyBody").innerHTML=rows.length?rows.map(r=>"<tr><td>"+fmtDate(r.ex_date)+"</td><td>"+fmtDate(r.payment_date)+"</td><td>"+(r.dividend==null?"ไม่ระบุ":Number(r.dividend).toLocaleString("en-US",{maximumFractionDigits:6})+" บาท")+"</td></tr>").join(""):'<tr><td colspan="3" class="empty">ยังไม่มีข้อมูลประวัติปันผลในชุดข้อมูล</td></tr>';
 const cutoff=new Date();cutoff.setFullYear(cutoff.getFullYear()-5);const cutoffText=cutoff.toISOString().slice(0,10);
 if(!oldest||oldest>cutoffText)$("historyNotice").innerHTML='<div class="history-note">ข้อควรทราบ: ข้อมูลต้นทางที่ระบบได้รับยังไม่ยืนยันว่าครอบคลุมครบ 5 ปี รายการเก่าสุดที่พบคือ '+(oldest?fmtDate(oldest):"ไม่มีข้อมูล")+' ระบบจะแสดงเฉพาะรายการที่ดึงได้จริง ไม่เติมข้อมูลย้อนหลังเอง</div>';
 $("historySource").innerHTML='แหล่งข้อมูล: SET Corporate Actions · ตรวจสอบเทียบได้ที่ <a class="ticker-link" target="_blank" rel="noopener" href="https://www.settrade.com/th/equities/quote/'+encodeURIComponent(ticker.replace(/\.BK$/,""))+'/rights-benefits">SETTRADE สิทธิประโยชน์</a>';
}
load().catch(e=>{$("historyTicker").textContent=ticker||"Dividend History";$("historyBody").innerHTML='<tr><td colspan="3" class="empty">'+esc(e.message)+'</td></tr>'});
