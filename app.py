import streamlit as st
import requests
from bs4 import BeautifulSoup
import csv
import time
import re

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
            writer.writerow(['競馬場', '距離',