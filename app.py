import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="採寸検索", layout="wide")
st.title("📏 採寸データ検索アプリ")

# Google認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# スプレッドシート読み込み
sheet = client.open("フォームの回答 1").sheet1
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
