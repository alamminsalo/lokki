from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Optional

import duckdb
import pandas as pd
from fast_flights import FlightData, Passengers, Result, get_flights

from lokki import flow, step


@step
def generate_route_date_pairs(
    route: tuple[str, str], start_date: str, end_date: str
) -> list:
    routes = [
        dict(origin=route[0], destination=route[1]),
        dict(origin=route[1], destination=route[0]),
    ]

    date_list = []
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end:
        date_list.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    return [(r["origin"], r["destination"], d) for r in routes for d in date_list]


@step(retry={"retries": 2, "delay": 1, "backoff": 2})
def fetch_flights(route_tuple: tuple) -> Optional[pd.DataFrame]:
    origin, destination, date = route_tuple

    try:
        result: Result = get_flights(
            flight_data=[
                FlightData(date=date, from_airport=origin, to_airport=destination),
            ],
            trip="one-way",
            seat="economy",
            passengers=Passengers(
                adults=1, children=0, infants_in_seat=0, infants_on_lap=0
            ),
            fetch_mode="local",
        )

    except Exception as e:
        print(e)
        return None

    if not result.flights:
        print("No flights in result!")
        return None

    df = pd.json_normalize(
        [asdict(flight) for flight in result.flights if flight.stops != "Unknown"]
    )
    df = df.dropna(subset=["name", "departure", "arrival", "duration"])

    df["origin"] = origin
    df["destination"] = destination
    df["date"] = date

    print(f"{date} {origin} -> {destination}: Found {len(df)} flights")

    return df


@step
def collect_dataframes(dfs: list) -> pd.DataFrame:
    filtered_dfs = [df for df in dfs if df is not None]
    if not filtered_dfs:
        return pd.DataFrame()

    df = pd.concat(filtered_dfs, ignore_index=True)

    return duckdb.sql("""
        SELECT
            * exclude (departure, arrival, price, delay, name, date),
            name as carrier,
            date::date as date,
            departure.strptime('%-I:%M %p on %a, %b %-d')::time as departure,
            arrival.strptime('%-I:%M %p on %a, %b %-d')::time as arrival,
            (price[2:])::float as price,
            price[1] as currency,
        FROM df
        WHERE price.regexp_full_match('€\\d+')
        AND NOT (name LIKE 'Self transfer%')
        ORDER BY date, origin, destination, departure
    """).df()


@flow
def flight_data_pipeline(
    origin: str = "HEL",
    destination: str = "ARN",
    begin_date: str = "2025-02-01",
    days: int = 2,
):
    """Flight data pipeline using DuckDB for analysis."""
    end_date = (
        datetime.strptime(begin_date, "%Y-%m-%d") + timedelta(days=days)
    ).strftime("%Y-%m-%d")

    return (
        generate_route_date_pairs((origin, destination), begin_date, end_date)
        .map(fetch_flights)
        .agg(collect_dataframes)
    )


if __name__ == "__main__":
    from lokki import main

    main(flight_data_pipeline)
