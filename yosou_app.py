import streamlit as st
import pandas as pd
import numpy as np
import re

# --- 画面設定 ---
st.set_page_config(page_title="AI競馬予想エンジン", page_icon="🧠", layout="wide")

# ==========================================
# 1. コースデータ・自動判定データベース
# ==========================================
def get_course_info(keibajo, c_type, dist):
    shiba_start_list = [
        ('東京', 1600), ('中山', 1200), ('京都', 1400), 
        ('阪神', 1400), ('阪神', 2000), ('中京', 1400), 
        ('新潟', 1200), ('福島', 1150)
    ]
    is_shiba_start = (c_type == 'ダ' and (keibajo, dist) in shiba_start_list)

    short_courses = [
        ('中山', '芝', 1600), ('中山', '芝', 2500), ('中山', 'ダ', 1800),
        ('阪神', '芝', 2000), ('阪神', '芝', 2200), ('阪神', 'ダ', 1800), ('阪神', 'ダ', 2000),
        ('京都', '芝', 2000), ('京都', 'ダ', 1400), ('京都', 'ダ', 1800), ('京都', 'ダ', 1900),
        ('東京', '芝', 2000),
        ('中京', '芝', 2000), ('中京', 'ダ', 1800), ('中京', 'ダ', 1900),
        ('小倉', '芝', 1200), ('小倉', '芝', 1800), ('小倉', 'ダ', 1700),
        ('福島', '芝', 1200), ('福島', '芝', 2000), ('福島', 'ダ', 1700),
        ('新潟', '芝', 2000), ('新潟', 'ダ', 1800),
        ('函館', 'ダ', 1700), ('札幌', 'ダ', 1700)
    ]
    
    long_courses = [
        ('東京', '芝', 1600), ('東京', '芝', 1800), ('東京', 'ダ', 1300), ('東京', 'ダ', 1400), ('東京', 'ダ', 1600),
        ('新潟', '芝', 1600), ('新潟', '芝', 1800), ('新潟', 'ダ', 1200),
        ('中山', 'ダ', 1200), 
        ('阪神', 'ダ', 1200), ('阪神', 'ダ', 1400),
        ('京都', '芝', 1600), ('京都', '芝', 1800)
    ]

    if (keibajo, c_type, dist) in short_courses:
        corner_len = '短い'
    elif (keibajo, c_type, dist) in long_courses:
        corner_len = '長い'
    else:
        corner_len = '標準'

    return is_shiba_start, corner_len

# ==========================================
# 2. データ前処理関数
# ==========================================
def preprocess_data(df_shutuba, df_past):
    past = df_past.copy()
    
    # 🌟 追加: 「中止」「除外」「取消」が含まれる行（レース）をデータから完全に除外する
    past = past[~past.get('着順', pd.Series(dtype=str)).astype(str).str.contains('中止|除外|取消', na=False)]
    
    # 🌟 追加: netkeiba特有の「不」を「不良」に統一（これで以降の道悪判定が全て正常に機能します）
    if '馬場' in past.columns:
        past['馬場'] = past['馬場'].astype(str).replace('不', '不良')
        
    past['着順_数値'] = pd.to_numeric(past.get('着順', 99), errors='coerce').fillna(99).astype(int)
    past['着差_数値'] = pd.to_numeric(past.get('着差', 9.9), errors='coerce').fillna(9.9)
    # ✅ 追加: 出走頭数を数値化（展開割合の計算に使用）
    past['頭数_数値'] = pd.to_numeric(past.get('頭数', 16), errors='coerce').fillna(16).astype(float)
        
    def extract_corner(x, pos='first'):
        if pd.isna(x) or not isinstance(x, str): return np.nan
        x = x.replace("'", "")
        if '-' not in x: return np.nan
        parts = x.split('-')
        try:
            return int(parts[0]) if pos == 'first' else int(parts[-1])
        except ValueError:
            return np.nan

    past['初角位置'] = past.get('通過', pd.Series(dtype=str)).apply(lambda x: extract_corner(x, 'first'))
    past['上り_順位'] = past.get('上り', pd.Series(dtype=str)).astype(str).str.extract(r'\((\d+)位\)').astype(float)
    past['コース種別'] = past.get('距離', pd.Series(dtype=str)).astype(str).str.extract(r'(芝|ダ|障)')
    past['距離_数値'] = past.get('距離', pd.Series(dtype=str)).astype(str).str.extract(r'(\d+)').astype(float)
    past['馬体重_数値'] = past.get('馬体重', pd.Series(dtype=str)).astype(str).str.extract(r'(\d+)').astype(float)

    shutuba = df_shutuba.copy()
    shutuba['コース種別'] = shutuba.get('距離', pd.Series(dtype=str)).astype(str).str.extract(r'(芝|ダ|障)')
    shutuba['距離_数値'] = shutuba.get('距離', pd.Series(dtype=str)).astype(str).str.extract(r'(\d+)').astype(float)
    shutuba['枠'] = pd.to_numeric(shutuba.get('枠', np.nan), errors='coerce')
    shutuba['馬番'] = pd.to_numeric(shutuba.get('馬番', np.nan), errors='coerce')
    shutuba['斤量_数値'] = pd.to_numeric(shutuba.get('斤量', np.nan), errors='coerce')
    shutuba['馬体重_数値'] = shutuba.get('馬体重', pd.Series(dtype=str)).astype(str).str.extract(r'(\d+)').astype(float)

    return shutuba, past

