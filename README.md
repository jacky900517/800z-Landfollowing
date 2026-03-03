因為用的是HSV的方式去處理遮罩<br>
開始跑之前要先校正過矩陣上下界<br>

先用`HSV_test.py`放在本機<br>
`pi_client.py`放在Pi5上<br>
執行後就可以透過滑軌調HSV的數值，視窗即時顯示結果<br>
找到最佳數值後記住就可退出<br>

去到`flaskweb_Lanefollowing.py`<br>
或是`EDGEfollowing.py`<br>
將line26後的內容更改一下<br>

舉例：
```md
# --- 白色線條的 HSV 閥值 ---
# 把上下界剛剛校正過的資料更新到矩陣中
LOWER_WHITE = np.array([0, 0, 150]) 
UPPER_WHITE = np.array([30, 120, 255]) 
```
