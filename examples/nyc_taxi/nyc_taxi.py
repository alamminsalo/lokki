"""TLC Taxi flow example for lokki - monthly stats."""

import pandas as pd

from lokki import flow, step


# Step 1: download/load dataset and group by month
@step
def load_tlc_data() -> list[dict]:
    """
    Downloads a publicly available NYC taxi trips parquet file.
    Groups data by pickup month (YYYY-MM).
    Returns a list of dicts grouped by month.
    """
    url = (
        "https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2023-01.parquet"
    )

    df = pd.read_parquet(url)

    # Ensure pickup datetime is parsed
    df["lpep_pickup_datetime"] = pd.to_datetime(df["lpep_pickup_datetime"])

    # Extract year-month (e.g., 2023-01)
    df["year_month"] = df["lpep_pickup_datetime"].dt.to_period("M").astype(str)

    groups = df.groupby("year_month")

    return [{"month": key, "df": group.to_dict("records")} for key, group in groups]


# Step 2: compute statistics for a single month
@step
def compute_month_stats(group_data: dict) -> dict:
    """
    Monthly stats: trip count, mean fare, max tip
    """
    records = group_data["df"]

    fares = [r["fare_amount"] for r in records if "fare_amount" in r]
    tips = [r["tip_amount"] for r in records if "tip_amount" in r]

    return {
        "month": group_data["month"],
        "count": len(records),
        "avg_fare": sum(fares) / len(fares) if fares else 0,
        "max_tip": max(tips) if tips else 0,
    }


# Step 3: aggregate all monthly statistics
@step
def aggregate_stats(stats_list: list[dict]) -> dict:
    """
    Combine monthly stats into a dictionary keyed by month.
    """
    return {
        stat["month"]: {
            "count": stat["count"],
            "avg_fare": stat["avg_fare"],
            "max_tip": stat["max_tip"],
        }
        for stat in stats_list
    }


@flow
def tlc_taxi_flow():
    return load_tlc_data().map(compute_month_stats).agg(aggregate_stats)


if __name__ == "__main__":
    from lokki import main

    main(tlc_taxi_flow)
