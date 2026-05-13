import streamlit as st
import pandas as pd
import json
import os
import uuid

# --- КОНФИГУРАЦИЯ ---
DB_FILE = "wine_db.json"
CATEGORIES = ["Новый Свет", "Европа", "Игристые", "Крепкие напитки"]
SHOPS = ["Лента", "Метро", "Магнит", "Перекресток", "О'кей", "Красное и Белое"]

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Инициализация базы
if 'wines' not in st.session_state:
    st.session_state.wines = load_data()
if 'edit_id' not in st.session_state:
    st.session_state.edit_id = None

# --- ФУНКЦИИ ПОДСВЕТКИ ---
def highlight_min_max(s):
    # Оставляем только числовые значения цен
    numeric_values = pd.to_numeric(s, errors='coerce').dropna()
    if numeric_values.empty:
        return ['' for _ in s]
    
    is_min = s == numeric_values.min()
    is_max = s == numeric_values.max()
    
    styles = []
    for m, x in zip(is_min, is_max):
        if m: styles.append('background-color: #d4edda; color: #155724') # Зеленый
        elif x: styles.append('background-color: #f8d7da; color: #721c24') # Красный
        else: styles.append('')
    return styles

# --- ИНТЕРФЕЙС ---
st.set_page_config(layout="wide", page_title="Wine Intelligence")

st.title("🍷 Wine Intelligence System")

# Боковое меню для выбора режима
st.sidebar.header("Управление")
mode = st.sidebar.radio("Режим:", ["Просмотр таблицы", "Добавить новое вино"])

# Если выбрано вино для редактирования, переключаем режим
if st.session_state.edit_id:
    mode = "Редактировать"

# --- РЕЖИМ: ТАБЛИЦА ---
if mode == "Просмотр таблицы":
    if not st.session_state.wines:
        st.info("База пуста. Добавьте первое вино.")
    else:
        # Фильтры
        st.subheader("📊 Мониторинг цен")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            sel_cat = st.multiselect("Категории:", CATEGORIES, default=CATEGORIES)
        
        # Подготовка DF
        rows = []
        for w in st.session_state.wines:
            if w['category'] in sel_cat:
                res = {
                    "Код": w['id'][:8],
                    "Название": w['name'],
                    "Категория": w['category'],
                    "Наша Рег.": w['our_reg'],
                    "Наша Итог.": w['our_disc'],
                    "% Скидки": f"{round((1 - w['our_disc']/w['our_reg'])*100, 1)}%" if w['our_reg'] > 0 else "0%"
                }
                # Добавляем цены конкурентов
                for shop in SHOPS:
                    comp = next((c for c in w['competitors'] if c['shop'] == shop), None)
                    if comp:
                        res[shop] = comp['disc'] if comp['in_stock'] else "Нет в наличии"
                    else:
                        res[shop] = "-"
                rows.append(res)

        df = pd.DataFrame(rows)
        
        # Инструкция для редактирования
        st.caption("Для редактирования выберите Код вина в выпадающем списке ниже.")
        target_edit = st.selectbox("Редактировать позицию:", [""] + [w['id'][:8] for w in st.session_state.wines])
        if target_edit:
            st.session_state.edit_id = next(w['id'] for w in st.session_state.wines if w['id'].startswith(target_edit))
            st.rerun()

        # Отображение таблицы с подсветкой
        styled_df = df.style.apply(highlight_min_max, axis=1, subset=[c for c in df.columns if c not in ["Код", "Название", "Категория", "% Скидки"]])
        st.dataframe(styled_df, use_container_width=True, height=500)

# --- РЕЖИМ: КАРТОЧКА (ДОБАВЛЕНИЕ / РЕДАКТИРОВАНИЕ) ---
if mode in ["Добавить новое вино", "Редактировать"]:
    is_edit = mode == "Редактировать"
    st.header("📝 Карточка товара" if not is_edit else f"📝 Редактирование: {st.session_state.edit_id[:8]}")
    
    # Загружаем данные если редактируем
    if is_edit:
        wine_data = next(w for w in st.session_state.wines if w['id'] == st.session_state.edit_id)
    else:
        wine_data = {"id": str(uuid.uuid4()), "name": "", "category": CATEGORIES[0], "our_reg": 0, "our_disc": 0, "competitors": []}

    with st.expander("Основная информация", expanded=True):
        name = st.text_input("Название вина*", value=wine_data['name'])
        cat = st.selectbox("Категория*", CATEGORIES, index=CATEGORIES.index(wine_data['category']))
        c1, c2 = st.columns(2)
        with c1:
            o_reg = st.number_input("Наша верхняя цена*", value=wine_data['our_reg'], min_value=0)
        with c2:
            o_disc = st.number_input("Наша цена со скидкой*", value=wine_data['our_disc'], min_value=0)

    st.subheader("Конкуренты")
    # Список текущих конкурентов в карточке
    current_comps = wine_data['competitors']
    
    # Кнопка добавления нового конкурента
    available_shops = [s for s in SHOPS if s not in [c['shop'] for c in current_comps]]
    if available_shops:
        new_comp_shop = st.selectbox("Добавить конкурента:", [""] + available_shops)
        if new_comp_shop:
            current_comps.append({"shop": new_comp_shop, "reg": 0, "disc": 0, "in_stock": True})
            st.rerun()

    # Отображение полей конкурентов
    for i, c in enumerate(current_comps):
        with st.container(border=True):
            cols = st.columns([2, 2, 2, 1, 1])
            with cols[0]:
                st.write(f"**{c['shop']}**")
            with cols[1]:
                c['reg'] = st.number_input(f"Верхняя ({c['shop']})", value=c['reg'], key=f"reg_{c['shop']}")
            with cols[2]:
                c['disc'] = st.number_input(f"Со скидкой ({c['shop']})", value=c['disc'], key=f"disc_{c['shop']}")
            with cols[3]:
                c['in_stock'] = st.toggle("Наличие", value=c['in_stock'], key=f"stock_{c['shop']}")
            with cols[4]:
                if st.button("❌", key=f"del_{c['shop']}"):
                    current_comps.pop(i)
                    st.rerun()

    # Кнопки действий
    st.divider()
    b1, b2, b3 = st.columns([2, 2, 5])
    
    with b1:
        if st.button("💾 Сохранить карточку", type="primary"):
            if not name or o_reg <= 0 or o_disc <= 0:
                st.error("Заполните название и цены!")
            else:
                new_wine = {
                    "id": wine_data['id'],
                    "name": name,
                    "category": cat,
                    "our_reg": o_reg,
                    "our_disc": o_disc,
                    "competitors": current_comps
                }
                if is_edit:
                    st.session_state.wines = [new_wine if w['id'] == wine_data['id'] else w for w in st.session_state.wines]
                else:
                    st.session_state.wines.append(new_wine)
                
                save_data(st.session_state.wines)
                st.session_state.edit_id = None
                st.success("Данные сохранены!")
                st.rerun()
    
    with b2:
        if is_edit:
            if st.button("🗑️ Удалить вино полностью"):
                st.session_state.wines = [w for w in st.session_state.wines if w['id'] != wine_data['id']]
                save_data(st.session_state.wines)
                st.session_state.edit_id = None
                st.rerun()
        if st.button("Отмена"):
            st.session_state.edit_id = None
            st.rerun()
