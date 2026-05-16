import streamlit as st
import pandas as pd
import json
import uuid
import base64
from github import Github
from datetime import datetime


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
STOCKS = ["1", "2", "3+"]

# --- РАБОТА С ДАННЫМИ ЧЕРЕЗ GITHUB ---
def load_data():
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file_content = repo.get_contents(FILE_PATH)
        decoded = base64.b64decode(file_content.content).decode('utf-8')
        data = json.loads(decoded)
        # Автоматически добавляем новые поля к старым записяям, чтобы не было ошибок
        for w in data:
            if 'purchase_price' not in w: w['purchase_price'] = 0
            if 'stock' not in w: w['stock'] = '3+'
            if 'history' not in w: w['history'] = []
        return data
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
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
        # Делаем глубокую копию, чтобы изменения не применялись до нажатия "Сохранить"
        st.session_state.current_wine = json.loads(json.dumps(wine))
    else:
        st.session_state.current_wine = {
            "id": str(uuid.uuid4()), "name": "", "category": CATEGORIES[0],
            "stock": "3+", "purchase_price": 0, "our_reg": 0, "our_disc": 0, 
            "competitors": [], "history": []
        }
    st.session_state.page = "edit"

# --- ДВИЖОК РЕКОМЕНДАЦИЙ ---
def generate_recommendation(wine):
    if wine.get('purchase_price', 0) <= 0 or wine['our_reg'] <= 0:
        return "⚠️ Для расчета рекомендаций заполните 'Закупочную стоимость' и 'Нашу Рег. цену'."
    
    pur_price = wine['purchase_price']
    min_retail_price = pur_price * 1.3
    
    active_comps = [c for c in wine['competitors'] if c['in_stock'] and c['disc'] > 0]
    
    if not active_comps:
         return "✅ **Вне конкуренции:** Конкурентов нет или товар у них отсутствует. Рекомендуется убрать скидку (0%)."
         
    cheapest = min(active_comps, key=lambda x: x['disc'])
    c_price = cheapest['disc']
    target = c_price * 1.1 # Наша идеальная цель
    
    # --- НОВАЯ ПРОВЕРКА: Если пользователь УЖЕ изменил цену ---
    current_disc_price = wine.get('our_disc', 0)
    if current_disc_price > 0 and current_disc_price <= target:
        if current_disc_price >= min_retail_price:
            return f"🟢 **Отличная цена:** Ваша текущая цена ({current_disc_price}₽) уже соответствует стратегии или бьёт цену конкурента ({c_price}₽) с учетом сервиса. Можно сохранять карточку!"
        else:
            return f"⚠️ **Внимание:** Вы установили цену ({current_disc_price}₽), которая бьёт конкурента, но она **ниже минимальной маржи** ({min_retail_price:.0f}₽). Вы работаете в убыток!"

    if target < min_retail_price:
        return f"🛑 **Капитуляция с честью:** У конкурента ({cheapest['shop']}) цена {c_price:.0f}₽. Наша целевая цена ({target:.0f}₽) падает ниже минимально допустимой розницы ({min_retail_price:.0f}₽). Не снижайте цену, делайте упор на сервис."
        
    if cheapest['disc'] == cheapest['reg']:
        return f"🎯 **Фиксированная цена:** Конкурент ({cheapest['shop']}) торгует без скидок по {c_price:.0f}₽. Поставьте у себя верхнюю цену около {target:.0f}₽ без скидки."
        
    discounts = [0, 10, 15, 20, 25, 30, 35, 40, 45]
    best_d = None
    for d in discounts:
        p = wine['our_reg'] * (1 - d/100.0)
        if p >= min_retail_price and p <= target:
            best_d = (d, p)
            break
            
    if best_d is not None:
         if best_d[0] == 0:
             return f"💡 **Снижение скидки:** Цены конкурентов позволяют продавать без скидки (0%) по {best_d[1]:.0f}₽ (Целевая: {target:.0f}₽)."
         else:
             return f"⚔️ **Борьба скидками:** Рекомендуемая скидка **{best_d[0]}%** (Ваша цена должна быть: {best_d[1]:.0f}₽). Целевая цена конкуренции: {target:.0f}₽."
             
    promo = []
    stock = wine.get('stock', '3+')
    if stock in ['2', '3+']:
         p_50 = wine['our_reg'] * 0.75
         if p_50 >= min_retail_price: promo.append("«-50% на вторую» (экв. скидки 25%)")
    if stock == '3+':
         p_11 = wine['our_reg'] * 0.666
         if p_11 >= min_retail_price: promo.append("«1+1=3» (экв. скидки 33%)")
              
    if promo:
         return "🎁 **Пакетные акции:** Обычные скидки слишком сильно режут маржу. Чтобы конкурировать, используйте объём:\n" + "\n".join([f"- {x}" for x in promo])
         
    return f"⚖️ Обычные скидки не достигают целевой цены {target:.0f}₽ без нарушения минимальной маржи. Отредактируйте 'Нашу Рег. цену' или продавайте без скидок."

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
            col_cfg.update({"ID": None, "Наша Рег.": st.column_config.NumberColumn(format="%d"), "Наша Итог.": st.column_config.NumberColumn(format="%d")})
            styled_df = df.style.format(precision=0, na_rep="-").apply(highlight_min_max, axis=1)
            event = st.dataframe(styled_df, use_container_width=True, height=600, on_select="rerun", selection_mode="single-row", column_config=col_cfg)
            if event and event.get("selection", {}).get("rows"):
                idx = event["selection"]["rows"][0]
                go_to_edit(df.iloc[idx]["ID"])
                st.rerun()

