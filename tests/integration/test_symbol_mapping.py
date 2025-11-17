"""Test script to see what message types we receive from Databento."""

import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import databento as db


def main():
    """Main function to run the symbol mapping test."""
    # Get API key from environment
    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        print("ERROR: DATABENTO_API_KEY environment variable not set")
        return 1

    print("Connecting to Databento live feed...")
    client = db.Live(key=api_key)

    try:
        client.subscribe(
            dataset="GLBX.MDP3",
            schema="ohlcv-1s",
            stype_in="continuous",
            symbols=["ES.c.0", "NQ.c.0"],
        )

        print("Streaming... will show first 50 messages:\n")

        count = 0
        for record in client:
            count += 1

            # Show message type and relevant fields
            msg_type = type(record).__name__
            print(f"{count}. {msg_type}")

            # If it's a SymbolMappingMsg, show the mapping
            if msg_type == "SymbolMappingMsg":
                print(f"   → instrument_id={record.instrument_id}")
                print(f"   → stype_in_symbol={record.stype_in_symbol}")
                print(f"   → stype_out_symbol={record.stype_out_symbol}")

            # If it's an OHLCV record, show symbol/instrument_id
            elif hasattr(record, "instrument_id"):
                symbol_attr = getattr(record, "symbol", "N/A")
                print(
                    f"   → instrument_id={record.instrument_id}, symbol attr={symbol_attr}, close={getattr(record, 'close', 'N/A')}"
                )

            if count >= 50:
                break

        client.terminate()
        print("\nDone!")
        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        try:
            client.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
