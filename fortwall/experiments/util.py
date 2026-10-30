import csv
from prettytable import PrettyTable

# read response times per url from csv file and convert the response time to ms and round to 2 decimal places
def read_response_times(file_name):
    response_times = {}
    with open(file_name, 'r') as file:
        reader = csv.reader(file)
        # skip header
        next(reader)
        for row in reader:
            url, response_time = row
            response_time = round(float(response_time) * 1000, 2)
            response_times[url] = response_time
    return response_times



# for 3 csv files, read the urls and associated response times from the files and per url :  write to a new csv in format: url, def, npl, pl

def merge_results(file_num):
    response_times_def = read_response_times(f'multi-url-def/response_time_def_{file_num}.csv')
    response_times_pl = read_response_times(f'multi-url-pl/response_time_prt_pl_{file_num}.csv')
    response_times_npl = read_response_times(f'multi-url-npl/response_time_prt_npl_{file_num}.csv')
    
    # when writing to csv consider that the urls are in different order in each file
    urls = set(response_times_def.keys()) | set(response_times_pl.keys()) | set(response_times_npl.keys())
    # print(urls)
    with open(f'merged_response_times_{file_num}.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['URL', 'DEF', 'NPL', 'PL'])
        for url in urls:
            writer.writerow([
                url,
                response_times_def.get(url, ''),
                response_times_npl.get(url, ''),
                response_times_pl.get(url, '')
            ])
    
        # Create a PrettyTable object with appropriate column headers
    # table = PrettyTable()
    # table.field_names = ["URL", "DEF (ms)", "NPL (ms)", "PL (ms)"]

    # # Fill the table with data
    # for url in urls:
    #     def_time = response_times_def.get(url, "N/A")
    #     npl_time = response_times_npl.get(url, "N/A")
    #     pl_time = response_times_pl.get(url, "N/A")
    #     table.add_row([url, def_time, npl_time, pl_time])

    # # Print the table
    # print(table)

def read_merged_results(file_names):
    # This dictionary will hold the data in the form:
    # {url: {concurrency: {"DEF": time, "NPL": time, "PL": time}}}
    data = {}

    for file_name in file_names:
        concurrency_level = file_name.split('_')[-1].split('.')[0]  # Extract concurrency level from the filename
        with open(file_name, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                url = row['URL']
                if url not in data:
                    data[url] = {}
                data[url][concurrency_level] = {
                    "DEF (ms)": row['DEF'],
                    "NPL (ms)": row['NPL'],
                    "PL (ms)": row['PL']
                }

    return data

def display_data(data):
    for url, timings in data.items():
        # Create a table for each URL
        table = PrettyTable()
        table.field_names = ["Concurrency Level", "DEF (ms)", "NPL (ms)", "PL (ms)"]
        
        # Sort the concurrency levels numerically before adding them to the table
        sorted_levels = sorted(timings.keys(), key=lambda x: int(x))
        for level in sorted_levels:
            table.add_row([level, timings[level]["DEF (ms)"], timings[level]["NPL (ms)"], timings[level]["PL (ms)"]])

        print(f"URL: {url}")
        print(table)
        print("\n")   



if __name__ == "__main__":
    # for files with numbers 1, 2, 4, 8, 16, 32 
    # for i in [1, 2, 4, 8, 16, 32]:
    #     response_times = read_response_times(f'multi-url-npl/response_time_prt_npl_{i}.csv')
    #     print(f"\nResponse Times for {i} concurrent requests:")
    #     for url, response_time in response_times.items():
    #         print(f"{response_time}")
    
    # Merged-results report (disabled)
    # merge_results(1)
    # merge_results(2)
    # merge_results(4)
    # merge_results(8)
    # merge_results(16)
    # merge_results(32)
    
    # file_names = [
    # "merged_response_times_1.csv",
    # "merged_response_times_2.csv",
    # "merged_response_times_4.csv",
    # "merged_response_times_8.csv",
    # "merged_response_times_16.csv",
    # "merged_response_times_32.csv"
    #     ]
    # data = read_merged_results(file_names)
    # display_data(data)

    # Multi-pool results report
    # read the response times from report_mpool/p3 folder
    # loop in files of the folder
    res_files = [1,2,4,8,16,32]
    for j in range (3,9):
        print('The results for the pool size:', j)
        for i in range (len(res_files)):
            file_name = f"largerun/mpool/{j}/response_time_prt_pl_{res_files[i]}.csv"
            response_times = read_response_times(file_name)
            print(f"\nResponse Times for {res_files[i]} concurrent requests:")
            for url, response_time in response_times.items():
                print(f"{url}: {response_time} ms")
         
    # res_files = [1,2,4,8,16,32]
    # for i in range (len(res_files)):
    #     file_name = f"response_time_prt_pl_{res_files[i]}.csv"
    #     response_times = read_response_times(file_name)
    #     print(f"\nResponse Times for {res_files[i]} concurrent requests:")
    #     for url, response_time in response_times.items():
    #         print(f"{url}: {response_time} ms")     