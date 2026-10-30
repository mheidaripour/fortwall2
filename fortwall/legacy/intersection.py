import shutil
import os
import glob

import numpy as np

from collections import defaultdict
from cluster import cluster



# backup stage2_out to /stage2_out_backup
def backup_stage2_out(source_path):
    file_name = source_path.split('/')[-1]
    dest_path = 'stage2_out_backup/' + file_name

    # python copy file from one directory to another
    shutil.copy(source_path, dest_path)
    print(f'{file_name} copied to the path:', dest_path)
    

# Function to categorize URLs based on their associated numbers
def categorize_urls_by_numbers(file_path):
    # Dictionary to hold groups of URLs by their associated numbers
    grouped_urls = defaultdict(list)

    # Reading the input file
    with open(file_path, 'r') as file:
        content = file.readlines()

    # Processing each line to extract URL and associated numbers
    for line in content:
        # Split line into URL and associated numbers
        parts = line.strip().split()
        url = parts[0]
        try:
            numbers = tuple(sorted(map(int, parts[1:])))  # Convert numbers to sorted tuple
        except ValueError:
        # Skip lines where parts[1:] contains non-numeric values
            print(f"Warning: Skipping malformed line: {line.strip()}")
            continue
        # numbers = tuple(sorted(map(int, parts[1:])))  # Convert numbers to sorted tuple

        # Group URLs by the same set of numbers
        grouped_urls[numbers].append(url)

    # Convert the grouped URLs into the desired list format
    categorized_urls = [{"associated_numbers": list(numbers), "urls": urls} for numbers, urls in grouped_urls.items()]

    return categorized_urls

def intersection_of_urls(categorized_urls):
    data = []
    for group in categorized_urls:
        data.append(set(group['associated_numbers']))

    data = np.array(data)

    # calculate the intersection of the associated system call numbers for all the sets
    intersection = set(data[0])
    for i in range(1, len(data)):
        intersection.intersection_update(data[i])
    
    print("Intersection of the associated system call numbers for all the sets:", intersection)
    print('Intersection Length',intersection.__len__())
    
    return intersection
# create the file and write the intersection of the associated system call numbers for all the sets
def write_intersection_to_file(intersection):
    with open('intersection', 'w') as f:
        f.write("%s" % intersection)

# Calculate the urls that their associated system call numbers are only the intersection set ie. the common set: syscalls (30 in all examples)
def calculate_urls_with_exact_intersection_set(categorized_urls, intersection):
    urls_with_exact_intersection_set = []
    for group in categorized_urls:
        if set(group['associated_numbers']) == intersection:
            urls_with_exact_intersection_set.extend(group['urls'])
    return urls_with_exact_intersection_set

# function to return the total urls
def total_urls(url_categories):
    return sum(len(category['urls']) for category in url_categories)

#  Calculate url_catergories number of urls percentage over the total number of urls per category
def calculate_url_categories_percentage(url_categories, threshold=10):
    total_urls = sum(len(category['urls']) for category in url_categories)
    category_percentages = [round((len(category['urls']) / total_urls)*100, 6) for category in url_categories]
    
    print('Total number of URLs:', total_urls)
    print('Category percentages:', category_percentages)
    print('the group with the highest percentage:', max(category_percentages))
    
    # print the categories with the  percentage > 10% and print sum of the percentages
    total_percentage = 0
    pools = 0
    cat_indices = []
    for i in range(len(category_percentages)):
        if category_percentages[i] >= threshold:
            total_percentage += category_percentages[i]
            print('Category:', i, 'Percentage:', category_percentages[i])
            # print the len of associated_numbers for the category
            print('Associated numbers:', len(url_categories[i]['associated_numbers']), 'percentage', round(len(url_categories[i]['associated_numbers'])/333,4))
            pools += 1
            cat_indices.append(i)
    print(f'Sum of the percentages covered with total number of pool {pools}: ', total_percentage)

    return cat_indices

# remove the intersection set syscalls from the associated system call numbers for all the sets
def remove_intersection_set_from_associated_numbers(categorized_urls, intersection):
    for group in categorized_urls:
        group['associated_numbers'] = list(set(group['associated_numbers']) - intersection)
    return categorized_urls


