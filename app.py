import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import time
import pandas as pd

# Настройки браузера для работы в облаке и обхода блокировок
def get_driver():
    options = Options()
    options.add_argument("--headless") # Работа без открытия окна
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def search_lenta(wine_name):
    driver = get_driver()
    try:
        # Прямой переход в поиск Ленты
        driver.get(f"https://lenta.com/search/?searchText={wine_name}")
        time.sleep(3) # Ждем загрузки
        # Ищем первый элемент цены в выдаче
        price_element = driver.find_element(By.CLASS_NAME, "price-label__integer")
        return f"{price_element.text} ₽"
    except:
        return "Не найдено"
    finally:
        driver.quit()

def search_metro(wine_name):
    driver = get_driver()
    try:
        driver.get(f"https://online.metro-cc.ru/search?q={wine_name}")
        time.sleep(3)
        # Ищем цену (селектор может меняться, это базовый пример)
        price_element = driver.find_element(By.CLASS_NAME, "product-unit-prices__actual-wrapper")
        return price_element.text.replace('\n', ' ')
    except:
        return "Не найдено"
    finally:
        driver.quit()

# Интерфейс Streamlit
st.title("🍷 Мониторинг винных конкурентов")

col1, col2 = st.columns(2)
with col1:
    wine_input = st.text_input("Название вина (на англ.)", "Casillero del Diablo Cabernet Sauvignon")
with col2:
    my_price = st.number_input("Ваша цена", value=1000)

if st.button("Запустить проверку"):
    with st.spinner('Связываюсь с магазинами...'):
        lenta_price = search_lenta(wine_input)
        metro_price = search_metro(wine_input)
        
        # Вывод результатов
        res_data = {
            "Магазин": ["Лента", "Metro"],
            "Цена конкурента": [lenta_price, metro_price],
            "Ваша цена": [f"{my_price} ₽", f"{my_price} ₽"]
        }
        
        df = pd.DataFrame(res_data)
        st.table(df)
        st.success("Данные обновлены!")
