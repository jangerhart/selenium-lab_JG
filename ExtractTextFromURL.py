from selenium import webdriver
from selenium.webdriver.common.by import By

URL = "https://the-internet.herokuapp.com/tables"

driver = webdriver.Chrome()  # případně webdriver.Edge()
driver.get(URL)

# stránka má obsah v #content, bereme jen to, ne menu prohlížeče
content_text = driver.find_element(By.ID, "content").text

print(content_text)

driver.quit()
