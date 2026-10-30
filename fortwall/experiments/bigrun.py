import concurrent.futures
import requests
import time
from collections import defaultdict
import argparse
import csv
from tqdm import tqdm

# Function to send a request and return the response time
def send_request(url):
    start_time = time.time()
    try:
        response = requests.get(url)
        end_time = time.time()
        response_time = end_time - start_time
        return url, response.status_code, response_time
    except requests.RequestException as e:
        end_time = time.time()
        response_time = end_time - start_time
        return url, None, response_time

def run_requests(urls, num_requests, app_type, total_requests=15000):
    import math

    response_times = defaultdict(list)
    num_urls = len(urls)

    print(f"\n[Concurrency Level = {num_requests}] Starting {total_requests} total requests across {num_urls} URLs...")

    # Each thread will handle one request, so we batch in num_requests at a time
    # This is how many batches we need to reach total_requests
    total_batches = math.ceil(total_requests / (num_requests))

    # Distribute URLs evenly across total requests
    url_index = 0
    for batch in tqdm(range(total_batches)):
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = []
            for _ in range(num_requests):
                url = urls[url_index % num_urls]  # round-robin selection
                url_index += 1
                futures.append(executor.submit(send_request, url))
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    url, status_code, response_time = future.result()
                    response_times[url].append(response_time)
                    if status_code is not None:
                        print(f"[Batch {batch+1}] URL: {url}, Status Code: {status_code}, Response Time: {response_time:.4f} sec")
                    else:
                        print(f"[Batch {batch+1}] URL: {url}, FAILED, Response Time: {response_time:.4f} sec")
                except Exception as exc:
                    print(f"[Batch {batch+1}] Exception: {exc}")

    print(f"\n[Concurrency Level = {num_requests}] Finished {total_requests} requests.")

    # Output average response times to CSV
    with open(f'response_time_{app_type}_{num_requests}.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["URL", "Average Response Time (sec)"])
        for url, times in response_times.items():
            avg_time = sum(times) / len(times)
            print(f"URL: {url}, Avg Time: {avg_time:.4f} sec over {len(times)} requests")
            writer.writerow([url, avg_time])


import argparse


# read urls from the file pool-urls and load into a list of multi-pool-urls

def read_urls(file_name):
    urls = []
    with open(file_name, 'r') as file:
        for line in file:
            urls.append(line.strip())
    return urls


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="Measure response times for URLs with concurrent requests.")
    parser.add_argument('-req','--num_requests', type=int,  nargs='?', help="Number of concurrent requests per URL")
    parser.add_argument('-t','--app_type', type=str, help="type of the application: def, prt_pl, prt_npl")
    # add argument for the filename
    parser.add_argument('-f','--file_name', type=str, default = 'pools-urls', help="name of the file containing the urls")
    args = parser.parse_args()
    
    
    urls = read_urls(args.file_name)
    # concatenate the http://localhost:8000 to the urls as prefix
    urls = [f"http://localhost:8000{url}" for url in urls]
    # print urls spareted by new line
    print("\n".join(urls))

    # print(urls)
    # exit()
    print('starting the requests...')
    
    # total requests per concurrency level (not per URL)
    total_requests = 15000

    for concurrency in tqdm([1, 2, 4, 8, 16, 32]):
        run_requests(urls, concurrency, app_type=args.app_type, total_requests=total_requests)
