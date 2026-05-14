import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import uuid

# --- КОНФИГУРАЦИЯ ---
# ВСТАВЬ СВОЮ ССЫЛКУ МЕЖДУ КАВЫЧЕК НИЖЕ
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1cCR0T34J6vjr_RvNrnR6hDoz5G83jSwuezPkNGW7_IY/edit?usp=sharing"

CATEGORIES = ["Новый Свет", "Европа", "Игристые", "Крепкие напитки"]
SHOPS = ["Лента", "Метро", "Магнит", "Перекресток", "О'кей", "Красное и Белое"]

# --- ФУНКЦИИ ОБЛАЧНОГО ХРАНЕНИЯ ---
def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        # Читаем данные из облака
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
        df = df.dropna(how="all")
        
        data = df.to_dict(orient="records")
        for item in data:
            # Восстанавливаем карточки конкурентов из JSON-строки
            if isinstance(item.get('competitors'), str) and item['competitors']:
                try:
                    item['competitors'] = json.loads(item['competitors'])
                except:
                    item['competitors'] = []
            else:
                item['competitors'] = []
        return data
    except Exception:
        return []

def save_data(data):
    conn = st.connection("gsheets", type=GSheetsConnection)
    save_list = []
    for item in data:
        temp = item.copy()
        # Запаковываем все карточки в одну строку для хранения
        temp['competitors'] = json.dumps(item['competitors'], ensure_ascii=False)
        save_list.append(temp)
    
    df = pd.DataFrame(save_list)
    # Отправляем в Google
    conn.update(spreadsheet=SPREADSHEET_URL, data=df)
    st.cache_data.clear()

# --- ИНИЦИАЛИЗАЦИЯ ---
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

st.set_page_config(layout="wide", page_title="Wine Intelligence Cloud")

# --- СТРАНИЦА: ТАБЛИЦА ---
if st.session_state.page == "table":
    st.title("🍷 Облачный мониторинг цен (Оренбург)")
    
    col_h1, col_h2 = st.columns([6, 1])
    with col_h2:
        if st.button("➕ Добавить вино", use_container_width=True):
            go_to_edit()
            st.rerun()

    if not st.session_state.wines:
        st.info("Данных нет. Проверьте ссылку на таблицу или добавьте вино.")
    else:
        f1, f2 = st.columns(2)
        with f1: search = st.text_input("🔍 Поиск", "")
        with f2: f_cat = st.multiselect("Категория", CATEGORIES, default=CATEGORIES)

        table_rows = []
        for w in st.session_state.wines:
            if (not search or search.lower() in str(w.get('name','')).lower()) and (w.get('category') in f_cat):
                row = {
                    "ID": w['id'],
                    "Название": w['name'],
                    "Категория": w['category'],
                    "Наша Рег.": w['our_reg'],
                    "Наша Итог.": w['our_disc'],
                    "% Скидки": f"{get_perc(w['our_reg'], w['our_disc'])}%"
                }
                for shop in SHOPS:
                    comp = next((c for c in w['competitors'] if c['shop'] == shop), None)
                    row[shop] = comp['disc'] if comp and comp.get('in_stock') else (None if not comp else "Нет в наличии")
                table_rows.append(row)

        if table_rows:
            df = pd.DataFrame(table_rows)
            column_settings = {shop: st.column_config.NumberColumn(format="%d") for shop in SHOPS}
            column_settings.update({"ID": None, "Наша Рег.": st.column_config.NumberColumn(format="%d"), "Наша Итог.": st.column_config.NumberColumn(format="%d")})

            styled_df = df.drop(columns=['ID']).style.format(precision=0, na_rep="-").apply(highlight_min_max, axis=1)
            
            st.caption("💡 Кликни на строку, чтобы открыть полную карточку")
            event = st.dataframe(styled_df, use_container_width=True, height=500, on_select="rerun", selection_mode="single-row")

            if event and event.get("selection", {}).get("rows"):
                idx = event["selection"]["rows"][0]
                go_to_edit(df.iloc[idx]["ID"])
                st.rerun()

# --- СТРАНИЦА: КАРТОЧКА ---
elif st.session_state.page == "edit":
    wine = st.session_state.current_wine
    st.title(f"📝 Карточка: {wine['name'] or 'Новое вино'}")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            wine['name'] = st.text_input("Название*", value=wine['name'])
            wine['category'] = st.selectbox("Категория*", CATEGORIES, index=CATEGORIES.index(wine['category']))
        with c2:
            wine['our_reg'] = st.number_input("Верхняя цена*", value=int(wine['our_reg']), min_value=0)
            wine['our_disc'] = st.number_input("Цена со скидкой*", value=int(wine['our_disc']), min_value=0)

    st.subheader("🛒 Цены конкурентов")
    used = [c['shop'] for c in wine['competitors']]
    avail = [s for s in SHOPS if s not in used]
    if avail:
        new_s = st.selectbox("Добавить конкурента:", [""] + avail)
        if new_s:
            wine['competitors'].append({"shop": new_s, "reg": 0, "disc": 0, "in_stock": True})
            st.rerun()

    for i, comp in enumerate(wine['competitors']):
        with st.expander(f"📍 {comp['shop']}", expanded=True):
            cc1, cc2, cc3, cc4 = st.columns([2, 2, 2, 1])
            with cc1: comp['reg'] = st.number_input(f"Рег. цена ({comp['shop']})", value=int(comp['reg']), key=f"r_{comp['shop']}")
            with cc2: comp['disc'] = st.number_input(f"Скидка ({comp['shop']})", value=int(comp['disc']), key=f"d_{comp['shop']}")
            with cc3: comp['in_stock'] = st.toggle("В наличии", value=comp['in_stock'], key=f"s_{comp['shop']}")
            with cc4: 
                if st.button("🗑️", key=f"del_{comp['shop']}"):
                    wine['competitors'].pop(i)
                    st.rerun()

    st.divider()
    b1, b2, b3 = st.columns([2, 2, 6])
    with b1:
        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if not wine['name'] or wine['our_reg'] <= 0:
                st.error("Ошибка заполнения!")
            else:
                idx = next((i for i, w in enumerate(st.session_state.wines) if w['id'] == wine['id']), None)
                if idx is not None: st.session_state.wines[idx] = wine
                else: st.session_state.wines.append(wine)
                save_data(st.session_state.wines)
                st.session_state.page = "table"
                st.rerun()
    with b2:
        if st.button("🔙 Отмена", use_container_width=True):
            st.session_state.page = "table"
            st.rerun()
    with b3:
        if st.button("🗑️ Удалить всё вино", type="secondary"):
            st.session_state.wines = [w for w in st.session_state.wines if w['id'] != wine['id']]
            save_data(st.session_state.wines)
            st.session_state.page = "table"
            st.rerun()
