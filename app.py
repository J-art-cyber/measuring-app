import streamlit as st
import pandas as pd
import gspread
import json
import re
import io
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ---------- 初期設定 ----------
st.set_page_config(page_title="採寸データ管理", layout="wide")
page = st.sidebar.selectbox("ページを選択", ["採寸入力", "採寸検索", "商品インポート", "採寸ヘッダー初期化"])

# ---------- Google Sheets認証と接続 ----------
@st.cache_resource
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
    return gspread.authorize(creds)

client = get_gspread_client()
spreadsheet = client.open("採寸管理データ")

# ---------- シート読み込み用キャッシュ ----------
@st.cache_data(ttl=60)
def load_sheet(name):
    sheet = spreadsheet.worksheet(name)
    df = pd.DataFrame(sheet.get_all_records())
    return df

# ---------- カテゴリ別理想順 ----------
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
# ------------------------
# 採寸入力ページ
# ------------------------
if page == "採寸入力":
    st.title("✍️ 採寸入力フォーム")
    try:
        master_df = load_sheet("商品マスタ")
        result_df = load_sheet("採寸結果")

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
        template_df = load_sheet("採寸テンプレート")
        item_row = template_df[template_df["カテゴリ"] == category]

        if not item_row.empty:
            raw_items = item_row.iloc[0]["採寸項目"].replace("、", ",").split(",")
            all_items = [re.sub(r'（.*?）', '', i).strip() for i in raw_items if i.strip()]
            ideal_order = ideal_order_dict.get(category, [])
            items = [i for i in ideal_order if i in all_items] + [i for i in all_items if i not in ideal_order]

            st.markdown("### 採寸値入力")

            # 🔍 類似商品検索ロジック（キーワードスコアベース）
            def extract_keywords(text):
                return set(re.findall(r'[A-Za-z0-9]+', str(text).upper()))

            def score(row):
                target_words = extract_keywords(row["商品名"])
                return len(keywords & target_words)

            keywords = extract_keywords(product_row["商品名"])
            keywords = {k for k in keywords if len(k) >= 3}

            result_df["score"] = result_df.apply(score, axis=1)
            candidates = result_df[result_df["サイズ"].astype(str).str.strip() == str(selected_size).strip()]
            candidates = candidates[candidates["score"] > 0].sort_values("score", ascending=False)

            previous_data = candidates.head(1)

            measurements = {}
            for item in items:
                key = f"measure_{item}_{selected_pid}_{selected_size}"
                default = previous_data.iloc[0][item] if not previous_data.empty and item in previous_data.columns else ""
                st.text_input(f"{item} (前回: {default})", value="", key=key)
                measurements[item] = st.session_state.get(key, "")

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
# ------------------------
# 採寸検索ページ
# ------------------------
elif page == "採寸検索":
    st.title("🔍 採寸結果検索")
    try:
        result_df = load_sheet("採寸結果")

        # フィルターUI
        selected_brands = st.multiselect("🔸 ブランドを選択", sorted(result_df["ブランド"].dropna().astype(str).unique()))
        selected_pids = st.multiselect("🔹 管理番号を選択", sorted(result_df["商品管理番号"].dropna().astype(str).unique()))
        selected_sizes = st.multiselect("🔺 サイズを選択", sorted(result_df["サイズ"].dropna().astype(str).unique()))
        keyword = st.text_input("🔍 キーワードで検索（商品名、管理番号など）")
        category_filter = st.selectbox("📂 カテゴリで表示項目を絞る", ["すべて表示"] + sorted(result_df["カテゴリ"].dropna().astype(str).unique()))

        # フィルタリング処理
        if selected_brands:
            result_df = result_df[result_df["ブランド"].astype(str).isin(selected_brands)]
        if selected_pids:
            result_df = result_df[result_df["商品管理番号"].astype(str).isin(selected_pids)]
        if selected_sizes:
            result_df = result_df[result_df["サイズ"].astype(str).isin(selected_sizes)]
        if keyword:
            result_df = result_df[result_df.apply(lambda row: keyword.lower() in str(row.values).lower(), axis=1)]
        if category_filter != "すべて表示":
            result_df = result_df[result_df["カテゴリ"].astype(str) == category_filter]

        # カラム順ソート（理想順）
        base_cols = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ"]
        ideal_cols = ideal_order_dict.get(category_filter, [])
        ordered_cols = base_cols + [col for col in ideal_cols if col in result_df.columns] + \
                       [col for col in result_df.columns if col not in base_cols + ideal_cols]
        result_df = result_df[ordered_cols]

        # 空白列削除（すべて空 or NaN の列を除外）
        result_df = result_df.loc[:, ~(result_df == "").all(axis=0) & result_df.isna().all(axis=0) == False]

        # 表示
        st.write(f"🔍 検索結果: {len(result_df)} 件")
        st.dataframe(result_df)

        # Excel出力
        if not result_df.empty:
            to_excel = io.BytesIO()
            with pd.ExcelWriter(to_excel, engine="openpyxl") as writer:
                result_df.to_excel(writer, index=False, sheet_name="採寸結果")
                writer.sheets["採寸結果"].auto_filter.ref = writer.sheets["採寸結果"].dimensions
            to_excel.seek(0)

            st.download_button(
                label="📥 検索結果をExcelでダウンロード（理想順で並び替え）",
                data=to_excel,
                file_name="採寸結果_検索結果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
# ------------------------
# 商品インポートページ
# ------------------------
elif page == "商品インポート":
    st.title("📦 商品マスタ：Excelインポートとサイズ展開")

    uploaded_file = st.file_uploader("Excelファイルをアップロード", type=["xlsx"])

    if uploaded_file:
        # 読み込み
        df = pd.read_excel(uploaded_file, header=1)
        st.subheader("元データ")
        st.dataframe(df)

        # サイズ展開処理（カンマ・全角カンマ対応）
        def expand_sizes(df):
            df = df.copy()
            df["サイズ"] = df["サイズ"].astype(str).str.replace("、", ",").str.split(",")
            df["サイズ"] = df["サイズ"].apply(lambda x: [s.strip() for s in x])
            return df.explode("サイズ").reset_index(drop=True)

        expanded_df = expand_sizes(df)
        expanded_df["サイズ"] = expanded_df["サイズ"].str.strip()

        st.subheader("展開後（1サイズ1行）")
        st.dataframe(expanded_df)

        # 保存処理
        if st.button("Googleスプレッドシートに保存"):
            try:
                sheet = spreadsheet.worksheet("商品マスタ")
                existing_df = pd.DataFrame(sheet.get_all_records())

                # 結合 & 重複排除
                combined_df = pd.concat([existing_df, expanded_df], ignore_index=True)
                combined_df.drop_duplicates(subset=["管理番号", "サイズ"], keep="last", inplace=True)

                # 書き込み
                sheet.clear()
                sheet.update([combined_df.columns.tolist()] + combined_df.values.tolist())
                st.success("✅ データを保存しました！")
            except Exception as e:
                st.error(f"保存エラー: {e}")
# ------------------------
# 採寸ヘッダー初期化ページ
# ------------------------
elif page == "採寸ヘッダー初期化":
    st.title("📋 採寸結果ヘッダーを初期化")

    headers = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ"] + \
              sorted(set(sum(ideal_order_dict.values(), [])))

    try:
        sheet = spreadsheet.worksheet("採寸結果")
        sheet.clear()
        sheet.append_row(headers)
        st.success("✅ 採寸結果シートのヘッダーを初期化しました！")
    except Exception as e:
        st.error(f"エラー: {e}")
