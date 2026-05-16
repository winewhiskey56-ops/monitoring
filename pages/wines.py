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
        st.session_state.current_wine = json.loads(json.dumps(wine))
    else:
        st.session_state.current_wine = {
            "id": str(uuid.uuid4()), "name": "", "category": CATEGORIES[0],
            "stock": "3+", "purchase_price": 0, "our_reg": 0, "our_disc": 0, 
            "competitors": [], "history": []
        }
    st.session_state.page = "edit"

# --- ОБНОВЛЕННЫЙ АВТОМАТИЧЕСКИЙ ДВИЖОК РЕКОМЕНДАЦИЙ ---
def generate_recommendation(wine):
    if wine.get('purchase_price', 0) <= 0 or wine['our_reg'] <= 0:
        return "⚠️ Для расчета рекомендаций заполните 'Закупочную стоимость' и 'Нашу Рег. цену'."
    
    pur_price = wine['purchase_price']
    our_reg = wine['our_reg']
    min_retail_price = pur_price * 1.3  # Маржа не менее 30% от закупа
    stock = wine.get('stock', '3+')
    
    active_comps = [c for c in wine['competitors'] if c['in_stock'] and c['disc'] > 0]
    
    # Если конкурентов нет на рынке
    if not active_comps:
        return f"🏆 **Вне конкуренции:** Конкурентов нет в наличии. Рекомендуется продавать без скидки.\n* **Рекомендуемая цена:** {our_reg:.0f}₽ (Скидка 0%)\n* **Наценка:** {our_reg - pur_price:.0f}₽"
         
    cheapest = min(active_comps, key=lambda x: x['disc'])
    c_price = cheapest['disc']
    
    # Идеальный вариант: быть немного ниже конкурента
    ideal_target = c_price - 10 
    
    # Вспомогательная функция для поиска подходящих промо-акций по эффективной цене за 1 шт
    def check_promo_options(target_p):
        options = []
        if stock == '3+':
            p_11 = our_reg * 0.666
            if p_11 >= min_retail_price and p_11 <= target_p:
                options.append({"type": "«1+1=3»", "price": p_11})
        if stock in ['2', '3+']:
            p_50 = our_reg * 0.75
            if p_50 >= min_retail_price and p_50 <= target_p:
                options.append({"type": "«-50% на вторую»", "price": p_50})
        return options

    # --- СТРАТЕГИЯ 1: Идеальный вариант (Перебить цену конкурента с маржой >= 30%) ---
    if ideal_target >= min_retail_price:
        # Если у конкурента нет скидок, просто снижаем нашу верхнюю (регулярную) цену
        if cheapest['disc'] == cheapest['reg'] and ideal_target <= our_reg:
            return f"🎯 **Вариант 1 (Идеал): Снижение базовой цены**\n\nКонкурент ({cheapest['shop']}) торгует без скидок за {c_price:.0f}₽. Ставим цену чуть ниже.\n* **Рекомендуемая цена:** {ideal_target:.0f}₽ (Без скидки)\n* **Наценка:** {ideal_target - pur_price:.0f}₽"
        
        # Ищем стандартную скидку под этот идеал
        discounts = [10, 15, 20, 25, 30, 35, 40, 45]
        for d in discounts:
            p = our_reg * (1 - d / 100.0)
            if p >= min_retail_price and p <= ideal_target:
                return f"⚔️ **Вариант 1 (Идеал): Фиксированная скидка**\n\nУспешно бьем цену конкурента ({cheapest['shop']}: {c_price:.0f}₽).\n* **Рекомендуемая скидка:** {d}%\n* **Новая цена:** {p:.0f}₽\n* **Наценка:** {p - pur_price:.0f}₽"
        
        # Если стандартные скидки не подошли, пробуем пакетные акции
        promos = check_promo_options(ideal_target)
        if promos:
            best_p = max(promos, key=lambda x: x['price'])
            return f"🎁 **Вариант 1 (Идеал): Пакетная акция**\n\nБьем цену конкурента за счет объема продаж.\n* **Рекомендуемая акция:** {best_p['type']}\n* **Эффективная цена за шт:** {best_p['price']:.0f}₽\n* **Наценка за шт:** {best_p['price'] - pur_price:.0f}₽"

    # --- СТРАТЕГИЯ 2: Погрешность +10% (Если идеал уходит в минус, но +10% к цене конкурента проходит маржу) ---
    error_target = c_price * 1.10
    if error_target >= min_retail_price:
        discounts = [10, 15, 20, 25, 30, 35, 40, 45]
        for d in discounts:
            p = our_reg * (1 - d / 100.0)
            if p >= min_retail_price and p <= error_target:
                return f"⚖️ **Вариант 2: Допустимая погрешность (+10%)**\n\nСделать цену ниже конкурента ({c_price:.0f}₽) нельзя из-за лимита закупки. Ставим цену в пределах +10% от его стоимости.\n* **Рекомендуемая скидка:** {d}%\n* **Новая цена:** {p:.0f}₽\n* **Наценка:** {p - pur_price:.0f}₽"
        
        promos = check_promo_options(error_target)
        if promos:
            best_p = max(promos, key=lambda x: x['price'])
            return f"🎁 **Вариант 2: Допустимая погрешность через объем**\n\nУдерживаем цену в пределах +10% от конкурента за счет пакетной акции.\n* **Рекомендуемая акция:** {best_p['type']}\n* **Эффективная цена за шт:** {best_p['price']:.0f}₽\n* **Наценка за шт:** {best_p['price'] - pur_price:.0f}₽"

    # --- СТРАТЕГИЯ 3: Максимально возможная скидка (Критическая зона защиты маржи) ---
    max_d = get_perc(our_reg, min_retail_price)
    return f"🛑 **Вариант 3: Максимально возможная скидка (Защита маржи)**\n\nКонкурент демпингует ниже нашего закупа ({c_price:.0f}₽ в {cheapest['shop']}). Устанавливаем минимально допустимый предел с маржой 30%.\n* **Рекомендуемая цена:** {min_retail_price:.0f}₽\n* **Скидка на ценнике:** {max_d:.0f}%\n* **Наценка:** {min_retail_price - pur_price:.0f}₽ (Строго 30%)\n* **Внимание:** Ниже опускаться запрещено!"

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
            
            pur_val = st.number_input("Закупочная стоимость*", value=int(wine.get('purchase_price', 0)), key="input_pur_price")
            wine['purchase_price'] = pur_val
            
        with c2:
            wine['our_reg'] = st.number_input("Наша Рег. цена*", value=int(wine['our_reg']), key="input_our_reg")
            wine['our_disc'] = st.number_input("Наша цена со скидкой*", value=int(wine['our_disc']), key="input_our_disc")
            
            if wine['our_reg'] > 0:
                p = get_perc(wine['our_reg'], wine['our_disc'])
                margin = wine['our_reg'] - wine['our_disc'] - wine['purchase_price']
                st.info(f"Скидка: **{p}%** | Наценка (руб): **{margin}₽**")
        with c3:
            st.write("📈 **Умный подбор под маржу магазина**")
            if st.button("🤖 Рассчитать лучший вариант", type="primary", use_container_width=True):
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
    
    if wine.get('history'):
        with st.expander("📜 История изменений"):
            for entry in wine['history']:
                st.caption(f"🗓️ {entry['date']}")
                for ch in entry['changes']:
                    st.write(f"• {ch}")
                st.write("---")

    b1, b2, b3 = st.columns([2, 2, 6])
    with b1:
        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if not wine['name']: st.error("Укажите название!")
            else:
                old_wine = next((w for w in st.session_state.wines if w['id'] == wine['id']), None)
                changes = []
                
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

                if changes:
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    if 'history' not in wine: wine['history'] = []
                    wine['history'].insert(0, {"date": now, "changes": changes})

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
        if st.button("🗑️ Удалить вино", type="secondary"):
            st.session_state.wines = [w for w in st.session_state.wines if w['id'] != wine['id']]
            save_data(st.session_state.wines)
            st.session_state.page = "table"
            st.rerun()
