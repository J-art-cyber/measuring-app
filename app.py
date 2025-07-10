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

# カテゴリごとの理想順
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
# 商品インポートページ
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
                existing_df = pd.DataFrame(sheet.get_all_records())
                combined_df = pd.concat([existing_df, expanded_df], ignore_index=True)
                combined_df.drop_duplicates(subset=["管理番号", "サイズ"], keep="last", inplace=True)
                sheet.clear()
                sheet.update([combined_df.columns.tolist()] + combined_df.values.tolist())
                st.success("✅ データを追記保存しました！")
            except Exception as e:
                st.error(f"保存エラー: {e}")

# 採寸ヘッダー初期化
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

# 採寸入力
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
        size_options = filtered_df[filtered_df["管理番号"] == selected_pid]["サイズ"].unique()
        selected_size = st.selectbox("サイズ", size_options)

        category = product_row["カテゴリ"]
        template_df = pd.DataFrame(spreadsheet.worksheet("採寸テンプレート").get_all_records())
        item_row = template_df[template_df["カテゴリ"] == category]

        if not item_row.empty:
            raw_items = item_row.iloc[0]["採寸項目"].replace("、", ",").split(",")
            all_items = [re.sub(r'（.*?）', '', i).strip() for i in raw_items if i.strip()]
            ideal_order = ideal_order_dict.get(category, [])
            items = [i for i in ideal_order if i in all_items] + [i for i in all_items if i not in ideal_order]

            st.markdown("### 採寸値入力")
            measurements = {}
            for item in items:
                key = f"measure_{item}_{selected_pid}_{selected_size}"
                measurements[item] = st.text_input(f"{item} (cm)", key=key)

            if st.button("保存"):
                save_data = {
                    "日付": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "商品管理番号": selected_pid,
                    "ブランド": selected_brand,
                    "カテゴリ": category,
                    "商品名": product_row["商品名"],
                    "カラー": product_row["カラー"],
                    "サイズ": selected_size
                }
                save_data.update(measurements)

                result_sheet = spreadsheet.worksheet("採寸結果")
                headers = result_sheet.row_values(1)
                new_row = [save_data.get(h, "") for h in headers]
                result_sheet.append_row(new_row)

                master_sheet = spreadsheet.worksheet("商品マスタ")
                all_records = master_sheet.get_all_records()
                master_df = pd.DataFrame(all_records)
                updated_df = master_df[~((master_df["管理番号"] == selected_pid) & (master_df["サイズ"] == selected_size))]
                master_sheet.clear()
                master_sheet.update([updated_df.columns.tolist()] + updated_df.values.tolist())

                st.success("✅ 採寸データを保存し、マスタから削除しました！")
        else:
            st.warning("テンプレートが見つかりません")
    except Exception as e:
        st.error(f"読み込みエラー: {e}")

# 採寸検索ページ
elif page == "採寸検索":
    st.title("🔍 採寸結果検索")
    try:
        result_df = pd.DataFrame(spreadsheet.worksheet("採寸結果").get_all_records())
        selected_brands = st.multiselect("🔸 ブランドを選択（複数可）", sorted([str(b) for b in result_df["ブランド"].dropna().unique()]))
        selected_pids = st.multiselect("🔹 管理番号を選択（複数可）", sorted([str(p) for p in result_df["商品管理番号"].dropna().unique()]))
        selected_sizes = st.multiselect("🔺 サイズを選択（複数可）", sorted([str(s) for s in result_df["サイズ"].dropna().unique()]))

        keyword = st.text_input("🔍 キーワードで検索（商品名、管理番号など）")
        category_filter = st.selectbox("📂 カテゴリで表示項目を絞る", ["すべて表示"] + sorted([str(c) for c in result_df["カテゴリ"].dropna().unique()]))

        if selected_brands:
            result_df = result_df[result_df["ブランド"].astype(str).isin(selected_brands)]
        if selected_pids:
            result_df = result_df[result_df["商品管理番号"].astype(str).isin(selected_pids)]
        if selected_sizes:
            result_df = result_df[result_df["サイズ"].astype(str).isin(selected_sizes)]
        if keyword:
            result_df = result_df[result_df.apply(lambda row: keyword in str(row.values), axis=1)]
        if category_filter != "すべて表示":
            result_df = result_df[result_df["カテゴリ"].astype(str) == category_filter]

        display_df = result_df.dropna(axis=1, how="all")
        display_df = display_df.loc[:, ~(display_df == "").all()]

        base_columns = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ"]
        category = category_filter if category_filter != "すべて表示" else None
        ideal_order = ideal_order_dict.get(category, [])
        reordered_cols = base_columns + [col for col in ideal_order if col in display_df.columns] + [
            col for col in display_df.columns if col not in base_columns + ideal_order
        ]
        display_df = display_df[reordered_cols]

        st.write(f"🔍 検索結果: {len(display_df)} 件")
        st.dataframe(display_df)

        if not display_df.empty:
            to_excel = io.BytesIO()
            with pd.ExcelWriter(to_excel, engine='openpyxl') as writer:
                display_df.to_excel(writer, index=False, sheet_name='採寸結果')
            to_excel.seek(0)
            st.download_button("📥 検索結果をExcelでダウンロード", data=to_excel,
                               file_name="採寸結果_検索結果.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
