"""TLC Taxi flow example for lokki."""

import pandas as pd

from lokki import flow, step


# Step 1: download/load dataset
@step
def load_tlc_data() -> list[dict]:
    """
    Downloads a publicly available NYC taxi trips parquet file.
    Example: January 2023 green taxi trips (~130MB parquet)
    Returns a list of dicts grouped by passenger count.
    """
    url = (
        "https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2023-01.parquet"
    )
    df = pd.read_parquet(url)
    groups = df.groupby("passenger_count")
    # Return list of (passenger_count, group_df) tuples for processing
    return [
        {"passengers": key, "df": group.to_dict("records")} for key, group in groups
    ]


# Step 2: compute statistics for a single group
@step
def compute_group_stats(group_data: dict) -> dict:
    """
    Example group stats: count, mean fare, max tip
    """
    records = group_data["df"]
    fares = [r["fare_amount"] for r in records if "fare_amount" in r]
    tips = [r["tip_amount"] for r in records if "tip_amount" in r]
    return {
        "passengers": group_data["passengers"],
        "count": len(records),
        "avg_fare": sum(fares) / len(fares) if fares else 0,
        "max_tip": max(tips) if tips else 0,
    }


# Step 3: aggregate all group statistics
@step
def aggregate_stats(stats_list: list[dict]) -> dict:
    """
    Combine group stats into overall summary
    """
    total_count = sum(s["count"] for s in stats_list)
    avg_fare = sum(s["avg_fare"] * s["count"] for s in stats_list) / total_count
    max_tip = max(s["max_tip"] for s in stats_list)
    return {
        "total_count": total_count,
        "overall_avg_fare": avg_fare,
        "max_tip": max_tip,
    }


@flow
def tlc_taxi_flow():
    # Group by passenger count for example
    return load_tlc_data().map(compute_group_stats).agg(aggregate_stats)


if __name__ == "__main__":
    from lokki import main

    main(tlc_taxi_flow)
