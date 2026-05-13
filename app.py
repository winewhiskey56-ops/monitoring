import streamlit as st
import pandas as pd
import json
import os
import uuid

# --- КОНФИГУРАЦИЯ ---
DB_FILE = "wine_monitoring_db.json"
CATEGORIES = ["Новый Свет", "Европа", "Игристые", "Крепкие напитки"]
SHOPS = ["Лента", "Метро", "Магнит", "Перекресток", "О'кей", "Красное и Белое"]

# --- ФУНКЦИИ РАБОТЫ С ДАННЫМИ ---
def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Базовая валидация структуры
                for item in data:
                    item.setdefault('id', str(uuid.uuid4()))
                    item.setdefault('name', 'Без названия')
                    item.setdefault('category', CATEGORIES[0])
                    item.setdefault('our_reg', 0)
                    item.setdefault('our_disc', 0)
                    item.setdefault('competitors', [])
                return data
        except:
            return []
    return []

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Инициализация состояний
if 'wines' not in st.session_state:
    st.session_state.wines = load_data()
if 'page' not in st.session_state:
    st.session_state.page = "table"
if 'current_wine' not in st.session_state:
    st.session_state.current_wine = None

# --- МАТЕМАТИКА ---
def get_perc(reg, disc):
    if reg > 0:
        return round((1 - disc / reg) * 100, 1)
    return 0

# --- СТИЛИЗАЦИЯ ---
def highlight_min_max(row):
    # Оставляем только те колонки, где могут быть цены (Начиная с 'Наша Итог.' и колонки магазинов)
    # Исключаем строки, где "Нет в наличии"
    price_cols = [c for c in row.index if c == "Наша Итог." or c in SHOPS]
    vals = {}
    
    for col in price_cols:
        val = row[col]
        if isinstance(val, (int, float)) and val > 0:
            vals[col] = val
    
    styles = ['' for _ in row]
    if not vals:
        return styles
    
    min_col = min(vals, key=vals.get)
    max_col = max(vals, key=vals.get)
    
    for i, col in enumerate(row.index):
        if col == min_col:
            styles[i] = 'background-color: #d4edda; color: #155724; font-weight: bold'
        elif col == max_col:
            styles[i] = 'background-color: #f8d7da; color: #721c24; font-weight: bold'
    return styles

# --- ЛОГИКА ПЕРЕКЛЮЧЕНИЯ СТРАНИЦ ---
def go_to_edit(wine_id=None):
    if wine_id:
        wine = next((w for w in st.session_state.wines if w['id'] == wine_id), None)
        st.session_state.current_wine = json.loads(json.dumps(wine)) # Глубокое копирование
    else:
        st.session_state.current_wine = {
            "id": str(uuid.uuid4()), "name": "", "category": CATEGORIES[0],
            "our_reg": 0, "our_disc": 0, "competitors": []
        }
    st.session_state.page = "edit"

def go_to_table():
    st.session_state.page = "table"
    st.session_state.current_wine = None

# --- ИНТЕРФЕЙС ---
st.set_page_config(layout="wide", page_title="Wine Admin")

# --- СТРАНИЦА: ТАБЛИЦА ---
if st.session_state.page == "table":
    st.title("📊 Мониторинг цен Оренбург")
    
    col_h1, col_h2 = st.columns([6, 1])
    with col_h2:
        if st.button("➕ Добавить вино", use_container_width=True):
            go_to_edit()
            st.rerun()

    if not st.session_state.wines:
        st.info("В базе пока нет товаров.")
    else:
        # Фильтры и поиск
        f_col1, f_col2 = st.columns([2, 2])
        with f_col1:
            search = st.text_input("🔍 Поиск по названию", "")
        with f_col2:
            f_cat = st.multiselect("Категория", CATEGORIES, default=CATEGORIES)

        # Сбор данных для таблицы
        table_rows = []
        for w in st.session_state.wines:
            if (not search or search.lower() in w['name'].lower()) and (w['category'] in f_cat):
                row = {
                    "ID": w['id'],
                    "Код": w['id'][:8],
                    "Название": w['name'],
                    "Категория": w['category'],
                    "Наша Рег.": w['our_reg'],
                    "Наша Итог.": w['our_disc'],
                    "% Скидки": f"{get_perc(w['our_reg'], w['our_disc'])}%"
                }
                for shop in SHOPS:
                    comp = next((c for c in w['competitors'] if c['shop'] == shop), None)
                    if comp:
                        row[shop] = comp['disc'] if comp['in_stock'] else "Нет в наличии"
                    else:
                        row[shop] = None
                table_rows.append(row)

        if table_rows:
            df = pd.DataFrame(table_rows)
            # Отображение
            st.write("### Сводная таблица")
            st.caption("Нажмите на Код вина ниже, чтобы изменить данные")
            
            # Выбор вина для редактирования
            selected_id_short = st.selectbox("Выбрать вино для редактирования:", [""] + [r['Код'] for r in table_rows])
            if selected_id_short:
                full_id = next(r['ID'] for r in table_rows if r['Код'] == selected_id_short)
                go_to_edit(full_id)
                st.rerun()

            styled_df = df.drop(columns=['ID']).style.apply(highlight_min_max, axis=1)
            st.dataframe(styled_df, use_container_width=True, height=600)
        else:
            st.warning("Ничего не найдено по вашим фильтрам.")

