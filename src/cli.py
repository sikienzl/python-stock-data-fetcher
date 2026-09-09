from trading import (
    fetch_finnhub_news,
    fetch_trading_news,
    fetch_data,
    FinnhubClient,
)

def main():
    print("=== Trading Data Fetcher ===")
    print("\n1. Fetch Finhub News")
    fetch_finnhub_news()

    print("\n2. Fetch Trading News")
    fetch_trading_news()

    print("\n3. Fetch Stock Data")
    try:
        data = fetch_data("AAPL", provider="finnhub")
        print(f"AAPL Quote: {data}")
    except Exception as error:
        print(f"Error fetching stock data: {error}")

if __name__ == "__main__":
    main()