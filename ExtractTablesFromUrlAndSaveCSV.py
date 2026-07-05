import json
import sqlite3
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By

URL = "https://the-internet.herokuapp.com/tables"

def extract_visible_text(driver) -> str:
    return driver.find_element(By.ID, "content").text

def extract_table_as_records(driver, table_id: str):
    table = driver.find_element(By.ID, table_id)
    headers = [th.text.strip() for th in table.find_elements(By.CSS_SELECTOR, "thead th")]

    records = []
    for row in table.find_elements(By.CSS_SELECTOR, "tbody tr"):
        cells = [td.text.strip() for td in row.find_elements(By.CSS_SELECTOR, "td")]
        records.append(dict(zip(headers, cells)))
    return records

def main():
    driver = webdriver.Chrome()
    try:
        driver.get(URL)

        # 1) text
        text = extract_visible_text(driver)
        with open("page_text.txt", "w", encoding="utf-8") as f:
            f.write(text)

        # 2) tabulky
        table1 = extract_table_as_records(driver, "table1")
        table2 = extract_table_as_records(driver, "table2")

        with open("table1.json", "w", encoding="utf-8") as f:
            json.dump(table1, f, ensure_ascii=False, indent=2)

        with open("table2.json", "w", encoding="utf-8") as f:
            json.dump(table2, f, ensure_ascii=False, indent=2)

        # 3) DataFrame + úpravy
        df2 = pd.DataFrame(table2)

        if "Due" in df2.columns:
            df2["Due"] = df2["Due"].str.replace("$", "", regex=False).astype(float)

        df2.to_csv("table2.csv", index=False, encoding="utf-8")

        # 4) SQLite
        conn = sqlite3.connect("extracted.db")
        df2.to_sql("table2", conn, if_exists="replace", index=False)
        conn.close()

        print("Hotovo: page_text.txt, table1.json, table2.json, table2.csv, extracted.db")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
