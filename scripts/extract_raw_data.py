"""Cut data/raw/ out of the two daily files from the Kenneth R. French Data Library.

Usage: python scripts/extract_raw_data.py <folder holding the two downloaded zips>

The zips are 10_Industry_Portfolios_daily_CSV.zip and F-F_Research_Data_Factors_daily_CSV.zip from
https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html. They are not committed.
Values are copied as text, so re-running on the same vintage gives byte-identical files.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
# Two years of history before the first day a run may report, which is the first trading day of 1986.
FIRST, LAST = 19840103, 20260930


def data_rows(lines: list[str], start: int) -> list[list[str]]:
    rows = []
    for line in lines[start:]:
        if not line.strip() or not line[0].isdigit():
            break
        parts = [x.strip() for x in line.split(",")]
        if FIRST <= int(parts[0]) <= LAST:
            rows.append(parts)
    return rows


def write(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="\n") as f:
        f.write(",".join(header) + "\n")
        f.writelines(",".join(r) + "\n" for r in rows)


def main(folder: Path) -> None:
    text = zipfile.ZipFile(folder / "10_Industry_Portfolios_daily_CSV.zip").read("10_Industry_Portfolios_Daily.csv")
    lines = text.decode("latin-1").splitlines()
    start = next(i for i, line in enumerate(lines) if "Average Value Weighted Returns" in line)
    header = lines[start + 1].strip(",").split(",")
    industry = data_rows(lines, start + 2)
    write(RAW / "ff_industry10_vw_daily_pct.csv", ["date", *header], industry)

    text = zipfile.ZipFile(folder / "F-F_Research_Data_Factors_daily_CSV.zip").read("F-F_Research_Data_Factors_daily.csv")
    lines = text.decode("latin-1").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(",Mkt-RF"))
    factors = data_rows(lines, start + 1)
    write(RAW / "ff_factors_daily_pct.csv", ["date", "MktRF", "SMB", "HML", "RF"], factors)

    assert [r[0] for r in industry] == [r[0] for r in factors], "the two files cover different dates"
    print(f"{len(industry)} days, {industry[0][0]} to {industry[-1][0]}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
