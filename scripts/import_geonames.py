#!/usr/bin/env python3
import io
import os
import sqlite3
import urllib.request
import zipfile

GEONAMES_URL = "https://download.geonames.org/export/dump/cities500.zip"
ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cities.sqlite3")


def fetch_admin1_names():
    with urllib.request.urlopen(ADMIN1_URL) as response:
        text = response.read().decode("utf-8")
    names = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        names[parts[0]] = parts[1]
    return names


def main():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)

    print("Downloading admin1 names...")
    admin1_names = fetch_admin1_names()

    print("Downloading GeoNames cities500.zip...")
    with urllib.request.urlopen(GEONAMES_URL) as response:
        data = response.read()

    print("Extracting...")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        with zf.open("cities500.txt") as f:
            lines = f.read().decode("utf-8").splitlines()

    print(f"Importing {len(lines)} cities...")

    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        DROP TABLE IF EXISTS cities_fts;
        DROP TABLE IF EXISTS cities;
        CREATE TABLE cities (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            ascii_name TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            country_code TEXT NOT NULL,
            state TEXT,
            population INTEGER
        );
    """)

    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 15:
            continue
        try:
            country_code = parts[8]
            admin1_code = parts[10]
            state = (
                admin1_names.get(f"{country_code}.{admin1_code}")
                if admin1_code
                else None
            )
            rows.append(
                (
                    int(parts[0]),
                    parts[1],
                    parts[2],
                    float(parts[4]),
                    float(parts[5]),
                    country_code,
                    state,
                    int(parts[14]) if parts[14] else 0,
                )
            )
        except (ValueError, IndexError):
            continue

    db.executemany("INSERT INTO cities VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)

    db.executescript("""
        CREATE VIRTUAL TABLE cities_fts USING fts5(
            name,
            ascii_name,
            content='cities',
            content_rowid='id'
        );
        INSERT INTO cities_fts(cities_fts) VALUES('rebuild');
    """)

    db.commit()
    db.close()
    print(f"Done: {len(rows)} cities imported.")


if __name__ == "__main__":
    main()
