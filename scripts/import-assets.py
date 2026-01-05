import copy
import csv
import json
import os
import requests
import sys
from pathlib import Path


# API Setup
API_URL = "https://gvxfokbptelmvvlxbigh.supabase.co/functions/v1/get-latest-export"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd2eGZva2JwdGVsbXZ2bHhiaWdoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI4NzY4NTAsImV4cCI6MjA2ODQ1Mjg1MH0.QLIyWCf8AGIUDmGlttbqRKrxxBSOBn_B5O-0yuCwlGE",
    "apikey": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd2eGZva2JwdGVsbXZ2bHhiaWdoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI4NzY4NTAsImV4cCI6MjA2ODQ1Mjg1MH0.QLIyWCf8AGIUDmGlttbqRKrxxBSOBn_B5O-0yuCwlGE",
}
script_dir = Path(__file__).parent


def load_json_file(file_name):
    file_path = os.path.join(script_dir, file_name)
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def download_latest_csv(csv_name, secondary_key):
    print(f"Fetching download URLs from API...")

    try:
        # Get the dictionary of URLs
        response = requests.get(API_URL, headers=HEADERS)
        response.raise_for_status()

        # Parse the JSON response
        data = response.json()
        target_key = "csv_files"

        if target_key not in data:
            print(f"Error: The key '{target_key}' was not found in the API response.")
            print(f"Keys found: {list(data.keys())}")
            sys.exit(1)

        csv_download_url = data[target_key][secondary_key]
        print(f"Found URL for {target_key}. Downloading CSV...")

        # Download the actual CSV
        csv_response = requests.get(csv_download_url)
        csv_response.raise_for_status()

        # Save to file
        csv_path = script_dir / csv_name
        csv_content = csv_response.content.decode("utf-8")

        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)

        print(f"Successfully saved {csv_name}.")

    except requests.exceptions.RequestException as e:
        print(f"Network Error: {e}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: API did not return valid JSON.")
        sys.exit(1)


def generate_default_output_path():
    """Returns the Path object for the TTS Saved Objects directory."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Tabletop Simulator" / "Saves" / "Saved Objects"
    elif sys.platform == "linux":
        return (
            home / ".local" / "share" / "Tabletop Simulator" / "Saves" / "Saved Objects"
        )
    else:
        return (
            home
            / "Documents"
            / "My Games"
            / "Tabletop Simulator"
            / "Saves"
            / "Saved Objects"
        )


def main():
    # Import Hex Spirits
    bag_name = "Hex Spirits"
    csv_name = "hex_spirits.csv"
    download_latest_csv(csv_name, "hex_spirits")

    bag = load_json_file("TTSBagTemplate.json")
    tile = load_json_file("HexSpiritTemplate.json")
    bag["ObjectStates"][0]["Nickname"] = bag_name
    bag["ObjectStates"][0]["Transform"]["scaleX"] = 2
    bag["ObjectStates"][0]["Transform"]["scaleY"] = 2
    bag["ObjectStates"][0]["Transform"]["scaleZ"] = 2
    bag["ObjectStates"][0]["ContainedObjects"] = []

    # Load csv and go through rows
    file_path = os.path.join(script_dir, csv_name)
    with open(file_path, mode="r", newline="", encoding="utf-8") as file:
        csv_reader = csv.DictReader(file)
        i = 0
        for row in csv_reader:
            i += 1

            # Skip bad data
            name = row["name"].strip()
            url = row["game_print_image_path"].strip()
            cost = row["cost"].strip()
            if name == "" or url == "" or cost == "":
                print(f"Skipped row {i} due to missing data.")
                continue

            # Build data and attach
            new_tile = copy.deepcopy(tile)
            new_tile["Nickname"] = name
            new_tile["Memo"] = cost
            new_tile["CustomImage"]["ImageURL"] = url
            bag["ObjectStates"][0]["ContainedObjects"].append(new_tile)

            if int(row["cost"]) < 6:
                bag["ObjectStates"][0]["ContainedObjects"].append(new_tile)

    # Save the bag
    bag_path = os.path.join(generate_default_output_path(), f"{bag_name}.json")
    with open(bag_path, "w", encoding="utf8") as f:
        json.dump(bag, f, ensure_ascii=False, indent=2)
    print(f"Successfully created output file at {bag_path}.")

    # Import artifacts
    basic_bag_name = "Artifacts (Basic)"
    guardian_bag_name = "Artifacts (Guardian)"
    other_bag_name = "Artifacts (Other)"
    csv_name = "artifacts.csv"
    download_latest_csv(csv_name, "artifacts")

    bag = load_json_file("TTSBagTemplate.json")
    tile = load_json_file("ArtifactTemplate.json")
    bag["ObjectStates"][0]["Transform"]["scaleX"] = 2
    bag["ObjectStates"][0]["Transform"]["scaleY"] = 2
    bag["ObjectStates"][0]["Transform"]["scaleZ"] = 2
    bag["ObjectStates"][0]["ContainedObjects"] = []

    # Load csv and go through rows
    basic_bag = copy.deepcopy(bag)
    basic_bag["ObjectStates"][0]["Nickname"] = basic_bag_name

    guardian_bag = copy.deepcopy(bag)
    guardian_bag["ObjectStates"][0]["Nickname"] = guardian_bag_name

    other_bag = copy.deepcopy(bag)
    other_bag["ObjectStates"][0]["Nickname"] = other_bag_name

    file_path = os.path.join(script_dir, csv_name)
    with open(file_path, mode="r", newline="", encoding="utf-8") as file:
        csv_reader = csv.DictReader(file)
        i = 0
        for row in csv_reader:
            i += 1

            # Skip bad data
            name = row["name"].strip()
            url = row["card_image_path"].strip()
            if name == "" or url == "":
                print(f"Skipped row {i} due to missing data.")
                continue

            # Build data and attach
            new_tile = copy.deepcopy(tile)
            new_tile["Nickname"] = name
            new_tile["CustomImage"]["ImageURL"] = url

            # Determine proper list
            tags = row["tags"].strip()
            if "Basic" in tags:
                basic_bag["ObjectStates"][0]["ContainedObjects"].append(new_tile)
            elif "Guardian" in tags:
                guardian_bag["ObjectStates"][0]["ContainedObjects"].append(new_tile)
            else:
                other_bag["ObjectStates"][0]["ContainedObjects"].append(new_tile)

    # Save the bags
    bag_path = os.path.join(generate_default_output_path(), f"{basic_bag_name}.json")
    with open(bag_path, "w", encoding="utf8") as f:
        json.dump(basic_bag, f, ensure_ascii=False, indent=2)
    print(f"Successfully created output file at {bag_path}.")

    bag_path = os.path.join(generate_default_output_path(), f"{guardian_bag_name}.json")
    with open(bag_path, "w", encoding="utf8") as f:
        json.dump(guardian_bag, f, ensure_ascii=False, indent=2)
    print(f"Successfully created output file at {bag_path}.")

    bag_path = os.path.join(generate_default_output_path(), f"{other_bag_name}.json")
    with open(bag_path, "w", encoding="utf8") as f:
        json.dump(other_bag, f, ensure_ascii=False, indent=2)
    print(f"Successfully created output file at {bag_path}.")


if __name__ == "__main__":
    main()
