"""CLI: research SIBO-friendly restaurants with Claude and write the PDF to the current directory.

    python generate_pdf.py Wageningen Italian
    python generate_pdf.py --lat 51.9692 --lon 5.6654 [cuisine]
"""

import argparse
import asyncio
import logging
from pathlib import Path

from sibo_bot.models import SearchQuery
from sibo_bot.pdf import render_report, report_filename
from sibo_bot.research import RestaurantResearcher


def parse_args() -> SearchQuery:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("words", nargs="*", help="city followed by optional cuisine, or just the cuisine with --lat/--lon")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    args = parser.parse_args()

    if args.lat is not None or args.lon is not None:
        if args.lat is None or args.lon is None:
            parser.error("--lat and --lon must be given together")
        return SearchQuery(latitude=args.lat, longitude=args.lon, cuisine=" ".join(args.words) or None)
    if not args.words:
        parser.error("give a city or --lat/--lon")
    return SearchQuery.from_text(" ".join(args.words))


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    query = parse_args()
    print(f"Researching SIBO-friendly restaurants near {query.label}...")
    report = await RestaurantResearcher().research(query)
    path = Path(report_filename(report))
    path.write_bytes(render_report(report))
    print(f"Wrote {path.resolve()} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
