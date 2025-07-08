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

elif page == "採寸入力":
    st.title("✍️ 採寸入力フォーム")

    try:
        # 商品マスタ読み込み
        spreadsheet = client.open("採寸管理データ")
        master_sheet = spreadsheet.worksheet("商品マスタ")
        master_data = master_sheet.get_all_records()

        if not master_data:
            st.warning("商品マスタにデータがありません。")
        else:
            master_df = pd.DataFrame(master_data)

            # ブランド選択
            brand_list = master_df["ブランド"].dropna().unique().tolist()
            selected_brand = st.selectbox("ブランドを選択", brand_list)

            if selected_brand:
                filtered_df = master_df[master_df["ブランド"] == selected_brand]

                # 管理番号選択
                product_ids = filtered_df["管理番号"].dropna().unique().tolist()
                selected_id = st.selectbox("管理番号を選択", product_ids)

                if selected_id:
                    product_row = filtered_df[filtered_df["管理番号"] == selected_id].iloc[0]
                    selected_category = product_row["カテゴリ"]
                    product_name = product_row["商品名"]
                    color = product_row["カラー"]
                    size = product_row["サイズ"]

                    st.markdown(f"**商品名**: {product_name}  \n**カラー**: {color}  \n**サイズ**: {size}")

                    # 採寸テンプレートの読み込み
                    category_sheet = spreadsheet.worksheet("採寸テンプレート")
                    category_data = category_sheet.get_all_records()
                    category_df = pd.DataFrame(category_data)

                    row = category_df[category_df["カテゴリ"] == selected_category]
                    if not row.empty:
                        item_str = row.iloc[0]["採寸項目"]
                        item_list = [item.strip() for item in item_str.replace("、", ",").split(",")]

                        st.markdown("### 採寸項目入力")
                        measurements = {}
                        for item in item_list:
                            value = st.text_input(f"{item}（cm）", key=item)
                            measurements[item] = value

                        if st.button("内容を確認"):
                            st.subheader("入力内容の確認")
                            st.write(f"管理番号: {selected_id}")
                            st.write(f"商品名: {product_name}")
                            st.write(f"カラー: {color}")
                            st.write(f"サイズ: {size}")
                            st.write(f"カテゴリ: {selected_category}")
                            st.write("採寸値:")
                            st.json(measurements)

    except Exception as e:
        st.error(f"読み込みエラー: {e}")
