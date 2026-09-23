from pathlib import Path
import time
import requests


COMMONS_API = "https://commons.wikimedia.org/w/api.php"

HEADERS = {
    "User-Agent": (
        "PL-Analytics-Football-Kits/1.0 "
        "(football kit research project)"
    )
}

REQUEST_DELAY = 1.0
MAX_RETRIES = 5


PARTS = {
    "left_arm": "Kit left arm{pattern}.png",
    "body": "Kit body{pattern}.png",
    "right_arm": "Kit right arm{pattern}.png",
    "shorts": "Kit shorts{pattern}.png",
    "socks": "Kit socks{pattern}.png",
}


BASE_FILES = {
    "left_arm": "Kit left arm.svg",
    "body": "Kit body.svg",
    "right_arm": "Kit right arm.svg",
    "shorts": "Kit shorts.svg",
    "socks": "Kit socks.svg",
}


session = requests.Session()
session.headers.update(HEADERS)


def request_with_retry(url, params=None):

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            response = session.get(
                url,
                params=params,
                timeout=30,
            )

            if response.status_code == 200:
                return response

            if response.status_code == 429:

                retry_after = response.headers.get("Retry-After")

                if retry_after:
                    try:
                        wait_time = float(retry_after)
                    except ValueError:
                        wait_time = 5 * attempt
                else:
                    wait_time = 5 * (2 ** (attempt - 1))

                print("  rate limited (429)")
                print(f"  waiting {wait_time:.0f}s...")

                time.sleep(wait_time)
                continue

            if response.status_code >= 500:

                wait_time = 2 ** attempt

                print(
                    f"  Wikimedia error "
                    f"{response.status_code}"
                )

                print(
                    f"  retrying in {wait_time}s..."
                )

                time.sleep(wait_time)
                continue

            response.raise_for_status()

        except requests.RequestException as error:

            if attempt == MAX_RETRIES:
                raise

            wait_time = 2 ** attempt

            print(f"  network error: {error}")
            print(f"  retrying in {wait_time}s...")

            time.sleep(wait_time)

    raise RuntimeError(
        f"Request failed after "
        f"{MAX_RETRIES} attempts."
    )


def get_file_url(filename):

    params = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "url",
        "titles": f"File:{filename}",
    }

    response = request_with_retry(
        COMMONS_API,
        params=params,
    )

    data = response.json()
    pages = data["query"]["pages"]
    page = next(iter(pages.values()))

    if "missing" in page:
        return None

    imageinfo = page.get("imageinfo")

    if not imageinfo:
        return None

    return imageinfo[0]["url"]


def download_file(url, destination):

    response = request_with_retry(url)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination.write_bytes(
        response.content
    )


def download_base_files(output_directory):

    output_directory = Path(output_directory)

    print()
    print("============================")
    print(" Wikimedia SVG base files")
    print("============================")
    print()

    for part, filename in BASE_FILES.items():

        destination = (
            output_directory
            / f"{part}.svg"
        )

        if destination.exists():
            print(f"Already exists: {destination}")
            continue

        print(f"Looking for: {filename}")

        time.sleep(REQUEST_DELAY)

        url = get_file_url(filename)

        if url is None:
            print(f"  NOT FOUND: {filename}")
            continue

        time.sleep(REQUEST_DELAY)

        try:
            download_file(
                url,
                destination,
            )

        except requests.RequestException as error:
            print(f"  FAILED: {error}")
            continue

        print(f"  downloaded -> {destination}")


def download_pattern(
    pattern,
    part,
    output_directory,
):

    if not pattern:
        return None

    if part not in PARTS:
        raise ValueError(
            f"Unknown kit part: {part}"
        )

    safe_pattern = pattern.replace("/", "_")

    destination = (
        Path(output_directory)
        / safe_pattern
        / f"{part}.png"
    )

    if destination.exists():
        print(f"Already exists: {destination}")
        return str(destination)

    filename = PARTS[part].format(
        pattern=pattern
    )

    print(f"Looking for: {filename}")

    time.sleep(REQUEST_DELAY)

    try:
        url = get_file_url(filename)

    except requests.RequestException as error:
        print(f"  FAILED to find file: {error}")
        return None

    if url is None:
        print(f"  NOT FOUND: {filename}")
        return None

    time.sleep(REQUEST_DELAY)

    try:
        download_file(
            url,
            destination,
        )

    except requests.RequestException as error:
        print(f"  FAILED to download: {error}")
        return None

    print(f"  downloaded -> {destination}")

    return str(destination)


def download_kit_patterns(
    kit_data,
    output_directory,
):

    downloaded = {}

    for part in PARTS:

        part_data = kit_data.get(part)

        if not part_data:
            continue

        pattern = part_data.get("pattern")

        if not pattern:
            continue

        path = download_pattern(
            pattern=pattern,
            part=part,
            output_directory=output_directory,
        )

        downloaded[part] = path

    return downloaded