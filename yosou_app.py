import streamlit as st
import pandas as pd
import numpy as np
import re

# --- 画面設定 ---
st.set_page_config(page_title="AI競馬予想エンジン", page_icon="🧠", layout="wide")

# ==========================================
# 1. データ前処理関数
# ==========================================
def preprocess_data(df_shutuba, df_past):
    past = df_past.copy()
    past['着順_数値'] = pd.to_numeric(past['着順'], errors='coerce').fillna(99).astype(int)
    past['着差_数値'] = pd.to_numeric(past['着差'], errors='coerce').fillna(9.9)
    
    def extract_corner(x, pos='first'):
        if pd.isna(x) or not isinstance(x, str): return np.nan
        x = x.replace("'", "")
        if '-' not in x: return np.nan
        parts = x.split('-')
        try:
            return int(parts[0]) if pos == 'first' else int(parts[-1])
        except ValueError:
            return np.nan

    past['初角位置'] = past['通過'].apply(lambda x: extract_corner(x, 'first'))
    past['上り_順位'] = past['上り'].str.extract(r'\((\d+)位\)').astype(float)
    past['コース種別'] = past['距離'].str.extract(r'(芝|ダ|障)')
    past['距離_数値'] = past['距離'].str.extract(r'(\d+)').astype(float)

    shutuba = df_shutuba.copy()
    shutuba['コース種別'] = shutuba['距離'].str.extract(r'(芝|ダ|障)')
    shutuba['距離_数値'] = shutuba['距離'].str.extract(r'(\d+)').astype(float)
    shutuba['枠'] = pd.to_numeric(shutuba['枠'], errors='coerce')
    shutuba['馬番'] = pd.to_numeric(shutuba['馬番'], errors='coerce')
    shutuba['斤量_数値'] = pd.to_numeric(shutuba['斤量'], errors='coerce')

    return shutuba, past

