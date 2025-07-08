import streamlit as st
import pandas as pd
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="採寸データ管理", layout="wide")

# サイドバーでページ選択
page = st.sidebar.selectbox("ページを選択", ["採寸検索", "商品インポート"])

# Google認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)

# 採寸検索ページ
if page == "採寸検索":
    st.title("📏 採寸データ検索アプリ")

    # 対象スプレッドシートを指定（ID で指定）
    sheet = client.open_by_key("18-bOcctw7QjOIe7d3TotPjCsWydNNTda8Wg-rWe6hgo").sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    # 検索UI
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

            # サイズ列を展開する関数
            def expand_sizes(df):
                df = df.copy()
                df["サイズ"] = df["サイズ"].astype(str).str.replace("、", ",").str.split(",")
                df["サイズ"] = df["サイズ"].apply(lambda x: [s.strip() for s in x])
                return df.explode("サイズ").reset_index(drop=True)

            # 展開処理実行
            expanded_df = expand_sizes(df)
            expanded_df["サイズ"] = expanded_df["サイズ"].str.strip()

            st.subheader("展開後（1サイズ1行）")
            st.dataframe(expanded_df)

            # ※今後ここに「保存処理」追加可（Google Sheets保存など）

        except Exception as e:
            st.error(f"読み込みエラー: {e}")
    else:
        st.info("Excelファイル（.xlsx）をアップロードしてください。")
