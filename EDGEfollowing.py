import cv2
import numpy as np
import time
import threading
import libcamera
from picamera2 import Picamera2
from flask import Flask, Response, render_template_string, jsonify
from LOBOROBOT2 import LOBOROBOT, FORWARD

# ##################################################################
# --- 1. 關鍵參數調整區 ---
# ##################################################################

# --- 循線與視野設定 ---
FOLLOW_SIDE = 'RIGHT'   # 即使只看右邊，這個參數留著給之後擴充用
TARGET_LINE_POS = 260   # 目標線在畫面中的 X 座標 (0~320)
                        # 因為我們只看右邊，這個數值應該會在 160 ~ 300 之間

# [關鍵新增] 搜尋起始點 X 座標
# 畫面寬度是 320。設定 160 代表「只看右半邊 (160~320)」，左半邊 (0~160) 全部遮掉。
# 如果你的線真的很靠右，可以設成 200，遮掉更多左邊區域。
SEARCH_START_X = 100    

# --- 馬達控制 ---
BASE_SPEED = 50
Kp = 0.21 
Kd = 0.24 

# --- 影像處理 ---
WW, HH = 640, 640
ROI_Y_START = int(HH * 0.35) 
ROI_HEIGHT = 500             

# --- 白色線條的 HSV 閥值 ---
LOWER_WHITE = np.array([0, 0, 150])
UPPER_WHITE = np.array([32, 120, 255])

# --- 寬限期 ---
GRACE_PERIOD = 0.5 

# ##################################################################
# --- 2. 網頁介面 (HTML) ---
# ##################################################################

INDEX_HTML = """
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>Pi5 右側專注循線</title>
  <style>
    body { font-family: Arial, sans-serif; text-align: center; background-color: #f0f0f0; }
    h3 { color: #333; }
    table { margin: 0 auto; border-collapse: collapse; }
    th, td { padding: 10px; border: 1px solid #ccc; background-color: #fff; }
    img { border-radius: 8px; border: 1px solid #333; display: block; }
    .controls { margin-top: 20px; }
    button {
      font-size: 16px;
      padding: 10px 20px;
      margin: 5px;
      border: none;
      border-radius: 5px;
      cursor: pointer;
    }
    #btn-start { background-color: #4CAF50; color: white; }
    #btn-stop { background-color: #f44336; color: white; }
    #status { margin-top: 10px; font-weight: bold; }
    .info { font-size: 14px; color: #555; margin-bottom: 10px; }
  </style>
</head>
<body>
  <h3>Raspberry Pi 5 右側專注模式</h3>
  <div class="info">
    視野設定：<b>遮蔽 X < {{ search_start }} 左側區域</b><br>
    目標位置：<b>{{ target_pos }}</b>
  </div>
  
  <table>
    <tr>
      <th>原始影像</th>
      <th>偵測結果 (左側已遮蔽)</th>
    </tr>
    <tr>
      <td><img src="/live_original" alt="原始影像"></td>
      <td><img src="/live_processed" alt="處理影像"></td>
    </tr>
  </table>

  <div class="controls">
    <button id="btn-start" onclick="startExecution()">開始執行</button>
    <button id="btn-stop" onclick="stopExecution()">停止執行</button>
    <div id="status">狀態：已停止</div>
  </div>

  <script>
    async function startExecution() {
      try {
        const response = await fetch('/api/start_execution', { method: 'POST' });
        const data = await response.json();
        if (data.ok) document.getElementById('status').innerText = '狀態：正在執行...';
      } catch (e) { console.error(e); }
    }

    async function stopExecution() {
      try {
        const response = await fetch('/api/stop_execution', { method: 'POST' });
        const data = await response.json();
        if (data.ok) document.getElementById('status').innerText = '狀態：已停止';
      } catch (e) { console.error(e); }
    }
  </script>
</body>
</html>
"""

# ##################################################################
# --- 3. 全域變數與鎖 ---
# ##################################################################

running = True
execution_running = False
latest_frame = None
latest_processed_frame = None

frame_lock = threading.Lock()
processed_frame_lock = threading.Lock()
execution_lock = threading.Lock()

last_error = 0
line_lost_timestamp = None

def clamp(value, min_val, max_val):
    return max(min_val, min(value, max_val))

# ##################################################################
# --- 4. 初始化 ---
# ##################################################################

print(f"初始化中... 將遮蔽 X < {SEARCH_START_X} 的左側區域")

robot = LOBOROBOT()
robot.t_stop(0.1)

picamera = Picamera2()
config = picamera.create_preview_configuration(
            main={"format": "RGB888", "size": (WW, HH)},
            transform=libcamera.Transform(hflip=1, vflip=1) 
)
picamera.configure(config)
picamera.start()
time.sleep(1.0)

