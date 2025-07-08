import streamlit as st
import pandas as pd
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="採寸データ管理", layout="wide")

# サイドバーでページ選択
page = st.sidebar.selectbox("ページを選択", ["採寸検索", "商品インポート", "採寸入力"])

# Google認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)

# 採寸検索ページ
if page == "採寸検索":
    st.title("📏 採寸データ検索アプリ")

    sheet = client.open_by_key("18-bOcctw7QjOIe7d3TotPjCsWydNNTda8Wg-rWe6hgo").sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    keyword = st.text_input("商品管理番号で検索（部分一致OK）")
    if keyword:
        filtered = df[df["商品管理番号を選択してください"].str.contains(keyword, case=False, na=False)]
        if not filtered.empty:
            st.success(f"{len(filtered)} 件ヒットしました。")
            st.dataframe(filtered)
        else:
            st.warning("該当データなし")
    else:
        st.info("検索ワードを入力してください。")

# 商品インポートページ
elif page == "商品インポート":
    st.title("📦 商品マスタ：Excelインポートとサイズ展開")

    uploaded_file = st.file_uploader("Excelファイルをアップロードしてください", type=["xlsx"])

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, header=1)

            st.subheader("元データ")
            st.dataframe(df)

            def expand_sizes(df):
                df = df.copy()
                df["サイズ"] = df["サイズ"].astype(str).str.replace("、", ",").str.split(",")
                df["サイズ"] = df["サイズ"].apply(lambda x: [s.strip() for s in x])
                return df.explode("サイズ").reset_index(drop=True)

            expanded_df = expand_sizes(df)
            expanded_df["サイズ"] = expanded_df["サイズ"].str.strip()

            st.subheader("展開後（1サイズ1行）")
            st.dataframe(expanded_df)

        except Exception as e:
            st.error(f"読み込みエラー: {e}")
    else:
        st.info("Excelファイル（.xlsx）をアップロードしてください。")

# 採寸入力ページ
elif page == "採寸入力":
    st.title("✍️ 採寸入力フォーム")

    product_id = st.text_input("商品管理番号")

    try:
        spreadsheet = client.open("採寸管理データ")
        category_sheet = spreadsheet.worksheet("採寸テンプレート")

        category_data = category_sheet.get_all_records()
        st.write("📋 データ取得結果:", category_data)  # ← ここでデバッグ表示

        category_df = pd.DataFrame(category_data)

        category_list = category_df["カテゴリ"].dropna().unique().tolist()
        selected_category = st.selectbox("カテゴリを選択", category_list)

        if selected_category:
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
                    st.write(f"商品管理番号: {product_id}")
                    st.write(f"カテゴリ: {selected_category}")
                    st.write("採寸値:")
                    st.json(measurements)

    except Exception as e:
        st.error(f"読み込みエラー: {e}")
