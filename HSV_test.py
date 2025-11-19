import cv2
import numpy as np
import imagezmq

# ##################################################################
# --- 1. 參數設定 ---
# ##################################################################

# 影像設定 (必須與 Pi 傳來的影像一致)
WW, HH = 320, 240

# --- 您舊的 HSV 閥值 (作為滑桿的「起始位置」) ---
H_MIN_START = 0
S_MIN_START = 0
V_MIN_START = 185 # <--- 這是您舊的 V_min

H_MAX_START = 180
S_MAX_START = 50
V_MAX_START = 255

# ##################################################################
# --- 2. 初始化 ImageZMQ 和 OpenCV 滑桿 ---
# ##################################################################

# 一個空函式，給 createTrackbar 使用
def nothing(x):
    pass

# 建立一個視窗來容納滑桿
cv2.namedWindow("HSV Tuner")
cv2.resizeWindow("HSV Tuner", 500, 300) # (寬, 高)

# 建立 6 個滑桿 (H, S, V 的 Min 和 Max)
cv2.createTrackbar('H_min', 'HSV Tuner', H_MIN_START, 179, nothing) # Hue 最大值是 179
cv2.createTrackbar('S_min', 'HSV Tuner', S_MIN_START, 255, nothing)
cv2.createTrackbar('V_min', 'HSV Tuner', V_MIN_START, 255, nothing)

cv2.createTrackbar('H_max', 'HSV Tuner', H_MAX_START, 179, nothing)
cv2.createTrackbar('S_max', 'HSV Tuner', S_MAX_START, 255, nothing)
cv2.createTrackbar('V_max', 'HSV Tuner', V_MAX_START, 255, nothing)

# 初始化 ImageZMQ 伺服器
image_hub = imagezmq.ImageHub()

print("PC HSV 調節器已啟動。正在等待 Pi 5 連線...")
print("請調整 'HSV Tuner' 視窗中的滑桿。")
print("按下 'q' 鍵 (在影像視窗上) 可停止程式。")

# ##################################################################
# --- 3. 處理迴圈 ---
# ##################################################################

try:
    while True:
        # 1. 接收來自 Pi 的影像 (RGB)
        rpi_name, frame_rgb = image_hub.recv_image()
        
        # 2. 將影像從 RGB 轉為 BGR (OpenCV 顯示用) 和 HSV (演算法用)
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        frame_hsv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2HSV)

        # 3. 從滑桿讀取目前的 H, S, V 值
        h_min = cv2.getTrackbarPos('H_min', 'HSV Tuner')
        s_min = cv2.getTrackbarPos('S_min', 'HSV Tuner')
        v_min = cv2.getTrackbarPos('V_min', 'HSV Tuner')
        
        h_max = cv2.getTrackbarPos('H_max', 'HSV Tuner')
        s_max = cv2.getTrackbarPos('S_max', 'HSV Tuner')
        v_max = cv2.getTrackbarPos('V_max', 'HSV Tuner')

        # 4. 建立 NumPy 陣列
        lower_bound = np.array([h_min, s_min, v_min])
        upper_bound = np.array([h_max, s_max, v_max])

        # 5. 執行 cv2.inRange() 來產生黑白遮罩
        mask = cv2.inRange(frame_hsv, lower_bound, upper_bound)
        
        # (可選) 將遮罩轉為 3 通道 BGR，以便和原圖合併
        mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        # 6. 建立一個並排的顯示畫面 (左:原圖, 右:遮罩)
        combined_display = np.hstack([frame_bgr, mask_bgr])

        # 7. 顯示影像
        cv2.imshow("Original (Left)  |  HSV Mask (Right)", combined_display)
        
        # 8. (重要) 傳送一個 "OK" 回應給 Pi 5，防止 Pi 5 卡住
        image_hub.send_reply(b'OK')

        # 9. 鍵盤中斷 (按下 'q' 鍵)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n偵測到 'q' 鍵，正在停止...")
            break 

except KeyboardInterrupt:
    print("\n偵測到 Ctrl+C，正在關閉...")
finally:
    # 關閉所有視窗並釋放資源
    cv2.destroyAllWindows()
    image_hub.close()
    
    # [新] 在程式結束時，印出您最後調整好的值
    print("\n--- 您調整後的 HSV 閥值 ---")
    print(f"LOWER_WHITE = np.array([{h_min}, {s_min}, {v_min}])")
    print(f"UPPER_WHITE = np.array([{h_max}, {s_max}, {v_max}])")
    print("---------------------------------")
    print("請將這兩行複製到您的 pc_server_cv.py 腳本中。")