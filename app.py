import streamlit as st
import pandas as pd
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="採寸データ管理", layout="wide")

# --- サイドバー ---
page = st.sidebar.selectbox("ページを選択", ["採寸検索", "商品インポート", "採寸入力"])

# --- Google 認証 ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)

# --- 採寸入力ページ ---
if page == "採寸入力":
    st.title("✍️ 採寸入力フォーム")

    try:
        spreadsheet = client.open("採寸管理データ")
        master_sheet = spreadsheet.worksheet("商品マスタ")
        template_sheet = spreadsheet.worksheet("採寸テンプレート")
        result_sheet = spreadsheet.worksheet("採寸結果")

        # --- 商品マスタ読み込み ---
        master_data = master_sheet.get_all_records()
        master_df = pd.DataFrame(master_data)

        # --- ブランド選択 ---
        brand_list = master_df["ブランド"].dropna().unique().tolist()
        selected_brand = st.selectbox("ブランドを選択", brand_list)

        filtered_df = master_df[master_df["ブランド"] == selected_brand]
        selected_code = st.selectbox("商品管理番号を選択", filtered_df["商品管理番号"].unique())

        # 選択された商品の詳細を取得
        product_row = filtered_df[filtered_df["商品管理番号"] == selected_code].iloc[0]
        st.write(f"🧾 **商品名：** {product_row['商品名']}")
        st.write(f"🎨 **カラー：** {product_row['カラー']}")

        # サイズ展開（カンマ or 全角カンマ区切り）
        size_list = str(product_row["サイズ"]).replace("、", ",").split(",")
        size_list = [s.strip() for s in size_list]
        selected_size = st.selectbox("サイズを選択", size_list)

        # カテゴリから採寸項目取得
        category_data = template_sheet.get_all_records()
        template_df = pd.DataFrame(category_data)
        category_row = template_df[template_df["カテゴリ"] == product_row["カテゴリ"]]

        if not category_row.empty:
            item_str = category_row.iloc[0]["採寸項目"]
            item_list = [i.strip() for i in item_str.replace("、", ",").split(",")]

            st.markdown("### 採寸値入力")
            measurements = {}
            for item in item_list:
                value = st.text_input(f"{item}（cm）", key=item)
                measurements[item] = value

            # --- 保存処理 ---
            if st.button("✅ 採寸データを保存"):
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_row = {
                    "日付": now,
                    "商品管理番号": selected_code,
                    "商品名": product_row["商品名"],
                    "カラー": product_row["カラー"],
                    "サイズ": selected_size,
                    **measurements
                }

                # 保存
                existing = result_sheet.get_all_values()
                if existing:
                    result_sheet.append_row(list(save_row.values()))
                else:
                    result_sheet.append_row(list(save_row.keys()))
                    result_sheet.append_row(list(save_row.values()))

                st.success("✅ 採寸データを保存しました！")

        else:
            st.warning("このカテゴリの採寸項目がテンプレートに存在しません。")

    except Exception as e:
        st.error(f"読み込みエラー: {e}")
