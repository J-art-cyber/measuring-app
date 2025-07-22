import streamlit as st
import pandas as pd
import gspread
import json
import re
import io
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="採寸データ管理", layout="wide")

# ━━━━━ Google Sheets認証 ━━━━━
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
json_key = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(json_key, scope)
client = gspread.authorize(creds)
spreadsheet = client.open("採寸管理データ")

# ━━━━━ キャッシュ付き読み込み関数 ━━━━━
@st.cache_data(ttl=30)
def load_master_data():
    return pd.DataFrame(spreadsheet.worksheet("商品マスタ").get_all_records())

@st.cache_data(ttl=30)
def load_template_data():
    return pd.DataFrame(spreadsheet.worksheet("採寸テンプレート").get_all_records())

@st.cache_data(ttl=30)
def load_result_data():
    return pd.DataFrame(spreadsheet.worksheet("採寸結果").get_all_records())

@st.cache_data(ttl=30)
def load_archive_data():
    return pd.DataFrame(spreadsheet.worksheet("採寸アーカイブ").get_all_records())

@st.cache_data(ttl=30)
def load_standard_data():
    return pd.DataFrame(spreadsheet.worksheet("基準データ").get_all_records())

# ━━━━━ 項目の表示順辞書 ━━━━━
ideal_order_dict = {
    "ジャケット": ["肩幅", "胸幅", "胴囲", "袖丈", "着丈"],
    "パンツ": ["ウエスト", "股上", "股下", "ワタリ", "裾幅"],
    "ダウン": ["肩幅", "胸幅", "袖丈", "着丈", "襟高"],
    "ブルゾン": ["肩幅", "胸幅", "袖丈", "着丈", "襟高"],
    "コート": ["肩幅", "胸幅", "胴囲", "袖丈", "着丈", "襟高"],
    "ニット": ["肩幅", "胸幅", "袖丈", "着丈", "首高"],
    "カットソー": ["肩幅", "胸幅", "袖丈", "着丈"],
    "レザー": ["肩幅", "胸幅", "袖丈", "着丈", "襟高"],
    "靴": ["全長", "最大幅"],
    "巻物": ["全長", "横幅"],
    "小物・その他": ["頭周り", "ツバ", "高さ", "横幅", "高さ", "マチ"],
    "シャツ": ["肩幅", "裄丈", "胸幅", "胴囲", "袖丈", "着丈"],
    "シャツジャケット": ["肩幅", "胸幅", "袖丈", "着丈"],
    "スーツ": ["肩幅", "胸幅", "胴囲", "袖丈", "着丈", "ウエスト", "股上", "股下", "ワタリ", "裾幅"],
    "ベルト": ["全長", "ベルト幅"],
    "半袖": ["肩幅", "胸幅", "袖丈", "前丈", "後丈"],
    "ラグラン": ["裄丈", "胸幅", "着丈"]
}

