import intersection as its
from cluster import cluster


total_syscalls = 333
sensitive_syscalls = 20


def url_analysis(file_path, num_clusters=5):

    # categorize the urls based on their associated system call numbers
    categorized_urls = its.categorize_urls_by_numbers(file_path)
    
    toral_urls = its.total_urls(categorized_urls) 
    # # Displaying the first few categorized groups for illustration
    # # for group in categorized_urls:
    # #     print(group)
    intersection = its.intersection_of_urls(categorized_urls)
  
    urls_with_exact_intersection_set = its.calculate_urls_with_exact_intersection_set(categorized_urls, intersection)
    
    print('URLs with exact intersection set:', len(urls_with_exact_intersection_set))
    
    # # load the intersection file and print the intersection set
    # with open('intersection', 'r') as f:
    #     content = f.readlines()
    
    # print('Intersection of the associated system call numbers for all the sets:', content)
    
    # Calculate the percentage of urls per category
    cat_indices = its.calculate_url_categories_percentage(categorized_urls)
    
    # remove intersection set syscalls from the associated system call numbers for all the sets
    new_categorized_urls = its.remove_intersection_set_from_associated_numbers(categorized_urls, intersection)

    # remove the categories with percentage_urls >= threshold
    new_categories = its.create_new_categories(new_categorized_urls, cat_indices)
    
    # print('Number of categories:', len(categorized_urls))
    print('Number of new categories after removing the high percentage categories:', len(new_categories))
    
    # cluster the rest of the categories
    supersets, cluster_urls, clusters_syscalls = cluster(new_categories, num_clusters)
    
    for cluser in cluster_urls:
        print(f"Cluster {cluser}: {round((len(cluster_urls[cluser])/toral_urls)*100,2)} urls")
    
    # print the number of sets in each cluster
    for i, superset in enumerate(supersets, start=1):
        print(f"Superset {i}:  Length of the superset: {len(superset)} and the percentage : {round(((len(superset)+ len(intersection))/total_syscalls)*100,2)} ")

    # create new categories including each cluster and associated urls, and prebuilt categories
    all_clusters = its.create_new_categories_with_clusters(new_categorized_urls, cat_indices, cluster_urls, supersets)
       
    return all_clusters, intersection
    
    
if __name__ == "__main__":
    file_path = 'stage2_out_backup/stage2_out_wordpress'  # Replace with your file path
    url_analysis(file_path)
    

    