# create a new categories by removing the categories with percentage_urls >= threshold
def create_new_categories(url_categories, cat_indices):
    new_categories = []
    for i in range(len(url_categories)):
        if i not in cat_indices:
            new_categories.append(url_categories[i])
    return new_categories


# create a new categories including each cluster and associated urls
def create_new_categories_with_clusters(url_categories,cat_indices, cluster_urls, supersets):
    new_categories = []
    for i in range(len(cat_indices)):
        new_categories.append(url_categories[cat_indices[i]])

    for i in range(len(cluster_urls)):
        new_categories.append({'associated_numbers': list(supersets[i]), 'urls': cluster_urls[i]})
    
    return new_categories


def sample_url_from_each_category(url_categories):
    for category in url_categories:
        print(category['urls'][0])


#!!!! Important change :  I should revise : Revised should be check for correctness 
# Create a new stage2_out file that includes urls and their associated system call numbers, while for each url, put the system call numbers in the category number
def create_new_stage2_out_file(new_categories, file_path):
    with open(file_path, 'w') as file:
            for i, category in enumerate(new_categories):
                for url in category['urls']:
                    # if category['associated_numbers']:
                    file.write(f"{url} {' '.join(map(str, category['associated_numbers']))}\n")
                    # else:
                    #     file.write(f"{url} {' '.join(map(str, [0, 1, 257, 3, 4, 5, 6, 262, 8, 9, 10, 11, 13, 14, 20, 25, 28, 39, 302, 186, 60, 62, 72, 202, 79, 217, 99, 229, 231, 234]))}\n")

# if the url_category has empty syscalls, remove it
def remove_clusters_empty_syscalls(url_categories):
    new_categories = []
    for category in url_categories:
        if category['associated_numbers']:
            new_categories.append(category)
    return new_categories

# create nginx url_map_categorynumber.conf which includes each url of the category maps to the specific pool, and the pool is the category number
def create_nginx_url_map(new_categories, file_path):
        for i, category in enumerate(new_categories):
            with open(f'{file_path}url_map_{i+1}.conf', 'w') as file:
                for url in category['urls']:
                    file.write(f"{url} unix:/opt/php-7.1/var/run/php/pool_{i+1}.sock;\n")

# creating php-fpm pool configuration files per cluster
def create_php_fpm_pool_configurations(new_categories, file_path):
    # read the sample file from the php-fpm pool configuration file www.conf: /opt/php-7.1/etc/php-fpm.d/, 
    # the config file should be named as the pool name for the category, pool_{i+1}.conf
    # if not file_path:
    php_fpm_file_path = '/opt/php-7.1/etc/php-fpm.d/'
    with open(f'{php_fpm_file_path}www.conf', 'r') as file:
        default_conf = file.readlines()
    
    with open(f'{file_path}www.conf', 'w') as file:    
        for line in default_conf:
            if line == 'pm.max_requests = 1\n':
                # print('found the line pm.max_requests = 1 in www.conf')
                file.write(line.replace('pm.max_requests = 1', 'pm.max_requests = 0'))
            # if line containes 'pm.max_children' replace it with 'pm.max_children = 1'
            elif line == 'pm.max_children = 8':
                file.write(line.replace('pm.max_children = 8', 'pm.max_children = 1'))
            elif line == 'pm.max_spare_servers = 3\n':
                file.write(line.replace('pm.max_spare_servers = 3', 'pm.max_spare_servers = 1'))
            else:
                file.write(line)
    
    # print(default_conf)
    # create a new pool configuration file for each category
    for i, category in enumerate(new_categories):
        with open(f'{file_path}pool_{i+1}.conf', 'w') as file:
            for line in default_conf:
                if line == '[www]\n':
                    file.write(line.replace('[www]\n', f'[pool_{i+1}]\n'))
                elif line == 'listen = /opt/php-7.1/var/run/php/php7.1-fpm.sock\n':
                    file.write(line.replace('listen = /opt/php-7.1/var/run/php/php7.1-fpm.sock\n', f'listen = /opt/php-7.1/var/run/php/pool_{i+1}.sock\n'))
                elif line == 'pm.max_requests = 1\n':
                    # print('found the line pm.max_requests = 1')
                    file.write(line.replace('pm.max_requests = 1', 'pm.max_requests = 0'))
                # if line containes 'pm.max_children' replace it with 'pm.max_children = 1'
                elif line == 'pm.max_children = 8\n':
                    file.write(line.replace('pm.max_children = 8', 'pm.max_children = 1'))
                elif line == 'pm.max_spare_servers = 3\n':
                    file.write(line.replace('pm.max_spare_servers = 3', 'pm.max_spare_servers = 1'))
                else:
                    file.write(line)
    
    