# --- СТРАНИЦА: КАРТОЧКА ---
elif st.session_state.page == "edit":
    wine = st.session_state.current_wine
    st.title(f"📝 Карточка: {wine['name'] or 'Новое вино'}")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            wine['name'] = st.text_input("Название вина*", value=wine['name'])
            wine['category'] = st.selectbox("Категория*", CATEGORIES, index=CATEGORIES.index(wine['category']))
        with c2:
            wine['our_reg'] = st.number_input("Наша верхняя цена*", value=wine['our_reg'], min_value=0)
            wine['our_disc'] = st.number_input("Наша цена со скидкой*", value=wine['our_disc'], min_value=0)
            st.metric("Наша скидка", f"{get_perc(wine['our_reg'], wine['our_disc'])}%")

    st.subheader("🛒 Сравнение с конкурентами")
    
    # Добавление конкурента
    used_shops = [c['shop'] for c in wine['competitors']]
    available_shops = [s for s in SHOPS if s not in used_shops]
    
    if available_shops:
        new_shop = st.selectbox("Выберите конкурента для добавления:", [""] + available_shops)
        if new_shop:
            wine['competitors'].append({"shop": new_shop, "reg": 0, "disc": 0, "in_stock": True})
            st.rerun()

    # Поля конкурентов
    for i, comp in enumerate(wine['competitors']):
        with st.expander(f"📍 {comp['shop']}", expanded=True):
            cc1, cc2, cc3, cc4 = st.columns([2, 2, 2, 1])
            with cc1:
                comp['reg'] = st.number_input(f"Рег. цена ({comp['shop']})", value=comp['reg'], key=f"r_{comp['shop']}")
            with cc2:
                comp['disc'] = st.number_input(f"Со скидкой ({comp['shop']})", value=comp['disc'], key=f"d_{comp['shop']}")
            with cc3:
                st.write(f"Скидка: {get_perc(comp['reg'], comp['disc'])}%")
                comp['in_stock'] = st.toggle("В наличии", value=comp['in_stock'], key=f"s_{comp['shop']}")
            with cc4:
                if st.button("🗑️", key=f"del_{comp['shop']}"):
                    wine['competitors'].pop(i)
                    st.rerun()

    # Кнопки сохранения/удаления
    st.divider()
    b1, b2, b3, b4 = st.columns([2, 2, 2, 4])
    with b1:
        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if not wine['name'] or wine['our_reg'] <= 0:
                st.error("Заполните название и цены!")
            else:
                # Обновляем в общем списке
                idx = next((i for i, w in enumerate(st.session_state.wines) if w['id'] == wine['id']), None)
                if idx is not None:
                    st.session_state.wines[idx] = wine
                else:
                    st.session_state.wines.append(wine)
                
                save_data(st.session_state.wines)
                go_to_table()
                st.rerun()
    with b2:
        if st.button("🔙 Отмена", use_container_width=True):
            go_to_table()
            st.rerun()
    with b3:
        if st.button("🗑️ Удалить вино", use_container_width=True):
            st.session_state.wines = [w for w in st.session_state.wines if w['id'] != wine['id']]
            save_data(st.session_state.wines)
            go_to_table()
            st.rerun()
