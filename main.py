import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse # 關鍵：處理網頁顯示
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

# 你的 Render 資料庫連結 (保持不變)
DATABASE_URL = "postgresql://admin:z4b7Wc7ydu1AilkOkjFkLEJKJH6HNfQP@dpg-cv66o1ogph6c738jcgig-a.singapore-postgres.render.com/warehouse_db_65f0"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

class ScanItem(BaseModel):
    barcode: str

# --- 這裡就是你要的網頁輸入框介面 ---
@app.get("/scan-page", response_class=HTMLResponse)
async def scan_page():
    return """
    <html>
        <head>
            <title>南屯冷鏈現場掃描端</title>
            <meta charset="utf-8">
        </head>
        <body style="text-align: center; padding-top: 50px; font-family: 'Microsoft JhengHei', Arial; background-color: #f4f4f9;">
            <div style="background: white; display: inline-block; padding: 30px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h1 style="color: #333;">📦 現場出入庫掃描系統</h1>
                <p style="color: #666;">請確保游標在框框內，直接使用掃描槍掃描</p>
                <input type="text" id="barcodeInput" autofocus 
                       style="font-size: 24px; width: 350px; padding: 10px; border: 2px solid #ddd; border-radius: 5px;">
                <div id="result" style="margin-top: 20px; font-size: 18px; color: #007bff; font-weight: bold;"></div>
            </div>

            <script>
                const input = document.getElementById('barcodeInput');
                input.addEventListener('keypress', function (e) {
                    if (e.key === 'Enter') {
                        const bc = input.value;
                        document.getElementById('result').innerText = "處理中...";
                        fetch('/scan', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ barcode: bc })
                        })
                        .then(res => res.json())
                        .then(data => {
                            if(data.error) {
                                document.getElementById('result').style.color = "red";
                                document.getElementById('result').innerText = "❌ 錯誤：" + data.error;
                            } else {
                                document.getElementById('result').style.color = "green";
                                document.getElementById('result').innerText = "✅ 成功：" + data.data.品名 + " (" + data.data.狀態 + ")";
                            }
                            input.value = ''; // 掃完自動清空，準備下一支
                        });
                    }
                });
            </script>
        </body>
    </html>
    """

@app.get("/")
def read_root():
    return {"status": "後端運行中", "manual": "請前往 /scan-page 進行掃描"}

@app.post("/scan")
async def receive_scan(item: ScanItem):
    raw_bc = item.barcode
    product_id = "未知"
    expiry_str = ""
    if len(raw_bc) >= 14 and raw_bc.startswith("01"):
        product_id = raw_bc[2:6]
        expiry_str = raw_bc[8:14]
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM product_master WHERE product_id = %s", (product_id,))
        prod_data = cur.fetchone()
        
        if not prod_data:
            return {"error": f"資料庫查無品號: {product_id}"}

        # 計算邏輯 (維持你專題要求的自主開發解析)
        expiry_date = datetime.strptime(f"20{expiry_str}", "%Y%m%d")
        remaining_days = (expiry_date - datetime.now()).days
        
        status_light = "綠燈"
        if remaining_days <= prod_data['critical_days']: status_light = "紅燈"
        elif remaining_days <= prod_data['warning_days']: status_light = "黃燈"

        # 存入出入庫紀錄
        cur.execute("""
            INSERT INTO inventory_log (product_id, barcode, status, remaining_days, action_time)
            VALUES (%s, %s, %s, %s, %s)
        """, (product_id, raw_bc, status_light, remaining_days, datetime.now()))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            "message": "成功",
            "data": {"品名": prod_data['product_name'], "狀態": status_light}
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)