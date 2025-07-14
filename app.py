import streamlit as st
import pandas as pd
import gspread
import json
import re
import io
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Streamlit 初期設定
st.set_page_config(page_title="採寸データ管理", layout="wide")
page = st.sidebar.selectbox("ページを選択", [
    "採寸入力", "採寸検索", "商品インポート", "採寸ヘッダー初期化", "アーカイブ管理"
])

# Google Sheets 認証
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)
spreadsheet = client.open("採寸管理データ")

# 採寸順序の定義
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

# ---------------------
# 採寸入力ページ（キャッシュ＋履歴表示＋前回候補除外＋rerun対応）
# ---------------------
if page == "採寸入力":
    st.title("✍️ 採寸入力フォーム")

    @st.cache_data(ttl=300)
    def load_combined_results():
        def to_df(values):
            if not values:
                return pd.DataFrame()
            headers = values[0]
            data = [row + [''] * (len(headers) - len(row)) for row in values[1:]]
            return pd.DataFrame(data, columns=headers)

        result_values = spreadsheet.worksheet("採寸結果").get_all_values()
        archive_values = spreadsheet.worksheet("採寸アーカイブ").get_all_values()
        result_df = to_df(result_values)
        archive_df = to_df(archive_values)
        return pd.concat([result_df, archive_df], ignore_index=True)

    try:
        master_df = pd.DataFrame(spreadsheet.worksheet("商品マスタ").get_all_records())
        combined_df = load_combined_results()

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

            def extract_keywords(text):
                return set(re.findall(r'[A-Za-z0-9]+', str(text).upper()))

            keywords = extract_keywords(product_row["商品名"])
            keywords = {k for k in keywords if len(k) >= 3}

            def score(row):
                target_words = extract_keywords(row["商品名"])
                return len(keywords & target_words)

            previous_data = pd.DataFrame()
            if not combined_df.empty:
                combined_df["score"] = combined_df.apply(score, axis=1)
                candidates = combined_df[
                    (combined_df["サイズ"].astype(str).str.strip() == str(selected_size).strip()) &
                    (combined_df["商品管理番号"] != selected_pid)
                ]
                candidates = candidates[candidates["score"] > 0].sort_values("score", ascending=False)
                previous_data = candidates.head(1)

                   measurements = {}
        for item in items:
            key = f"measure_{item}_{selected_pid}_{selected_size}"
            default = previous_data.iloc[0][item] if not previous_data.empty and item in previous_data.columns else ""
            st.text_input(f"{item} (前回: {default})", value="", key=key)
            measurements[item] = st.session_state.get(key, "")

        # 📝 備考欄（任意入力）
        remark_key = f"remark_{selected_pid}_{selected_size}"
        remarks = st.text_area("📝 備考（任意）", key=remark_key)

        # 💾 保存ボタン
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
            save_data["備考"] = remarks  # ← 備考追加

            result_sheet = spreadsheet.worksheet("採寸結果")
            headers = result_sheet.row_values(1)
            new_row = [save_data.get(h, "") for h in headers]
            result_sheet.append_row(new_row)

            master_sheet = spreadsheet.worksheet("商品マスタ")
            master_df = pd.DataFrame(master_sheet.get_all_records())
            updated_df = master_df[~((master_df["管理番号"] == selected_pid) & (master_df["サイズ"] == selected_size))]
            master_sheet.clear()
            master_sheet.update([updated_df.columns.tolist()] + updated_df.values.tolist())

            st.success("✅ 採寸データを保存しました！ページを更新しています...")
            st.rerun()


            # 👕 同モデル履歴（入力中データ含む）
            st.markdown("### 👕 同じモデルの過去採寸データ（比較用）")
            try:
                model_prefix = selected_pid[:8]
                model_df = combined_df[
                    (combined_df["商品管理番号"].str[:8] == model_prefix) &
                    (combined_df["商品管理番号"] != selected_pid)
                ]

                input_row = {
                    "日付": "（入力中）",
                    "商品管理番号": selected_pid,
                    "サイズ": selected_size
                }
                for item in items:
                    input_row[item] = measurements.get(item, "")

                model_df = pd.concat([pd.DataFrame([input_row]), model_df], ignore_index=True)

                base_cols = ["日付", "商品管理番号", "サイズ"]
                show_cols = base_cols + [col for col in model_df.columns if col in items]
                show_df = model_df[show_cols].sort_values(by=["日付", "サイズ"], ascending=[False, True])
                st.dataframe(show_df, use_container_width=True)
            except Exception as e:
                st.warning(f"同モデル採寸データの取得に失敗しました: {e}")

            # 📅 本日登録一覧
            st.markdown("### 📅 本日登録した採寸データ一覧")
            today_str = datetime.now().strftime("%Y-%m-%d")
            try:
                today_df = combined_df[combined_df["日付"] == today_str]
                if not today_df.empty:
                    base_cols = ["商品管理番号", "サイズ"]
                    show_cols = base_cols + [col for col in today_df.columns if col in items]
                    show_df = today_df[show_cols].copy()
                    show_df = show_df.sort_values(by=["商品管理番号", "サイズ"])
                    st.dataframe(show_df, use_container_width=True)
                else:
                    st.info("今日はまだ採寸データが登録されていません。")
            except Exception as e:
                st.warning(f"今日の採寸データを表示できませんでした: {e}")

        else:
            st.warning("テンプレートが見つかりません")
    except Exception as e:
        st.error(f"読み込みエラー: {e}")

