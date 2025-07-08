import streamlit as st
import pandas as pd
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ページ設定
st.set_page_config(page_title="採寸データ管理", layout="wide")

# サイドバー：ページ選択
page = st.sidebar.selectbox("ページを選択", ["採寸入力", "採寸検索", "商品インポート", "採寸ヘッダー初期化"])

# Google認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)

# 各スプレッドシート参照
spreadsheet = client.open("採寸管理データ")

# =====================
# 商品インポート
# =====================
if page == "商品インポート":
    st.title("📦 商品マスタ：Excelインポートとサイズ展開")
    uploaded_file = st.file_uploader("Excelファイルをアップロード", type=["xlsx"])

    if uploaded_file:
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
                sheet = spreadsheet.worksheet("商品マスタ")
                sheet.clear()
                sheet.update([expanded_df.columns.tolist()] + expanded_df.values.tolist())
                st.success("✅ 保存完了")
            except Exception as e:
                st.error(f"保存エラー: {e}")

# =====================
# 採寸ヘッダー初期化
# =====================
elif page == "採寸ヘッダー初期化":
    st.title("📋 採寸結果ヘッダーを初期化")
    headers = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ",
               "肩幅", "胸幅", "胴囲", "袖丈", "着丈", "襟高", "ウエスト", "股上", "股下",
               "ワタリ", "裾幅", "全長", "最大幅", "横幅", "頭周り", "ツバ", "高さ", "裄丈", "ベルト幅", "前丈", "後丈"]
    try:
        sheet = spreadsheet.worksheet("採寸結果")
        sheet.clear()
        sheet.append_row(headers)
        st.success("✅ ヘッダーを初期化しました")
    except Exception as e:
        st.error(f"エラー: {e}")

# =====================
# 採寸入力
# =====================
elif page == "採寸入力":
    st.title("✍️ 採寸入力フォーム")

    try:
        master_df = pd.DataFrame(spreadsheet.worksheet("商品マスタ").get_all_records())

        brand_list = master_df["ブランド"].dropna().unique().tolist()
        selected_brand = st.selectbox("ブランドを選択", brand_list)

        filtered_df = master_df[master_df["ブランド"] == selected_brand]
        product_ids = filtered_df["管理番号"].dropna().unique().tolist()
        selected_pid = st.selectbox("管理番号を選択", product_ids)

        product_row = filtered_df[filtered_df["管理番号"] == selected_pid].iloc[0]

        st.write(f"**商品名:** {product_row['商品名']}")
        st.write(f"**カラー:** {product_row['カラー']}")
        selected_size = st.selectbox("サイズ", filtered_df[filtered_df["管理番号"] == selected_pid]["サイズ"].unique())

        category = product_row["カテゴリ"]
        template_df = pd.DataFrame(spreadsheet.worksheet("採寸テンプレート").get_all_records())
        item_row = template_df[template_df["カテゴリ"] == category]

        if not item_row.empty:
            items = item_row.iloc[0]["採寸項目"].replace("、", ",").split(",")
            items = [i.strip() for i in items]

            st.markdown("### 採寸値入力")
            measurements = {}
            for item in items:
                val = st.text_input(f"{item} (cm)", key=item)
                measurements[item] = val

            if st.button("保存"):
                save_data = {
                    "日付": datetime.now().strftime("%Y-%m-%d"),
                    "商品管理番号": selected_pid,
                    "ブランド": selected_brand,
                    "カテゴリ": category,
                    "商品名": product_row["商品名"],
                    "カラー": product_row["カラー"],
                    "サイズ": selected_size
                }
                save_data.update(measurements)

                sheet = spreadsheet.worksheet("採寸結果")
                headers = sheet.row_values(1)
                new_row = [save_data.get(h, "") for h in headers]
                sheet.append_row(new_row)
                st.success("✅ 採寸データを保存しました！")
        else:
            st.warning("テンプレートが見つかりません")
    except Exception as e:
        st.error(f"読み込みエラー: {e}")

# =====================
# 採寸検索
# =====================
elif page == "採寸検索":
    st.title("🔍 採寸結果検索")
    try:
        result_df = pd.DataFrame(spreadsheet.worksheet("採寸結果").get_all_records())
        keyword = st.text_input("キーワードで検索（商品名、管理番号など）")

        if keyword:
            mask = result_df.apply(lambda row: keyword in str(row.values), axis=1)
            filtered = result_df[mask]
            st.write(f"{len(filtered)} 件ヒット")
            st.dataframe(filtered)
        else:
            st.dataframe(result_df)
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
