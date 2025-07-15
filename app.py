import streamlit as st
import pandas as pd
import gspread
import json
import re
import io
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="採寸データ管理", layout="wide")
page = st.sidebar.selectbox("ページを選択", [
    "採寸入力", "採寸検索", "商品インポート", "基準値インポート", "採寸ヘッダー初期化", "アーカイブ管理"
])

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)
spreadsheet = client.open("採寸管理データ")

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
if page == "採寸入力":
    st.title("📱 採寸入力")

    @st.cache_data(ttl=300)
    def load_sheet(name):
        return pd.DataFrame(spreadsheet.worksheet(name).get_all_records())

    master_df = load_sheet("商品マスタ")
    template_df = load_sheet("採寸テンプレート")
    result_df = load_sheet("採寸結果")
    archive_df = load_sheet("採寸アーカイブ")
    combined_df = pd.concat([result_df, archive_df], ignore_index=True)

    brand_list = master_df["ブランド"].dropna().unique().tolist()
    selected_brand = st.selectbox("ブランドを選択", brand_list)
    filtered_df = master_df[master_df["ブランド"] == selected_brand]

    pid_list = filtered_df["管理番号"].dropna().unique().tolist()
    selected_pid = st.selectbox("管理番号を選択", pid_list)
    product_group = filtered_df[filtered_df["管理番号"] == selected_pid]
    product_row = product_group.iloc[0]
    category = product_row["カテゴリ"]

    st.write(f"**商品名：** {product_row['商品名']}　　**カラー：** {product_row['カラー']}")
    sizes = product_group["サイズ"].tolist()

    template_row = template_df[template_df["カテゴリ"] == category]
    if template_row.empty:
        st.warning("テンプレートが見つかりません")
        st.stop()

    raw_items = template_row.iloc[0]["採寸項目"].replace("、", ",").split(",")
    all_items = [re.sub(r'（.*?）', '', i).strip() for i in raw_items if i.strip()]
    custom_order = ideal_order_dict.get(category, [])
    items = [i for i in custom_order if i in all_items] + [i for i in all_items if i not in custom_order]

    # 既存採寸をDataFrameに格納
    data = {item: [] for item in items}
    remarks = []
    for size in sizes:
        row = combined_df[(combined_df["商品管理番号"] == selected_pid) & (combined_df["サイズ"] == size)]
        for item in items:
            val = row[item].values[0] if not row.empty and item in row.columns else ""
            data[item].append(val)
        note = row["備考"].values[0] if not row.empty and "備考" in row.columns else ""
        remarks.append(note)
    data["備考"] = remarks
    df = pd.DataFrame(data, index=sizes)
    df.index.name = "サイズ"

    # ---- 基準値表示 ----
    try:
        standard_df = load_sheet("基準データ")
        filtered_standard = standard_df[standard_df["商品管理番号"] == selected_pid]

        if not filtered_standard.empty:
            filtered_standard = filtered_standard.set_index("サイズ")
            show_columns = [col for col in ideal_order_dict.get(category, []) if col in filtered_standard.columns]
            display_df = filtered_standard[show_columns].copy()

            st.markdown("### ✏️ この商品のサイズ別 基準採寸値")
            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("この商品に該当する基準データが見つかりませんでした。")
    except Exception as e:
        st.warning(f"基準値の表示に失敗しました: {e}")

    # ---- 編集フォーム ----
    st.markdown("### ✍ 採寸と備考の入力（直接編集）")
    edited_df = st.data_editor(df.copy(), use_container_width=True, num_rows="dynamic", key="editor")

    # ---- 保存処理 ----
    if st.button("保存する"):
        result_sheet = spreadsheet.worksheet("採寸結果")
        headers = result_sheet.row_values(1)
        master_sheet = spreadsheet.worksheet("商品マスタ")
        full_master_df = pd.DataFrame(master_sheet.get_all_records())

        saved_sizes = []

        for size in edited_df.index:
            size_str = str(size).strip()
            if not size_str:
                continue
            if edited_df.loc[size, items].replace("", float("nan")).isna().all():
                continue

            save_data = {
                "日付": datetime.now().strftime("%Y-%m-%d"),
                "商品管理番号": selected_pid,
                "ブランド": selected_brand,
                "カテゴリ": category,
                "商品名": product_row["商品名"],
                "カラー": product_row["カラー"],
                "サイズ": size_str,
                "備考": edited_df.loc[size, "備考"]
            }
            for item in items:
                save_data[item] = edited_df.loc[size, item]

            new_row = [save_data.get(h, "") for h in headers]
            result_sheet.append_row(new_row)
            saved_sizes.append(size_str)

        updated_master_df = full_master_df[~(
            (full_master_df["管理番号"] == selected_pid) &
            (full_master_df["サイズ"].isin(saved_sizes))
        )]
        master_sheet.clear()
        master_sheet.update([updated_master_df.columns.tolist()] + updated_master_df.values.tolist())

        with st.spinner("保存中...しばらくお待ちください"):
            st.success("✅ 採寸データを保存し、商品マスタから該当サイズを削除しました。")
            time.sleep(2)  # ここで2秒待機

        st.experimental_rerun()



    # --- 過去比較 ---
    st.markdown("### 👕 同じモデルの過去採寸データ（比較用）")
    try:
        model_prefix = selected_pid[:8]
        model_df = combined_df[
            (combined_df["商品管理番号"].str[:8] == model_prefix) &
            (combined_df["商品管理番号"] != selected_pid)
        ]
        base_cols = ["日付", "商品管理番号", "サイズ"]
        show_cols = base_cols + [col for col in model_df.columns if col in items]
        show_df = model_df[show_cols].sort_values(by=["日付", "サイズ"], ascending=[False, True])
        st.dataframe(show_df, use_container_width=True)
    except Exception as e:
        st.warning(f"同モデル採寸データの取得に失敗しました: {e}")

    # --- 本日登録データ ---
    st.markdown("### 📅 本日登録した採寸データ一覧")
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        today_df = combined_df[combined_df["日付"] == today_str]
        if not today_df.empty:
            base_cols = ["商品管理番号", "サイズ"]
            show_cols = base_cols + [col for col in today_df.columns if col in items]
            show_df = today_df[show_cols].sort_values(by=["商品管理番号", "サイズ"])
            st.dataframe(show_df, use_container_width=True)
        else:
            st.info("今日はまだ採寸データが登録されていません。")
    except Exception as e:
        st.warning(f"今日の採寸データを表示できませんでした: {e}")

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
    st.title("📦 商品マスタ：Excelインポート")
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
                product_sheet = spreadsheet.worksheet("商品マスタ")
                existing_df = pd.DataFrame(product_sheet.get_all_records())
                updated_df = pd.concat([existing_df, expanded_df], ignore_index=True).drop_duplicates()
                product_sheet.clear()
                product_sheet.update([updated_df.columns.tolist()] + updated_df.values.tolist())
                st.success("✅ 商品マスタに保存しました！")
            except Exception as e:
                st.error(f"保存エラー: {e}")
