因為用的是HSV的方式去處理遮罩<br>
開始跑之前要先校正過矩陣上下界<br>

先用HSV_test.py放在本機<br>
pi_client.py放在Pi5上<br>
執行後就可以透過滑軌調HSV的數值，視窗即時顯示結果<br>
找到最佳數值後記住就可退出<br>

去到flaskweb_Lanefollowing.py<br>
將 line26後的內容更改一下<br>

```md
# --- 白色線條的 HSV 閥值 ---
LOWER_WHITE = np.array([0, 0, 150])
UPPER_WHITE = np.array([30, 120, 255])
```

更改完成後就可以開始車道偵測循線了，Picamera的角度要喬一下<br>
可以的話最好配合更改line 21的ROI作用範圍，防止車道線丟失