# copy nginx default config files to the path : /nginxdefaults/
def backup_nginx_default_config_files():
    dest_path_nginxconf = 'nginxdefaults/nginx.conf'
    dest_path_default = 'nginxdefaults/default'

    source_path_nginxconf ='/etc/nginx/nginx.conf'
    source_path_default = '/etc/nginx/sites-enabled/default'
    
    # python copy file from one directory to another
    shutil.copy(source_path_nginxconf, dest_path_nginxconf)
    print('nginx default config files copied to the path:', dest_path_nginxconf, dest_path_default)
    shutil.copy(source_path_default, dest_path_default)
    print('nginx/sites-enabled default config files copied to the path:', dest_path_default)


def restore_nginx_default_config_files():
    source_path_nginxconf = 'nginxdefaults/nginx.conf'
    source_path_default = 'nginxdefaults/default'
    
    dest_path_nginxconf = '/etc/nginx/nginx.conf'
    dest_path_default = '/etc/nginx/sites-enabled/default'
    
    # python copy file from one directory to another
    shutil.copy(source_path_nginxconf, dest_path_nginxconf)
    print('nginx default config files restored to the path:', dest_path_nginxconf)
    shutil.copy(source_path_default, dest_path_default)
    print('nginx/sites-enabled default config files restored to the path:', dest_path_default)    

# backup php-fpm pool configuration files to the path : /php-fpm-defaults/
def backup_php_fpm_pool_config_files():
    dest_path = 'php-fpm-defaults/'
    source_path = '/opt/php-7.1/etc/php-fpm.d/'
    
    # List all files in the source directory
    files = os.listdir(source_path)
    
    # Loop through each file and copy it to the destination directory
    for file_name in files:
        full_file_name = os.path.join(source_path, file_name)
        if os.path.isfile(full_file_name):
            shutil.copy(full_file_name, dest_path)
            
    print('php-fpm pool configuration files copied to the path:', dest_path)

# change nginx config file to add the $upstream section to end of the http block, and include the url_map_categorynumber.conf files
def change_nginx_config_file(file_path, new_categories):
    with open(file_path, 'r') as file:
        nginx_conf = file.readlines()

    new_conf = []
    for i,line in enumerate(nginx_conf):
        if line == '         default unix:/opt/php-7.1/var/run/php/php7.1-fpm.sock;\n':
            # print('found the line')
            new_conf.append(line)
            for i in range(len(new_categories)):
                new_conf.append(f'         include /etc/nginx/urlmapphp/url_map_{i+1}.conf;\n')
        else:
            new_conf.append(line)
    
    # write the new configuration to the nginx config file
    with open('nginx.conf', 'w') as file:
        for line in new_conf:
            file.write(line)    

# change the default config in the nginx/sites-enabled to use the $upstream section
def change_nginx_sites_enabled_config_file(file_path):
    with open(file_path, 'r') as file:
        default_conf = file.readlines()

    # print(default_conf)
    new_conf = []
    for i,line in enumerate(default_conf):
        if line == '\tfastcgi_pass unix:/opt/php-7.1/var/run/php/php7.1-fpm.sock;\n':
            # print('found the line')
            # new_conf.append(line)
            new_conf.append('\tfastcgi_pass $upstream;\n')
        else:
            new_conf.append(line)

    # write the new configuration to the nginx/sites-enabled/default file
    with open('default', 'w') as file:
        for line in new_conf:
            file.write(line)


# copy the intersection file to the path : /var/www/intersect_filter
def copy_intersection_file_to_path(source_path):
    dest_path = '/var/www/intersect_filter'

    # python copy file from one directory to another
    shutil.copy(source_path, dest_path)
    print('Intersection file copied to the path:', dest_path)
    