blank_frame = np.zeros((ROI_HEIGHT, WW, 3), dtype=np.uint8)
cv2.putText(blank_frame, "Ready", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
latest_processed_frame = blank_frame.copy()

print("初始化完成。")

# ##################################################################
# --- 5. 背景執行緒 ---
# ##################################################################

def capture_loop():
    global latest_frame, running
    while running:
        frame_rgb = picamera.capture_array()
        with frame_lock:
            latest_frame = frame_rgb
        time.sleep(0.01)

def motor_control_loop():
    global running, execution_running, latest_frame, latest_processed_frame
    global last_error, line_lost_timestamp
    
    while running:
        with execution_lock:
            is_active = execution_running
            
        with frame_lock:
            if latest_frame is None:
                time.sleep(0.01)
                continue
            frame_rgb = latest_frame.copy()

        # --- A. 影像處理 ---
        frame_hsv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2HSV)
        mask_white = cv2.inRange(frame_hsv, LOWER_WHITE, UPPER_WHITE)
        roi = mask_white[ROI_Y_START : ROI_Y_START + ROI_HEIGHT, :]
        
        # [關鍵修改]：強制遮蔽左側區域
        # 將 ROI 中，X 座標小於 SEARCH_START_X 的部分全部設為 0 (黑色)
        # 這樣 findContours 就絕對找不到左邊的東西
        roi[:, :SEARCH_START_X] = 0

        # 找出剩餘區域(右半邊)的輪廓
        contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_contours = [c for c in contours if cv2.contourArea(c) > 50]
        
        target_contour = None
        cX = -1

        if len(valid_contours) > 0:
            # 既然左邊都遮掉了，我們直接找現存輪廓中最靠近設定位置的
            # 或者單純找「最大」的輪廓 (通常就是車道線)
            # 這裡我們找 "最右邊" 的，確保是外側車道線
            target_contour = max(valid_contours, key=lambda c: cv2.boundingRect(c)[0])
            
            M = cv2.moments(target_contour)
            if M["m00"] > 0:
                cX = int(M["m10"] / M["m00"])

        # --- B. 視覺化 ---
        processed_img = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
        
        # 畫一條灰線，顯示遮蔽的分界
        cv2.line(processed_img, (SEARCH_START_X, 0), (SEARCH_START_X, ROI_HEIGHT), (100, 100, 100), 1)
        # 畫藍色目標線
        cv2.line(processed_img, (TARGET_LINE_POS, 0), (TARGET_LINE_POS, ROI_HEIGHT), (255, 0, 0), 1)
        
        if target_contour is not None:
            x, y, w, h = cv2.boundingRect(target_contour)
            cv2.rectangle(processed_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.circle(processed_img, (cX, ROI_HEIGHT//2), 5, (0, 0, 255), -1)
            err_val = cX - TARGET_LINE_POS
            cv2.putText(processed_img, f"Err:{err_val}", (SEARCH_START_X + 10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        with processed_frame_lock:
            latest_processed_frame = processed_img

        # --- C. 馬達控制 ---
        if not is_active:
            if last_error != 0:
                robot.t_stop(0)
                last_error = 0
            time.sleep(0.1)
            continue

        if cX != -1:
            line_lost_timestamp = None 
            error = cX - TARGET_LINE_POS
            derivative = error - last_error
            turn_offset = (Kp * error) + (Kd * derivative)
            last_error = error
            
            left_speed = clamp(BASE_SPEED + turn_offset, 0, 100)
            right_speed = clamp(BASE_SPEED - turn_offset, 0, 100)

            robot.MotorRun(0, FORWARD, left_speed)
            robot.MotorRun(1, FORWARD, right_speed)
            robot.MotorRun(2, FORWARD, left_speed)
            robot.MotorRun(3, FORWARD, right_speed)

        else:
            if line_lost_timestamp is None:
                line_lost_timestamp = time.time()
                robot.move(FORWARD, BASE_SPEED, 0)
            else:
                elapsed = time.time() - line_lost_timestamp
                if elapsed > GRACE_PERIOD:
                    print("迷路超時(右側無理)，停止。")
                    robot.t_stop(0)
                else:
                    robot.move(FORWARD, BASE_SPEED, 0)

        time.sleep(0.01)
    
    robot.t_stop(0.1)

# ##################################################################
# --- 6. Flask 伺服器 ---
# ##################################################################

app = Flask(__name__)

def mjpeg_generator(source_type):
    global latest_frame, latest_processed_frame
    while True:
        frame = None
        if source_type == 'original':
            with frame_lock:
                if latest_frame is not None:
                    frame = latest_frame.copy()
            if frame is not None:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        elif source_type == 'processed':
            with processed_frame_lock:
                if latest_processed_frame is not None:
                    frame = latest_processed_frame.copy()
        
        if frame is None:
            time.sleep(0.01)
            continue
            
        ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")

@app.route("/")
def index():
    html = INDEX_HTML.replace("{{ search_start }}", str(SEARCH_START_X))
    html = html.replace("{{ target_pos }}", str(TARGET_LINE_POS))
    return render_template_string(html)

@app.route("/live_original")
def video_feed_original():
    return Response(mjpeg_generator('original'), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/live_processed")
def video_feed_processed():
    return Response(mjpeg_generator('processed'), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/start_execution", methods=["POST"])
def start_execution():
    global execution_running
    with execution_lock: execution_running = True
    return jsonify({"ok": True})

@app.route("/api/stop_execution", methods=["POST"])
def stop_execution():
    global execution_running
    with execution_lock: execution_running = False
    return jsonify({"ok": True})

def cleanup():
    global running
    running = False
    try:
        t_camera.join(1.0)
        t_motor.join(1.0)
    except: pass
    robot.t_stop(0.5)
    picamera.stop()
    print("程式結束")

if __name__ == "__main__":
    t_camera = threading.Thread(target=capture_loop, daemon=True)
    t_motor = threading.Thread(target=motor_control_loop, daemon=True)
    t_camera.start()
    t_motor.start()
    
    print(f"啟動服務: http://0.0.0.0:5000")
    try:
        app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()
