import humanize
import json
import os
import pytz
import requests
import time
import yaml
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Union
from urllib.parse import quote


def download_reddit_search(
    subreddit: str, search_query: str
) -> Optional[BeautifulSoup]:
    base_url = "https://old.reddit.com/r/{}/search"
    params = {
        "q": search_query,
        "restrict_sr": "on",
        "include_over_18": "on",
        "sort": "new",
        "t": "week",
    }

    url = base_url.format(quote(subreddit))
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"
    }
    a = requests.adapters.HTTPAdapter(max_retries=20)
    session = requests.Session()
    session.cookies.set("over18", "1")
    session.mount("https://", a)
    try:
        response = session.get(url, params=params, headers=headers, timeout=5.0)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"An error occurred while fetching the URL: {e}")
        return None


def parse_reddit_search_results(
    soup: BeautifulSoup,
) -> List[Dict[str, Union[str, datetime]]]:
    results = []
    search_results = soup.find_all("div", class_="search-result-link")

    for result in search_results:
        post_data = {}

        # Extract the post ID
        post_data["id"] = result.get("data-fullname", "").split("_")[-1]

        # Extract the post title
        title_element = result.find("a", class_="search-title")
        post_data["title"] = (
            title_element.text.strip() if title_element else "No title found"
        )

        author_element = result.find("a", class_="author")
        post_data["author"] = author_element.text if author_element else "Unknown"

        # Extract the post link
        post_data["link"] = (
            title_element["href"]
            if title_element and title_element.has_attr("href")
            else ""
        )

        # If the link is relative, make it absolute
        if post_data["link"].startswith("/"):
            post_data["link"] = f"https://www.reddit.com{post_data['link']}"

        # Extract the post time
        time_element = result.find("time")
        if time_element and time_element.has_attr("datetime"):
            time_str = time_element["datetime"]
            try:
                post_data["time"] = datetime.fromisoformat(time_str).replace(
                    tzinfo=pytz.UTC
                )
            except ValueError:
                post_data["time"] = None
        else:
            post_data["time"] = None

        results.append(post_data)

    return results


def fetch_and_parse_reddit_search(
    subreddit: str, search_query: str
) -> List[Dict[str, str]]:
    soup = download_reddit_search(subreddit, search_query)
    if soup:
        return parse_reddit_search_results(soup)
    return []


def send_pushbullet_notification(title, body):
    api_key = os.environ.get("PUSHBULLET_API_KEY")

    if not api_key:
        raise ValueError("PUSHBULLET_API_KEY environment variable is not set")

    url = "https://api.pushbullet.com/v2/pushes"
    headers = {"Access-Token": api_key, "Content-Type": "application/json"}
    data = {"type": "note", "title": title, "body": body}

    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        print("Notification sent successfully!")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send notification: {e}")


def send_reddit_notifications(
    subreddit: str, search_query: str, notified_ids: Set[str]
):
    """
    Check for new Reddit posts and send notifications.

    Args:
    subreddit (str): The subreddit to search in.
    search_query (str): The search query to use.
    notified_ids (Set[str]): A set of post IDs that have already been notified about.
    """
    # Fetch search results
    posts = fetch_and_parse_reddit_search(subreddit, search_query)
    notified_cnt = 0
    # Check for new posts and send notifications
    for post in posts:
        if post["id"] not in notified_ids:
            # Calculate time difference
            time_diff = datetime.now(pytz.utc) - post["time"]

            # Construct notification message
            title = (
                f"New post in r/{subreddit} by {post['author']} {humanize.naturaltime(time_diff)}"
            )
            body = (
                f"Title: {post['title']}\n"
                f"Author: {post['author']}\n"
                f"Time: {post['time'].astimezone(pytz.timezone('America/New_York')).isoformat()}\n"
                f"Link: {post['link']}"
            )

            # Send notification
            send_pushbullet_notification(title, body)
            notified_cnt += 1

            # Add to notified set
            notified_ids.add(post["id"])

    print(
        f"Checked for new posts. Total posts: {len(posts)}, new posts: {notified_cnt}"
    )


def load_search_config(file_path: str) -> List[Dict[str, str]]:
    """
    Loads subreddit-search pairs from a YAML file.

    Args:
    file_path (str): The path to the YAML configuration file.

    Returns:
    List[Dict[str, str]]: A list of dictionaries, each containing 'subreddit' and 'search_query' keys.

    Raises:
    FileNotFoundError: If the specified file is not found.
    yaml.YAMLError: If there's an error parsing the YAML file.
    ValueError: If the YAML file is not in the expected format.
    """
    try:
        with open(file_path, "r") as file:
            config = yaml.safe_load(file)

        if not isinstance(config, list):
            raise ValueError(
                "YAML file should contain a list of subreddit-search pairs"
            )

        search_configs = []
        for item in config:
            if (
                not isinstance(item, dict)
                or "subreddit" not in item
                or "search_query" not in item
            ):
                raise ValueError(
                    "Each item in the YAML file should be a dictionary with 'subreddit' and 'search_query' keys"
                )
            search_configs.append(
                {"subreddit": item["subreddit"], "search_query": item["search_query"]}
            )

        return search_configs

    except FileNotFoundError:
        print(f"Config file not found: {file_path}")
        raise
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        raise
    except ValueError as e:
        print(f"Invalid YAML format: {e}")
        raise


def main():
    cfg = load_search_config("searches.yml")
    notified_ids_fname = "notified_ids.json"
    try:
        with open(notified_ids_fname, "r") as f:
            notified_ids = set(json.load(f))
    except FileNotFoundError:
        notified_ids = set()

    while True:
        print(
            f"Searching at {datetime.now().astimezone(pytz.timezone('America/New_York'))}"
        )
        try:
            for search_config in cfg:
                print(
                    f"Searching in r/{search_config['subreddit']} for '{search_config['search_query']}'"
                )
                send_reddit_notifications(
                    search_config["subreddit"],
                    search_config["search_query"],
                    notified_ids,
                )
                time.sleep(10)
            with open(notified_ids_fname, "w") as f:
                json.dump(list(notified_ids), f)
        except Exception as e:
            print(f"An error occurred: {e}")
        print("Sleeping for 5 minutes...")
        time.sleep(300)


if __name__ == "__main__":
    main()