# copy the stage2_out_wordpress_new file to the path : /home/paper/stage2_out_wordpress
def copy_stage2_out_file_to_path(source_path, dest_path=None, app_name= None):
    if not dest_path:
        dest_path = '../stage2_out_wordpress'
    if not app_name:
        app_name = 'wordpress'

    # python copy file from one directory to another
    shutil.copy(source_path, dest_path)
    print(f'stage2_out_{app_name}_new file copied to the path:', dest_path)

# replace the nginx config file with the new one
def replace_nginx_config_file(source_path):
    dest_path = '/etc/nginx/nginx.conf'
    # python copy file from one directory to another
    shutil.copy(source_path, dest_path)
    print('nginx config file replaced with the new one:', dest_path)

# replace the sites-enabled default file with the new one
def replace_nginx_sites_enabled_config_file(source_path):
    dest_path = '/etc/nginx/sites-enabled/default'
    # python copy file from one directory to another
    shutil.copy(source_path, dest_path)
    print('nginx sites-enabled default file replaced with the new one:', dest_path)

# copy the folder nginx-url-map-files to the path : /etc/nginx/
def copy_nginx_url_map_files(source_path):
    dest_path = '/etc/nginx/urlmapphp'

    # python copy files from one directory to another
    shutil.copytree(source_path, dest_path)
    print('nginx url map files copied to the path:', dest_path)


# copy the php-fpm pool configuration files to the path : /opt/php-7.1/etc/php-fpm.d/
def copy_php_fpm_pool_config_files(source_path):
    dest_path = '/opt/php-7.1/etc/php-fpm.d/'

    # List all files in the source directory
    files = os.listdir(source_path)
    
    # Loop through each file and copy it to the destination directory
    for file_name in files:
        full_file_name = os.path.join(source_path, file_name)
        if os.path.isfile(full_file_name):
            shutil.copy(full_file_name, dest_path)
            
    print('php-fpm pool configuration files copied to the path:', dest_path)

# remove all created config files
def clean_configs(app_name):
    
    # restore the default stage2_out file
    # dest_path = f'/home/paper/stage2_out_{app_name}'
    # shutil.copy(f'stage2_out_backup/stage2_out_{app_name}', dest_path)
    
    # nginx url_map files
    dest_path = '/etc/nginx/urlmapphp'
    if os.path.exists(dest_path):
        shutil.rmtree(dest_path)
        print('nginx url map files removed from the path:', dest_path)
    
    # nginx config file: revert to the original file
    dest_path = '/etc/nginx/nginx.conf'
    shutil.copy('nginxdefaults/nginx.conf', dest_path)
    
    # nginx sites-enabled default file: revert to the original file
    dest_path = '/etc/nginx/sites-enabled/default'
    shutil.copy('nginxdefaults/default', dest_path)
    
    # php-fpm pool configuration files
    dest_path = '/opt/php-7.1/etc/php-fpm.d/pool*.conf'
    # Use glob to find all files matching the pattern
    files = glob.glob(dest_path)

    # Loop through the list of files and remove each one
    for file in files:
        try:
            os.remove(file)
            print(f"Removed: {file}")
        except OSError as e:
            print(f"Error: {file} : {e.strerror}")
    
    # restore the default php-fpm pool configuration file www.conf
    dest_path = '/opt/php-7.1/etc/php-fpm.d/www.conf'
    shutil.copy('php-fpm-defaults/www.conf', dest_path)
    
    # restore the defult stage2_out file
    dest_path = f'/home/paper/stage2_out_{app_name}'
    shutil.copy(f'stage2_out_backup/stage2_out_{app_name}', dest_path)
    
    # remove local pooling configs
    remove_local_pooling_configs()

def change_php_fpm_www_conf_to_default():
    source_path = 'php-fpm-defaults/wwwdefault.conf'
    dest_path = '/opt/php-7.1/etc/php-fpm.d/www.conf'
    shutil.copy(source_path, dest_path)
    print('php-fpm www.conf file replaced with the default one:', dest_path)

# a function to restart the nginx
def restart_nginx():
    os.system('sudo systemctl restart nginx')
    print('Nginx restarted')


# function to remove the nginx-url-map-files folder and remove the php-fpm-pool-config-files folder
def remove_local_pooling_configs():
    dest_path = 'nginx-url-map-files'
    if os.path.exists(dest_path):
        shutil.rmtree(dest_path)
        print('nginx url map files removed from the path:', dest_path)
    
    # remove the php-fpm pool configuration files
    dest_path = 'php-fpm-config-files'
    if os.path.exists(dest_path):
        shutil.rmtree(dest_path)
        print('php-fpm pool configuration files removed from the path:', dest_path)


