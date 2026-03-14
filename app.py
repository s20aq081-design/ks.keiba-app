import streamlit as st
import requests
from bs4 import BeautifulSoup
import csv
import time
import re

# --- Webアプリの画面設定 ---
st.set_page_config(page_title="競馬データ一括取得アプリ", page_icon="🏇")

# --- ダウンロード保持用の裏金庫（セッションステート） ---
if "data_fetched" not in st.session_state:
    st.session_state.data_fetched = False
    st.session_state.csv_shutuba_data = None
    st.session_state.csv_past_data = None
    st.session_state.csv_shutuba_name = ""
    st.session_state.csv_past_name = ""

# ==========================================
# 🔒 ログイン機能
# ==========================================
def check_password():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("🔒 ログイン")
        st.write("このアプリを利用するにはIDとパスワードが必要です。")
        
        user_id = st.text_input("ID")
        password = st.text_input("パスワード", type="password")
        
        if st.button("ログイン"):
            if user_id == st.secrets["app_user"]["id"] and password == st.secrets["app_user"]["password"]:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("IDまたはパスワードが間違っています。")
        return False
    return True

# ==========================================
# メインのアプリ処理
# ==========================================
if check_password():
    st.title("🏇 競馬データ一括取得Webアプリ")
    st.write("netkeibaの出馬表URLを基準に、指定した複数レースのデータを1つのファイルにまとめて取得します。")
    
    if st.button("ログアウト"):
        st.session_state.logged_in = False
        st.session_state.data_fetched = False
        st.rerun()

    # --- 入力フォーム（複数レース対応版） ---
    st.markdown("### 📝 取得設定")
    race_url = st.text_input("基準となる出馬表URL (何レース目のURLでもOKです)", placeholder="例: https://race.netkeiba.com/race/shutuba.html?race_id=202607010211")
    
    col1, col2 = st.columns(2)
    with col1:
        start_race = st.number_input("開始レース", min_value=1, max_value=12, value=1)
    with col2:
        end_race = st.number_input("終了レース", min_value=1, max_value=12, value=12)

    file_prefix = st.text_input("出力するCSVの名前", placeholder="例: 20260315_中京競馬場")

    # 実行ボタン
    if st.button("一括データ取得開始"):
        
        st.session_state.data_fetched = False # 金庫リセット
        
        if race_url:
            race_url = race_url.replace("race.sp.netkeiba.com", "race.netkeiba.com")

        # URLから「12桁のレースID」を探し出し、先頭10桁（日付と場所）を基準IDとして抜き出す
        match_id = re.search(r'race_id=(\d{12})', race_url)
        if not match_id and "race_id=" not in race_url:
            match_id = re.search(r'(\d{12})', race_url) # URL直書きへのフォールバック

        if not match_id:
            st.error("【エラー】URLから12桁のレースIDが見つかりません。正しいURLを入力してください。")
        elif start_race > end_race:
            st.error("【エラー】開始レースは、終了レース以下の数字にしてください。")
        else:
            base_id = match_id.group(1)[:10] # 先頭10桁
            
            if not file_prefix.strip():
                file_prefix = f"一括取得_{base_id}"
                
            csv_shutuba = f"{file_prefix}_{start_race}Rから{end_race}R_出走馬データ.csv"
            csv_past = f"{file_prefix}_{start_race}Rから{end_race}R_戦績データ.csv"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

            all_horse_list = []
            all_horse_urls = []
            
            total_races = end_race - start_race + 1

            # ==========================================
            # 1. 出馬表データの取得（複数レースをループ）
            # ==========================================
            st.info(f"🐎 {start_race}R から {end_race}R までの出馬表データを集めています...")
            shutuba_progress = st.progress(0)
            
            for idx, r_num in enumerate(range(start_race, end_race + 1)):
                # レース番号(1〜12)を2桁のゼロ埋め(01〜12)にしてURLを作成
                current_race_id = f"{base_id}{r_num:02d}"
                current_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={current_race_id}"
                
                response = requests.get(current_url, headers=headers)
                response.encoding = 'euc-jp'
                soup = BeautifulSoup(response.text, 'html.parser')
                
                rows = soup.select('.RaceTableArea tr.HorseList')
                if not rows:
                    # そのレースが存在しない場合（11Rまでしかない等）はスキップ
                    shutuba_progress.progress((idx + 1) / total_races)
                    time.sleep(1)
                    continue

                race_data01_text = soup.select_one('.RaceData01').text if soup.select_one('.RaceData01') else ""
                race_data02_text = soup.select_one('.RaceData02').text if soup.select_one('.RaceData02') else ""
                dist_match = re.search(r'(芝|ダ|障)\d+m', race_data01_text)
                baba_match = re.search(r'馬場:([良稍重不]+)', race_data01_text)
                places = ["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉", "帯広", "門別", "盛岡", "水沢", "浦和", "船橋", "大井", "川崎", "金沢", "笠松", "名古屋", "園田", "姫路", "高知", "佐賀"]
                place_match = re.search(r'(' + '|'.join(places) + r')', race_data02_text)

                race_dist = dist_match.group(0) if dist_match else "不明"
                race_baba = baba_match.group(1) if baba_match else "不明"
                race_place = place_match.group(0) if place_match else "不明"

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
                            # 左端に「何レース目か」を追加して1つのリストに合流させる
                            all_horse_list.append([f"{r_num}R", race_place, race_dist, race_baba, waku, umaban, horse_name, seirei, kinryo, jockey, kyusha, bataiju, odds, ninki])
                            
                            if horse_elem and 'href' in horse_elem.attrs:
                                match = re.search(r'\d{10}', horse_elem['href'])
                                if match:
                                    all_horse_urls.append((horse_name, match.group(0)))
                
                shutuba_progress.progress((idx + 1) / total_races)
                time.sleep(1) # サーバー負荷軽減

            # 出馬表CSVの書き込み（ヘッダーに「レース」列を追加）
            with open(csv_shutuba, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['レース', '競馬場', '距離', '馬場', '枠', '馬番', '馬名', '性齢', '斤量', '騎手', '厩舎', '馬体重', 'オッズ', '人気'])
                writer.writerows(all_horse_list)

            # ==========================================
            # 2. 過去戦績データの取得（全レースの馬を一括処理）
            # ==========================================
            total_horses = len(all_horse_urls)
            st.info(f"📊 続いて、全{total_horses}頭の過去20戦データを一気に取得します！（約{total_horses}秒かかります）")
            past_progress_bar = st.progress(0)
            status_text = st.empty()
            
            all_past_results = []

            for i, (horse_name, horse_id) in enumerate(all_horse_urls):
                status_text.text(f"処理中: {horse_name} ({i+1}/{total_horses}頭目)")

                url_res = f"https://db.netkeiba.com/horse/result/{horse_id}/"
                res_res = requests.get(url_res, headers=headers)
                res_res.encoding = 'euc-jp'
                soup_res = BeautifulSoup(res_res.text, 'html.parser')
                
                th_elements = soup_res.select('table.db_h_race_results th')
                col_map = {th.text.strip(): idx for idx, th in enumerate(th_elements)}
                
                history_rows = soup_res.select('table.db_h_race_results tr')
                race_count = 0
                
                for h_row in history_rows:
                    tds = h_row.find_all('td')
                    if len(tds) >= 25 and col_map: 
                        date = tds[col_map.get('日付', 0)].text.strip()
                        
                        kaisai_raw = tds[col_map.get('開催', 1)].text.strip()
                        keibajo = re.sub(r'\d+', '', kaisai_raw)
                        
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
                        if tsuuka != "":
                            tsuuka = f"'{tsuuka}"
                        else:
                            tsuuka = "直線"
                            
                        pace = tds[col_map.get('ペース', 21)].text.strip()
                        bataiju = tds[col_map.get('馬体重', 23)].text.strip()
                        
                        agari = ""
                        agari_idx = col_map.get('上り', 22)
                        if len(tds) > agari_idx:
                            agari_td = tds[agari_idx]
                            agari_time = agari_td.text.strip()
                            
                            classes = agari_td.get('class', [])
                            if 'rank_1' in classes:
                                agari = f"{agari_time}(1位)"
                            elif 'rank_2' in classes:
                                agari = f"{agari_time}(2位)"
                            elif 'rank_3' in classes:
                                agari = f"{agari_time}(3位)"
                            else:
                                agari = agari_time

                        all_past_results.append([horse_name, date, keibajo, race_name, tousuu, waku, umaban, odds, ninki, chakujun, jockey, kinryo, kyori, baba, time_str, chakusa, tsuuka, pace, agari, bataiju])
                        
                        race_count += 1
                        if race_count >= 20: 
                            break
                            
                time.sleep(1)
                past_progress_bar.progress((i + 1) / total_horses)

            # 戦績CSVの書き込み
            with open(csv_past, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['馬名', '日付', '競馬場', 'レース名', '頭数', '枠番', '馬番', 'オッズ', '人気', '着順', '騎手', '斤量', '距離', '馬場', 'タイム', '着差', '通過', 'ペース', '上り', '馬体重'])
                writer.writerows(all_past_results)

            status_text.text("すべてのデータ取得が完了しました！")
            
            # データを金庫に保存
            with open(csv_shutuba, 'rb') as f:
                st.session_state.csv_shutuba_data = f.read()
            st.session_state.csv_shutuba_name = csv_shutuba
            
            with open(csv_past, 'rb') as f:
                st.session_state.csv_past_data = f.read()
            st.session_state.csv_past_name = csv_past
            
            st.session_state.data_fetched = True

    # ==========================================
    # 3. ダウンロードボタンの表示
    # ==========================================
    if st.session_state.data_fetched:
        st.success("✨ 取得完了！下のボタンからダウンロードしてください。")
        st.write("※どちらを先にダウンロードしても、画面はリセットされません。")
        
        st.download_button(
            label=f"📥 【1】出馬表データ（複数レース合体版）をダウンロード", 
            data=st.session_state.csv_shutuba_data, 
            file_name=st.session_state.csv_shutuba_name, 
            mime='text/csv'
        )

        st.download_button(
            label=f"📥 【2】過去戦績データ（全馬合体版）をダウンロード", 
            data=st.session_state.csv_past_data, 
            file_name=st.session_state.csv_past_name, 
            mime='text/csv'
        )