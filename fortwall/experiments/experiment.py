import concurrent.futures
import requests
import time
from collections import defaultdict
import argparse
import csv

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

# Main function to handle concurrent requests
def run_requests(urls, num_requests, app_type):
    response_times = defaultdict(list)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(urls) * num_requests) as executor:
        futures = [executor.submit(send_request, url) for url in urls for _ in range(num_requests)]
        
        for future in concurrent.futures.as_completed(futures):
            try:
                url, status_code, response_time = future.result()
                response_times[url].append(response_time)
                if status_code is not None:
                    print(f"URL: {url}, Status Code: {status_code}, Response Time: {response_time:.4f} seconds")
                else:
                    print(f"URL: {url}, Request failed, Response Time: {response_time:.4f} seconds")
            except Exception as exc:
                print(f"Generated an exception: {exc}")
    
    # Calculate and print the average response time for each URL
    print("\nAverage Response Times:")
    # output the response time for each URl in a csv file
    with open(f'response_time_{app_type}_{num_requests}.csv', 'w') as file:
        writer = csv.writer(file)
        for url, times in response_times.items():
            avg_response_time = sum(times) / len(times)
            print(f"URL: {url}, Average Response Time: {avg_response_time:.4f} seconds")
            writer.writerow([url, avg_response_time])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Measure response times for URLs with concurrent requests.")
    parser.add_argument('-req','--num_requests', type=int, help="Number of concurrent requests per URL")
    parser.add_argument('-t','--app_type', type=str, help="type of the application: org, prt_pl, prt_npl")
    args = parser.parse_args()
    
    # Example URL list
    urls = [
        "http://localhost:8000/wp-admin",
        "http://localhost:8000/wp-login.php",
        "http://localhost:8000/wp-comments-post.php",
        "http://localhost:8000/wp-admin/load-scripts.php",
        "http://localhost:8000/index.php",
        "http://localhost:8000/?cat=1",
        "http://localhost:8000/?p=1#comments"
    ]
    
    
    # urls = [
    #         "http://localhost:8000/wp-login.php",
    #         "http://localhost:8000/index.php"
    #     ]

    # main(urls, args.num_requests, app_type=args.app_type)

    # runt the main function for number of requests [1,30]
    # for i in range(1,31):
    #     main(urls, i, app_type=args.app_type)
        
    # run parallel requests with different levels of concurrency: 1, 2 , 4, 8, 16, 32
    run_requests(urls, 1, app_type=args.app_type)
    run_requests(urls, 2, app_type=args.app_type)
    run_requests(urls, 4, app_type=args.app_type)
    run_requests(urls, 8, app_type=args.app_type)
    run_requests(urls, 16, app_type=args.app_type)
    run_requests(urls, 32, app_type=args.app_type)