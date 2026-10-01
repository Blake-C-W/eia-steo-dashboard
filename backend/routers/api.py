from fastapi import APIRouter
from backend.services import steo_scraper, historical_scraper, accuracy, connection, henry_hub_spot_scraper
import pandas as pd

router = APIRouter()

HH_SERIES = "Natural Gas Henry Hub Spot Price ($/mcf)"


@router.post("/api/scrape")
def refresh():
    steo_scraper.run()
    historical_scraper.run()
    henry_hub_spot_scraper.run()
    # banded, by_month = accuracy.run()

    return {"status": "ok"}


@router.get("/api/read_historical")
def get_all_historical():
    con = connection.get_connection()

    # ------------------------------------------------------------------
    # STORAGE
    # Weekly actuals get a rolling 5-year avg / low / high.
    # STEO forecast remains monthly and does NOT participate in the 5Y calc.
    # ------------------------------------------------------------------
    storage = con.execute("SELECT * FROM tbl_storage ORDER BY series_name, date").df()

    storage = storage[
        storage["series_name"].isin([
            "Lower 48",
            "East",
            "Midwest",
            "Mountain",
            "Pacific",
            "South Central",
        ])
    ].copy()

    storage["series_name"] = storage["series_name"].replace({
        "Lower 48": "Natural Gas Working Inventory Lower 48",
        "East": "Natural Gas Working Inventory East Region",
        "Midwest": "Natural Gas Working Inventory Midwest Region",
        "Mountain": "Natural Gas Working Inventory Mountain Region",
        "Pacific": "Natural Gas Working Inventory Pacific Region",
        "South Central": "Natural Gas Working Inventory South Central Consuming Region",
    })

    storage["date"] = pd.to_datetime(storage["date"])
    storage = storage.dropna(subset=["date", "value"]).sort_values(["series_name", "date"])
    storage["year"] = storage["date"].dt.isocalendar().year.astype(int)
    storage["week"] = storage["date"].dt.isocalendar().week.astype(int)

    # Keep one observation per region / ISO week in case the table contains duplicates.
    storage = storage.drop_duplicates(["series_name", "year", "week"], keep="last")

    # Calculate the 5-year statistics separately for every historical year.
    # Example: a 2024 weekly point uses the same ISO week from 2019-2023.
    # This keeps the band fully weekly and prevents monthly STEO values from
    # contaminating the historical 5-year calculation.
    stats_frames = []
    for target_year in sorted(storage["year"].unique()):
        previous_five = storage[
            storage["year"].between(target_year - 5, target_year - 1)
        ]

        if previous_five.empty:
            continue

        year_stats = (
            previous_five
            .groupby(["series_name", "week"])
            .agg(
                five_year_avg=("value", "mean"),
                five_year_low=("value", "min"),
                five_year_high=("value", "max"),
                five_year_count=("year", "nunique"),
            )
            .reset_index()
        )

        # Only call it a 5-year statistic when all five prior years exist.
        incomplete = year_stats["five_year_count"] < 5
        year_stats.loc[incomplete, ["five_year_avg", "five_year_low", "five_year_high"]] = None
        year_stats["year"] = target_year
        stats_frames.append(year_stats.drop(columns="five_year_count"))

    if stats_frames:
        five_year_stats = pd.concat(stats_frames, ignore_index=True)
        storage_historical = storage.merge(
            five_year_stats,
            on=["series_name", "year", "week"],
            how="left",
        )
    else:
        storage_historical = storage.copy()
        storage_historical["five_year_avg"] = None
        storage_historical["five_year_low"] = None
        storage_historical["five_year_high"] = None

    storage_historical = storage_historical[
        [
            "date",
            "series_name",
            "value",
            "five_year_avg",
            "five_year_low",
            "five_year_high",
        ]
    ].copy()
    storage_historical["historical_forecast"] = "historical"

    cursor = con.cursor()
    cursor.execute("SELECT MAX(last_updated) FROM tbl_meta_data WHERE table_name = 'tbl_historical'")
    last_updated = pd.Timestamp(cursor.fetchone()[0])

    tbl_historical = con.execute("SELECT * FROM tbl_historical ORDER BY series_name, date").df()
    tbl_historical["date"] = pd.to_datetime(tbl_historical["date"])

    # STEO rows dated from the latest STEO release onward are used for
    # the other forecast series below (Henry Hub, LNG, and balance).
    steo_forecast = tbl_historical[tbl_historical["date"] >= last_updated].copy()

    # STEO Lower 48 is the sum of the five regional working-inventory series.
    # Do NOT use the STEO U.S. Total series for Lower 48.
    regional_storage_forecast_names = [
        "Natural Gas Working Inventory East Region",
        "Natural Gas Working Inventory Midwest Region",
        "Natural Gas Working Inventory South Central Consuming Region",
        "Natural Gas Working Inventory Mountain Region",
        "Natural Gas Working Inventory Pacific Region",
    ]

    storage_forecast_regions = tbl_historical[
        tbl_historical["series_name"].isin(regional_storage_forecast_names)
    ][["date", "series_name", "value"]].copy()

    # Build the monthly Lower 48 STEO forecast by summing East + Midwest +
    # South Central + Mountain + Pacific for each forecast month.
    lower_48_forecast = (
        storage_forecast_regions
        .groupby("date", as_index=False)["value"]
        .sum(min_count=len(regional_storage_forecast_names))
    )
    lower_48_forecast["series_name"] = "Natural Gas Working Inventory Lower 48"
    lower_48_forecast = lower_48_forecast[["date", "series_name", "value"]]

    # Keep the five regional monthly STEO forecasts as well, then append the
    # calculated Lower 48 total.
    storage_forecast = pd.concat(
        [storage_forecast_regions, lower_48_forecast],
        ignore_index=True,
    )

    # Keep only STEO rows that occur after the last weekly actual for each
    # region. This makes the forecast a clean monthly continuation of actuals
    # and keeps it completely out of the weekly 5-year calculations above.
    last_actual_by_series = storage_historical.groupby("series_name")["date"].max().to_dict()
    storage_forecast["last_actual"] = storage_forecast["series_name"].map(last_actual_by_series)
    storage_forecast = storage_forecast[
        storage_forecast["last_actual"].notna()
        & (storage_forecast["date"] > storage_forecast["last_actual"])
    ].copy()
    storage_forecast = storage_forecast.drop(columns="last_actual")

    # Forecast storage is monthly STEO only. No 5Y avg/bands are calculated
    # or attached to forecast rows.
    storage_forecast["five_year_avg"] = None
    storage_forecast["five_year_low"] = None
    storage_forecast["five_year_high"] = None
    storage_forecast["historical_forecast"] = "forecast"

    storage_forecast = storage_forecast.drop_duplicates(
        ["series_name", "date"], keep="last"
    ).sort_values(["series_name", "date"])

    storage = pd.concat([storage_historical, storage_forecast], ignore_index=True)
    storage = storage.sort_values(["series_name", "date"])

    # ------------------------------------------------------------------
    # HENRY HUB
    # tbl_hh_spot is the historical source; normalize its series name so the
    # frontend cannot accidentally filter the actual observations out.
    # ------------------------------------------------------------------
    hh = con.execute("SELECT * FROM tbl_hh_spot ORDER BY series_id, date").df()
    hh["date"] = pd.to_datetime(hh["date"])
    hh = hh[["date", "value"]].dropna(subset=["date", "value"]).copy()
    hh["series_name"] = HH_SERIES
    hh["historical_forecast"] = "historical"
    hh = hh[["date", "series_name", "value", "historical_forecast"]]
    hh = hh.sort_values("date").drop_duplicates("date", keep="last")

    hh_forecast = steo_forecast[
        steo_forecast["series_name"] == HH_SERIES
    ][["date", "series_name", "value"]].copy()

    if not hh.empty:
        hh_forecast = hh_forecast[hh_forecast["date"] > hh["date"].max()]

    hh_forecast["historical_forecast"] = "forecast"

    hh = pd.concat([hh, hh_forecast], ignore_index=True)
    hh = hh.sort_values("date")

    # ------------------------------------------------------------------
    # LNG EXPORTS + BALANCE
    # ------------------------------------------------------------------
    rest_series = [
        "Natural Gas LNG Gross Exports",
        "Natural Gas Balancing Item (Consumption - Supply)",
    ]

    rest = tbl_historical[tbl_historical["series_name"].isin(rest_series)].copy()
    rest = rest[["date", "series_name", "value"]]
    rest["historical_forecast"] = "historical"
    rest.loc[rest["date"] >= last_updated, "historical_forecast"] = "forecast"
    rest = rest.sort_values(["series_name", "date"])

    def clean_records(df):
        records = df.to_dict(orient="records")
        for record in records:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
        return records

    return {
        "hh": clean_records(hh),
        "storage": clean_records(storage),
        "rest": clean_records(rest),
    }
