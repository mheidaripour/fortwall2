# Clustering the system call sets
import numpy as np

from sklearn.cluster import AgglomerativeClustering
from scipy.spatial.distance import pdist, squareform



def cluster(categorized_urls, num_clusters = 5):

    # List of sets
    data = []
    for group in categorized_urls:
        data.append(set(group['associated_numbers']))
    data = np.array(data)

    # # calculate the intersection of the associated system call numbers for all the sets
    # intersection = set(data[0])
    # for i in range(1, len(data)):
    #     intersection.intersection_update(data[i])

    # print('intersection length: ',intersection.__len__())

    # # remove the intersection from the associated system call numbers for all the sets
    # for i in range(len(data)):
    #     data[i] = data[i] - intersection

    # # remove the empty sets from the data
    # data = [x for x in data if x]
    # data = np.array(data)
    # Define the universal set of all unique elements
    universal_set = set().union(*data)
    element_to_index = {element: idx for idx, element in enumerate(universal_set)}

    # Convert each set to a binary vector
    binary_data = np.zeros((len(data), len(universal_set)), dtype=int)
    for i, s in enumerate(data):
        for element in s:
            if element in element_to_index:
                binary_data[i, element_to_index[element]] = 1

    # Step 1: Compute the Jaccard distances
    jaccard_distances = pdist(binary_data, metric="jaccard")

    # Step 2: Convert to square form
    jaccard_dist_matrix = squareform(jaccard_distances)

    # Step 3: Perform hierarchical clustering
    clustering_model = AgglomerativeClustering(
        n_clusters=num_clusters, affinity="precomputed", linkage="average"
    )
    cluster_labels = clustering_model.fit_predict(jaccard_dist_matrix)

    # Step 4: Create supersets by merging sets within each cluster
    supersets = []
    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if cluster_labels[i] == cluster_id]
        cluster_superset = set().union(*cluster_sets)
        supersets.append(cluster_superset)



    # Print results
    for i, superset in enumerate(supersets, start=1):
        print(f"Superset {i}: {superset}")
        print ("length of the superset:", len(superset))

    # print the number of sets in each cluster
    cluster_sets = []
    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if cluster_labels[i] == cluster_id]
        print(f"Cluster {cluster_id+1}: {len(cluster_sets)} sets")
        
        
    # for each cluster, create a dic, and append the syscalls set per urlcategory that are in each cluster
    clusters_syscalls = {}
    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if cluster_labels[i] == cluster_id]
        clusters_syscalls[cluster_id] = cluster_sets

    # print the group_urls associated with each set inside the clusters
    # for cluster_id in range(num_clusters):
    #     cluster_sets = [data[i] for i in range(len(data)) if cluster_labels[i] == cluster_id]
    #     print(f"Cluster {cluster_id+1}:")
        # print(f"Cluster_set {cluster_sets}:")
        # add the intersection set to the all the sets inside the cluster sets
        # for i, group in enumerate(cluster_sets):
        #     # add the intersection to each group set
        #     cluster_sets[i] = group.union(intersection)
            # update the cluster_sets with the new group
            
            # print(f"  Group : {group}")
        # print('-'*100)
        # print(cluster_sets)
        
        # for i, group in enumerate(categorized_urls):
        #     if group['associated_numbers'] in cluster_sets:
        #         print(f"  Group {i+1}: {len(group['urls'])}")
        
    # for i in range(len(cluster_sets)):
    #     for j in range(len(categorized_urls)):
    #         if set(categorized_urls[j]['associated_numbers']) == cluster_sets[i]:
    #             print(f"  Group {j+1}: {len(categorized_urls[j]['urls'])}")
    
    
    
    # for each cluster, find the urls that are associated with the sets in the cluster
    cluster_urls = {}
    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if cluster_labels[i] == cluster_id]
        urls = []
        for i in range(len(cluster_sets)):
            for j in range(len(categorized_urls)):
                if set(categorized_urls[j]['associated_numbers']) == cluster_sets[i]:
                    urls.extend(categorized_urls[j]['urls'])
        cluster_urls[cluster_id] = urls
    
    # print the urls associated with each cluster
    for cluster_id in range(num_clusters):
        print(f"Cluster {cluster_id+1}: {len(cluster_urls[cluster_id])} urls")
        
    # calculate the standard deviation of the len(syscalls) for urls in each cluster
    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if cluster_labels[i] == cluster_id]
        syscalls = [len(group) for group in cluster_sets]
        print(f"Cluster {cluster_id+1} standard deviation: {round(np.std(syscalls), 1)}")
    
    import sen_syscalls as sns
    
    sensitive_syscalls = sns.parse_syscall_classifications(sns.syscall_classifications)
    # print(f"Sensitive syscalls: {sensitive_syscalls}")
    # write a code that for each cluster, per urlset: calculate the superset of the cluseter - urlset(how many syscalls we are adding to the urlset)
    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if cluster_labels[i] == cluster_id]
        for i, group in enumerate(cluster_sets):
            superset = supersets[cluster_id]
            difference = superset - group
            gr_sn_syscalls = difference.intersection(sensitive_syscalls)
            # print(f"Cluster {cluster_id+1}, Set {i+1}: Adding {len(difference)} syscalls to the set, and {len(gr_sn_syscalls)} sensitive syscalls")

        # max of the gr_sn_syscalls in each cluster
        max_sn_syscalls = max(len((superset - group).intersection(sensitive_syscalls)) for group in cluster_sets)
        max_difference = max(len(superset - group) for group in cluster_sets)
        print(f"Cluster {cluster_id+1}: Max syscalls to add to any set: {(max_difference/sns.total_syscalls)*100:.2f}% of total syscalls, Max of sensitive syscalls: {(max_sn_syscalls/sns.SN_base)*100:.2f}% of sensitive syscalls")
        

        # calculate the intersection of the sensitive syscalls with the max difference syscalls
        # sensitive_syscalls_in_cluster = set()
        # for group in cluster_sets:
        #     sensitive_syscalls_in_cluster.update(group.intersection(sensitive_syscalls))
    
    return supersets, cluster_urls, clusters_syscalls