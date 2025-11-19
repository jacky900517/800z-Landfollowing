import cv2
import time
import imagezmq
import libcamera
from picamera2 import Picamera2
from LOBOROBOT2 import LOBOROBOT, FORWARD
import socket # 用於取得 Pi 的名稱

# ##################################################################
# --- 1. Pi 端的參數設定 ---
# ##################################################################

# [關鍵] 請將 '192.168.1.100' 改成您上一步查到的「電腦 IP 位址」
PC_IP_ADDRESS = '172.20.10.13'

# 影像設定 (必須與 PC 端一致)
WW, HH = 320, 240

# ##################################################################
# --- 2. 初始化 Pi ---
# ##################################################################

print("正在初始化元件...")

# 初始化 LOBOROBOT
try:
    robot = LOBOROBOT()
    robot.t_stop(0.1)
    print("馬達控制 (LOBOROBOT) 已載入。")
except Exception as e:
    print(f"錯誤: 無法載入 LOBOROBOT2。 {e}")
    print("請檢查 LOBOROBOT2.py 是否存在，以及 lgpio 是否已安裝 (pip install lgpio)")
    exit()

# 初始化 Picamera2
try:
    picamera = Picamera2()
    config = picamera.create_preview_configuration(
                main={"format": "RGB888", "size": (WW, HH)},
                transform=libcamera.Transform(hflip=1, vflip=1) 
    )
    picamera.configure(config)
    picamera.start()
    time.sleep(1.0)
    print("攝影機 (Picamera2) 已啟動。")
except Exception as e:
    print(f"錯誤: 無法啟動 Picamera2。 {e}")
    print("請檢查相機是否插好，以及 picamera2 是否已安裝 (pip install picamera2)")
    exit()

# 初始化 ImageZMQ 傳送器
sender = imagezmq.ImageSender(connect_to=f'tcp://{PC_IP_ADDRESS}:5555')

# 取得 Pi 的名稱 (只是為了讓伺服器知道是誰)
rpi_name = socket.gethostname()

print(f"Pi ({rpi_name}) 正在連線到 PC 大腦 ({PC_IP_ADDRESS})...")

# ##################################################################
# --- 3. 傳送/接收 迴圈 ---
# ##################################################################

try:
    while True:
        # 1. 擷取影像 (RGB 格式)
        frame_rgb = picamera.capture_array()
        
        # 2. [傳送] 將影像傳送給 PC，並「等待」PC 回應
        #    這一步會自動鎖住迴圈，直到 PC 處理完並回傳指令
        reply_bytes = sender.send_image(rpi_name, frame_rgb)
        
        # 3. [接收] 解碼 PC 傳來的指令
        try:
            reply_str = reply_bytes.decode('utf-8')
            left_speed, right_speed = map(int, reply_str.split(','))
            
            # (可選) 在 Pi 的終端機顯示收到的指令
            # print(f"收到指令: Left={left_speed}, Right={right_speed}")
            
            # 4. [執行] 控制馬達
            if left_speed == 0 and right_speed == 0:
                robot.t_stop(0)
            else:
                robot.MotorRun(0, FORWARD, left_speed)
                robot.MotorRun(1, FORWARD, right_speed)
                robot.MotorRun(2, FORWARD, left_speed)
                robot.MotorRun(3, FORWARD, right_speed)

        except Exception as e:
            print(f"解析指令時發生錯誤: {e}")
            robot.t_stop(0)

except KeyboardInterrupt:
    print("\n偵測到 Ctrl+C，正在停止...")
finally:
    robot.t_stop(0.5)
    picamera.stop()
    sender.close()
    print("Pi 客戶端已關閉。")