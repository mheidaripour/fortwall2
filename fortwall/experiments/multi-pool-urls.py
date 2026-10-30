import experiment as exp
import argparse


# read urls from the file pool-urls and load into a list of multi-pool-urls

def read_urls(file_name):
    urls = []
    with open(file_name, 'r') as file:
        for line in file:
            urls.append(line.strip())
    return urls



# main function to handle the concurrent requests
parser = argparse.ArgumentParser(description="Measure response times for URLs with concurrent requests.")
parser.add_argument('-req','--num_requests', type=int,  nargs='?', help="Number of concurrent requests per URL")
parser.add_argument('-t','--app_type', type=str, help="type of the application: def, prt_pl, prt_npl")
# add argument for the filename
parser.add_argument('-f','--file_name', type=str, help="name of the file containing the urls")
args = parser.parse_args()

urls = read_urls(args.file_name)
# concatenate the http://localhost:8000 to the urls as prefix
urls = [f"http://localhost:8000{url}" for url in urls]
# print urls spareted by new line
print("\n".join(urls))

# print(urls)
# exit()
print('starting the requests...')
exp.run_requests(urls, 1, app_type=args.app_type)
exp.run_requests(urls, 2, app_type=args.app_type)
exp.run_requests(urls, 4, app_type=args.app_type)
exp.run_requests(urls, 8, app_type=args.app_type)
exp.run_requests(urls, 16, app_type=args.app_type)
exp.run_requests(urls, 32, app_type=args.app_type)
print('finished the requests!')
