import streamlit as st
import pandas as pd
import gspread
import json
import re
import io
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
import pytz

# ---------- 初期設定 ----------
st.set_page_config(page_title="採寸データ管理", layout="wide")
page = st.sidebar.selectbox("ページを選択", ["採寸入力", "採寸検索", "商品インポート", "採寸ヘッダー初期化"])

# ---------- Google Sheets認証 ----------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)
spreadsheet = client.open("採寸管理データ")

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

# ---------- 自動アーカイブ処理（30日以上前のデータを移動） ----------
def archive_old_records():
    try:
        now = datetime.now(pytz.timezone("Asia/Tokyo"))
        cutoff = now - timedelta(days=30)

        result_ws = spreadsheet.worksheet("採寸結果")
        archive_ws = spreadsheet.worksheet("採寸アーカイブ")

        result_df = pd.DataFrame(result_ws.get_all_records())
        if result_df.empty:
            return

        result_df["日付_dt"] = pd.to_datetime(result_df["日付"], errors='coerce')

        to_archive = result_df[result_df["日付_dt"] < cutoff]
        keep = result_df[result_df["日付_dt"] >= cutoff]

        if not to_archive.empty:
            archive_existing = pd.DataFrame(archive_ws.get_all_records())
            combined = pd.concat([archive_existing, to_archive.drop(columns="日付_dt")], ignore_index=True)

            archive_ws.clear()
            archive_ws.update([combined.columns.tolist()] + combined.values.tolist())

            result_ws.clear()
            result_ws.update([keep.drop(columns="日付_dt").columns.tolist()] + keep.drop(columns="日付_dt").values.tolist())
    except Exception as e:
        st.warning(f"アーカイブ処理エラー: {e}")

archive_old_records()
# ---------- 採寸入力ページ ----------
if page == "採寸入力":
    st.title("✍️ 採寸入力フォーム")
    try:
        master_df = pd.DataFrame(spreadsheet.worksheet("商品マスタ").get_all_records())
        result_df = pd.DataFrame(spreadsheet.worksheet("採寸結果").get_all_records())

        brand_list = master_df["ブランド"].dropna().unique().tolist()
        selected_brand = st.selectbox("ブランドを選択", brand_list, key="brand_select")
        filtered_df = master_df[master_df["ブランド"] == selected_brand]

        product_ids = filtered_df["管理番号"].dropna().unique().tolist()
        selected_pid = st.selectbox("管理番号を選択", product_ids, key="pid_select")

        product_row = filtered_df[filtered_df["管理番号"] == selected_pid].iloc[0]
        size_options = filtered_df[filtered_df["管理番号"] == selected_pid]["サイズ"].unique()
        selected_size = st.selectbox("サイズ", size_options, key="size_select")

        category = product_row["カテゴリ"]
        template_df = pd.DataFrame(spreadsheet.worksheet("採寸テンプレート").get_all_records())
        item_row = template_df[template_df["カテゴリ"] == category]

        if not item_row.empty:
            raw_items = item_row.iloc[0]["採寸項目"].replace("、", ",").split(",")
            all_items = [re.sub(r'（.*?）', '', i).strip() for i in raw_items if i.strip()]
            ideal_order = ideal_order_dict.get(category, [])
            items = [i for i in ideal_order if i in all_items] + [i for i in all_items if i not in ideal_order]

            # 🔍 類似データ自動補完
            def extract_keywords(text):
                return set(re.findall(r'[A-Za-z0-9]+', str(text).upper()))

            keywords = extract_keywords(product_row["商品名"])
            keywords = {k for k in keywords if len(k) >= 3}

            def score(row):
                target_words = extract_keywords(row["商品名"])
                return len(keywords & target_words)

            result_df["score"] = result_df.apply(score, axis=1)
            candidates = result_df[result_df["サイズ"].astype(str).str.strip() == str(selected_size).strip()]
            candidates = candidates[candidates["score"] > 0].sort_values("score", ascending=False)
            previous_data = candidates.head(1)

            st.markdown("### 採寸値入力")
            measurements = {}
            for item in items:
                key = f"{item}_{selected_pid}_{selected_size}"
                default = previous_data.iloc[0][item] if not previous_data.empty and item in previous_data.columns else ""
                st.text_input(f"{item} (前回: {default})", value="", key=key)
                measurements[item] = st.session_state.get(key, "")

            if st.button("保存", key="save_button"):
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

                # マスタから削除
                master_sheet = spreadsheet.worksheet("商品マスタ")
                master_all = pd.DataFrame(master_sheet.get_all_records())
                updated_df = master_all[~((master_all["管理番号"] == selected_pid) & (master_all["サイズ"] == selected_size))]
                master_sheet.clear()
                master_sheet.update([updated_df.columns.tolist()] + updated_df.values.tolist())

                st.success("✅ 採寸データを保存し、マスタから削除しました！")
        else:
            st.warning("テンプレートが見つかりません")
    except Exception as e:
        st.error(f"読み込みエラー: {e}")