# ━━━━━ サイドバーでページ切り替え ━━━━━
page = st.sidebar.selectbox("ページを選択", [
    "採寸入力", "採寸検索", "商品インポート", "基準値インポート", "採寸ヘッダー初期化", "アーカイブ管理"
])
if page == "採寸入力":
    st.title("📱 採寸入力")

    master_df = load_master_data()
    template_df = load_template_data()
    result_df = load_result_data()
    archive_df = load_archive_data()
    combined_df = pd.concat([result_df, archive_df], ignore_index=True)

    custom_orders = {
        "パンツ": ["ウエスト", "股上", "ワタリ", "股下", "裾幅"],
        "シャツ": ["肩幅", "胸幅", "胴囲", "裄丈", "袖丈", "着丈"]
    }

    selected_brand = st.selectbox("ブランドを選択", master_df["ブランド"].dropna().unique())
    filtered_df = master_df[master_df["ブランド"] == selected_brand]
    selected_pid = st.selectbox("管理番号を選択", filtered_df["管理番号"].dropna().unique())
    product_group = filtered_df[filtered_df["管理番号"] == selected_pid]
    product_row = product_group.iloc[0]
    category = product_row["カテゴリ"]
    sizes = product_group["サイズ"].tolist()

    st.write(f"**商品名：** {product_row['商品名']}　　**カラー：** {product_row['カラー']}")

    template_row = template_df[template_df["カテゴリ"] == category]
    if template_row.empty:
        st.warning("テンプレートが見つかりません")
        st.stop()

    raw_items = template_row.iloc[0]["採寸項目"].replace("、", ",").split(",")
    all_items = [re.sub(r'（.*?）', '', i).strip() for i in raw_items if i.strip()]
    custom_order = custom_orders.get(category, [])
    items = [i for i in custom_order if i in all_items] + [i for i in all_items if i not in custom_order]

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
    df = df.astype(str)

        # --- 📐 基準値の表示（採寸入力の上） ---
    st.markdown("### 📐 該当商品の基準値")

    try:
        standard_df = load_standard_data()
        std_row = standard_df[
            (standard_df["商品管理番号"] == selected_pid) &
            (standard_df["サイズ"].isin(sizes))
        ]

        if std_row.empty:
            st.info("この商品には基準値データが登録されていません。")
        else:
            std_row = std_row.set_index("サイズ")
            show_cols = [col for col in items if col in std_row.columns]
            show_df = std_row[show_cols].astype(str)
            st.dataframe(show_df, use_container_width=True)
    except Exception as e:
        st.warning(f"基準値の表示に失敗しました: {e}")


    # --- 表示 ---
    st.markdown("### ✍ 採寸")
    edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic")

    # --- 保存処理 ---
    if st.button("保存する"):
        try:
            result_sheet = spreadsheet.worksheet("採寸結果")
            headers = result_sheet.row_values(1)
            saved_sizes = []

            for size in edited_df.index:
                size_str = str(size).strip()
                if not size_str:
                    continue
                row_values = edited_df.loc[size, items]
                if isinstance(row_values, pd.Series) and row_values.replace("", pd.NA).isna().all():
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

                new_row = ["" if save_data.get(h) is None else str(save_data.get(h)) for h in headers]
                result_sheet.append_row(new_row)
                saved_sizes.append(size_str)

            # 商品マスタ更新
            master_sheet = spreadsheet.worksheet("商品マスタ")
            full_master_df = pd.DataFrame(master_sheet.get_all_records())
            full_master_df["サイズ"] = full_master_df["サイズ"].astype(str)
            updated_master_df = full_master_df[~(
                (full_master_df["管理番号"] == selected_pid) &
                (full_master_df["サイズ"].isin(saved_sizes))
            )]
            master_sheet.clear()
            master_sheet.update([updated_master_df.columns.tolist()] + updated_master_df.values.tolist())

            st.success("✅ 採寸データを保存しました。")
            st.rerun()  # ← この1行を追加


        except Exception as e:
            st.error(f"保存時にエラーが発生しました: {e}")

    # --- 👕 同モデルの過去採寸データ（比較用） ---
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

    # --- 📅 本日登録データ一覧 ---
    st.markdown("### 📅 本日登録した採寸データ一覧")
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
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

        selected_brands = st.multiselect("🔸 ブランドを選択", sorted(combined_df["ブランド"].dropna().unique()))

        if selected_brands:
            filtered_df = combined_df[combined_df["ブランド"].isin(selected_brands)]
        else:
            filtered_df = combined_df

        pid_options = sorted(filtered_df["商品管理番号"].dropna().unique())
        size_options = sorted(filtered_df["サイズ"].dropna().unique())
        category_options = sorted(filtered_df["カテゴリ"].dropna().unique())

        selected_pids = st.multiselect("🔹 管理番号を選択", pid_options)
        selected_sizes = st.multiselect("🔺 サイズを選択", size_options)
        keyword = st.text_input("🔍 キーワードで検索（商品名、管理番号など）")
        category_filter = st.selectbox("📂 カテゴリで表示項目を絞る", ["すべて表示"] + category_options)

        df = filtered_df.copy()
        if selected_pids:
            df = df[df["商品管理番号"].isin(selected_pids)]
        if selected_sizes:
            df = df[df["サイズ"].isin(selected_sizes)]
        if keyword:
            df = df[df.apply(lambda row: keyword.lower() in str(row.values).lower(), axis=1)]
        if category_filter != "すべて表示":
            df = df[df["カテゴリ"] == category_filter]

        base_cols = ["日付", "商品管理番号", "ブランド", "カテゴリ", "商品名", "カラー", "サイズ"]
        ideal_cols = ideal_order_dict.get(category_filter, [])
        ordered_cols = base_cols + [c for c in ideal_cols if c in df.columns] + \
                       [c for c in df.columns if c not in base_cols + ideal_cols]
        df = df[ordered_cols]
        df = df.loc[:, ~(df.isna() | (df == "")).all(axis=0)]

        st.write(f"🔍 検索結果: {len(df)} 件")
        st.dataframe(df, use_container_width=True)

        if not df.empty:
            to_excel = io.BytesIO()
            with pd.ExcelWriter(to_excel, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="採寸結果")
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

        def expand_sizes(df_in):
            df2 = df_in.copy()
            df2["サイズ"] = df2["サイズ"].astype(str).str.replace("、", ",").str.split(",")
            df2["サイズ"] = df2["サイズ"].apply(lambda x: [s.strip() for s in x])
            return df2.explode("サイズ").reset_index(drop=True)

        expanded_df = expand_sizes(df)
        st.subheader("展開後（1サイズ1行）")
        st.dataframe(expanded_df)

        if st.button("Googleスプレッドシートに保存"):
            try:
                product_sheet = spreadsheet.worksheet("商品マスタ")
                existing = pd.DataFrame(product_sheet.get_all_records())
                merged = pd.concat([existing, expanded_df], ignore_index=True).drop_duplicates()
                product_sheet.clear()
                product_sheet.update([merged.columns.tolist()] + merged.values.tolist())
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
            prod_df = pd.read_excel(uploaded_file, sheet_name="商品マスタ")
            std_df = pd.read_excel(uploaded_file, sheet_name="基準ID")
            merged = pd.merge(prod_df, std_df, on="基準ID", how="inner")
            merged = merged.dropna(axis=1, how="all")
            merged["日付"] = datetime.now().strftime("%Y-%m-%d")
            st.markdown("### 👀 アップロード内容（統合済）")
            st.dataframe(merged, use_container_width=True)

            if st.button("Googleスプレッドシートに保存"):
                try:
                    sheet = spreadsheet.worksheet("基準データ")
                except gspread.exceptions.WorksheetNotFound:
                    sheet = spreadsheet.add_worksheet(title="基準データ", rows="100", cols="50")
                exist = pd.DataFrame(sheet.get_all_records())
                if not exist.empty:
                    keys = set(zip(merged["商品管理番号"], merged["サイズ"]))
                    exist = exist[~exist.apply(lambda r: (r["商品管理番号"], r["サイズ"]) in keys, axis=1)]
                final = pd.concat([exist, merged], ignore_index=True)
                sheet.clear()
                sheet.update([final.columns.tolist()] + final.fillna("").values.tolist())
                st.success("✅ 基準データを保存しました！")
        except Exception as e:
            st.error(f"読み込みエラー: {e}")

