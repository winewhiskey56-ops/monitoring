### Полный код `app.py`

```python
import streamlit as st
import pandas as pd
import json
import uuid
import base64
from github import Github

# --- КОНФИГУРАЦИЯ GITHUB ---
REPO_NAME = "winewhiskey56-ops/monitoring"
FILE_PATH = "wine_db.json"
# Токен берем из секретов Streamlit
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
        st.warning(f"База еще не создана или ошибка доступа. Начнем с чистого листа.")
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_perc(reg, disc):
    return round((1 - disc / reg) * 100, 1) if reg > 0 else 0

def highlight_min_max(row):
    """Подсветка лучшей (зеленой) и худшей (красной) цены"""
    price_cols = [c for c in row.index if c == "Наша Итог." or c in SHOPS]
    vals = {col: row[col] for col in price_cols if isinstance(row[col], (int, float)) and row[col] > 0}
    
    styles = ['' for _ in row]
    if vals:
        min_v = min(vals.values())
        max_v = max(vals.values())
        for i, col in enumerate(row.index):
            if col in vals:
                if vals[col] == min_v:
                    styles[i] = 'background-color: #d4edda; color: #155724; font-weight: bold'
                elif vals[col] == max_v:
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

# --- ОСНОВНОЙ ИНТЕРФЕЙС ---
st.set_page_config(layout="wide", page_title="Wine Monitoring System")

# --- СТРАНИЦА: ТАБЛИЦА ---
if st.session_state.page == "table":
    st.title("🍷 Мониторинг цен (Оренбург)")
    
    c_h1, c_h2 = st.columns([6, 1])
    with c_h2:
        if st.button("➕ Добавить вино", use_container_width=True, type="primary"):
            go_to_edit()
            st.rerun()

    if not st.session_state.wines:
        st.info("База пуста. Добавьте первое вино, чтобы начать мониторинг.")
    else:
        f1, f2 = st.columns(2)
        with f1: search = st.text_input("🔍 Поиск по названию", "")
        with f2: f_cat = st.multiselect("Категории", CATEGORIES, default=CATEGORIES)

        table_rows = []
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
                        row[shop] = comp['disc'] if comp['in_stock'] else "Нет"
                    else:
                        row[shop] = None
                table_rows.append(row)

        if table_rows:
            df = pd.DataFrame(table_rows)
            
            # Конфигурация колонок (убираем лишние нули .0000)
            col_cfg = {shop: st.column_config.NumberColumn(format="%d") for shop in SHOPS}
            col_cfg.update({
                "ID": None,
                "Наша Рег.": st.column_config.NumberColumn(format="%d"),
                "Наша Итог.": st.column_config.NumberColumn(format="%d")
            })

            # Стилизация и вывод
            styled_df = df.style.format(precision=0, na_rep="-").apply(highlight_min_max, axis=1)
            
            st.caption("💡 Кликни на строку, чтобы отредактировать цены")
            event = st.dataframe(
                styled_df,
                use_container_width=True,
                height=600,
                on_select="rerun",
                selection_mode="single-row",
                column_config=col_cfg
            )

            if event and event.get("selection", {}).get("rows"):
                row_idx = event["selection"]["rows"][0]
                go_to_edit(df.iloc[row_idx]["ID"])
                st.rerun()

# --- СТРАНИЦА: РЕДАКТИРОВАНИЕ (КАРТОЧКА) ---
elif st.session_state.page == "edit":
    wine = st.session_state.current_wine
    st.title(f"📝 {wine['name'] or 'Новая позиция'}")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            wine['name'] = st.text_input("Название вина*", value=wine['name'])
            wine['category'] = st.selectbox("Категория*", CATEGORIES, index=CATEGORIES.index(wine['category']))
        with c2:
            wine['our_reg'] = st.number_input("Наша регулярная цена*", value=int(wine['our_reg']), min_value=0)
            wine['our_disc'] = st.number_input("Наша цена со скидкой*", value=int(wine['our_disc']), min_value=0)
            st.metric("Наша скидка", f"{get_perc(wine['our_reg'], wine['our_disc'])}%")

    st.subheader("🛒 Цены конкурентов")
    used_shops = [c['shop'] for c in wine['competitors']]
    avail_shops = [s for s in SHOPS if s not in used_shops]
    
    if avail_shops:
        new_shop = st.selectbox("Добавить магазин:", [""] + avail_shops)
        if new_shop:
            wine['competitors'].append({"shop": new_shop, "reg": 0, "disc": 0, "in_stock": True})
            st.rerun()

    for i, comp in enumerate(wine['competitors']):
        with st.expander(f"📍 {comp['shop']}", expanded=True):
            cc1, cc2, cc3, cc4 = st.columns([2, 2, 2, 1])
            with cc1: comp['reg'] = st.number_input(f"Рег. цена ({comp['shop']})", value=int(comp['reg']), key=f"r_{comp['shop']}")
            with cc2: comp['disc'] = st.number_input(f"Цена скидка ({comp['shop']})", value=int(comp['disc']), key=f"d_{comp['shop']}")
            with cc3: comp['in_stock'] = st.toggle("В наличии", value=comp['in_stock'], key=f"s_{comp['shop']}")
            with cc4:
                if st.button("🗑️", key=f"del_{comp['shop']}"):
                    wine['competitors'].pop(i)
                    st.rerun()

    st.divider()
    b1, b2, b3 = st.columns([2, 2, 6])
    with b1:
        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if not wine['name']:
                st.error("Укажите название!")
            else:
                # Обновляем или добавляем в список
                idx = next((i for i, w in enumerate(st.session_state.wines) if w['id'] == wine['id']), None)
                if idx is not None:
                    st.session_state.wines[idx] = wine
                else:
                    st.session_state.wines.append(wine)
                
                save_data(st.session_state.wines)
                st.session_state.page = "table"
                st.rerun()
    with b2:
        if st.button("🔙 Отмена", use_container_width=True):
            st.session_state.page = "table"
            st.rerun()
    with b3:
        if st.button("🗑️ Удалить всё вино из базы", type="secondary"):
            st.session_state.wines = [w for w in st.session_state.wines if w['id'] != wine['id']]
            save_data(st.session_state.wines)
            st.session_state.page = "table"
            st.rerun()
