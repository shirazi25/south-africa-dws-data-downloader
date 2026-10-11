# South Africa DWS Data Downloader

This small Python program downloads river discharge or stage data from South Africa's Department of Water and Sanitation (DWS) Verified Hydrological Data portal. It is intended for researchers and students who need a simple way to retrieve one gauge at a time.

You can select a station in either of two ways:

- enter its DWS gauge number, such as `A2H001`; or
- enter a latitude and longitude and let the program find the nearest gauge in the included catalogue.

The catalogue contains 1,294 South African river gauges and their coordinates. It is provided as `south_africa_dws_gauges.csv` so it can also be viewed or downloaded on its own.

## Data available

`discharge` downloads the DWS daily average flow. The output is in cubic metres per second (`m³/s`).

`stage` downloads the corrected primary water-level observations. The output is in metres (`m`) and keeps the original observation time.

The DWS portal limits a request to 20 years for daily data and one year for primary data. The program automatically divides longer periods into acceptable requests and waits between them.

## Installation

Python 3.10 or newer is recommended.

```bash
pip install -r requirements.txt
```

## Examples

Download discharge for one gauge. If no dates are supplied, the default period is 1 January to 31 December 2023.

```bash
python download_dws_data.py --gauge A2H001 --variable discharge
```

Download stage for a chosen period:

```bash
python download_dws_data.py --gauge A2H001 --variable stage --start-date 2023-01-01 --end-date 2023-12-31
```

Find the closest listed gauge to a location and download its discharge:

```bash
python download_dws_data.py --coordinates -25.73386 27.85969 --variable discharge
```

Choose the output filename:

```bash
python download_dws_data.py --gauge A2H001 --variable discharge --output my_discharge.csv
```

Without `--output`, results are saved in the `data` directory. Discharge files contain the gauge number, date, discharge, and quality code. Stage files contain the gauge number, date and time, stage, and quality code.

## Quality codes

The `quality_code` column is copied directly from the DWS result. It is important to keep this value because it describes the status or quality assigned by DWS to that observation. The meaning should be checked using the **Quality Codes** link on the relevant station page in the [DWS Verified Hydrological Data portal](https://www.dws.gov.za/Hydrology/Verified/hymain.aspx), since the codes are maintained by the data provider.

## Notes

The coordinates option chooses the nearest station geographically. It does not guarantee that the station is on the same river or that it contains data for the requested dates. For a hydrological study, check the selected station and catchment before using the result.

DWS data are continuously updated and reviewed. A successful request can still return no records when a station has no observations for the chosen variable or dates.

## Data source

Department of Water and Sanitation, South Africa: [Verified Hydrological Data](https://www.dws.gov.za/Hydrology/Verified/hymain.aspx).

## License

The Python code is released under the MIT License. Data downloaded with the program remain subject to the terms and attribution requirements of the original DWS source.