# ---------------------
# 採寸ヘッダー初期化ページ
# ---------------------
elif page == "採寸ヘッダー初期化":
    st.title("📋 採寸シート ヘッダー初期化（※データは残る）")
    headers = ["日付","商品管理番号","ブランド","カテゴリ","商品名","カラー","サイズ",
               "肩幅","胸幅","胴囲","袖丈","着丈","襟高","ウエスト","股上","股下",
               "ワタリ","裾幅","全長","最大幅","横幅","頭周り","ツバ","高さ","裄丈","ベルト幅","前丈","後丈"]
    def reinit(name):
        try:
            ws = spreadsheet.worksheet(name)
            rows = ws.get_all_values()[1:]
            ws.clear()
            ws.append_row(headers)
            if rows:
                norm = [r + [''] * (len(headers) - len(r)) for r in rows]
                ws.append_rows(norm)
            st.success(f"✅ 『{name}』のヘッダーを初期化しました！")
        except Exception as e:
            st.error(f"処理エラー: {e}")

    if st.button("🧼 採寸結果シートの初期化"):
        reinit("採寸結果")
    if st.button("🧼 採寸アーカイブシートの初期化"):
        reinit("採寸アーカイブ")

# ---------------------
# アーカイブ管理ページ（30日超→移動）
# ---------------------
elif page == "アーカイブ管理":
    st.title("🗃️ 採寸データのアーカイブ管理")
    def parse_date(s):
        for f in ("%Y-%m-%d","%Y/%m/%d","%Y.%m.%d"):
            try:
                return datetime.strptime(s.strip(), f)
            except:
                pass
        return None

    if st.button("📦 30日以上前の採寸結果をアーカイブに移動"):
        try:
            res = spreadsheet.worksheet("採寸結果")
            arc = spreadsheet.worksheet("採寸アーカイブ")
            vals = res.get_all_values()
            hdr, rows = vals[0], vals[1:]
            old, recent = [], []
            today = datetime.now()
            for r in rows:
                r += [''] * (len(hdr) - len(r))
                d = parse_date(r[0])
                (old if d and (today - d).days > 30 else recent).append(r)
            if old:
                if not arc.get_all_values():
                    arc.append_row(hdr)
                arc.append_rows(old)
            res.clear()
            res.append_row(hdr)
            if recent:
                res.append_rows(recent)
            st.success(f"✅ {len(old)}件をアーカイブに移動しました！")
        except Exception as e:
            st.error(f"エラー: {e}")
