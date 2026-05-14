import streamlit as st
import pandas as pd
import json
import uuid
import base64
from github import Github

# --- КОНФИГУРАЦИЯ GITHUB ---
REPO_NAME = "winewhiskey56-ops/monitoring"
FILE_PATH = "wine_db.json"

try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
except:
    st.error("Критическая ошибка: GITHUB_TOKEN не найден в Secrets!")
    st.stop()

# --- КОНСТАНТЫ БИЗНЕСА ---
CATEGORIES = ["Новый Свет", "Европа", "Игристые", "Крепкие напитки"]
SHOPS = ["Лента", "Метро", "Магнит", "Перекресток", "О'кей", "Красное и Белое"]

# --- РАБОТА С ДАННЫМИ ЧЕРЕЗ GITHUB ---
def load_data():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file_content = repo.get_contents(FILE_PATH)
        decoded = base64.b64decode(file_content.content).decode('utf-8')
        return json.loads(decoded)
    except Exception as e:
        st.warning("База еще не создана. Начнем с чистого листа.")
        return []

def save_data(data):
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(FILE_PATH)
        new_json = json.dumps(data, ensure_ascii=False, indent=4)
        repo.update_file(
            path=FILE_PATH,
            message="Авто-обновление базы цен 🍷",
            content=new_json,
            sha=contents.sha
        )
        st.toast("Данные сохранены в GitHub!", icon="✅")
    except Exception as e:
        st.error(f"Ошибка сохранения: {e}")

# --- ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ ---
if 'wines' not in st.session_state:
    st.session_state.wines = load_data()
if 'page' not in st.session_state:
    st.session_state.page = "table"
if 'current_wine' not in st.session_state:
    st.session_state.current_wine = None

def get_perc(reg, disc):
    return round((1 - disc / reg) * 100, 1) if reg > 0 else 0

def highlight_min_max(row):
    price_cols = [c for c in row.index if c == "Наша Итог." or c in SHOPS]
    vals = {col: row[col] for col in price_cols if isinstance(row[col], (int, float)) and row[col] > 0}
    styles = ['' for _ in row]
    if vals:
        min_v, max_v = min(vals.values()), max(vals.values())
        for i, col in enumerate(row.index):
            if col in vals:
                if vals[col] == min_v: styles[i] = 'background-color: #d4edda; color: #155724; font-weight: bold'
                elif vals[col] == max_v: styles[i] = 'background-color: #f8d7da; color: #721c24; font-weight: bold'
    return styles

def go_to_edit(wine_id=None):
    if wine_id:
        wine = next((w for w in st.session_state.wines if w['id'] == wine_id), None)
        st.session_state.current_wine = json.loads(json.dumps(wine))
    else:
        st.session_state.current_wine = {
            "id": str(uuid.uuid4()), "name": "", "category": CATEGORIES[0],
            "our_reg": 0, "our_disc": 0, "competitors": []
        }
    st.session_state.page = "edit"

st.set_page_config(layout="wide", page_title="Wine Monitoring System")

if st.session_state.page == "table":
    st.title("🍷 Мониторинг цен (Оренбург)")
    c_h1, c_h2 = st.columns([6, 1])
    with c_h2:
        if st.button("➕ Добавить вино", use_container_width=True, type="primary"):
            go_to_edit()
            st.rerun()

    if not st.session_state.wines:
        st.info("База пуста.")
    else:
        f1, f2 = st.columns(2)
        with f1: search = st.text_input("🔍 Поиск", "")
        with f2: f_cat = st.multiselect("Категории", CATEGORIES, default=CATEGORIES)

        table_rows = []
        for w in st.session_state.wines:
            if (not search or search.lower() in w['name'].lower()) and (w['category'] in f_cat):
                row = {
                    "ID": w['id'], "Название": w['name'], "Категория": w['category'],
                    "Наша Рег.": w['our_reg'], "Наша Итог.": w['our_disc'],
                    "% Скидки": f"{get_perc(w['our_reg'], w['our_disc'])}%"
                }
                for shop in SHOPS:
                    comp = next((c for c in w['competitors'] if c['shop'] == shop), None)
                    row[shop] = comp['disc'] if comp and comp.get('in_stock') else (None if not comp else "Нет")
                table_rows.append(row)

        if table_rows:
            df = pd.DataFrame(table_rows)
            col_cfg = {shop: st.column_config.NumberColumn(format="%d") for shop in SHOPS}
            col_cfg.update({"ID": None, "
