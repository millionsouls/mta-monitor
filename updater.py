import os
import requests
import json
import zipfile
import shutil

feeds = {
    "nyct": "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip",
    "lirr": "https://rrgtfsfeeds.s3.amazonaws.com/gtfslirr.zip"
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

    # Process each feed
    # Save to metadata
    for name, url in feeds.items():
        check_and_download(name, url)
    with open(meta_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    print("GTFS updates complete.")