# ---------------------
# 基準値インポートページ
# ---------------------
elif page == "基準値インポート":
    st.title("📏 基準値インポート")

    uploaded_file = st.file_uploader("基準値Excelファイルをアップロード", type=["xlsx"])

    if uploaded_file:
        try:
            # データ読み込み
            product_df = pd.read_excel(uploaded_file, sheet_name="商品マスタ")
            standard_df = pd.read_excel(uploaded_file, sheet_name="基準ID")

            # JOINして1行構成に変換
            merged_df = pd.merge(product_df, standard_df, on="基準ID", how="inner")

            # 👇 この行を追加
            merged_df = merged_df.dropna(axis=1, how="all")

            # 日付列追加
            merged_df["日付"] = datetime.now().strftime("%Y-%m-%d")


            # 表示
            st.markdown("### 👀 アップロード内容（統合済）")
            st.dataframe(merged_df, use_container_width=True)

            if st.button("Googleスプレッドシートに保存"):
                try:
                    # シート取得（なければ作成）
                    try:
                        sheet = spreadsheet.worksheet("基準データ")
                    except gspread.exceptions.WorksheetNotFound:
                        sheet = spreadsheet.add_worksheet(title="基準データ", rows="100", cols="50")

                    # 既存データ読み込み
                    existing_df = pd.DataFrame(sheet.get_all_records())

                    # 同じ「商品管理番号＋サイズ」は削除（上書き扱い）
                    if not existing_df.empty:
                        merged_keys = set(zip(merged_df["商品管理番号"], merged_df["サイズ"]))
                        existing_df = existing_df[~existing_df.apply(
                            lambda row: (row["商品管理番号"], row["サイズ"]) in merged_keys, axis=1
                        )]

                    # 結合して保存（NaNは空にする）
                    final_df = pd.concat([existing_df, merged_df], ignore_index=True)
                    sheet.clear()
                    sheet.update([final_df.columns.tolist()] + final_df.fillna("").values.tolist())

                    st.success("✅ 基準データをスプレッドシートに保存しました！")
                except Exception as e:
                    st.error(f"保存エラー: {e}")

        except Exception as e:
            st.error(f"読み込みエラー: {e}")

# ---------------------
# 採寸ヘッダー初期化ページ（両方対応）
# ---------------------
elif page == "採寸ヘッダー初期化":
    st.title("📋 採寸シート ヘッダー初期化（※データは残る）")

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
