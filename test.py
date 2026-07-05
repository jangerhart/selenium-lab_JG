from selenium import webdriver
from selenium.webdriver.common.by import By
import time

driver = webdriver.Chrome()
driver.get("https://the-internet.herokuapp.com/login")

print(driver.title)
input("Press Enter to continue...")


time.sleep(5)
driver.quit()