# ---------------------
# 採寸検索ページ（アーカイブと統合検索＋ブランド連動で管理番号・サイズ・カテゴリを絞る）
# ---------------------
elif page == "採寸検索":
    st.title("🔍 採寸結果検索")
    try:
        result_values = spreadsheet.worksheet("採寸結果").get_all_values()
        archive_values = spreadsheet.worksheet("採寸アーカイブ").get_all_values()

        def to_df(values):
            if not values:
                return pd.DataFrame()
            headers = values[0]
            data = [row + [''] * (len(headers) - len(row)) for row in values[1:]]
            return pd.DataFrame(data, columns=headers)

        result_df = to_df(result_values)
        archive_df = to_df(archive_values)
        combined_df = pd.concat([result_df, archive_df], ignore_index=True)

        # ブランド選択
        selected_brands = st.multiselect("🔸 ブランドを選択", sorted(combined_df["ブランド"].dropna().unique()))

        # ブランドに基づくフィルタリング
        if selected_brands:
            filtered_df = combined_df[combined_df["ブランド"].isin(selected_brands)]
            pid_options = sorted(filtered_df["商品管理番号"].dropna().unique())
            size_options = sorted(filtered_df["サイズ"].dropna().unique())
            category_options = sorted(filtered_df["カテゴリ"].dropna().unique())
        else:
            pid_options = sorted(combined_df["商品管理番号"].dropna().unique())
            size_options = sorted(combined_df["サイズ"].dropna().unique())
            category_options = sorted(combined_df["カテゴリ"].dropna().unique())

        # 管理番号・サイズ・カテゴリを選択肢表示
        selected_pids = st.multiselect("🔹 管理番号を選択", pid_options)
        selected_sizes = st.multiselect("🔺 サイズを選択", size_options)
        keyword = st.text_input("🔍 キーワードで検索（商品名、管理番号など）")
        category_filter = st.selectbox("📂 カテゴリで表示項目を絞る", ["すべて表示"] + category_options)

        # 条件に応じてフィルタリング
        filtered_df = combined_df.copy()
        if selected_brands:
            filtered_df = filtered_df[filtered_df["ブランド"].isin(selected_brands)]
        if selected_pids:
            filtered_df = filtered_df[filtered_df["商品管理番号"].isin(selected_pids)]
        if selected_sizes:
            filtered_df = filtered_df[filtered_df["サイズ"].isin(selected_sizes)]
        if keyword:
            filtered_df = filtered_df[filtered_df.apply(lambda row: keyword.lower() in str(row.values).lower(), axis=1)]
        if category_filter != "すべて表示":
            filtered_df = filtered_df[filtered_df["カテゴリ"] == category_filter]

        # 表示列の並び替え
        base_cols = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ"]
        ideal_cols = ideal_order_dict.get(category_filter, [])
        ordered_cols = base_cols + [col for col in ideal_cols if col in filtered_df.columns] + \
                       [col for col in filtered_df.columns if col not in base_cols + ideal_cols]
        filtered_df = filtered_df[ordered_cols]
        filtered_df = filtered_df.loc[:, ~((filtered_df == "") | (filtered_df.isna())).all(axis=0)]

        # 検索結果表示
        st.write(f"🔍 検索結果: {len(filtered_df)} 件")
        st.dataframe(filtered_df, use_container_width=True)

        # Excel出力
        if not filtered_df.empty:
            to_excel = io.BytesIO()
            with pd.ExcelWriter(to_excel, engine="openpyxl") as writer:
                filtered_df.to_excel(writer, index=False, sheet_name="採寸結果")
                writer.sheets["採寸結果"].auto_filter.ref = writer.sheets["採寸結果"].dimensions
            to_excel.seek(0)

            st.download_button(
                label="📥 検索結果をExcelでダウンロード",
                data=to_excel,
                file_name="採寸結果_検索結果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    except Exception as e:
        st.error(f"読み込みエラー: {e}")

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
                st.success("✅ データを保存しました")
            except Exception as e:
                st.error(f"保存エラー: {e}")

# ---------------------
# 採寸ヘッダー初期化ページ（両方対応）
# ---------------------
elif page == "採寸ヘッダー初期化":
    st.title("📋 採寸シート ヘッダー初期化（※データは残す）")

    headers = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ",
               "肩幅", "胸幅", "胴囲", "袖丈", "着丈", "襟高", "ウエスト", "股上", "股下",
               "ワタリ", "裾幅", "全長", "最大幅", "横幅", "頭周り", "ツバ", "高さ", "裄丈", "ベルト幅", "前丈", "後丈"]

    def reinitialize_sheet(sheet_name):
        try:
            sheet = spreadsheet.worksheet(sheet_name)
            all_data = sheet.get_all_values()[1:]  # データ部分（2行目以降）

            sheet.clear()
            sheet.append_row(headers)

            if all_data:
                normalized = [row + [''] * (len(headers) - len(row)) for row in all_data]
                sheet.append_rows(normalized)
            st.success(f"✅ 『{sheet_name}』のヘッダーを初期化しました！")
        except Exception as e:
            st.error(f"『{sheet_name}』の処理エラー: {e}")

    if st.button("🧼 採寸結果シートの初期化"):
        reinitialize_sheet("採寸結果")

    if st.button("🧼 採寸アーカイブシートの初期化"):
        reinitialize_sheet("採寸アーカイブ")