# if __name__ == '__main__':
    
    # # categorize the urls based on their associated system call numbers
    # file_path = 'stage2_out_backup/stage2_out_wordpress'  # Path to your file
    # categorized_urls = categorize_urls_by_numbers(file_path)

    # # backup the stage2_out file
    # # backup_stage2_out(file_path)
    
    # # Displaying the first few categorized groups for illustration
    # # for group in categorized_urls:
    # #     print(group)
    # intersection = intersection_of_urls(categorized_urls)
    # write_intersection_to_file(intersection)
    # urls_with_exact_intersection_set = calculate_urls_with_exact_intersection_set(categorized_urls, intersection)
    # print('URLs with exact intersection set:', len(urls_with_exact_intersection_set))
    
    # # load the intersection file and print the intersection set
    # with open('intersection', 'r') as f:
    #     content = f.readlines()
    
    # print('Intersection of the associated system call numbers for all the sets:', content)
    
    # # Calculate the percentage of urls per category
    # cat_indices = calculate_url_categories_percentage(categorized_urls)
    
    # # remove intersection set syscalls from the associated system call numbers for all the sets
    # new_categorized_urls = remove_intersection_set_from_associated_numbers(categorized_urls, intersection)

    # # remove the categories with percentage_urls >= threshold
    # new_categories = create_new_categories(new_categorized_urls, cat_indices)
    
    # print('Number of categories:', len(categorized_urls))
    # print('Number of new categories after removing the high percentage categories:', len(new_categories))
    
    # # cluster the rest of the categories
    # supersets, cluster_urls, clusters_syscalls = cluster(new_categories)
    
    # # create new categories including each cluster and associated urls, and prebuilt categories
    # all_clusters = create_new_categories_with_clusters(new_categorized_urls, cat_indices, cluster_urls, supersets)
    
    # # create new stage2_out file
    # # create_new_stage2_out_file(all_clusters, 'stage2_out_wordpress')
    
    # nginx_pools_map = remove_clusters_empty_syscalls(all_clusters)
    
    # print('Number of categories after removing the empty syscalls:', len(nginx_pools_map))
    
    # # restore the default config files
    # # restore_nginx_default_config_files()
    
    # # backup the default config files
    # backup_nginx_default_config_files()
    
    # # create nginx url_map_categorynumber.conf, path to nginx conf: /etc/nginx/
    # create_nginx_url_map(nginx_pools_map, 'nginx-url-map-files/')
    
    #backup php-fpm pool configuration files
    # backup_php_fpm_pool_config_files()
    
    # creating php-fpm pool configuration files
    # create_php_fpm_pool_configurations(nginx_pools_map, 'php-fpm-config-files/')
    
    # # apply changes to nginx-config file
    # change_nginx_config_file('/etc/nginx/nginx.conf', nginx_pools_map)
    
    # # apply changes to nginx/sites-enabled/default
    # change_nginx_sites_enabled_config_file('/etc/nginx/sites-enabled/default')
    
    # #  copy the intersection file to the path : /var/www/intersect_filter
    # copy_intersection_file_to_path('intersection')
    
    # # copy the stage2_out_wordpress_new file to the path : /home/paper/stage2_out_wordpress
    # copy_stage2_out_file_to_path('stage2_out_wordpress')
    
    # # copy the new nginx config file to the path : /etc/nginx/nginx.conf
    # replace_nginx_config_file('nginx.conf')
    
    # # copy the new sites-enabled default file to the path : /etc/nginx/sites-enabled/default
    # replace_nginx_sites_enabled_config_file('default')
    
    # # copy nginx url_map files to the path : /etc/nginx/
    # copy_nginx_url_map_files('nginx-url-map-files')
    
    # copy the php-fpm pool configuration files to the path : /opt/php-7.1/etc/php-fpm.d/
    # copy_php_fpm_pool_config_files('php-fpm-config-files')
    
    # # restart nginx
    # restart_nginx()
    
    # # clean configs and restart nginx
    # clean_configs()
    # restart_nginx()
    