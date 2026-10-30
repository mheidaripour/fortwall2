import re
import intersection as its
from urlanalyze import url_analysis


total_syscalls = 333
SN_base = 20

# sysfilter output for the php interpreter allow-list
sysfilter_syscalls = [0,1,3,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,24,25,28,32,33,37,38,
                   39,41,42,43,44,45,47,48,49,50,51,52,53,54,55,56,59,60,61,62,63,72,73,
                   74,75,77,79,80,81,82,83,84,86,87,88,89,90,91,92,93,94,95,96,98,99,100,
                   102,104,105,106,107,108,109,110,111,112,113,114,115,116,117,119,121,
                   124,137,138,140,141,142,143,144,145,146,147,157,161,186,201,202,203,
                   204,217,228,230,231,234,257,259,262,270,273,280,293,302,307,318,326,
                   334,435,436]

# Sample input
syscall_classifications = """
System Call Classification Applicable System Calls
Arbitrary Code Execution execve, execveat, fork, vfork, clone, ptrace
Memory Permissions mprotect, mmap, mremap, remap_file_pages
Privilege Escalation chmod, setuid, setgid, setreuid
Networking socket, bind, connect, listen, accept, accept4
"""

# Function to read the system call table
def read_syscall_table(file_path):
    """
    Reads the system call table from the given file and returns a dictionary
    with system call numbers as keys and names as values.
    """
    syscall_table = {}
    
    with open(file_path, 'r') as file:
        for line in file:
            if line.startswith("#define __NR_"):
                parts = line.split()
                if len(parts) == 3:
                    name = parts[1].replace("__NR_", "")
                    number = int(parts[2])
                    syscall_table[number] = name
    
    return syscall_table

# Function to parse the system call classifications
def parse_syscall_classifications(classifications):
    """
    Parses the system call classifications and returns a dictionary
    with classifications as keys and lists of system calls as values.
    """
    classification_dict = {}
    lines = classifications.strip().split('\n')[1:]  # Skip the header line
    for line in lines:
        parts = line.split(' ', 1)
        classification = parts[0]
        syscalls = re.findall(r'\w+', parts[1])
        classification_dict[classification] = syscalls
    return classification_dict

# Function to calculate the intersection of system calls
def calculate_intersection(classification_dict, syscall_table):
    """
    Calculates the intersection of system calls with the system call table
    and returns a dictionary with classifications as keys and lists of
    intersecting system calls as values.
    """
    intersect_dict = {}
    syscall_set = set(syscall_table.values())
    for classification, syscalls in classification_dict.items():
        intersection = [sc for sc in syscalls if sc in syscall_set]
        intersect_dict[classification] = intersection
    return intersect_dict


# a function to calcualte the intersection of clusters syscalls and the sensitive syscalls
def sensitive_syscalls_intersection(sensitive_syscalls, clusters_syscalls):
    """
    Calculates the intersection of sensitive syscalls with the clusters syscalls
    and returns a dictionary with clusters as keys and lists of
    intersecting system calls as values.
    """
    intersect_dict = {}
    sensitive_syscall_set = set(sensitive_syscalls)
    for cluster, syscalls in clusters_syscalls.items():
        intersection = [sc for sc in syscalls if sc in sensitive_syscall_set]
        intersect_dict[cluster] = intersection
    return intersect_dict


# write a function that reads the syscalls associated with each single url from the original mapping file
def read_syscall_mapping(file_path, url):
        # categorize the urls based on their associated system call numbers
    categorized_urls = its.categorize_urls_by_numbers(file_path)
    # for the input url lookup syscalls list and return the syscalls as a list
    for group in categorized_urls:
        # if group['urls'] contains the url          
        if url in group['urls']:
            return group['associated_numbers']
    
# read urls from the file pool-urls and load into a list of multi-pool-urls
def read_urls(file_name):
    urls = []
    with open(file_name, 'r') as file:
        for line in file:
            urls.append(line.strip())
    return urls

import argparse

