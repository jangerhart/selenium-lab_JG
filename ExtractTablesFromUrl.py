from selenium import webdriver
from selenium.webdriver.common.by import By

def extract_table_as_records(driver, table_id: str):
    table = driver.find_element(By.ID, table_id)

    # Hlavičky
    headers = [th.text.strip() for th in table.find_elements(By.CSS_SELECTOR, "thead th")]

    # Řádky
    records = []
    rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
    for row in rows:
        cells = [td.text.strip() for td in row.find_elements(By.CSS_SELECTOR, "td")]
        # někdy může být na konci "Action" sloupec (edit/delete) apod.
        record = dict(zip(headers, cells))
        records.append(record)

    return records

URL = "https://the-internet.herokuapp.com/tables"

driver = webdriver.Chrome()
driver.get(URL)

table1_records = extract_table_as_records(driver, "table1")
table2_records = extract_table_as_records(driver, "table2")

print(table1_records[:2])
print(table2_records[:2])

driver.quit()
