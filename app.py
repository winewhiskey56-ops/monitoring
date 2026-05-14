import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json

# --- ПОДКЛЮЧЕНИЕ К ОБЛАКУ ---
# Вставь сюда ссылку на свою таблицу, которую скопировал в Шаге 1
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1cCR0T34J6vjr_RvNrnR6hDoz5G83jSwuezPkNGW7_IY/edit?usp=sharing"

def load_data():
    conn = st.connection("gsheets", type=GSheetsConnection)
    try:
        # Читаем данные. Мы берем запас в 1000 строк
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
        df = df.dropna(how="all")
        
        data = df.to_dict(orient="records")
        for item in data:
            # Превращаем текст обратно в список конкурентов
            if isinstance(item.get('competitors'), str):
                try:
                    item['competitors'] = json.loads(item['competitors'])
                except:
                    item['competitors'] = []
            else:
                item['competitors'] = []
        return data
    except Exception as e:
        st.error(f"Ошибка загрузки: {e}")
        return []

def save_data(data):
    conn = st.connection("gsheets", type=GSheetsConnection)
    # Готовим данные: превращаем списки конкурентов в текст для таблицы
    save_list = []
    for item in data:
        temp = item.copy()
        temp['competitors'] = json.dumps(item['competitors'], ensure_ascii=False)
        save_list.append(temp)
    
    df = pd.DataFrame(save_list)
    # Отправляем в Google
    conn.update(spreadsheet=SPREADSHEET_URL, data=df)
    # Очищаем кэш, чтобы сайт сразу увидел изменения
    st.cache_data.clear()

if 'wines' not in st.session_state:
    st.session_state.wines = load_data()
if 'page' not in st.session_state:
    st.session_state.page = "table"
if 'current_wine' not in st.session_state:
    st.session_state.current_wine = None

def get_perc(reg, disc):
    return round((1 - disc / reg) * 100, 1) if reg > 0 else 0

# Исправленная функция подсветки
def highlight_min_max(row):
    # Выбираем только колонки с ценами
    price_cols = [c for c in row.index if c == "Наша Итог." or c in SHOPS]
    # Преобразуем в числа, игнорируя текст "Нет в наличии"
    vals = {}
    for col in price_cols:
        val = row[col]
        if isinstance(val, (int, float)) and val > 0:
            vals[col] = val
    
    styles = ['' for _ in row]
    if vals:
        min_val = min(vals.values())
        max_val = max(vals.values())
        for i, col in enumerate(row.index):
            if col in vals:
                if vals[col] == min_val:
                    styles[i] = 'background-color: #d4edda; color: #155724; font-weight: bold'
                elif vals[col] == max_val:
                    styles[i] = 'background-color: #f8d7da; color: #721c24; font-weight: bold'
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

st.set_page_config(layout="wide", page_title="Wine Intelligence")

# --- СТРАНИЦА: ТАБЛИЦА ---
if st.session_state.page == "table":
    st.title("🍷 Мониторинг цен Оренбург")
    
    col_header, col_add = st.columns([6, 1])
    with col_add:
        if st.button("➕ Добавить вино", use_container_width=True):
            go_to_edit()
            st.rerun()

    if not st.session_state.wines:
        st.info("База пуста.")
    else:
        f1, f2 = st.columns(2)
        with f1: search = st.text_input("🔍 Поиск", "")
        with f2: f_cat = st.multiselect("Категория", CATEGORIES, default=CATEGORIES)

        data = []
        for w in st.session_state.wines:
            if (not search or search.lower() in w['name'].lower()) and (w['category'] in f_cat):
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
                    if comp:
                        row[shop] = comp['disc'] if comp['in_stock'] else "Нет в наличии"
                    else:
                        row[shop] = None
                data.append(row)

        if data:
            df = pd.DataFrame(data)
            
            # Настройки отображения колонок (убираем нули)
            column_settings = {shop: st.column_config.NumberColumn(format="%d") for shop in SHOPS}
            column_settings["ID"] = None
            column_settings["Наша Рег."] = st.column_config.NumberColumn(format="%d")
            column_settings["Наша Итог."] = st.column_config.NumberColumn(format="%d")

            # Форматируем таблицу (precision=0 убирает точки и нули после них)
            display_df = df.drop(columns=['ID'])
            styled_df = display_df.style.format(precision=0, na_rep="-").apply(highlight_min_max, axis=1)

            st.write("### Сводная таблица")
            st.caption("💡 Просто нажми на нужную строку, чтобы открыть карточку")

            # Вывод таблицы
            event = st.dataframe(
                styled_df,
                use_container_width=True,
                height=600,
                on_select="rerun",
                selection_mode="single-row",
                column_config=column_settings
            )

            # Проверка выбора строки
            if event and "selection" in event and event["selection"]["rows"]:
                row_idx = event["selection"]["rows"][0]
                selected_id = df.iloc[row_idx]["ID"]
                go_to_edit(selected_id)
                st.rerun()
        else:
            st.warning("Ничего не найдено.")

# --- СТРАНИЦА: КАРТОЧКА (Логика без изменений, чтобы не ломать рабочее) ---
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

    st.subheader("🛒 Конкуренты")
    used_shops = [c['shop'] for c in wine['competitors']]
    available_shops = [s for s in SHOPS if s not in used_shops]
    
    if available_shops:
        new_shop = st.selectbox("Добавить конкурента:", [""] + available_shops)
        if new_shop:
            wine['competitors'].append({"shop": new_shop, "reg": 0, "disc": 0, "in_stock": True})
            st.rerun()

    for i, comp in enumerate(wine['competitors']):
        with st.expander(f"📍 {comp['shop']}", expanded=True):
            cc1, cc2, cc3, cc4 = st.columns([2, 2, 2, 1])
            with cc1: comp['reg'] = st.number_input(f"Рег. цена ({comp['shop']})", value=comp['reg'], key=f"r_{comp['shop']}")
            with cc2: comp['disc'] = st.number_input(f"Со скидкой ({comp['shop']})", value=comp['disc'], key=f"d_{comp['shop']}")
            with cc3: 
                st.write(f"Скидка: {get_perc(comp['reg'], comp['disc'])}%")
                comp['in_stock'] = st.toggle("В наличии", value=comp['in_stock'], key=f"s_{comp['shop']}")
            with cc4:
                if st.button("🗑️", key=f"del_{comp['shop']}"):
                    wine['competitors'].pop(i)
                    st.rerun()

    st.divider()
    b1, b2, b3 = st.columns([2, 2, 6])
   with b1:
        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if not wine['name'] or wine['our_reg'] <= 0: 
                st.error("Заполни поля!")
            else:
                # Ищем, есть ли уже такое вино в базе
                idx = next((i for i, w in enumerate(st.session_state.wines) if w['id'] == wine['id']), None)
                if idx is not None: 
                    st.session_state.wines[idx] = wine
                else: 
                    st.session_state.wines.append(wine)
                
                # ВОТ ТУТ МАГИЯ: сохраняем ВЕСЬ список (вместе с карточками) в облако
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
