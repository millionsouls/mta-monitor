import os
import requests
import json
import zipfile
import shutil

feeds = {
    "nyct": "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip",
    "lirr": "https://rrgtfsfeeds.s3.amazonaws.com/gtfslirr.zip",
    "mnr": "https://rrgtfsfeeds.s3.amazonaws.com/gtfsmnr.zip"
}

meta_file = "meta.json"
data_dir = "data"

os.makedirs(data_dir, exist_ok=True)

def run_updates():
    # Load ETag/Last-Modified tracking
    if os.path.exists(meta_file):
        with open(meta_file, 'r') as f:
            metadata = json.load(f)
    else:
        metadata = {}

    def check_and_download(name, url):
        print(f"Checking updates for {name}...")
        response = requests.head(url)
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        stored = metadata.get(name, {})

        if stored.get("ETag") == etag and stored.get("Last-Modified") == last_modified:
            print(f"No update needed.")
            return

        print(f"Update detected. Downloading...")
        response = requests.get(url)
        # Log amount of data downloaded from the GET request
        try:
            downloaded_bytes = len(response.content) if response.content is not None else 0
        except Exception:
            downloaded_bytes = 0
        print(f"Downloaded {downloaded_bytes} bytes from {url}")

        zip_path = os.path.join(data_dir, f"{name}.zip")
        with open(zip_path, 'wb') as f:
            f.write(response.content)

        file_size = os.path.getsize(zip_path)
        print(f"ZIP saved to {zip_path} ({file_size} bytes)")
        extract_path = os.path.join(data_dir, name)

        # Clean up old data
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path)
        os.makedirs(extract_path, exist_ok=True)

        # Extract ZIP
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            print(f"Extracted to {extract_path}")
        except zipfile.BadZipFile:
            print(f"ERROR: {zip_path} is not a valid ZIP file.")
            return

        # Clean up ZIP file
        os.remove(zip_path)
        print(f"Deleted {zip_path}")

        # Save metadata
        metadata[name] = {
            "ETag": etag,
            "Last-Modified": last_modified
        }
        # If this is the NYCT feed, copy stops.txt into the app static folder
        if name == 'nyct':
            # find stops.txt inside the extracted folder (search recursively)
            stops_src = None
            for root, dirs, files in os.walk(extract_path):
                if 'stops.txt' in files:
                    stops_src = os.path.join(root, 'stops.txt')
                    break
            if stops_src:
                static_dir = os.path.join(os.path.dirname(__file__), 'static')
                os.makedirs(static_dir, exist_ok=True)
                stops_dst = os.path.join(static_dir, 'stops.txt')
                try:
                    shutil.copyfile(stops_src, stops_dst)
                    print(f"Copied NYCT stops to {stops_dst}")
                except Exception as e:
                    print(f"WARNING: failed to copy stops.txt to static: {e}")
            else:
                print("WARNING: stops.txt not found in NYCT feed extraction")

    # Process each feed
    # Save to metadata
    for name, url in feeds.items():
        check_and_download(name, url)
    with open(meta_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    print("GTFS updates complete.")