# ---------------------
# アーカイブ管理ページ（30日超データ移動）
# ---------------------
elif page == "アーカイブ管理":
    st.title("🗃️ 採寸データのアーカイブ管理")

    def parse_date_flexibly(date_str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except:
                continue
        return None  # 不正な日付なら None

    if st.button("📦 30日以上前の採寸結果をアーカイブに移動"):
        try:
            result_ws = spreadsheet.worksheet("採寸結果")
            archive_ws = spreadsheet.worksheet("採寸アーカイブ")
            values = result_ws.get_all_values()
            headers = values[0]
            rows = values[1:]

            old_rows = []
            recent_rows = []
            today = datetime.now()

            for row in rows:
                row += [''] * (len(headers) - len(row))
                parsed_date = parse_date_flexibly(row[0])

                if parsed_date and (today - parsed_date).days > 30:
                    old_rows.append(row)
                else:
                    recent_rows.append(row)

            if old_rows:
                archive_data = archive_ws.get_all_values()
                if not archive_data:
                    archive_ws.append_row(headers)
                archive_ws.append_rows(old_rows)

            result_ws.clear()
            result_ws.append_row(headers)
            if recent_rows:
                result_ws.append_rows(recent_rows)

            st.success(f"✅ {len(old_rows)} 件をアーカイブに移動しました！")
        except Exception as e:
            st.error(f"エラー: {e}")
