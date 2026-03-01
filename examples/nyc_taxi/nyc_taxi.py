"""TLC Taxi flow example for lokki - monthly stats."""

import pandas as pd

from lokki import flow, step


@step
def load_tlc_data(url: str) -> list[dict]:
    """
    Downloads a publicly available NYC taxi trips parquet file.
    Groups data by pickup month (YYYY-MM).
    Returns a list of dicts grouped by month.
    """
    df = pd.read_parquet(url)

    df["lpep_pickup_datetime"] = pd.to_datetime(df["lpep_pickup_datetime"])

    df["year_month"] = df["lpep_pickup_datetime"].dt.to_period("M").astype(str)

    groups = df.groupby("year_month")

    return [{"month": key, "df": group.to_dict("records")} for key, group in groups]


@step
def filter_by_fare(group_data: dict, min_fare: float = 0.0, **kwargs) -> dict:
    """Filter records by minimum fare."""
    if kwargs:
        min_fare = kwargs.get("min_fare", min_fare)

    records = group_data["df"]
    filtered = [r for r in records if r.get("fare_amount", 0) >= min_fare]
    return {"month": group_data["month"], "df": filtered, "count": len(filtered)}


@step
def compute_month_stats(group_data: dict, include_tips: bool = True, **kwargs) -> dict:
    """Monthly stats: trip count, mean fare, max tip."""
    if kwargs:
        include_tips = kwargs.get("include_tips", include_tips)

    records = group_data.get("df", [])

    fares = [r["fare_amount"] for r in records if "fare_amount" in r]
    tips = []
    if include_tips:
        tips = [r["tip_amount"] for r in records if "tip_amount" in r]

    return {
        "month": group_data.get("month", "unknown"),
        "count": group_data.get("count", len(records)),
        "avg_fare": sum(fares) / len(fares) if fares else 0,
        "max_tip": max(tips) if tips else 0,
    }


@step
def aggregate_stats(stats_list: list[dict], sort_by: str = "count") -> dict:
    """Combine monthly stats into a dictionary keyed by month."""
    valid_stats = [s for s in stats_list if s is not None]
    sorted_stats = sorted(valid_stats, key=lambda x: x.get(sort_by, 0), reverse=True)
    return {
        stat["month"]: {
            "count": stat["count"],
            "avg_fare": stat["avg_fare"],
            "max_tip": stat["max_tip"],
        }
        for stat in sorted_stats
    }


@step
def format_output(stats: dict, format_type: str = "summary") -> str:
    """Format the aggregated stats as a string."""
    if format_type == "summary":
        lines = ["NYC Taxi Monthly Stats", "=" * 30]
        for month, data in sorted(stats.items()):
            lines.append(
                f"{month}: {data['count']} trips, "
                f"avg fare: ${data['avg_fare']:.2f}, "
                f"max tip: ${data['max_tip']:.2f}"
            )
        return "\n".join(lines)
    elif format_type == "json":
        import json

        return json.dumps(stats, indent=2)
    else:
        return str(stats)


@flow
def tlc_taxi_flow(
    url: str = "https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2023-01.parquet",
    min_fare: float = 0.0,
    include_tips: bool = True,
    sort_by: str = "count",
    format_type: str = "summary",
):
    """
    NYC Taxi flow demonstrating various lokki API features:
    - Flow-level parameters passed via **kwargs
    - .map() for parallel processing
    - .next() to chain steps inside a map block
    - .agg() for aggregation
    """
    return (
        load_tlc_data(url)
        .map(filter_by_fare)  # Flow params passed via **kwargs
        .next(compute_month_stats)
        .agg(aggregate_stats)
        .next(format_output)
    )


if __name__ == "__main__":
    from lokki import main

    main(tlc_taxi_flow)
