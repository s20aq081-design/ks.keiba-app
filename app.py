import streamlit as st
import requests
from bs4 import BeautifulSoup
import csv
import time
import re
import os

# --- Webアプリの画面設定 ---
st.set_page_config(page_title="競馬データ取得アプリ", page_icon="🏇")
st.title("🏇 競馬データ取得Webアプリ")
st.write("netkeibaの出馬表URLから、Gemini予想用の高精度データを取得します。")

# 入力フォーム
race_url = st.text_input("取得したいレースの出馬表URL", placeholder="例: https://race.netkeiba.com/race/shutuba.html?race_id=...")
file_prefix = st.text_input("出力するCSVの名前", placeholder="例: 20260315_金鯱賞")

# 実行ボタン
if st.button("データ取得開始"):
    if not race_url or "race.netkeiba.com" not in race_url:
        st.error("【エラー】netkeibaの出馬表URLを正しく入力してください。")
    else:
        if not file_prefix.strip():
            file_prefix = "未設定レース"
            
        csv_shutuba = f"{file_prefix}_出走馬データ.csv"
        csv_past = f"{file_prefix}_戦績データ_過去20戦.csv"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

        # ==========================================
        # 1. 出馬表データの取得
        # ==========================================
        st.info(f"出走馬データを取得中...")
        response = requests.get(race_url, headers=headers)
        response.encoding = 'euc-jp'
        soup = BeautifulSoup(response.text, 'html.parser')

        horse_list = []
        horse_urls = []

        race_data01_text = soup.select_one('.RaceData01').text if soup.select_one('.RaceData01') else ""
        race_data02_text = soup.select_one('.RaceData02').text if soup.select_one('.RaceData02') else ""
        dist_match = re.search(r'(芝|ダ|障)\d+m', race_data01_text)
        baba_match = re.search(r'馬場:([良稍重不]+)', race_data01_text)
        places = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉", "帯広", "門別", "盛岡", "水沢", "浦和", "船橋", "大井", "川崎", "金沢", "笠松", "名古屋", "園田", "姫路", "高知", "佐賀"]
        place_match = re.search(r'(' + '|'.join(places) + r')', race_data02_text)

        race_dist = dist_match.group(0) if dist_match else "不明"
        race_baba = baba_match.group(1) if baba_match else "不明"
        race_place = place_match.group(0) if place_match else "不明"

        rows = soup.select('.RaceTableArea tr.HorseList')

        for row in rows:
            tds = row.find_all('td')
            if len(tds) >= 11:
                waku = tds[0].text.strip()
                umaban = tds[1].text.strip()
                horse_elem = tds[3].find('a')
                horse_name = horse_elem.text.strip() if horse_elem else tds[3].text.strip()
                seirei = tds[4].text.strip()
                kinryo = tds[5].text.strip()
                jockey = tds[6].text.strip()
                kyusha = tds[7].text.strip()
                bataiju = tds[8].text.strip()
                odds = tds[9].text.strip()
                ninki = tds[10].text.strip()
                
                if horse_name:
                    horse_list.append([race_place, race_dist, race_baba, waku, umaban, horse_name, seirei, kinryo, jockey, kyusha, bataiju, odds, ninki])
                    if horse_elem and 'href' in horse_elem.attrs:
                        match = re.search(r'\d{10}', horse_elem['href'])
                        if match:
                            db_url = f"https://db.netkeiba.com/horse/result/{match.group(0)}/"
                            horse_urls.append((horse_name, db_url))

        with open(csv_shutuba, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['競馬場', '距離', '馬場', '枠', '馬番', '馬名', '性齢', '斤量', '騎手', '厩舎', '馬体重', 'オッズ', '人気'])
            writer.writerows(horse_list)

        # できたファイルをダウンロードボタンとして表示
        with open(csv_shutuba, 'rb') as f:
            st.download_button(label=f"📥 {csv_shutuba} をダウンロード", data=f, file_name=csv_shutuba, mime='text/csv')

        # ==========================================
        # 2. 過去戦績データの取得
        # ==========================================
        st.info("過去20戦のデータを取得しています...（約30秒〜1分かかります）")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        past_results = []
        total_horses = len(horse_urls)

        for i, (horse_name, url) in enumerate(horse_urls):
            status_text.text(f"処理中: {horse_name} ({i+1}/{total_horses}頭目)")
            res_horse = requests.get(url, headers=headers)
            res_horse.encoding = 'euc-jp'
            soup_horse = BeautifulSoup(res_horse.text, 'html.parser')
            
            th_elements = soup_horse.select('table.db_h_race_results th')
            col_map = {th.text.strip(): idx for idx, th in enumerate(th_elements)}
            
            history_rows = soup_horse.select('table.db_h_race_results tr')
            race_count = 0
            
            for h_row in history_rows:
                tds = h_row.find_all('td')
                if len(tds) >= 25 and col_map: 
                    date = tds[col_map.get('日付', 0)].text.strip()
                    race_name = tds[col_map.get('レース名', 4)].text.strip()
                    tousuu = tds[col_map.get('頭数', 6)].text.strip()
                    waku = tds[col_map.get('枠番', 7)].text.strip()
                    umaban = tds[col_map.get('馬番', 8)].text.strip()
                    odds = tds[col_map.get('オッズ', 9)].text.strip()
                    ninki = tds[col_map.get('人気', 10)].text.strip()
                    chakujun = tds[col_map.get('着順', 11)].text.strip()
                    jockey = tds[col_map.get('騎手', 12)].text.strip()
                    kinryo = tds[col_map.get('斤量', 13)].text.strip()
                    kyori = tds[col_map.get('距離', 14)].text.strip()
                    baba = tds[col_map.get('馬場', 15)].text.strip()
                    time_str = tds[col_map.get('タイム', 17)].text.strip()
                    chakusa = tds[col_map.get('着差', 18)].text.strip()
                    tsuuka = tds[col_map.get('通過', 20)].text.strip()
                    pace = tds[col_map.get('ペース', 21)].text.strip()
                    bataiju = tds[col_map.get('馬体重', 23)].text.strip()
                    
                    if tsuuka == "":
                        tsuuka = "直線"
                        
                    agari_td = tds[col_map.get('上り', 22)]
                    agari = agari_td.text.strip()
                    agari_html = str(agari_td).lower()
                    
                    if 'yellow' in agari_html: agari += "(1位)"
                    elif 'blue' in agari_html or 'aqua' in agari_html: agari += "(2位)"
                    elif 'orange' in agari_html or 'red' in agari_html: agari += "(3位)"

                    past_results.append([horse_name, date, race_name, tousuu, waku, umaban, odds, ninki, chakujun, jockey, kinryo, kyori, baba, time_str, chakusa, tsuuka, pace, agari, bataiju])
                    
                    race_count += 1
                    if race_count >= 20: 
                        break
                        
            time.sleep(2)
            progress_bar.progress((i + 1) / total_horses)

        with open(csv_past, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['馬名', '日付', 'レース名', '頭数', '枠番', '馬番', 'オッズ', '人気', '着順', '騎手', '斤量', '距離', '馬場', 'タイム', '着差', '通過', 'ペース', '上り', '馬体重'])
            writer.writerows(past_results)

        status_text.text("すべてのデータ取得が完了しました！")
        st.success("取得完了！下のボタンからダウンロードしてください。")
        
        with open(csv_past, 'rb') as f:
            st.download_button(label=f"📥 {csv_past} をダウンロード", data=f, file_name=csv_past, mime='text/csv')