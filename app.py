import streamlit as st

# Явно указываем Стримлиту на файлы внутри папки pages
wines_page = st.Page("pages/wines.py", title="Витрина вин и карточки", icon="🍷", default=True)
purchases_page = st.Page("pages/purchases.py", title="Анализ цен номенклатуры", icon="🔍")

# Рисуем красивое меню навигации
pg = st.navigation([wines_page, purchases_page])
pg.run()
