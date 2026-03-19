import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
import io

st.set_page_config(page_title="レース結果スクレイピング", layout="wide")

st.title("🐎 競馬レース結果 スクレイピングアプリ")
st.write("netkeibaのレース結果URLを入力すると、結果データを抽出してテキストコピー可能な形式に変換します。")

# URL入力欄
default_url = "https://race.netkeiba.com/race/result.html?race_id=202606020611"
url_input = st.text_input("レース結果のURLを入力してください:", default_url)

if st.button("データを抽出する"):
    with st.spinner('データを取得中...'):
        try:
            # サーバーに負荷をかけないようヘッダーを設定
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url_input, headers=headers)
            response.encoding = 'EUC-JP' # netkeiba特有の文字コードに対応
            html = response.text
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # pandasを使ってHTML内のテーブル（表）を一括取得
            tables = pd.read_html(io.StringIO(html))
            
            if len(tables) > 0:
                # ------------------------------
                # 1. メインのレース結果テーブル
                # ------------------------------
                st.subheader("🏆 レース結果")
                df_result = tables[0] # 通常、最初の表が着順データ
                
                # Streamlitの表として表示
                st.dataframe(df_result, use_container_width=True)
                
                # Excelやスプレッドシートにコピペしやすいようタブ区切りで出力
                st.write("▼ Excel/スプレッドシート貼り付け用（テキストをコピーしてください）")
                st.text_area("レース結果コピー用", df_result.to_csv(sep='\t', index=False), height=200)

                # ------------------------------
                # 2. 払い戻しテーブル
                # ------------------------------
                st.subheader("💰 払い戻し")
                # 払い戻し情報は通常、2番目以降のテーブルに分割されている
                pay_dfs = []
                for table in tables[1:]:
                    if len(table.columns) >= 2 and len(table) > 0:
                        pay_dfs.append(table)
                
                if pay_dfs:
                    # 払い戻し表を縦に結合して表示
                    df_payout = pd.concat(pay_dfs, ignore_index=True)
                    st.dataframe(df_payout, use_container_width=True)
                    st.text_area("払い戻しコピー用", df_payout.to_csv(sep='\t', index=False), height=150)

                # ------------------------------
                # 3. コーナー通過順位・ラップタイム
                # ------------------------------
                st.subheader("⏱ コーナー通過順 / ラップタイム")
                
                # HTMLから特定のクラスを持つ要素を検索
                lap_info = soup.find('div', class_='Race_HaronTime')
                corner_info = soup.find('div', class_='Corner_Pass')
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if lap_info:
                        st.markdown("**ラップタイム**")
                        # テキストとして抽出して整形
                        lap_text = lap_info.get_text(separator='\t', strip=True)
                        st.text_area("ラップタイムコピー用", lap_text, height=100)
                    else:
                        st.info("ラップタイム情報が見つかりませんでした。")

                with col2:
                    if corner_info:
                        st.markdown("**コーナー通過順位**")
                        corner_text = corner_info.get_text(separator='\n', strip=True)
                        st.text_area("コーナー順位コピー用", corner_text, height=100)
                    else:
                        st.info("コーナー通過順位情報が見つかりませんでした。")

        except Exception as e:
            st.error(f"データ抽出中にエラーが発生しました: {e}")
            st.warning("URLが間違っているか、サイトのHTML構造が変更された可能性があります。")