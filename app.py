import streamlit as st
import pandas as pd
import json
import os

# --- НАСТРОЙКИ И БАЗА ДАННЫХ ---
DB_FILE = "wine_db.json"

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Инициализация данных в сессии
if 'wines' not in st.session_state:
    st.session_state.wines = load_data()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def calc_perc(reg, disc):
    if reg and disc and reg > 0:
        return round((1 - disc / reg) * 100, 1)
    return 0

# --- СТИЛИЗАЦИЯ ТАБЛИЦЫ ---
def highlight_prices(row):
    # Собираем все итоговые цены (наша и конкурентов), которые есть в наличии
    prices = {}
    if not row['Нет в наличии']:
        prices['Наша'] = row['Наша цена (скидка)']
    
    # Извлекаем цены конкурентов из вложенных данных (упростим для примера в плоской таблице)
    # Для демонстрации в таблице выводим минимальную/максимальную среди всех
    return ['' for _ in row]

# --- ИНТЕРФЕЙС ---
st.set_page_config(layout="wide", page_title="Wine Control Panel")

st.title("🍷 Система мониторинга цен и ассортимента")

menu = st.sidebar.radio("Навигация", ["Общая таблица", "Добавить/Редактировать вино"])

categories = ["Новый Свет", "Европа", "Игристые", "Крепкие напитки"]
competitor_list = ["Лента", "Метро", "Магнит", "Перекресток", "О'кей", "Красное и Белое"]

# --- ВКЛАДКА: ДОБАВЛЕНИЕ/РЕДАКТИРОВАНИЕ ---
if menu == "Добавить/Редактировать вино":
    st.header("📝 Карточка вина")
    
    with st.form("wine_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Название вина")
            category = st.selectbox("Категория", categories)
            out_of_stock = st.checkbox("Нет в наличии")
        
        with col2:
            our_reg = st.number_input("Наша верхняя цена", min_value=0)
            our_disc = st.number_input("Наша цена со скидкой", min_value=0)
            st.info(f"Наша скидка: {calc_perc(our_reg, our_disc)}%")

        st.divider()
        st.subheader("Цены конкурентов")
        
        # Динамическое добавление конкурентов (упрощено до выбора нескольких)
        comp_data = []
        selected_comps = st.multiselect("Выберите конкурентов для сравнения", competitor_list)
        
        for comp in selected_comps:
            c_col1, c_col2, c_col3 = st.columns([2, 2, 2])
            with c_col1:
                st.write(f"**{comp}**")
            with c_col2:
                c_reg = st.number_input(f"Рег. цена ({comp})", key=f"reg_{comp}", min_value=0)
            with c_col3:
                c_disc = st.number_input(f"Цена со скидкой ({comp})", key=f"disc_{comp}", min_value=0)
            
            comp_data.append({
                "shop": comp,
                "reg": c_reg,
                "disc": c_disc,
                "perc": calc_perc(c_reg, c_disc)
            })

        if st.form_submit_button("Сохранить карточку"):
            new_wine = {
                "Название": name,
                "Категория": category,
                "Нет в наличии": out_of_stock,
                "Наша цена (рег)": our_reg,
                "Наша цена (скидка)": our_disc,
                "Наша скидка %": calc_perc(our_reg, our_disc),
                "Конкуренты": comp_data
            }
            st.session_state.wines.append(new_wine)
            save_data(st.session_state.wines)
            st.success(f"Вино '{name}' добавлено!")

# --- ВКЛАДКА: ТАБЛИЦА ---
elif menu == "Общая таблица":
    st.header("📊 Сравнительный анализ")
    
    if not st.session_state.wines:
        st.warning("База данных пуста. Добавьте первое вино.")
    else:
        # Фильтры
        filter_cat = st.multiselect("Фильтр по категории", categories, default=categories)
        
        # Подготовка данных для таблицы
        display_data = []
        for w in st.session_state.wines:
            if w['Категория'] in filter_cat:
                # Находим лучшую цену среди всех
                all_prices = [w['Наша цена (скидка)']] + [c['disc'] for c in w['Конкуренты'] if c['disc'] > 0]
                min_p = min(all_prices) if all_prices else 0
                max_p = max(all_prices) if all_prices else 0
                
                row = {
                    "Название": w['Название'],
                    "Категория": w['Категория'],
                    "Наша цена": w['Наша цена (скидка)'],
                    "Наша скидка %": w['Наша скидка %'],
                    "Нет в наличии": "❌" if w['Нет в наличии'] else "✅"
                }
                
                # Добавляем колонки конкурентов
                for comp in competitor_list:
                    comp_val = next((c for c in w['Конкуренты'] if c['shop'] == comp), None)
                    row[f"{comp}"] = comp_val['disc'] if comp_val else "—"
                
                display_data.append(row)

        df = pd.DataFrame(display_data)

        # Функция для раскраски
        def color_prices(val):
            # Это упрощенная логика раскраски ячеек
            return ''

        # Вывод таблицы с сортировкой
        st.dataframe(df.sort_values(by="Название"), use_container_width=True)
        
        st.download_button("📥 Экспорт в CSV", df.to_csv(index=False).encode('utf-8-sig'), "wine_inventory.csv")