# ==========================================
# 2. AI評価エンジンクラス（A〜F判定）
# ==========================================
class HorseEvaluator:
    def __init__(self, horse_row, past_data, race_context):
        self.horse = horse_row
        self.past = past_data
        self.race = race_context
        self.scores = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0}
        self.details = []

    def log(self, item_id, description, point):
        if point != 0:
            self.details.append(f"[{item_id}] {description}: {point:+d}点")

    def eval_A(self):
        score_a, bonus_a = 0, 0
        current_dist = self.race.get('距離_数値', 1600)
        recent_5 = self.past.head(5)
        if len(recent_5) > 0:
            if recent_5[(recent_5['レース名'].str.contains('GI|G1', na=False)) & (recent_5['着順_数値'] <= 5)].shape[0] > 0:
                score_a += 5; self.log('A2', 'G1(5着内)実績', 5)
            elif recent_5[(recent_5['レース名'].str.contains('GII|G2', na=False)) & (recent_5['着順_数値'] <= 5)].shape[0] > 0:
                score_a += 3; self.log('A2', 'G2(5着内)実績', 3)
            elif recent_5[(recent_5['レース名'].str.contains('GIII|G3', na=False)) & (recent_5['着順_数値'] <= 5)].shape[0] > 0:
                score_a += 2; self.log('A2', 'G3(5着内)実績', 2)
        
        if len(self.past[(self.past['距離_数値'] >= current_dist) & (self.past['着順_数値'] > 1) & (self.past['着差_数値'] <= 0.5) & (self.past['上り_順位'] <= 3)]) > 0:
            score_a += 4; self.log('A4', '同距離以上で僅差＆上がり上位', 4)

        if len(self.past[(self.past['着順_数値'] == 1) & (self.past['着差_数値'] >= 0.8)]) > 0:
            bonus_a += 10; self.log('A9', '特例: 圧勝歴ボーナス', 10)

        self.scores['A'] = min(score_a, 10) + bonus_a

    def eval_B(self):
        score_b = 0
        current_place = self.race.get('競馬場', '')
        current_dist = self.race.get('距離_数値', 1600)
        current_baba = self.race.get('馬場', '良')
        course_type = self.race.get('コース種別', '芝')
        waku = self.horse.get('枠', 4)

        if len(self.past[(self.past['競馬場'] == current_place) & (self.past['距離_数値'] == current_dist) & (self.past['着順_数値'] == 1)]) > 0:
            score_b += 5; self.log('B1', 'コース適性(同条件勝利歴)', 5)

        if len(self.past[(self.past['馬場'] == current_baba) & (self.past['着順_数値'] == 1)]) > 0:
            score_b += 4; self.log('B5', f'当日馬場({current_baba})勝利歴', 4)

        if course_type == 'ダ' and current_dist <= 1400:
            if waku >= 6 and (self.past.head(3)['初角位置'] <= 5).any():
                score_b += 6; self.log('B20', 'ダ短距離: 外枠好位特例', 6)

        self.scores['B'] = min(score_b, 25)

    def eval_C(self):
        score_c = 0
        jockey = str(self.horse.get('騎手', ''))
        if any(name in jockey for name in ['モレイラ', 'レーン', 'Ｃ．デムーロ']):
            score_c += 2; self.log('C1', '世界的名手補正', 2)
        self.scores['C'] = min(score_c, 5)

    def eval_D(self):
        score_d = 0
        if len(self.past) >= 3 and (self.past.head(3)['上り_順位'] <= 3).sum() >= 2:
            score_d += 5; self.log('D4', '上がり特化枠', 5)
            
        if self.race.get('pace_forecast') == 'スロー(前残り)' and (self.past.head(3)['初角位置'] <= 5).any():
            score_d += 5; self.log('D5', 'スロー特権(先行実績)', 5)
        self.scores['D'] = min(score_d, 30)

    def eval_E(self):
        score_e = 0
        if self.race.get('pace_forecast') == 'ハイ(前崩れ)' and self.race.get('front_runners_count', 0) >= 4:
            if len(self.past) >= 3 and (self.past.head(3)['初角位置'] <= 4).all():
                score_e -= 10; self.log('E1', '激流巻き込まれ・自滅リスク', -10)

        if self.race.get('course_type') == '芝' and self.race.get('short_to_first_corner') and self.horse.get('枠') >= 7:
            score_e -= 4; self.log('E4', '芝: 外枠距離損リスク', -4)
        elif self.race.get('course_type') == 'ダート':
            self.log('E4', 'ダートのため外枠距離損免除', 0)

        self.scores['E'] = score_e

    def eval_F(self):
        score_f = 0
        if len(self.past) > 0:
            prev_race = self.past.iloc[0]
            if prev_race['着順_数値'] >= 10 and str(prev_race['コース種別']) != self.race.get('コース種別'):
                if len(self.past[(self.past['コース種別'] == self.race.get('コース種別')) & (self.past['着順_数値'] == 1)]) > 0:
                    score_f += 10; self.log('F7', '適性バウンドバック(馬場替わりリセット)', 10)
        self.scores['F'] = min(score_f, 30)

    def calculate_total(self):
        self.eval_A()
        self.eval_B()
        self.eval_C()
        self.eval_D()
        self.eval_E()
        self.eval_F()
        return sum(self.scores.values())

# ==========================================
# 3. Streamlit UI 画面構築
# ==========================================
st.title("🧠 AI競馬予想エンジン（スコア算出＆買い目構築）")
st.write("データ取得アプリでダウンロードした「出馬表CSV」と「過去戦績CSV」をアップロードしてください。")

col_file1, col_file2 = st.columns(2)
with col_file1:
    uploaded_shutuba = st.file_uploader("📥 出馬表CSVをアップロード", type=['csv'])
with col_file2:
    uploaded_past = st.file_uploader("📥 過去戦績CSVをアップロード", type=['csv'])

