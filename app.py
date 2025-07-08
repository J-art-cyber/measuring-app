import streamlit as st
import pandas as pd
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="採寸データ管理", layout="wide")

# Google認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)

# 商品インポートページ
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

        # ✅ Google Sheetsに保存
        if st.button("Googleスプレッドシートに保存"):
            try:
                spreadsheet = client.open("採寸管理データ")
                sheet = spreadsheet.worksheet("商品マスタ")

                # ⚠ 念のため空チェック
                if not expanded_df.empty:
                    # 一旦シートをクリアしてから更新
                    sheet.clear()

                    # ヘッダー + データ を1つの list に結合
                    data_to_write = [expanded_df.columns.tolist()] + expanded_df.values.tolist()
                    sheet.update(data_to_write)

                    st.success("✅ Googleスプレッドシートに保存しました")
                else:
                    st.warning("⚠️ 保存するデータが空です")

            except Exception as e:
                st.error(f"保存エラー: {e}")

    except Exception as e:
        st.error(f"読み込みエラー: {e}")

else:
    st.info("Excelファイル（.xlsx）をアップロードしてください。")
