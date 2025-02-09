import csv
import json
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Function to convert a CSV to JSON
# Takes the file paths as arguments
def convert(csv_file_path, json_file_path):
    # create a dictionary
    data = {}
    # Open a csv reader called DictReader
    with open(csv_file_path, encoding='utf-8') as csvf:
        # Remove BOM if present
        content = csvf.read().lstrip('\ufeff')
        csvf.seek(0)
        csv_reader = csv.DictReader(content.splitlines())
        # Convert each row into a dictionary
        # and add it to data
        for rows in csv_reader:
            try:
                # Assuming a column named 'Ticker' or 'Symbol' to be the primary key
                key = rows.get('Ticker') or rows.get('Symbol')
                if key is None:
                    raise KeyError('Ticker or Symbol')
                if 'Symbol' in rows:
                    rows['Ticker'] = rows.pop('Symbol')
                data[key] = rows
            except KeyError as e:
                logging.error(f"Key {e} not found in {csv_file_path}")
                continue

    # Convert the dictionary to a list of dictionaries
    data_list = list(data.values())

    # Open a json writer, and use the json.dumps()
    # function to dump data
    with open(json_file_path, 'w', encoding='utf-8') as jsonf:
        jsonf.write(json.dumps(data_list, indent=4))

def main():
    config_folder = 'config'
    logging.info(f'Exploring config folder: {config_folder}')
    for filename in os.listdir(config_folder):
        if filename.endswith('.csv'):
            csv_file_path = os.path.join(config_folder, filename)
            json_file_path = os.path.join(config_folder, filename.replace('.csv', '.json'))
            logging.info(f'Converting {csv_file_path} to {json_file_path}')
            convert(csv_file_path, json_file_path)

if __name__ == "__main__":
    main()
