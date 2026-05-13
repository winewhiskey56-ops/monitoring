import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import pandas as pd

# 1. Настройка драйвера (Универсальная для облака и локала)
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Пытаемся найти путь для Streamlit Cloud, если нет — используем стандартный
    try:
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    except:
        from webdriver_manager.chrome import ChromeDriverManager
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

# 2. Функции парсинга
def search_lenta(wine_name):
    driver = get_driver()
    try:
        driver.get("https://lenta.com/")
        time.sleep(2)
        driver.add_cookie({"name": "city", "value": "orenburg"})
        driver.get(f"https://lenta.com/search/?searchText={wine_name}")
        time.sleep(4)
        price_elem = driver.find_element(By.CSS_SELECTOR, ".price-label__integer")
        return f"{price_elem.text} ₽"
    except:
        return "Не найдено"
    finally:
        driver.quit()

def search_metro(wine_name):
    driver = get_driver()
    try:
        driver.get("https://online.metro-cc.ru/")
        time.sleep(2)
        driver.add_cookie({"name": "metro_store_id", "value": "68"}) 
        driver.get(f"https://online.metro-cc.ru/search?q={wine_name}")
        time.sleep(4)
        price_elem = driver.find_element(By.CSS_SELECTOR, ".product-unit-prices__actual-wrapper .product-price__sum-rubles")
        return f"{price_elem.text} ₽"
    except:
        return "Не найдено"
    finally:
        driver.quit()

# 3. ИНТЕРФЕЙС (То, что пропало)
st.set_page_config(page_title="Мониторинг цен Оренбург", page_icon="🍷")

st.title("🍷 Мониторинг винных конкурентов")
st.markdown("### Регион: Оренбург")

# Контейнер для ввода данных
with st.container():
    col1, col2 = st.columns(2)
    with col1:
        wine_input = st.text_input("Введите название вина", "Martini Asti")
    with col2:
        my_price = st.number_input("Ваша цена в винотеке", value=1000, step=50)

# Кнопка запуска
if st.button("Проверить цены конкурентов"):
    if wine_input:
        with st.spinner(f'Ищу "{wine_input}" в магазинах Оренбурга...'):
            lenta_res = search_lenta(wine_input)
            metro_res = search_metro(wine_input)
            
            # Создаем таблицу результатов
            data = {
                "Магазин": ["Лента", "Metro"],
                "Цена конкурента": [lenta_res, metro_res],
                "Ваша цена": [f"{my_price} ₽", f"{my_price} ₽"]
            }
            
            df = pd.DataFrame(data)
            
            st.divider()
            st.subheader("Результаты анализа")
            st.table(df)
            
            if "Не найдено" in [lenta_res, metro_res]:
                st.warning("Некоторые товары не найдены. Попробуйте уточнить название или проверить наличие на сайте вручную.")
    else:
        st.error("Введите название вина для поиска!")

st.sidebar.info("Этот инструмент парсит цены в реальном времени. Помните, что сайты могут менять структуру, что потребует обновления кода.")
