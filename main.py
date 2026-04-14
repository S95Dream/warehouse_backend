import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime

app = FastAPI()

# 1. 自動修正後的資料庫網址（包含 SSL 協議）
DATABASE_URL = "postgresql://admin:z4b7Wc7ydu1AilkOkjFkLEJKJH6HNfQP@dpg-d7abkoua2pns73abkgn0-a.singapore-postgres.render.com/warehouse_db_jygk?sslmode=require"

def get_db_connection():
    # 確保連線時強制要求 SSL
    return psycopg2.connect(DATABASE_URL, sslmode='require')

class ScanItem(BaseModel):
    barcode: str

@app.get("/scan-page", response_class=HTMLResponse)
async def scan_page():
    return """
    <html>
        <head><title>南屯冷鏈現場掃描端</title><meta charset="utf-8"></head>
        <body style="text-align: center; padding-top: 50px; font-family: Arial; background-color: #f4f4f9;">
            <div style="background: white; display: inline-block; padding: 30px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h1>📦 現場出入庫掃描</h1>
                <p>請確保游標在框框內，直接開始掃描</p>
                <input type="text" id="barcodeInput" autofocus style="font-size: 24px; width: 350px; padding: 10px;">
                <div id="result" style="margin-top: 20px; font-size: 18px; font-weight: bold;"></div>
            </div>
            <script>
                const input = document.getElementById('barcodeInput');
                input.addEventListener('keypress', function (e) {
                    if (e.key === 'Enter') {
                        const bc = input.value;
                        fetch('/scan', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ barcode: bc })
                        })
                        .then(res => res.json())
                        .then(data => {
                            const resDiv = document.getElementById('result');
                            if(data.error) {
                                resDiv.style.color = "red";
                                resDiv.innerText = "❌ 錯誤：" + data.error;
                            } else {
                                let lightColor = "green";
                                if(data.data.狀態 === "紅燈") lightColor = "red";
                                if(data.data.狀態 === "黃燈") lightColor = "orange";
                                
                                resDiv.style.color = lightColor;
                                resDiv.innerText = "✅ 成功：" + data.data.品名 + " (" + data.data.狀態 + ")";
                            }
                            input.value = '';
                        });
                    }
                });
            </script>
        </body>
    </html>
    """

@app.post("/scan")
async def receive_scan(item: ScanItem):
    raw_bc = item.barcode
    product_id = "未知"
    expiry_str = ""
    
    # GS1-128 條碼解析邏輯
    if len(raw_bc) >= 14 and raw_bc.startswith("01"):
        product_id = raw_bc[2:6]   # 取得 A101
        expiry_str = raw_bc[8:14]  # 取得 240817
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 2. 修正 SQL 語法：確保欄位名稱為 barcode (無拼錯)
        cur.execute("SELECT * FROM product_master WHERE barcode = %s", (product_id,))
        prod_data = cur.fetchone()
        
        if not prod_data:
            return {"error": f"資料庫查無此品號: {product_id}"}

        # 到期日計算
        expiry_date = datetime.strptime(f"20{expiry_str}", "%Y%m%d")
        remaining_days = (expiry_date - datetime.now()).days
        
        # 使用 .get() 並嘗試不同的大小寫組合，確保萬無一失
        c_days = prod_data.get('criticaldays') or prod_data.get('CRITICALDAYS') or 0
        w_days = prod_data.get('warningdays') or prod_data.get('WARNINGDAYS') or 0
        p_name = prod_data.get('productname') or prod_data.get('PRODUCTNAME') or "未知商品"

        status_light = "綠燈"
        if remaining_days <= int(c_days): 
            status_light = "紅燈"
        elif remaining_days <= int(w_days): 
            status_light = "黃燈"
            
        # 下方的 Return 也請同步修改
        return {
            "message": "查詢成功", 
            "data": {
                "品名": p_name, 
                "狀態": status_light
            }
        }

        # 寫入日誌 (請確保 inventory_log 表欄位名稱也對應正確)
        cur.execute("""
            INSERT INTO inventory_logs (barcode, status, remaining_days, action_time)
            VALUES (%s, %s, %s, %s)
        """, (product_id, status_light, remaining_days, datetime.now()))
        
        conn.commit()
        cur.close()
        conn.close()
        
        # 4. 修正品名取值：productname
        return {
            "message": "查詢成功", 
            "data": {
                "品名": prod_data['productname'], 
                "狀態": status_light
            }
        }
    except Exception as e:
        if conn: conn.close()
        return {"error": f"系統異常: {str(e)}"}