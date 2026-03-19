import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
import io

st.set_page_config(page_title="競馬結果スクレイパー", layout="wide")

st.title("🐎 競馬結果抽出アプリ")
st.write("URLを入力すると、結果と払い戻しをコピー可能な形式で抽出します。")

url_input = st.text_input("netkeiba レース結果URL:", "https://race.netkeiba.com/race/result.html?race_id=202606020611")

if st.button("データ抽出開始"):
    with st.spinner('データを解析中...'):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url_input, headers=headers)
            response.encoding = 'EUC-JP'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # --- ペース情報の取得 ---
            # netkeibaのレース概要欄からペース（例：前3F 34.5 - 後3F 35.8）を探します
            pace_val = "取得失敗"
            race_data = soup.find('div', class_='RaceData01')
            if race_data:
                # サイト構造から「ペース」という文字を含む要素を検索
                pace_info = [span.get_text() for span in race_data.find_all('span') if '前' in span.get_text() or '後' in span.get_text()]
                if pace_info:
                    pace_val = " / ".join(pace_info)
                else:
                    # ペースが直接見つからない場合はハロンタイムから推測（簡易版）
                    pace_val = "サイト上で確認してください"

            # --- テーブルデータの取得 ---
            tables = pd.read_html(io.StringIO(response.text))
            
            # 1. レース結果（着順、枠、馬番、馬名、性齢、斤量、騎手、タイム、着差、人気、単勝オッズ、後3F、コーナー通過順、厩舎、馬体重）
            df_result = tables[0]
            
            # 2. 払い戻し（単勝〜3連単まで全て結合）
            pay_dfs = []
            for t in tables[1:]:
                # 払い戻しテーブル特有の「単勝」や「三連単」という文字が含まれているかチェック
                if any(x in str(t.values) for x in ['単勝', '三連単', '馬連']):
                    pay_dfs.append(t)
            df_payout = pd.concat(pay_dfs, ignore_index=True) if pay_dfs else pd.DataFrame()

            # --- 画面表示 ---
            st.success(f"解析完了！ ペース: **{pace_val}**")
            
            # コピー用テキストの作成
            result_text = f"【ペース】: {pace_val}\n\n" + df_result.to_csv(sep='\t', index=False)
            payout_text = df_payout.to_csv(sep='\t', index=False) if not df_payout.empty else "払い戻しデータなし"

            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📋 レース結果 (コピー用)")
                st.info("右上のアイコンをクリックで全選択コピーできます")
                # st.code を使うと右上にコピーボタンが出現します
                st.code(result_text, language="text")

            with col2:
                st.subheader("💰 払い戻し (コピー用)")
                st.info("単勝〜3連単まで抽出済み")
                st.code(payout_text, language="text")

            # プレビュー用表示
            with st.expander("表形式でプレビューを確認"):
                st.write("### 結果一覧")
                st.dataframe(df_result)
                st.write("### 払い戻し一覧")
                st.dataframe(df_payout)

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")