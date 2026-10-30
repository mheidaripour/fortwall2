import matplotlib.pyplot as plt
import csv

# read 10 csv report files, which include the response time for each URL for the protected and pooling application the no_pool applications, then per url draw a scatter plot
def plot_response_time():
    app_types = ['org', 'prt_pl', 'prt_npl']
    for app_type in app_types:
        for num_requests in range(1, 11):
            response_times = {}
            with open(f'response_time_{app_type}_{num_requests}.csv', 'r') as file:
                reader = csv.reader(file)
                for row in reader:
                    url, avg_response_time = row
                    response_times[url] = float(avg_response_time)
            
            plt.figure()
            plt.scatter(response_times.keys(), response_times.values())
            plt.title(f'Average Response Time for {app_type} with {num_requests} concurrent requests')
            plt.xlabel('URL')
            plt.ylabel('Average Response Time (seconds)')
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig(f'response_time_{app_type}_{num_requests}.png')