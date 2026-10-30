import csv

# load the three csv files

with open('response_time_prt_npl.csv', 'r') as file:
    reader = csv.reader(file)
    response_time_protect_no_pool = list(reader)

with open('response_time_prt_pl.csv', 'r') as file:
    reader = csv.reader(file)
    response_time_protected = list(reader)

with open('response_time_org.csv', 'r') as file:
    reader = csv.reader(file)
    response_time_original = list(reader)

# calulate the overhead of the no_pool and protected response time over the original response time

overhead_protect_no_pool = []
overhead_protected = []

for i in range(len(response_time_original)):
    url = response_time_original[i][0]
    time_original = float(response_time_original[i][1])
    time_protect_no_pool = float(response_time_protect_no_pool[i][1])
    time_protected = float(response_time_protected[i][1])
    
    overhead_protect_no_pool.append([url, ((time_protect_no_pool - time_original)/time_original)*100])
    overhead_protected.append([url, ((time_protected - time_original)/time_original)*100])

# output the overhead of the no_pool and protected response time over the original response time in table format
print("\nOverhead of response times:")
print("\nNo Pool:")
print("URL\t\t\tOverhead")
print("----\t\t\t--------")
for url, overhead in overhead_protect_no_pool:
    print(f"{url}\t{overhead:.4f}")
   
print("\nProtected with pooling:")
print("URL\t\t\tOverhead")
print("----\t\t\t--------")
for url, overhead in overhead_protected:
    print(f"{url}\t{overhead:.4f}")
