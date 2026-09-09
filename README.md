# python-stock-data-fetcher
A Python client to fetch stock market data from Finnhub.io and Alpha Vantage APIs.

## Installation
Install the package via install script:
``` 
$ sh install_data_fetcher.sh
``` 
For development or local testing, clone the repository and install in editable mode:
``` 
$ git clone https://github.com/sikienzl/python-stock-data-fetcher.git
$ cd python-stock-data-fetcher
$ git checkout develop
$ pip3 install -r requirements.txt
```

## Contributing
Contributions are welcome! Feel free to:
* Report issues: [GitHub Issues](https://github.com/sikienzl/python-stock-data-fetcher/issues)
* Submit pull requests for improvements.

## Configuration
1. Add your API keys to a `.env` file:
```
FINNHUB_API_KEY=your_finnhub_key
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key
```
2. The `.env` file will be automatically loaded when using the client.

## License
[Apache License Version 2.0](https://github.com/sikienzl/python-stock-data-fetcher/blob/main/LICENSE)

Maintainer contact: sikienzl.github@t-online.de