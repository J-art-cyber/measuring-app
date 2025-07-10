import streamlit as st
import pandas as pd
import gspread
import json
import re
import io
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="採寸データ管理", layout="wide")
page = st.sidebar.selectbox("ページを選択", ["採寸入力", "採寸検索", "商品インポート", "採寸ヘッダー初期化"])

# Google Sheets認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)
spreadsheet = client.open("採寸管理データ")

# カテゴリ別理想順
ideal_order_dict = {
    "ジャケット": ["肩幅", "胸幅", "胴囲", "袖丈", "着丈"],
    "パンツ": ["ウエスト", "股上", "股下", "ワタリ", "裾幅"],
    "ダウン": ["肩幅", "胸幅", "袖丈", "着丈", "襟高"],
    "ブルゾン": ["肩幅", "胸幅", "袖丈", "着丈", "襟高"],
    "コート": ["肩幅", "胸幅", "袖丈", "着丈", "襟高"],
    "ニット": ["肩幅", "胸幅", "袖丈", "着丈"],
    "カットソー": ["肩幅", "胸幅", "袖丈", "着丈"],
    "レザー": ["肩幅", "胸幅", "袖丈", "着丈", "襟高"],
    "靴": ["全長", "最大幅"],
    "巻物": ["全長", "横幅"],
    "小物・その他": ["頭周り", "ツバ", "高さ", "横幅", "マチ"],
    "シャツ": ["肩幅", "裄丈", "胸幅", "胴囲", "袖丈", "着丈"],
    "シャツジャケット": ["肩幅", "胸幅", "袖丈", "着丈"],
    "スーツ": ["肩幅", "胸幅", "胴囲", "袖丈", "着丈", "ウエスト", "股上", "股下", "ワタリ", "裾幅"],
    "ベルト": ["全長", "ベルト幅"],
    "半袖": ["肩幅", "胸幅", "袖丈", "前丈", "後丈"]
}

# 🔍 採寸検索ページ
if page == "採寸検索":
    st.title("🔍 採寸結果検索")
    try:
        result_df = pd.DataFrame(spreadsheet.worksheet("採寸結果").get_all_records())

        selected_brands = st.multiselect("🔸 ブランドを選択", sorted(result_df["ブランド"].dropna().unique()))
        selected_pids = st.multiselect("🔹 管理番号を選択", sorted(result_df["商品管理番号"].dropna().unique()))
        selected_sizes = st.multiselect("🔺 サイズを選択", sorted(result_df["サイズ"].dropna().unique()))
        keyword = st.text_input("🔍 キーワードで検索（商品名、管理番号など）")
        category_filter = st.selectbox("📂 カテゴリで表示項目を絞る", ["すべて表示"] + sorted(result_df["カテゴリ"].dropna().unique()))

        # フィルタリング処理
        if selected_brands:
            result_df = result_df[result_df["ブランド"].isin(selected_brands)]
        if selected_pids:
            result_df = result_df[result_df["商品管理番号"].isin(selected_pids)]
        if selected_sizes:
            result_df = result_df[result_df["サイズ"].isin(selected_sizes)]
        if keyword:
            result_df = result_df[result_df.apply(lambda row: keyword.lower() in str(row.values).lower(), axis=1)]
        if category_filter != "すべて表示":
            result_df = result_df[result_df["カテゴリ"] == category_filter]

        # 並び順調整
        base_cols = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ"]
        current_category = category_filter if category_filter != "すべて表示" else None
        ideal_cols = ideal_order_dict.get(current_category, [])
        ordered_cols = base_cols + [col for col in ideal_cols if col in result_df.columns] + [
            col for col in result_df.columns if col not in base_cols + ideal_cols
        ]
        result_df = result_df[ordered_cols]

        # ✅ 空欄列を安全に除去（str/int混在対応）
        is_blank = result_df.applymap(lambda x: pd.isna(x) or x == "")
        result_df = result_df.loc[:, ~is_blank.all()]

        st.write(f"🔍 検索結果: {len(result_df)} 件")
        st.dataframe(result_df)

        # Excel出力
        if not result_df.empty:
            to_excel = io.BytesIO()
            with pd.ExcelWriter(to_excel, engine='openpyxl') as writer:
                result_df.to_excel(writer, index=False, sheet_name="採寸結果")
            to_excel.seek(0)
            st.download_button("📥 検索結果をExcelでダウンロード", data=to_excel,
                               file_name="採寸結果_検索.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
