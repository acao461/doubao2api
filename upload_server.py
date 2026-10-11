#!/usr/bin/env python3
"""
二维码上传识别服务 - 自动处理豆包扫码登录流程
接收用户上传的二维码截图，自动识别二维码内容，完成豆包登录状态获取
"""
import os
import re
import json
import time
import uuid
import requests
from io import BytesIO
from typing import Optional, Dict
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import uvicorn
import cv2
import numpy as np
from pyzbar.pyzbar import decode, ZBarSymbol

# 配置
app = FastAPI(title="豆包二维码自动登录服务", version="1.0.0")
DOUBOA_BASE_URL = "https://www.doubao.com"
CHECK_QR_INTERVAL = 2  # 轮询间隔 秒
MAX_CHECK_TIMES = 30  # 最大轮询次数
SESSION_DIR = os.environ.get("SESSION_DIR", "/tmp/sessions")
os.makedirs(SESSION_DIR, exist_ok=True)

def qr_scan_image(image_bytes: bytes) -> Optional[str]:
    """从图片字节流中识别二维码内容"""
    try:
        # 读取图片
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        
        # 转为灰度图提升识别率
        gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # 识别二维码
        decoded_objects = decode(gray_img, symbols=[ZBarSymbol.QRCODE])
        
        if not decoded_objects:
            return None
        
        # 返回第一个识别到的二维码内容
        return decoded_objects[0].data.decode('utf-8').strip()
    except Exception as e:
        print(f"二维码识别错误: {str(e)}")
        return None

def extract_qr_content(qr_text: str) -> Dict:
    """从二维码内容中提取qr_code等参数"""
    # 二维码格式通常是: https://www.doubao.com/passport/web/qrconnect/?qr_code=xxxx
    # 或者直接是qr_code值
    if qr_text.startswith("http"):
        # 从URL中提取qr_code参数
        match = re.search(r'qr_code=([a-zA-Z0-9]+)', qr_text)
        if match:
            qr_code = match.group(1)
        else:
            qr_code = qr_text.split('/')[-1]
    else:
        qr_code = qr_text
    
    return {
        "qr_code": qr_code,
        "raw_content": qr_text
    }

def poll_qr_status(qr_code: str) -> Dict:
    """轮询二维码状态直到确认登录"""
    session = requests.Session()
    check_url = f"{DOUBOA_BASE_URL}/passport/web/check_qrconnect"
    
    for i in range(MAX_CHECK_TIMES):
        try:
            resp = session.get(
                check_url,
                params={
                    "qr_code": qr_code,
                    "is_ajax": 1,
                    "_": int(time.time() * 1000)
                },
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            
            status = data.get('data', {}).get('status')
            
            if status == 'confirmed':
                # 登录成功，获取sessionid
                cookies = session.cookies.get_dict()
                session_id = cookies.get('sessionid', '')
                result = {
                    "status": "confirmed",
                    "sessionid": session_id,
                    "cookies": cookies,
                    "raw_data": data
                }
                return result
            
            elif status == 'scanned':
                print(f"二维码已扫码，等待确认... 第{i+1}次检查")
                time.sleep(CHECK_QR_INTERVAL)
                continue
            
            elif status == 'expired':
                return {"status": "expired", "message": "二维码已过期"}
            
            elif status == 'canceled':
                return {"status": "canceled", "message": "用户已取消扫码"}
            
        except Exception as e:
            print(f"检查二维码状态错误: {str(e)}")
            time.sleep(CHECK_QR_INTERVAL)
    
    return {"status": "timeout", "message": "等待扫码确认超时"}

def save_session(session_data: Dict, qr_code: str) -> str:
    """保存session到持久化目录"""
    session_id = str(uuid.uuid4())
    file_path = os.path.join(SESSION_DIR, f"{session_id}.json")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump({
            "created_at": time.time(),
            "qr_code": qr_code,
            "data": session_data
        }, f, ensure_ascii=False, indent=2)
    
    return session_id

@app.post("/upload_qr", summary="上传二维码截图完成自动登录")
async def upload_qr(file: UploadFile = File(...)):
    """
    上传豆包二维码截图，自动识别并完成登录流程
    - **file**: 二维码图片文件
    """
    try:
        # 读取上传的文件
        image_bytes = await file.read()
        if not image_bytes:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "上传文件为空"}
            )
        
        # 识别二维码
        qr_text = qr_scan_image(image_bytes)
        if not qr_text:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "图片中未识别到二维码"}
            )
        
        # 提取qr_code
        qr_info = extract_qr_content(qr_text)
        qr_code = qr_info['qr_code']
        print(f"识别到二维码内容: {qr_text}, 提取qr_code: {qr_code}")
        
        # 轮询扫码状态
        login_result = poll_qr_status(qr_code)
        print(f"扫码结果: {login_result}")
        
        if login_result.get('status') == 'confirmed':
            # 保存session
            session_id = save_session(login_result, qr_code)
            login_result['session_file_id'] = session_id
            login_result['session_save_path'] = os.path.join(SESSION_DIR, f"{session_id}.json")
        
        return JSONResponse(content=login_result)
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"处理失败: {str(e)}"}
        )

@app.get("/health", summary="健康检查")
async def health_check():
    return {"status": "ok", "session_dir": SESSION_DIR}

# 如果作为独立服务运行，直接启动
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
