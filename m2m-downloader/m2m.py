import os
import time
import pathlib
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


LOGIN_URL = "http://www.m2m-iot.cc/sign/showLogin#"

USERNAME = os.environ.get("M2M_USERNAME", "")
PASSWORD = os.environ.get("M2M_PASSWORD", "")
if not USERNAME or not PASSWORD:
    raise RuntimeError("Missing M2M_USERNAME / M2M_PASSWORD env vars")

BROWSER = os.environ.get("M2M_BROWSER", "firefox")
HEADLESS = os.environ.get("M2M_HEADLESS", "false").lower() in {"1", "true", "yes"}

OUT_DIR = pathlib.Path.cwd() / "m2m_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def dump_debug(driver, label: str = "debug") -> None:
    stamp = ts()
    png = OUT_DIR / f"{label}_{stamp}.png"
    html = OUT_DIR / f"{label}_{stamp}.html"
    try:
        driver.save_screenshot(str(png))
        print(f"[debug] Saved screenshot: {png}")
    except Exception as exc:
        print(f"[debug] Could not save screenshot: {exc}")

    try:
        html.write_text(driver.page_source, encoding="utf-8")
        print(f"[debug] Saved HTML: {html}")
    except Exception as exc:
        print(f"[debug] Could not save HTML: {exc}")


def make_driver():
    if BROWSER.lower() == "chrome":
        from selenium.webdriver.chrome.options import Options

        options = Options()
        if HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
    else:
        from selenium.webdriver.firefox.options import Options

        options = Options()
        if HEADLESS:
            options.add_argument("-headless")
        driver = webdriver.Firefox(options=options)

    driver.set_page_load_timeout(60)
    return driver


def find_first(driver, locators, timeout: int = 12):
    last_err = None
    for by, sel in locators:
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((by, sel))
            )
            return element
        except Exception as err:
            last_err = err
    raise last_err


def try_click(driver, locators, timeout: int = 8) -> bool:
    for by, sel in locators:
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by, sel))
            )
            element.click()
            return True
        except Exception:
            continue
    return False


def login(driver) -> None:
    driver.get(LOGIN_URL)

    WebDriverWait(driver, 20).until(
        lambda d: len(d.find_elements(By.TAG_NAME, "input")) > 0
    )

    username_locators = [
        (By.ID, "username"),
        (By.NAME, "username"),
        (By.NAME, "userName"),
        (By.ID, "userName"),
        (By.NAME, "user"),
        (By.ID, "user"),
        (By.CSS_SELECTOR, "input[type='text']"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (
            By.XPATH,
            "//input[contains(@placeholder,'User') or contains(@placeholder,'user')]",
        ),
        (
            By.XPATH,
            "//input[contains(@placeholder,'Name') or contains(@placeholder,'name')]",
        ),
        (
            By.XPATH,
            "//input[contains(@placeholder,'Account') or contains(@placeholder,'account')]",
        ),
        (By.XPATH, "//input[contains(@autocomplete,'username')]")
    ]

    password_locators = [
        (By.ID, "password"),
        (By.NAME, "password"),
        (By.ID, "passWord"),
        (By.NAME, "passWord"),
        (By.CSS_SELECTOR, "input[type='password']"),
        (
            By.XPATH,
            "//input[contains(@placeholder,'Pass') or contains(@placeholder,'pass')]",
        ),
        (
            By.XPATH,
            "//input[contains(@autocomplete,'current-password')]",
        )
    ]

    try:
        user_el = find_first(driver, username_locators, timeout=12)
        pass_el = find_first(driver, password_locators, timeout=12)
    except Exception as err:
        print("[error] Could not find login fields. Saving debug files...")
        dump_debug(driver, label="login_fields_not_found")
        raise err

    user_el.clear()
    user_el.send_keys(USERNAME)

    pass_el.clear()
    pass_el.send_keys(PASSWORD)

    login_button_locators = [
        (By.ID, "loginButton"),
        (By.NAME, "loginButton"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "input[type='submit']"),
        (
            By.XPATH,
            "//button[contains(.,'Login') or contains(.,'Sign in') or contains(.,'Sign In')]",
        ),
        (
            By.XPATH,
            "//a[contains(.,'Login') or contains(.,'Sign in') or contains(.,'Sign In')]",
        )
    ]

    clicked = try_click(driver, login_button_locators, timeout=6)
    if not clicked:
        pass_el.send_keys(Keys.RETURN)

    time.sleep(1)

    try:
        WebDriverWait(driver, 20).until(
            lambda d: (d.current_url != LOGIN_URL) or ("showLogin" not in d.current_url)
        )
    except Exception:
        pass

    still_has_password = len(driver.find_elements(By.CSS_SELECTOR, "input[type='password']")) > 0
    if still_has_password and "showLogin" in driver.current_url:
        print("[error] Login may have failed (still on login screen). Saving debug files...")
        dump_debug(driver, label="login_maybe_failed")
        raise RuntimeError("Login may have failed. Check artifacts in m2m_outputs.")

    print("[info] Login step completed or at least navigated away from the obvious login page.")


def export_data(driver) -> None:
    print("[info] Capturing post-login page for next-step selector wiring.")
    dump_debug(driver, label="post_login_page")

    print(
        "[next] Review the saved HTML in m2m_outputs and gather:\n"
        "  1) The section that lists the Toowoomba Regional Council group\n"
        "  2) The action that opens Live View\n"
        "  3) How Depth, Velocity, and Flow are labeled\n"
        "  4) The selector for any Export or Download button\n"
        "Once known, extend export_data with the required navigation and downloads."
    )


def main() -> None:
    driver = make_driver()
    try:
        login(driver)
        export_data(driver)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
