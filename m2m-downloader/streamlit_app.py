import asyncio
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import plotly.express as px
import pytz
import streamlit as st
from playwright.async_api import TimeoutError, async_playwright

DEFAULT_GROUP_FILTER = "Toowoomba Regional Council"
DEFAULT_TZ = "Australia/Brisbane"
LOGIN_URL = "http://www.m2m-iot.cc/sign/showLogin#"
HISTORY_STATE_KEY = "m2m_history"


def ensure_chromium_installed() -> None:
    """Install the Playwright chromium browser bundle when missing."""
    chromium_root = Path.home() / ".cache" / "ms-playwright" / "chromium"
    if chromium_root.exists() and any(chromium_root.iterdir()):
        return
    subprocess.run(["playwright", "install", "chromium"], check=True)


def sanitize_numeric(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.Series(dtype=float, index=series.index)
    cleaned = series.astype(str).str.replace(r"[^0-9.+-]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def prepare_for_analysis(df: pd.DataFrame, tz_name: str) -> pd.DataFrame:
    processed = df.copy()
    processed["Timestamp"] = pd.to_datetime(
        processed["Timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce"
    )
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone(DEFAULT_TZ)
    if processed["Timestamp"].dt.tz is None:
        try:
            processed["Timestamp"] = processed["Timestamp"].dt.tz_localize(
                tz, nonexistent="NaT", ambiguous="NaT"
            )
        except (TypeError, ValueError):
            pass
    else:
        try:
            processed["Timestamp"] = processed["Timestamp"].dt.tz_convert(tz)
        except Exception:
            pass

    processed["Depth_mm"] = sanitize_numeric(processed["Depth (mm)"])
    processed["Velocity_mps"] = sanitize_numeric(processed["Velocity (mps)"])
    processed["Flow_lps"] = sanitize_numeric(processed["Flow (lps)"])
    return processed


def update_history(state_key: str, current_df: pd.DataFrame) -> pd.DataFrame:
    history = st.session_state.get(state_key)
    if history is None or history.empty:
        history = current_df.copy()
    else:
        history = pd.concat([history, current_df], ignore_index=True)
        history = history.drop_duplicates(subset=["Timestamp", "Device ID"], keep="last")
        history = history.sort_values("Timestamp")
    st.session_state[state_key] = history
    return history


async def fetch_latest_readings(
    username: str,
    password: str,
    group_filter: str,
    max_devices: int,
    tz_name: str,
) -> Tuple[List[Dict[str, str]], List[str]]:
    records: List[Dict[str, str]] = []
    warnings: List[str] = []
    try:
        local_tz = pytz.timezone(tz_name)
    except Exception:
        local_tz = pytz.timezone(DEFAULT_TZ)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        try:
            await page.fill('xpath=//*[@id="loginname"]', username)
            await page.fill('xpath=//*[@id="pass"]', password)
            await page.click('xpath=//*[@id="button_login"]')
            await page.wait_for_selector('[id^="datagrid-row-"]', timeout=30000)
        except TimeoutError as exc:
            await browser.close()
            raise RuntimeError("Login failed or device table did not load in time") from exc

        rows = await page.query_selector_all('[id^="datagrid-row-"]')
        if not rows:
            await browser.close()
            return records, ["No device rows detected after login."]

        for idx, row in enumerate(rows):
            if max_devices and len(records) >= max_devices:
                break

            try:
                cells = await row.query_selector_all("td")
                if len(cells) < 7:
                    continue

                group = (await cells[4].inner_text() or "").strip()
                if group_filter and group_filter not in group:
                    continue

                device_id = (await cells[2].inner_text() or "").strip()
                device_name = (await cells[3].inner_text() or "").strip()

                realtime_link = await row.query_selector('td:nth-child(1) div a:nth-child(1)')
                if not realtime_link:
                    warnings.append(f"[{device_id}] Realtime link not found")
                    continue

                is_new = False
                detail_page = page
                try:
                    async with context.expect_page(timeout=2500) as new_page_info:
                        await realtime_link.click()
                    detail_page = await new_page_info.value
                    await detail_page.wait_for_load_state()
                    is_new = True
                except TimeoutError:
                    detail_page = page

                table_id = f"table_{device_id}_AD"
                await detail_page.wait_for_selector(f"#{table_id}", timeout=15000)

                flow_xpath = f'//*[@id="{table_id}"]/tbody/tr[1]/td[4]/p'
                depth_xpath = f'//*[@id="{table_id}"]/tbody/tr[2]/td[4]/p'
                velocity_xpath = f'//*[@id="{table_id}"]/tbody/tr[3]/td[4]/p'

                flow = await detail_page.text_content(f"xpath={flow_xpath}")
                depth = await detail_page.text_content(f"xpath={depth_xpath}")
                velocity = await detail_page.text_content(f"xpath={velocity_xpath}")

                timestamp = datetime.now(local_tz).strftime("%Y-%m-%d %H:%M:%S")
                records.append(
                    {
                        "Timestamp": timestamp,
                        "Device ID": device_id,
                        "Device Name": device_name,
                        "Depth (mm)": (depth or "").strip(),
                        "Velocity (mps)": (velocity or "").strip(),
                        "Flow (lps)": (flow or "").strip(),
                    }
                )

                if is_new:
                    await detail_page.close()
                else:
                    try:
                        await page.click('xpath=//*[@id="tt"]/div[1]/div[3]/ul/li[1]/a[1]/span[1]')
                        await page.wait_for_selector('[id^="datagrid-row-"]', timeout=10000)
                    except Exception:
                        warnings.append(f"[{device_id}] Unable to return to list; refreshing table")
                        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
                        await page.wait_for_selector('[id^="datagrid-row-"]', timeout=30000)

            except Exception as exc:
                warnings.append(f"[{idx}] Error scraping device: {exc}")

        await browser.close()

    return records, warnings


def build_csv_download(records: List[Dict[str, str]]) -> Tuple[pd.DataFrame, bytes]:
    df = pd.DataFrame(records)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return df, csv_bytes


def resolve_secret(key: str) -> str:
    if key in st.secrets:
        return st.secrets[key]
    return os.getenv(key, "")


def format_metric(value: float, unit: str) -> str:
    if pd.isna(value):
        return "N/A"
    return f"{value:,.2f} {unit}" if unit else f"{value:,.2f}"


st.set_page_config(page_title="M2M Live Downloader", page_icon="📥", layout="wide")
st.title("M2M Live Data Downloader")
st.caption("Engineering snapshot for Depth, Velocity, and Flow measurements.")

username_secret = resolve_secret("M2M_USERNAME")
password_secret = resolve_secret("M2M_PASSWORD")

with st.expander("Credentials", expanded=not (username_secret and password_secret)):
    if username_secret and password_secret:
        st.success("Using credentials supplied via Streamlit secrets or environment variables.")
        override = st.checkbox("Override credentials", value=False)
        if override:
            username_secret = st.text_input("Username", value="", key="username_override")
            password_secret = st.text_input("Password", type="password", value="", key="password_override")
    else:
        username_secret = st.text_input("Username", value=username_secret, key="username_input")
        password_secret = st.text_input("Password", type="password", value=password_secret, key="password_input")

options_col, timezone_col = st.columns(2)
with options_col:
    group_filter = st.text_input("Group name contains", value=DEFAULT_GROUP_FILTER)
    max_devices = st.number_input("Max devices to capture (0 = all)", min_value=0, max_value=200, value=0, step=1)

with timezone_col:
    tz_name = st.text_input("Timezone", value=DEFAULT_TZ)

run_button = st.button("Fetch latest readings", type="primary")

if run_button:
    if not username_secret or not password_secret:
        st.error("Username and password are required.")
        st.stop()

    tz_choice = (tz_name or DEFAULT_TZ).strip()
    try:
        pytz.timezone(tz_choice)
    except Exception:
        st.warning(f"Timezone '{tz_choice}' not recognised. Falling back to {DEFAULT_TZ}.")
        tz_choice = DEFAULT_TZ

    try:
        ensure_chromium_installed()
    except subprocess.CalledProcessError:
        st.error("Failed to install Playwright chromium bundle. Check logs and try again.")
        st.stop()

    with st.spinner("Collecting live readings..."):
        try:
            records, warnings = asyncio.run(
                fetch_latest_readings(
                    username=username_secret,
                    password=password_secret,
                    group_filter=group_filter.strip(),
                    max_devices=max_devices,
                    tz_name=tz_choice,
                )
            )
        except Exception as exc:
            st.error(f"Scrape failed: {exc}")
            st.stop()

    for msg in warnings:
        st.warning(msg)

    if not records:
        st.info("No matching device readings found.")
    else:
        df, csv_bytes = build_csv_download(records)
        processed_df = prepare_for_analysis(df, tz_choice)
        history_df = update_history(HISTORY_STATE_KEY, processed_df)

        st.success(f"Captured {len(df)} device readings.")

        tabs = st.tabs(["Snapshot", "Trendlines", "Historical Summary"])

        with tabs[0]:
            st.subheader("Current Snapshot")
            latest_ts = processed_df["Timestamp"].max()
            latest_snapshot = processed_df[processed_df["Timestamp"] == latest_ts]

            total_devices = int(latest_snapshot["Device ID"].nunique())
            avg_depth = latest_snapshot["Depth_mm"].mean()
            avg_velocity = latest_snapshot["Velocity_mps"].mean()
            avg_flow = latest_snapshot["Flow_lps"].mean()

            metrics = st.columns(4)
            metrics[0].metric("Devices", f"{total_devices}")
            metrics[1].metric("Avg Depth", format_metric(avg_depth, "mm"))
            metrics[2].metric("Avg Velocity", format_metric(avg_velocity, "m/s"))
            metrics[3].metric("Avg Flow", format_metric(avg_flow, "L/s"))

            display_cols = [
                "Device Name",
                "Timestamp",
                "Depth (mm)",
                "Velocity (mps)",
                "Flow (lps)",
            ]
            st.dataframe(latest_snapshot[display_cols].set_index("Device Name"), use_container_width=True)

            st.download_button(
                "Download latest CSV",
                data=csv_bytes,
                file_name=f"m2m_readings_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
            )

        with tabs[1]:
            st.subheader("Engineering Trendlines")
            if history_df.empty or history_df["Timestamp"].isna().all():
                st.info("Trendlines will appear after multiple captures with valid timestamps.")
            else:
                trend_df = history_df.dropna(subset=["Timestamp"]).copy()
                trend_df = trend_df.sort_values("Timestamp")

                depth_fig = px.line(
                    trend_df,
                    x="Timestamp",
                    y="Depth_mm",
                    color="Device Name",
                    markers=True,
                    template="plotly_white",
                    labels={"Depth_mm": "Depth (mm)", "Timestamp": "Time"},
                    title="Depth Over Time",
                )
                depth_fig.update_layout(legend_title_text="")

                velocity_fig = px.line(
                    trend_df,
                    x="Timestamp",
                    y="Velocity_mps",
                    color="Device Name",
                    markers=True,
                    template="plotly_white",
                    labels={"Velocity_mps": "Velocity (m/s)", "Timestamp": "Time"},
                    title="Velocity Over Time",
                )
                velocity_fig.update_layout(legend_title_text="")

                flow_fig = px.line(
                    trend_df,
                    x="Timestamp",
                    y="Flow_lps",
                    color="Device Name",
                    markers=True,
                    template="plotly_white",
                    labels={"Flow_lps": "Flow (L/s)", "Timestamp": "Time"},
                    title="Flow Over Time",
                )
                flow_fig.update_layout(legend_title_text="")

                st.plotly_chart(depth_fig, use_container_width=True)
                st.plotly_chart(velocity_fig, use_container_width=True)
                st.plotly_chart(flow_fig, use_container_width=True)

        with tabs[2]:
            st.subheader("Historical Summary")
            if history_df.empty:
                st.info("No historical data yet. Run multiple captures to build history.")
            else:
                summary = (
                    history_df.groupby("Device Name")[["Depth_mm", "Velocity_mps", "Flow_lps"]]
                    .agg(["min", "mean", "max"])
                    .round(2)
                )
                summary.columns = [" ".join(col).strip() for col in summary.columns]
                st.dataframe(summary, use_container_width=True)

                history_export = history_df.copy()
                history_export["Timestamp"] = history_export["Timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S %Z")
                history_csv = history_export.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download history CSV",
                    data=history_csv,
                    file_name="m2m_history.csv",
                    mime="text/csv",
                )

st.markdown(
    """
    **Deployment notes**

    1. Add `M2M_USERNAME` and `M2M_PASSWORD` via Streamlit Secrets.
    2. Include `selenium`, `playwright`, `streamlit`, `pandas`, `plotly`, and `pytz` in `requirements.txt`.
    3. Run `playwright install chromium` during build (handled automatically on first launch via this app).
    4. Trigger the capture using the button above whenever you need a fresh CSV or trend update.
    """
)