# ==========================================
# 3. AI評価エンジンクラス
# ==========================================
class HorseEvaluator:
    def __init__(self, horse_row, past_data, race_context, total_horses):
        self.horse = horse_row
        self.past = past_data
        self.race = race_context
        self.total_horses = total_horses
        self.scores = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0}
        self.details = []
        
        self.sex_age = str(self.horse.get('性齢', ''))
        self.kinryo = self.horse.get('斤量_数値', 55)
        self.waku = self.horse.get('枠', 4)
        self.c_type = self.race.get('コース種別', '芝')
        self.dist = self.race.get('距離_数値', 1600)
        self.keibajo = self.race.get('競馬場', '')
        self.baba = self.race.get('馬場', '良') 
        self.is_hinba = self.race.get('is_hinba_only', False) or ('牝' in self.sex_age) # is_hinba判定を強化

        self.details.append(f"【レース環境】 {self.c_type}戦 / 初角距離[{self.race.get('corner_len')}] / 芝スタート[{self.race.get('is_shiba_start')}]")
        
        self.base_kinryo_standard = 54 if self.is_hinba else (56 if '牝' in self.sex_age else 58)

    def log(self, item_id, title, point, is_match=True):
        if point != 0:
            self.details.append(f"[{item_id}] {title} ({point:+d}点)")

    def eval_A(self):
        score_a, bonus_a = 0, 0
        recent_5 = self.past.head(5)
        
        if len(self.past) > 0 and self.past.iloc[0]['着差_数値'] <= 0.2 and self.kinryo < pd.to_numeric(self.past.iloc[0].get('斤量', 55), errors='coerce'):
            score_a += 3; self.log('A1', '斤量差の逆転', 3, True)

        if len(recent_5) > 0 and 'レース名' in recent_5.columns:
            if recent_5[(recent_5['レース名'].astype(str).str.contains('GI|G1', na=False)) & (recent_5['着順_数値'] <= 5)].shape[0] > 0:
                score_a += 5; self.log('A2', '格の優先順位(G1)', 5, True)
            elif recent_5[(recent_5['レース名'].astype(str).str.contains('GII|G2', na=False)) & (recent_5['着順_数値'] <= 5)].shape[0] > 0:
                score_a += 3; self.log('A2', '格の優先順位(G2)', 3, True)
            elif recent_5[(recent_5['レース名'].astype(str).str.contains('GIII|G3', na=False)) & (recent_5['着順_数値'] <= 5)].shape[0] > 0:
                score_a += 2; self.log('A2', '格の優先順位(G3)', 2, True)
            elif recent_5.iloc[0]['着順_数値'] == 1 and (recent_5.iloc[0]['上り_順位'] == 1 or recent_5.iloc[0]['着差_数値'] <= -0.4):
                score_a += 4; self.log('A2', '格の優先順位(前走完勝)', 4, True)

        if self.kinryo >= self.base_kinryo_standard and self.race.get('pace_forecast') == 'ハイ(前崩れ)' and len(self.past[(self.past['着差_数値'] <= 0.3) | (self.past['着順_数値'] <= 5)]) > 0:
            score_a += 3; self.log('A3', 'タフネス評価', 3, True)

        if len(self.past[(self.past['距離_数値'] >= self.dist) & (self.past['着差_数値'] <= 0.5) & (self.past['上り_順位'] <= 3)]) > 0:
            score_a += 4; self.log('A4', '実績補正', 4, True)

        if len(self.past) > 0 and self.past.iloc[0]['距離_数値'] == self.dist and self.past.iloc[0]['着差_数値'] <= 0.4 and self.kinryo <= pd.to_numeric(self.past.iloc[0].get('斤量', 0), errors='coerce') - 1.0:
            score_a += 5; self.log('A5', '斤量スタミナ補正', 5, True)

        if len(self.past) > 0 and pd.notna(self.horse.get('馬体重_数値')) and pd.notna(self.past.iloc[0].get('馬体重_数値')) and ('3' in self.sex_age or '4' in self.sex_age) and self.horse['馬体重_数値'] >= self.past.iloc[0]['馬体重_数値'] + 10:
            score_a += 1; self.log('A6', '成長・地力復活', 1, True)

        if any(age in self.sex_age for age in ['7', '8', '9', '10']) and self.baba in ['稍', '重', '不良'] and len(self.past[(self.past['馬場'].isin(['稍', '重', '不良'])) & (self.past['着順_数値'] <= 2)]) > 0:
            score_a += 5; self.log('A7', '高齢馬の道悪特例', 5, True)

        if ('2' in self.sex_age or '3' in self.sex_age) and len(self.past) >= 2 and (recent_5.head(2)['上り_順位'] == 1).all() and recent_5.iloc[0]['着順_数値'] == 1 and recent_5.iloc[0]['着差_数値'] <= -0.3:
            score_a += 4; self.log('A8', '若駒の成長力補正', 4, True)

        if len(self.past[(self.past['着順_数値'] == 1) & (self.past['着差_数値'] <= -0.8)]) > 0:
            bonus_a += 10; self.log('A9', '規格外能力ボーナス', 10, True)

        # 🌟 追加・修正: 牝馬特例 (小回り判定の厳密化)
        is_hanshin_soto = (self.keibajo == '阪神' and self.c_type == '芝' and self.dist in [1600, 1800, 2400])
        is_komawari_target = self.keibajo in ['中山', '小倉', '福島', '函館', '札幌'] or (self.keibajo == '阪神' and not is_hanshin_soto)

        if self.is_hinba and self.kinryo <= 53 and len(self.past) > 0 and (recent_5.head(3).get('初角位置', pd.Series([99]*3)) <= 4).any() and is_komawari_target:
            bonus_a += 8; self.log('牝馬特例', '真の軽ハンデ×先行力特大加点(小回り限定)', 8, True)

        self.scores['A'] = min(score_a, 10) + bonus_a

    def eval_B(self):
        score_b = 0
        bias = self.race.get('track_bias', 'フラット')
        pace = self.race.get('pace_forecast', 'ミドル')
        short_corner = self.race.get('short_to_first_corner', False)
        long_corner = self.race.get('long_to_first_corner', False)
        nige_disabled = self.race.get('nige_bias_disabled', False)
        is_shiba_start = self.race.get('is_shiba_start', False)
        
        is_senko = len(self.past) > 0 and (self.past.head(3)['初角位置'] <= 4).any()
        is_sashi = len(self.past) > 0 and (self.past.head(3)['初角位置'] >= 7).any()
        has_agari = len(self.past[self.past['上り_順位'] <= 3]) > 0

        if len(self.past[(self.past['競馬場'] == self.keibajo) & (self.past['距離_数値'] == self.dist) & (self.past['着順_数値'] == 1)]) > 0:
            pts = 8 if self.keibajo in ['京都', '小倉', '新潟'] else 5
            score_b += pts; self.log('B1', 'コース適性', pts, True)

        if self.baba == '良' and self.waku <= 4 and not nige_disabled:
            score_b += 3; self.log('B3', '枠順・バイアス基本補正(前半/良)', 3, True)

        if self.baba in ['稍', '重', '不良'] and self.waku >= 6 and has_agari:
            score_b += 3; self.log('B4', '枠順・バイアス基本補正(後半/荒れ)', 3, True)

        # 🌟 追加・修正: 馬場状態の適性チェック（加点・減点）
        if self.baba in ['稍', '重', '不良']:
            # 加点：当日の道悪馬場と完全一致で1着実績あり
            if len(self.past[(self.past['馬場'] == self.baba) & (self.past['着順_数値'] == 1)]) > 0:
                score_b += 4; self.log('B5', '当日馬場状態の完全一致(道悪巧者)', 4, True)
            
            # 減点：道悪（稍・重・不良）を3戦以上走って3着以内ゼロ（道悪の明確な苦手）
            past_michiwaku = self.past[self.past['馬場'].isin(['稍', '重', '不良'])]
            if len(past_michiwaku) >= 3 and len(past_michiwaku[past_michiwaku['着順_数値'] <= 3]) == 0:
                score_b -= 5; self.log('B5', '道悪の明確な苦手実績(3戦以上で好走なし)', -5, True)
        else:
            # 良馬場の場合の基本加点
            if len(self.past[(self.past['馬場'] == '良') & (self.past['着順_数値'] == 1)]) > 0:
                score_b += 4; self.log('B5', '当日馬場状態の完全一致(良馬場)', 4, True)

        if bias == '内有利' and self.waku <= 6 and len(self.past) > 0 and 3 <= self.past.head(3)['初角位置'].mean() <= 6 and nige_disabled:
            score_b += 5; self.log('B6', '芝開幕週の特例と解除(好位インへのスライド)', 5, True)

        if bias == '外伸び(差し優勢)' and self.waku >= 6 and is_sashi and has_agari:
            score_b += 8; self.log('B7', 'リアルタイム補正(外差し優勢)', 8, True)

        if bias == '外伸び(差し優勢)' and self.waku >= 6 and is_senko and long_corner:
            score_b += 7; self.log('B8', 'リアルタイム補正(外伸び+初角長い)', 7, True)

        if bias == '外伸び(差し優勢)' and short_corner:
            if self.waku >= 7: score_b += 2; self.log('B9', 'リアルタイム補正(大外加点半減)', 2, True)
            elif 4 <= self.waku <= 6 and is_sashi: score_b += 5; self.log('B9', 'リアルタイム補正(中枠差し)', 5, True)

        if bias == '内有利' and self.waku <= 4 and is_senko and not nige_disabled:
            score_b += 5; self.log('B10', 'リアルタイム補正(内優勢)', 5, True)

        if bias == '外伸び(差し優勢)' and self.waku >= 6 and self.horse.get('馬体重_数値', 0) >= 500 and not has_agari:
            score_b -= 4; self.log('B11', 'バイアス恩恵の半減(外枠大型馬)', -4, True)

        if short_corner and pace == 'ハイ(前崩れ)' and self.waku <= 4 and is_senko:
            if not (self.race.get('front_collapse_flag') and not len(self.past[(self.past['着順_数値'] <= 3) & (self.past['レース名'].astype(str).str.contains('G', na=False))]) > 0):
                score_b += 8; self.log('B12', 'インベタ・ポケット恩恵', 8, True)

        if short_corner and self.waku <= 4 and self.race.get('is_tanki_nige_waku') == self.waku:
            score_b += 8; self.log('B13', '初角短い＋内枠逃げ馬', 8, True)

        if short_corner and self.c_type == 'ダ' and self.waku >= 6 and is_senko:
            score_b += 5; self.log('B15', '初角短い＋小回りダート外枠先行', 5, True)

        if short_corner and self.waku >= 6 and len(self.past) > 0 and (self.past.head(3)['初角位置'] <= 2).any():
            score_b += 3; self.log('B16', '初角短い＋外枠先行(テン速い)', 3, True)

        steep_courses = ['中山', '阪神', '中京']
        if self.keibajo in steep_courses and len(self.past[(self.past['競馬場'].isin(steep_courses)) & (self.past['上り_順位'] <= 3) & (self.past['着順_数値'] <= 2)]) > 0:
            score_b += 4; self.log('B17', '急坂＋長直線＋過去急坂上がり上位', 4, True)

        flat_courses = ['京都', '小倉', '新潟', '札幌', '函館', '福島']
        if self.keibajo in flat_courses and len(self.past[(self.past['競馬場'].isin(flat_courses)) & (self.past['初角位置'] <= 3) & (self.past['着順_数値'] <= 3)]) > 0:
            score_b += 4; self.log('B18', '平坦＋小回り＋同形態で4角3番手以内実績', 4, True)

        if self.c_type == 'ダ' and (is_shiba_start or self.waku >= 6 or len(self.past[(self.past['コース種別'] == '芝') & (self.past['着順_数値'] <= 3)]) > 0):
            score_b += 4; self.log('B19', '芝スタートダート・外枠先行・芝実績', 4, True)

        if self.c_type == 'ダ' and self.dist <= 1400 and self.waku >= 6 and is_senko:
            score_b += 6; self.log('B20', 'ダート短距離「外枠好位」特例', 6, True)

        if self.c_type == 'ダ' and self.dist <= 1400 and self.waku >= 6 and is_sashi and has_agari:
            score_b += 5; self.log('B21', 'ダート短距離 砂被り回避・外枠補正', 5, True)

        if self.c_type == 'ダ' and self.dist <= 1400 and self.waku >= 6 and len(self.past) > 0 and self.past.iloc[0]['距離_数値'] >= 1600:
            score_b += 4; self.log('B22', 'ダート短距離「距離短縮×外枠差し」特例', 4, True)

        if self.c_type == 'ダ' and self.dist <= 1400 and self.baba in ['稍', '重', '不良'] and self.waku >= 6 and len(self.past) > 0 and (self.past.head(3)['初角位置'] <= 3).any():
            score_b += 10; self.log('B23', '道悪ダート黄金条件', 10, True)

        if self.c_type == 'ダ' and self.dist <= 1400 and self.baba in ['稍', '重', '不良'] and self.waku >= 5 and is_senko:
            score_b += 5; self.log('B24', '道悪ダートキックバック回避', 5, True)

        if len(self.past[(self.past['競馬場'] == self.keibajo) & (self.past['距離_数値'] == self.dist) & (self.past['着順_数値'] <= 3) & (self.past['レース名'].astype(str).str.contains('G', na=False))]) > 0:
            score_b = max(score_b, 15)
            if score_b == 15: 
                self.log('B2', 'リピーター絶対保護による下限適用', 0, True) 

        self.scores['B'] = min(score_b, 25)

    def eval_C(self):
        score_c = 0
        jockey = str(self.horse.get('騎手', ''))
        
        if any(name in jockey for name in ['モレイラ', 'レーン', 'Ｃ．デムーロ']):
            score_c += 2; self.log('C1', '特定コンビ補正', 2, True)
            
        if '高杉' in jockey:
            score_c += 3; self.log('C3', '高杉騎手補正', 3, True)
            
        self.scores['C'] = min(score_c, 5)

    def eval_D(self):
        score_d = 0
        pace = self.race.get('pace_forecast', 'ミドル')
        front_collapse = self.race.get('front_collapse_flag', False)
        super_collapse = self.race.get('super_front_collapse_flag', False)
        ninki = pd.to_numeric(self.horse.get('人気', 99), errors='coerce')
        
        if len(self.past[(self.past['初角位置'] <= 3) & (self.past['着順_数値'] <= 3)]) > 0 or len(self.past[(self.past['初角位置'] >= 10) & (self.past['着順_数値'] == 1)]) > 0:
            score_d += 5; self.log('D1', '展開耐性', 5, True)
        
        special_courses = [
            ('東京', '芝', 2000), ('中山', '芝', 1600), ('新潟', '芝', 2000),
            ('阪神', '芝', 2200), ('中山', '芝', 2200)
        ]
        if (self.keibajo, self.c_type, self.dist) in special_courses:
            if len(self.past) > 0 and self.past.iloc[0]['初角位置'] <= 4 and self.past.iloc[0]['上り_順位'] <= 3:
                score_d += 8; self.log('D2', '特殊コース特化立ち回り(スタート直後コーナー)', 8, True)
        
        if self.race.get('is_tanki_nige_waku') == self.waku:
            score_d += 10; self.log('D3', '単騎逃げの特権', 10, True)
        
        if len(self.past) >= 3 and (self.past.head(3)['上り_順位'] <= 3).sum() >= 2:
            score_d += 5; self.log('D4', '上がり特化枠', 5, True)
        
        if pace == 'スロー(前残り)' and len(self.past) > 0 and (self.past.head(3)['初角位置'] <= 5).any():
            score_d += 5; self.log('D5', 'スローペース特権', 5, True)
        
        if self.keibajo in ['中山', '阪神', '中京'] and pace == 'ハイ(前崩れ)' and len(self.past[(self.past['競馬場'].isin(['中山', '阪神'])) & (self.past['上り_順位'] <= 3)]) > 0:
            score_d += 4; self.log('D7', '急坂特化展開利', 4, True)
        
        is_light_weight = (self.kinryo <= 52) if getattr(self, 'is_hinba', False) else (self.kinryo <= 54)
        if self.baba in ['稍', '重', '不良'] and is_light_weight and self.waku <= 4:
            score_d += 5; self.log('D8', '軽量・イン突き伏兵(男女補正済)', 5, True)

        if front_collapse and len(self.past) >= 3:
            recent_5 = self.past.head(5)
            avg_ratio = (recent_5['初角位置'] / recent_5['頭数_数値']).mean()
            
            is_leader = avg_ratio <= 0.25
            is_rear = avg_ratio >= 0.65
            is_mid = 0.25 < avg_ratio < 0.65
            
            has_agari = (recent_5['上り_順位'] <= 3).any()
            is_steep_small = self.keibajo in ['中山', '阪神', '小倉', '福島', '函館', '札幌']
            is_dirt_short = (self.c_type == 'ダ') and (self.dist <= 1400)

            if super_collapse:
                if is_mid: score_d += 8; self.log('Dペース', '超前崩れ(中団直撃)', 8, True)
                elif is_rear and has_agari:
                    pts = 3 if is_dirt_short else 12
                    score_d += pts; self.log('Dペース', '超前崩れ(後方待機)', pts, True)
            else:
                if is_mid:
                    pts = 8 if (ninki <= 3 or self.scores.get('A', 0) >= 8) else 10
                    score_d += pts; self.log('Dペース', '前崩れ(中団恩恵)', pts, True)
                elif is_rear:
                    if is_steep_small or is_dirt_short:
                        score_d += 3; self.log('Dペース', '前崩れ(急坂小回後方)', 3, True)

        self.scores['D'] = min(score_d, 30)

    def eval_E(self):
        score_e = 0
        pace = self.race.get('pace_forecast', 'ミドル')
        front_collapse = self.race.get('front_collapse_flag', False)
        super_collapse = self.race.get('super_front_collapse_flag', False)
        short_corner = self.race.get('short_to_first_corner', False)
        bias = self.race.get('track_bias', 'フラット')

        is_pocket = (short_corner and self.waku <= 4)
        has_heavy_high_record = len(self.past[(self.past['着順_数値'] <= 3) & (self.past['レース名'].astype(str).str.contains('G', na=False))]) > 0
        
        if front_collapse and len(self.past) >= 3 and (self.past.head(3)['初角位置'] <= 4).all():
            if is_pocket and has_heavy_high_record: 
                pass
            elif is_pocket and not has_heavy_high_record: score_e -= 10; self.log('E1', '激流インベタ自滅直撃', -10, True)
            elif super_collapse: score_e -= 5; self.log('E1', '超前崩れ: 人気馬自滅', -5, True)
            elif self.scores.get('A', 0) >= 5: score_e -= 5; self.log('E1', '激流巻き込まれ(実績馬半減)', -5, True)
            else: score_e -= 10; self.log('E1', '激流巻き込まれ・自滅リスク', -10, True)

        if bias == '内有利' and len(self.past) > 0 and self.past.iloc[0]['初角位置'] >= 10:
            score_e -= 7; self.log('E3', '極端なバイアス逆行', -7, True)

        if self.c_type == '芝' and short_corner and self.waku >= 7:
            score_e -= 4; self.log('E4', '芝専用: 初角短いの外枠距離損リスク', -4, True)

        if self.c_type == 'ダ' and self.waku <= 3 and len(self.past) > 0 and not (self.past['初角位置'] == 1).any():
            score_e -= 5; self.log('E5', 'ダート戦の内枠・砂被りリスク', -5, True)

        if self.c_type == 'ダ' and self.waku <= 2 and self.horse.get('馬体重_数値', 0) >= 530 and len(self.past) > 0 and not (self.past.head(3)['初角位置'] <= 3).any():
            score_e -= 3; self.log('E6', '大型馬の内枠リスク', -3, True)

        if self.keibajo in ['中山', '阪神'] and len(self.past[(self.past['競馬場'].isin(['京都','小倉','新潟'])) & (self.past['着順_数値'] == 1) & (self.past['初角位置'] == 1)]) > 0 and not len(self.past[(self.past['競馬場'].isin(['中山', '阪神'])) & (self.past['着順_数値'] <= 3)]) > 0:
            score_e -= 5; self.log('E7', '急坂＋長直線＋平坦逃げ切りのみ', -5, True)

        if self.c_type == 'ダ' and len(self.past) > 0 and not (self.past['コース種別'] == 'ダ').any():
            score_e -= 5; self.log('E8', '初ダート特例減点', -5, True)

        if self.c_type == 'ダ' and self.baba in ['稍', '重', '不良'] and pace == 'ハイ(前崩れ)' and len(self.past) > 0 and self.past.iloc[0]['初角位置'] >= 7:
            score_e -= 8; self.log('E9', 'スピード馬場後方待機リスク', -8, True)

        if bias == '内有利' and self.waku <= 3 and len(self.past) >= 3:
            recent_3 = self.past.head(3)
            if (recent_3['初角位置'] / recent_3['頭数_数値'] >= 0.65).all():
                score_e -= 5; self.log('E10', '内枠ドン詰まりリスク(後方常習)', -5, True)

        if front_collapse and len(self.past) >= 3 and (self.past.head(3)['着差_数値'] >= 1.0).all():
            score_e -= 5; self.log('E11', '能力不足の後方待機馬への足切り', -5, True)
        
        if getattr(self, 'is_hinba', False) and self.kinryo >= 55.5 and self.scores.get('A', 0) <= 5:
            score_e -= 5; self.log('牝馬特例', '重ハンデ過信排除', -5, True)

        self.scores['E'] = score_e

    def eval_F(self):
        score_f = 0
        if len(self.past) > 0:
            prev = self.past.iloc[0]
            
            if self.c_type == 'ダ':
                try:
                    today_date = pd.to_datetime(self.race.get('日付', pd.Timestamp.today()))
                    prev_date = pd.to_datetime(prev.get('日付', pd.Timestamp('1900-01-01')))
                    interval_days = (today_date - prev_date).days
                except:
                    interval_days = 999
                
                if interval_days <= 24 and (prev['着順_数値'] <= 5 or prev['着差_数値'] <= 0.6):
                    score_f += 4; self.log('F1', 'ローテーション好転(短期好調維持)', 4, True)

            if len(self.past[(self.past['競馬場'] == self.keibajo) & (self.past['着順_数値'] <= 3)]) > 0:
                score_f += 4; self.log('F2', '条件好転', 4, True)

            if len(self.past[(self.past['競馬場'] == self.keibajo) & (self.past['距離_数値'] == self.dist) & (self.past['着順_数値'] <= 2)]) > 0:
                score_f += 7; self.log('F4', 'コースリピーター', 7, True)

            ninki = pd.to_numeric(self.horse.get('人気', 1), errors='coerce')
            has_track_record = len(self.past[(self.past['競馬場'] == self.keibajo) & (self.past['距離_数値'] == self.dist) & (self.past['着順_数値'] <= 3)]) > 0
            if ninki >= 6 and has_track_record and (prev['着順_数値'] >= 10 or str(prev['コース種別']) != self.c_type or abs(prev['距離_数値'] - self.dist) >= 400):
                score_f += 6; self.log('F5', 'ブラインドスポット加点', 6, True)

            same_course = self.past[(self.past['競馬場'] == self.keibajo) & (self.past['距離_数値'] == self.dist)]
            if len(same_course) >= 3 and (len(same_course[same_course['着順_数値'] <= 3]) / len(same_course)) >= 0.5:
                score_f += 10; self.log('F6', '同条件超得意馬', 10, True)

            if prev['着順_数値'] >= 10 and str(prev['コース種別']) != self.c_type and len(self.past[(self.past['コース種別'] == self.c_type) & (self.past['着順_数値'] == 1)]) > 0:
                score_f += 10; self.log('F7', '適性バウンドバック', 10, True)

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
# 4. Streamlit UI 画面構築
# ==========================================
st.title("🧠 AI競馬予想エンジン（CSV読込対応・UI最適化版 Ver.1.4）")