if __name__ == "__main__":

    
    parser = argparse.ArgumentParser(description="Process syscall data")
    parser.add_argument("--file", type=str, default=f'stage2_out_backup/stage2_out_phpmyadmin', help="Path to the file to process")
    parser.add_argument("--app", type=str, default="wordpress", help="Path to the output file")
    parser.add_argument("--urls", action="store_true", help="Enable analysis of the selective urls from the selective pools-urls file")
    # add number of clusters argument
    parser.add_argument("--num_clusters", type=int, default=5, help="Number of clusters to form")
    
    
    args = parser.parse_args()

    # Build the file path using the app name
    file_path = f'/home/paper/stage2_out_{args.app}'
    
    # Example usage
    syscall_table_file = 'unistd_64_.h'  # Update with the actual path to your file
    syscall_table = read_syscall_table(syscall_table_file)
    classification_dict = parse_syscall_classifications(syscall_classifications)
    sen_syscalls = calculate_intersection(classification_dict, syscall_table)
    
    
    # Print the results
    for classification, sen_syscalls in sen_syscalls.items():
        print(f"{classification}: {', '.join(sen_syscalls)}")
       
    
    # create a list of syscall numbers from the sensitive syscalls
    sensitive_syscalls = []
    for classification, syscalls in classification_dict.items():
        sensitive_syscalls.extend([key for key, value in syscall_table.items() if value in syscalls])

    print(f"Total Sensitive Syscalls: {sensitive_syscalls}")
    
    all_clusters, intersection = url_analysis(file_path, num_clusters=args.num_clusters)
    
    # add the intersection to all the clusters associated_numbers
    for cluster in all_clusters:
        cluster['associated_numbers'] = set(cluster['associated_numbers']) | intersection
    
    
    # calculate the intersection of the sensitive syscalls with the clusters syscalls
    sn_clusters = {}
    for i, cluster in enumerate(all_clusters):
        sn_clusters[i] = cluster['associated_numbers'].intersection(sensitive_syscalls)
        
    # Print the results
    for cluster in all_clusters:
        print(f"Cluster:{len(cluster['urls'])}")
        total_urls = sum(len(cluster['urls']) for cluster in all_clusters)
        # print url percentage
        print(f"Cluster URL Percentage: {round((len(cluster['urls'])/total_urls)*100, 2)}")
        
    print(sn_clusters)
    
    # calculate the security metric sn = |sn_clusters|/|cluster['associated_numbers'])|
    for i, cluster in enumerate(all_clusters):
        sn = round(((SN_base-len(sn_clusters[i]))/SN_base)*100, 2)
        print(f"Security Metric for Cluster {i}(SN%): {sn}")
        sp = round(((total_syscalls-(len(cluster['associated_numbers'])))/total_syscalls)*100, 2)
        print(f"Cluster {i} SP%: {sp}")
        
        
    # calculate the percentage of sensitive syscalls and the allowed percentage for sysfilter
    # print SP%
    print('STATISTICS FOR THE SYSFILTER')
    print("SP%", round(((total_syscalls-(len(sysfilter_syscalls)))/total_syscalls)*100, 2))
    
    # calculate the intersection of the sensitive syscalls with the sysfilter syscalls
    sysfilter_intersection = [sc for sc in sensitive_syscalls if sc in sysfilter_syscalls]
    # print SN%
    print("SN%", round(((SN_base-(len(sysfilter_intersection)))/SN_base)*100, 2))
    
    
    if args.urls:
        # calculate SP and SN for the input url for saphire 
        
        print('STATISTICS FOR THE URLS SUPERSETS IN saphire')
        # read the file pools_urls
        urls = read_urls('pools-urls')
        for url in urls:
            print("URL:", url)
            # read the syscalls associated with the input url
            url_syscalls = read_syscall_mapping(file_path, url)
            # calculate the intersection of the sensitive syscalls with the url syscalls
            url_intersection = [sc for sc in sensitive_syscalls if sc in url_syscalls]
            # print SN%
            print("SN% for the input url:", round(((SN_base-(len(url_intersection)))/SN_base)*100, 2))
            # print SP%
            print("SP% for the input url:", round(((total_syscalls-(len(url_syscalls)))/total_syscalls)*100, 2))

        print('STATISTICS FOR THE URLS SUPERSETS IN FORTWALL')
        # lookup the urls in the final categorized urls and get the syscalls associated with the urls and calculate the SP and SN for urls
        for cluster in all_clusters:
            for url in urls:
                if url in cluster['urls']:
                    # print the url
                    print("URL:", url)
                    print("Cluster length:", len(cluster['associated_numbers']))
                    url_superset = cluster['associated_numbers']
                    intersection = [sc for sc in sensitive_syscalls if sc in url_superset]
                    # print SN%
                    print("SN% for the input url:", round(((SN_base-len(intersection))/SN_base)*100, 2))
                    # print SP%
                    print("SP% for the input url:", round(((total_syscalls-(len(url_superset)))/total_syscalls)*100, 2))
        
    # for each url print the cluster number and the syscalls associated with the url
    # for cluster in all_clusters:
    #     for url in urls:
    #         if url in cluster['urls']:
    #             # print the url
    #             print("URL:", url)
    #             print("Cluster Number:", cluster['cluster_number'])
    #             print("Syscalls associated with the url:", cluster['associated_numbers'])