# --- СТРАНИЦА: РЕДАКТИРОВАНИЕ (КАРТОЧКА) ---
elif st.session_state.page == "edit":
    wine = st.session_state.current_wine
    st.title(f"📝 {wine['name'] or 'Новая позиция'}")
    
    with st.container(border=True):
        c1, c2, c3 = st.columns([1, 1, 1.5])
        with c1:
            wine['name'] = st.text_input("Название вина*", value=wine['name'])
            wine['category'] = st.selectbox("Категория*", CATEGORIES, index=CATEGORIES.index(wine['category']))
            wine['stock'] = st.radio("Остаток на складе", STOCKS, index=STOCKS.index(wine.get('stock', '3+')), horizontal=True)
            wine['purchase_price'] = st.number_input("Закупочная стоимость*", value=int(wine.get('purchase_price', 0)))
        with c2:
            wine['our_reg'] = st.number_input("Наша Рег. цена*", value=int(wine['our_reg']))
            wine['our_disc'] = st.number_input("Наша цена со скидкой*", value=int(wine['our_disc']))
            if wine['our_reg'] > 0:
                p = get_perc(wine['our_reg'], wine['our_disc'])
                margin = wine['our_reg'] - wine['our_disc'] - wine['purchase_price']
                st.info(f"Скидка: **{p}%** | Наценка (руб): **{margin}₽**")
        with c3:
            st.write("📈 **AI-Аналитика Цен**")
            if st.button("🤖 Получить рекомендацию", type="primary", use_container_width=True):
                rec = generate_recommendation(wine)
                st.success(rec)

    st.subheader("🛒 Конкуренты")
    used = [c['shop'] for c in wine['competitors']]
    avail = [s for s in SHOPS if s not in used]
    if avail:
        new_s = st.selectbox("Добавить магазин:", [""] + avail)
        if new_s:
            wine['competitors'].append({"shop": new_s, "reg": 0, "disc": 0, "in_stock": True})
            st.rerun()

    for i, comp in enumerate(wine['competitors']):
        with st.expander(f"📍 {comp['shop']}", expanded=True):
            cc1, cc2, cc3, cc4 = st.columns([2, 2, 2, 1])
            with cc1: comp['reg'] = st.number_input(f"Рег.", value=int(comp['reg']), key=f"r_{comp['shop']}")
            with cc2: comp['disc'] = st.number_input(f"Скидка", value=int(comp['disc']), key=f"d_{comp['shop']}")
            with cc3: 
                if comp['reg'] > 0:
                    cp = get_perc(comp['reg'], comp['disc'])
                    st.write(f"Скидка: **{cp}%**")
                comp['in_stock'] = st.toggle("В наличии", value=comp['in_stock'], key=f"s_{comp['shop']}")
            with cc4:
                if st.button("🗑️", key=f"del_{comp['shop']}"):
                    wine['competitors'].pop(i)
                    st.rerun()

    st.divider()
    
    # --- БЛОК ИСТОРИИ ---
    if wine.get('history'):
        with st.expander("📜 История изменений"):
            for entry in wine['history']:
                st.caption(f"🗓️ {entry['date']}")
                for ch in entry['changes']:
                    st.write(f"• {ch}")
                st.write("---")

    # --- СОХРАНЕНИЕ С ГЕНЕРАЦИЕЙ ИСТОРИИ ---
    b1, b2, b3 = st.columns([2, 2, 6])
    with b1:
        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if not wine['name']: st.error("Укажите название!")
            else:
                old_wine = next((w for w in st.session_state.wines if w['id'] == wine['id']), None)
                changes = []
                
                # Логика сравнения изменений
                if old_wine:
                    if old_wine['name'] != wine['name']: changes.append(f"Название: {old_wine['name']} -> {wine['name']}")
                    if old_wine['category'] != wine['category']: changes.append(f"Категория: {old_wine['category']} -> {wine['category']}")
                    if old_wine.get('stock') != wine['stock']: changes.append(f"Остаток: {old_wine.get('stock')} -> {wine['stock']}")
                    if old_wine.get('purchase_price') != wine['purchase_price']: changes.append(f"Закупка: {old_wine.get('purchase_price')} -> {wine['purchase_price']}")
                    if old_wine['our_reg'] != wine['our_reg']: changes.append(f"Наша Рег.: {old_wine['our_reg']} -> {wine['our_reg']}")
                    if old_wine['our_disc'] != wine['our_disc']: changes.append(f"Наша Скидка: {old_wine['our_disc']} -> {wine['our_disc']}")
                    
                    old_comps = {c['shop']: c for c in old_wine['competitors']}
                    new_comps = {c['shop']: c for c in wine['competitors']}
                    
                    for shop in new_comps:
                        if shop not in old_comps: changes.append(f"Добавлен конкурент: {shop}")
                        else:
                            oc, nc = old_comps[shop], new_comps[shop]
                            if oc['reg'] != nc['reg']: changes.append(f"{shop} (Рег): {oc['reg']} -> {nc['reg']}")
                            if oc['disc'] != nc['disc']: changes.append(f"{shop} (Скидка): {oc['disc']} -> {nc['disc']}")
                            if oc['in_stock'] != nc['in_stock']: changes.append(f"{shop} (Наличие): {oc['in_stock']} -> {nc['in_stock']}")
                    for shop in old_comps:
                        if shop not in new_comps: changes.append(f"Удален конкурент: {shop}")
                else:
                    changes.append("Карточка создана")

                # Если есть изменения, добавляем их в начало истории
                if changes:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    if 'history' not in wine: wine['history'] = []
                    wine['history'].insert(0, {"date": now, "changes": changes})

                idx = next((i for i, w in enumerate(st.session_state.wines) if w['id'] == wine['id']), None)
                if idx is not None: st.session_state.wines[idx] = wine
                else: st.session_state.wines.append(wine)
                save_data(st.session_state.wines)
                st.session_state.page = "table"; st.rerun()
    with b2:
        if st.button("🔙 Отмена", use_container_width=True):
            st.session_state.page = "table"; st.rerun()
    with b3:
        if st.button("🗑️ Удалить вино", type="secondary"):
            st.session_state.wines = [w for w in st.session_state.wines if w['id'] != wine['id']]
            save_data(st.session_state.wines); st.session_state.page = "table"; st.rerun()