# ---------------------
# 採寸検索ページ
# ---------------------
elif page == "採寸検索":
    st.title("🔍 採寸結果検索")
    try:
        result_df = pd.DataFrame(spreadsheet.worksheet("採寸結果").get_all_records())
        archive_df = pd.DataFrame(spreadsheet.worksheet("採寸アーカイブ").get_all_records())
        result_df = pd.concat([result_df, archive_df], ignore_index=True)

        selected_brands = st.multiselect("🔸 ブランドを選択", sorted(result_df["ブランド"].dropna().astype(str).unique()))
        selected_pids = st.multiselect("🔹 管理番号を選択", sorted(result_df["商品管理番号"].dropna().astype(str).unique()))
        selected_sizes = st.multiselect("🔺 サイズを選択", sorted(result_df["サイズ"].dropna().astype(str).unique()))
        keyword = st.text_input("🔍 キーワード検索（商品名、管理番号など）")
        category_filter = st.selectbox("📂 カテゴリで表示項目を絞る", ["すべて表示"] + sorted(result_df["カテゴリ"].dropna().astype(str).unique()))

        # フィルタリング
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

        # 項目順整列
        base_cols = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ"]
        ideal_cols = ideal_order_dict.get(category_filter, [])
        ordered_cols = base_cols + [col for col in ideal_cols if col in result_df.columns] + \
                       [col for col in result_df.columns if col not in base_cols + ideal_cols]
        result_df = result_df[ordered_cols]

        # 全て空の列を削除
        result_df = result_df.loc[:, ~((result_df == "") | (result_df.isna())).all()]

        st.write(f"🔍 検索結果: {len(result_df)} 件")
        st.dataframe(result_df)

        if not result_df.empty:
            to_excel = io.BytesIO()
            with pd.ExcelWriter(to_excel, engine="openpyxl") as writer:
                result_df.to_excel(writer, index=False, sheet_name="採寸結果")
                writer.sheets["採寸結果"].auto_filter.ref = writer.sheets["採寸結果"].dimensions
            to_excel.seek(0)

            st.download_button(
                label="📥 検索結果をExcelでダウンロード",
                data=to_excel,
                file_name="採寸検索結果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    except Exception as e:
        st.error(f"検索エラー: {e}")
# ---------------------
# 商品インポートページ
# ---------------------
elif page == "商品インポート":
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
                st.success("✅ データを保存しました！")
            except Exception as e:
                st.error(f"保存エラー: {e}")
# ---------------------
# 採寸ヘッダー初期化ページ
# ---------------------
elif page == "採寸ヘッダー初期化":
    st.title("📋 採寸結果ヘッダーを初期化")

    headers = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ"]
    all_items = sorted(set(sum(ideal_order_dict.values(), [])))
    headers.extend(all_items)

    try:
        sheet = spreadsheet.worksheet("採寸結果")
        sheet.clear()
        sheet.append_row(headers)
        st.success("✅ ヘッダーを初期化しました（既存データは削除されます）")
    except Exception as e:
        st.error(f"初期化エラー: {e}")