# --- CSV読み込み関数（文字コード自動判定付き） ---
def load_csv(uploaded_file):
    try:
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, encoding='utf-8')
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        return pd.read_csv(uploaded_file, encoding='cp932')

col_file1, col_file2 = st.columns(2)
with col_file1:
    uploaded_shutuba = st.file_uploader("📥 出馬表CSV", type=['csv'])
with col_file2:
    uploaded_past = st.file_uploader("📥 過去戦績CSV", type=['csv'])

if uploaded_shutuba is not None and uploaded_past is not None:
    raw_shutuba = load_csv(uploaded_shutuba)
    raw_past = load_csv(uploaded_past)
    
    df_shutuba, df_past = preprocess_data(raw_shutuba, raw_past)

    if 'レース' in df_shutuba.columns:
        target_race = st.selectbox("🎯 予想するレースを選択", df_shutuba['レース'].unique())
        target_shutuba = df_shutuba[df_shutuba['レース'] == target_race]
    else:
        target_shutuba = df_shutuba
    
    is_hinba_only = target_shutuba['性齢'].astype(str).str.contains('牝').all()
    if is_hinba_only: st.info("🎀 牝馬限定戦：基準斤量ゼロリセット等の特例を適用します。")

    st.markdown("### 🔍 当日の環境・バイアス設定（手動）")
    col_bias1, col_bias2 = st.columns(2)
    with col_bias1: track_bias = st.selectbox("馬場バイアス", ["フラット", "内有利", "外伸び(差し優勢)"])
    with col_bias2: current_baba = st.selectbox("当日の馬場状態", ["良", "稍", "重", "不良"])

    if st.button("🚀 この設定で予想を実行"):
        with st.spinner('絶対遵守プロトコルに従い、全条件を合算中...'):
            
            keibajo_target = target_shutuba.iloc[0].get('競馬場', '')
            c_type_target = target_shutuba.iloc[0].get('コース種別', '芝')
            dist_target = target_shutuba.iloc[0].get('距離_数値', 1600)
            
            is_shiba_start, corner_len = get_course_info(keibajo_target, c_type_target, dist_target)

            front_runners_count = 0 
            top3_leaders_count = 0 
            total_horses = len(target_shutuba)
            nige_horses_waku = []
            senko_horses_soto = 0

            for index, horse_row in target_shutuba.iterrows():
                waku = pd.to_numeric(horse_row.get('枠', 4), errors='coerce')
                ninki = pd.to_numeric(horse_row.get('人気', 99), errors='coerce')
                horse_name = horse_row.get('馬名', '')
                
                if horse_name in df_past['馬名'].values:
                    past_data = df_past[df_past['馬名'] == horse_name]
                    recent_3 = past_data.head(3)
                    
                    if len(recent_3) > 0 and (recent_3['初角位置'] <= 3).any():
                        front_runners_count += 1
                        if ninki <= 3: top3_leaders_count += 1
                    
                    if len(recent_3) > 0 and (recent_3['初角位置'] == 1).any():
                        nige_horses_waku.append(waku)
                    
                    if waku >= 7 and len(recent_3) > 0 and (recent_3['初角位置'] <= 3).any():
                        senko_horses_soto += 1

            auto_pace = "ミドル"
            auto_bias = track_bias
            nige_bias_disabled = False 
            is_tanki_nige_waku = nige_horses_waku[0] if len(nige_horses_waku) == 1 else None

            if len(nige_horses_waku) == 0:
                auto_pace = "スロー(前残り)"
            elif 1 <= len(nige_horses_waku) <= 2 and sum(1 for w in nige_horses_waku if w <= 4) == len(nige_horses_waku):
                auto_pace = "スロー(前残り)"
                auto_bias = "内有利"

            if front_runners_count >= (total_horses / 3):
                auto_pace = "ハイ(前崩れ)"
            elif sum(1 for w in nige_horses_waku if w <= 6) >= 2:
                auto_pace = "ハイ(前崩れ)"
                nige_bias_disabled = True
            elif corner_len == '短い' and total_horses >= 14 and senko_horses_soto >= 3:
                auto_pace = "ハイ(前崩れ)"
                auto_bias = "外伸び(差し優勢)"

            race_context = {
                '競馬場': keibajo_target,
                '距離_数値': dist_target,
                '馬場': current_baba,
                'コース種別': c_type_target,
                'track_bias': auto_bias,
                'pace_forecast': auto_pace,
                'corner_len': corner_len,
                'short_to_first_corner': (corner_len == '短い'),
                'long_to_first_corner': (corner_len == '長い'),
                'is_shiba_start': is_shiba_start,
                'front_collapse_flag': (auto_pace == "ハイ(前崩れ)"),
                'super_front_collapse_flag': (top3_leaders_count >= 2),
                'nige_bias_disabled': nige_bias_disabled,
                'is_tanki_nige_waku': is_tanki_nige_waku,
                'is_hinba_only': is_hinba_only
            }

            results = []
            for index, horse_row in target_shutuba.iterrows():
                past_data = df_past[df_past['馬名'] == horse_row.get('馬名', '')]
                evaluator = HorseEvaluator(horse_row, past_data, race_context, total_horses)
                total_score = evaluator.calculate_total()
                
                results.append({
                    "馬番": horse_row.get('馬番', index+1),
                    "馬名": horse_row.get('馬名', f"馬{index+1}"),
                    "基礎スコア": total_score,
                    "加点・減点ログ": "\n".join(evaluator.details) if evaluator.details else "特筆すべきスコア増減なし"
                })

            df_results = pd.DataFrame(results).sort_values(by="基礎スコア", ascending=False).reset_index(drop=True)
            
            def assign_rank(idx, score):
                if idx <= 1 and score > 15: return 'S'
                elif idx <= 4 and score > 5: return 'A'
                elif idx <= 8 and score >= 0: return 'B'
                else: return 'C'
                
            df_results['ランク'] = [assign_rank(i, row['基礎スコア']) for i, row in df_results.iterrows()]

            df_summary = df_results[['ランク', '馬番', '馬名', '基礎スコア']]

            st.success(f"【判定完了】自動コース判定: 芝スタート[{is_shiba_start}] / 初角距離[{corner_len}] | 逃げ馬候補 {len(nige_horses_waku)}頭 -> 自動設定ペース: {auto_pace}")
            st.dataframe(df_summary, use_container_width=True, hide_index=True)

            st.markdown("### 📝 各馬の評価ログ詳細（クリックで展開）")
            for _, row in df_results.iterrows():
                with st.expander(f"【{row['ランク']}】 {int(row['馬番'])}番 {row['馬名']} (スコア: {row['基礎スコア']}点)"):
                    st.code(row['加点・減点ログ'], language="text")

            st.markdown("### 🎫 推奨買い目フォーメーション")
            s_horses = df_results[df_results['ランク'] == 'S']['馬番'].dropna().astype(int).tolist()
            a_horses = df_results[df_results['ランク'] == 'A']['馬番'].dropna().astype(int).tolist()
            b_horses = df_results[df_results['ランク'] == 'B']['馬番'].dropna().astype(int).tolist()

            if len(s_horses) == 1:
                st.info(f"**【3連複 1頭軸流し】**\n軸: {s_horses[0]}\n相手: {', '.join(map(str, a_horses + b_horses))}")
                st.info(f"**【3連単 フォーメーション (1強特化)】**\n1着: {s_horses[0]}\n2着: {', '.join(map(str, a_horses))}\n3着: {', '.join(map(str, a_horses + b_horses))}")
            elif len(s_horses) >= 2:
                st.info(f"**【3連複 2頭軸流し】**\n軸: {s_horses[0]}, {s_horses[1]}\n相手: {', '.join(map(str, a_horses + b_horses))}")
                st.info(f"**【3連単 フォーメーション (上位拮抗)】**\n1着: {s_horses[0]}, {s_horses[1]}\n2着: {', '.join(map(str, s_horses + a_horses))}\n3着: {', '.join(map(str, s_horses + a_horses + b_horses))}")
            else:
                st.warning("圧倒的なSランク不在のため、Aランク馬を中心としたBOX買い、または馬連推奨の大混戦です。")

            # 🌟 ここから追加：コピー用出力エリア 🌟
            st.markdown("---")
            st.markdown("### 📋 予想結果まとめ（コピー用）")
            st.markdown("※右上のコピーアイコンを押すと一括コピーできます。SNSへの投稿やメモ帳への貼り付けにご活用ください。")
            
            # 1. レース情報のテキスト構築
            copy_text = f"【レース情報】\n"
            copy_text += f"競馬場: {keibajo_target} / コース: {c_type_target} / 距離: {dist_target}m / 馬場: {current_baba}\n"
            copy_text += f"想定ペース: {auto_pace} / トラックバイアス: {auto_bias}\n\n"
            
            # 2. 各出走馬の評価テキスト構築
            copy_text += f"【各出走馬の評価詳細】\n"
            for _, row in df_results.iterrows():
                copy_text += f"■ [{row['ランク']}] {int(row['馬番'])}番 {row['馬名']} (スコア: {row['基礎スコア']}点)\n"
                
                # ログを見やすくインデントして追加
                if pd.notna(row['加点・減点ログ']) and row['加点・減点ログ'] != "":
                    # 改行ごとにインデントを下げて見やすくする
                    formatted_logs = str(row['加点・減点ログ']).replace('\n', '\n  ・')
                    copy_text += f"  ・{formatted_logs}\n"
                else:
                    copy_text += "  ・特筆すべきスコア増減なし\n"
                
                copy_text += "-" * 30 + "\n"
            
            # 3. テキストエリア（コピーボタン付き）として出力
            st.code(copy_text, language="text")