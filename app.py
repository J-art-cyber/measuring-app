import streamlit as st
import pandas as pd
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="採寸データ管理", layout="wide")

# サイドバーでページ選択
page = st.sidebar.selectbox(
    "ページを選択",
    ["採寸検索", "商品インポート", "採寸入力", "採寸結果ヘッダー初期化"]
)

# Google認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)

# 採寸項目（全カテゴリ共通化されたもの）
MEASUREMENT_HEADERS = [
    "日付", "商品管理番号", "商品名", "カラー", "サイズ", "カテゴリ",
    "ウエスト", "ツバ", "ベルト幅", "マチ", "ワタリ", "前丈", "全長", "肩幅", "胸幅",
    "袖丈", "裄丈", "後丈", "胴囲", "最大幅", "着丈", "襟高", "横幅", "股上", "股下", "高さ", "裾幅"
]

# --------------------------
# 採寸検索ページ
# --------------------------
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

# --------------------------
# 商品インポートページ
# --------------------------
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

            if st.button("Googleスプレッドシートに保存"):
                try:
                    spreadsheet = client.open("採寸管理データ")
                    target_sheet = spreadsheet.worksheet("商品マスタ")
                    target_sheet.clear()
                    target_sheet.update([expanded_df.columns.values.tolist()] + expanded_df.values.tolist())
                    st.success("✅ データをGoogleスプレッドシートに保存しました！")
                except Exception as e:
                    st.error(f"保存エラー: {e}")

        except Exception as e:
            st.error(f"読み込みエラー: {e}")
    else:
        st.info("Excelファイル（.xlsx）をアップロードしてください。")

# --------------------------
# 採寸入力ページ
# --------------------------
elif page == "採寸入力":
    st.title("✍️ 採寸入力フォーム")

    product_id = st.text_input("商品管理番号")

    try:
        spreadsheet = client.open("採寸管理データ")
        category_sheet = spreadsheet.worksheet("採寸テンプレート")
        category_data = category_sheet.get_all_records()

        if category_data and "カテゴリ" in category_data[0] and "採寸項目" in category_data[0]:
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

                    color = st.text_input("カラー")
                    size = st.text_input("サイズ")
                    product_name = st.text_input("商品名")

                    if st.button("内容を保存"):
                        try:
                            result_sheet = spreadsheet.worksheet("採寸結果")
                            row_data = {
                                "日付": datetime.now().strftime("%Y-%m-%d"),
                                "商品管理番号": product_id,
                                "商品名": product_name,
                                "カラー": color,
                                "サイズ": size,
                                "カテゴリ": selected_category,
                            }
                            row_data.update(measurements)

                            final_row = [row_data.get(col, "") for col in MEASUREMENT_HEADERS]
                            result_sheet.append_row(final_row)
                            st.success("✅ 採寸データを保存しました")
                        except Exception as e:
                            st.error(f"保存エラー: {e}")
        else:
            st.error("🛑 'カテゴリ' または '採寸項目' の列が見つかりません。")
    except Exception as e:
        st.error(f"読み込みエラー: {e}")

# --------------------------
# 採寸結果ヘッダー初期化ページ
# --------------------------
elif page == "採寸結果ヘッダー初期化":
    st.title("📋 採寸結果ヘッダー自動生成")

    if st.button("採寸結果シートのヘッダーを上書きする"):
        try:
            spreadsheet = client.open("採寸管理データ")
            result_sheet = spreadsheet.worksheet("採寸結果")
            result_sheet.clear()
            result_sheet.append_row(MEASUREMENT_HEADERS)
            st.success("✅ 採寸結果シートのヘッダーを初期化しました！")
        except Exception as e:
            st.error(f"ヘッダー書き込みエラー: {e}")