if uploaded_shutuba is not None and uploaded_past is not None:
    # データの読み込みと前処理
    raw_shutuba = pd.read_csv(uploaded_shutuba)
    raw_past = pd.read_csv(uploaded_past)
    df_shutuba, df_past = preprocess_data(raw_shutuba, raw_past)

    # レース選択UI（複数レースが含まれている場合に対応）
    race_list = df_shutuba['レース'].unique()
    target_race = st.selectbox("🎯 予想するレースを選択してください", race_list)
    
    # 選択したレースでデータを絞り込み
    target_shutuba = df_shutuba[df_shutuba['レース'] == target_race]
    
    st.markdown("---")
    st.markdown("### 🔍 当日の環境・バイアス設定（AIへの指示）")
    col_bias1, col_bias2, col_bias3 = st.columns(3)
    with col_bias1:
        track_bias = st.selectbox("馬場バイアス", ["フラット", "内有利", "外伸び(差し優勢)"])
    with col_bias2:
        pace_forecast = st.selectbox("展開・ペース想定", ["ミドル", "ハイ(前崩れ)", "スロー(前残り)"])
    with col_bias3:
        short_to_first_corner = st.checkbox("初角までの距離が短いコース", value=False)

    if st.button("🚀 この設定で予想を実行する"):
        with st.spinner('全出走馬の条件を合算し、AIスコアを計算中...'):
            
            # 展開予想用の逃げ・先行馬カウント（過去3走で初角3番手以内の経験がある馬の数）
            front_runners_count = 0
            for _, horse_row in target_shutuba.iterrows():
                past_data = df_past[df_past['馬名'] == horse_row['馬名']]
                if len(past_data) > 0 and (past_data.head(3)['初角位置'] <= 3).any():
                    front_runners_count += 1

            race_context = {
                '競馬場': target_shutuba.iloc[0]['競馬場'],
                '距離_数値': target_shutuba.iloc[0]['距離_数値'],
                '馬場': target_shutuba.iloc[0]['馬場'],
                'コース種別': target_shutuba.iloc[0]['コース種別'],
                'track_bias': track_bias,
                'pace_forecast': pace_forecast,
                'short_to_first_corner': short_to_first_corner,
                'front_runners_count': front_runners_count
            }

            results = []
            for index, horse_row in target_shutuba.iterrows():
                past_data = df_past[df_past['馬名'] == horse_row['馬名']]
                evaluator = HorseEvaluator(horse_row, past_data, race_context)
                total_score = evaluator.calculate_total()
                
                results.append({
                    "馬番": horse_row['馬番'],
                    "馬名": horse_row['馬名'],
                    "オッズ": horse_row['オッズ'],
                    "人気": horse_row['人気'],
                    "基礎スコア": total_score,
                    "加点・減点ログ": " / ".join(evaluator.details) if evaluator.details else "特筆すべき条件合致なし"
                })

            df_results = pd.DataFrame(results).sort_values(by="基礎スコア", ascending=False).reset_index(drop=True)
            
            # ランク付け (S, A, B, C)
            def assign_rank(idx, score):
                if idx <= 1 and score > 15: return 'S (軸候補)'
                elif idx <= 4 and score > 5: return 'A (対抗・紐)'
                elif idx <= 8 and score >= 0: return 'B (ヒモ穴)'
                else: return 'C (消し)'
                
            df_results['ランク'] = [assign_rank(i, row['基礎スコア']) for i, row in df_results.iterrows()]
            
            # カラムの並び替え
            df_results = df_results[['ランク', '馬番', '馬名', '基礎スコア', 'オッズ', '人気', '加点・減点ログ']]

            st.success(f"予想完了！ (想定逃げ・先行馬: {front_runners_count}頭)")
            st.dataframe(df_results, use_container_width=True)

            # --- 買い目フォーメーションの自動提案 ---
            st.markdown("### 🎫 推奨買い目フォーメーション")
            s_horses = df_results[df_results['ランク'].str.contains('S')]['馬番'].tolist()
            a_horses = df_results[df_results['ランク'].str.contains('A')]['馬番'].tolist()
            b_horses = df_results[df_results['ランク'].str.contains('B')]['馬番'].tolist()

            if len(s_horses) == 1:
                st.info(f"**【3連複 1頭軸流し】**\n軸: {s_horses[0]}\n相手: {', '.join(map(str, a_horses + b_horses))}")
                st.info(f"**【3連単 フォーメーション (1強特化)】**\n1着: {s_horses[0]}\n2着: {', '.join(map(str, a_horses))}\n3着: {', '.join(map(str, a_horses + b_horses))}")
            elif len(s_horses) >= 2:
                st.info(f"**【3連複 2頭軸流し】**\n軸: {s_horses[0]}, {s_horses[1]}\n相手: {', '.join(map(str, a_horses + b_horses))}")
            else:
                st.warning("圧倒的なSランク不在のため、Aランク馬を中心としたBOX買い、または馬連推奨の大混戦です。")