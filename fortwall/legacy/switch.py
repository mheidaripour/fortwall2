import argparse
import os

import intersection as its
from cluster import cluster



# there are 2 arguments: switch mode which is a string [saphire/mpool] and the second which is optional is the number of pools [pools_num]

# create a parser object
parser = argparse.ArgumentParser(description='Switch between saphire and mpool modes')

# add arguments to the parser
parser.add_argument('-m', '--mode', type=str, help='switch mode [saphire/mpool/default]', choices=['saphire', 'mpool', 'default'])
parser.add_argument('-p', '--pools_num', type=int, default = 7 , nargs='?', help='number of pools')
parser.add_argument('-app', '--application', type=str, help='application name [wordpress/joomla/drupal]', choices=['wordpress', 'joomla', 'drupal', 'phpmyadmin','moodle'], default='wordpress')
# parse the arguments
args = parser.parse_args()

if args.mode == 'default':
    # change php-fpm www.conf file to default, with pm.max_requests = 0
    its.change_php_fpm_www_conf_to_default()

elif args.mode == 'saphire':
    print('Switching to saphire mode')
    # clean configs
    # restart Nginx
    its.clean_configs(args.application)
    its.restart_nginx()
    # start saphire with protection
       
elif args.mode == 'mpool':
    print('Switching to mpool mode')
    if args.pools_num is not None:
        print('Number of pools: ', args.pools_num)
    
    # clean configs
    its.clean_configs(args.application)
    
    # backup defaults
    # its.backup_php_fpm_pool_config_files()
    # its.backup_nginx_default_config_files()
    
    # categorize the urls based on their associated system call numbers
    file_path = f'/home/paper/stage2_out_{args.application}'  # Path to your file
    categorized_urls = its.categorize_urls_by_numbers(file_path)

    # backup the stage2_out file
    its.backup_stage2_out(file_path)
    
    # # Displaying the first few categorized groups for illustration
    # # for group in categorized_urls:
    # #     print(group)
    intersection = its.intersection_of_urls(categorized_urls)
    its.write_intersection_to_file(intersection)
    urls_with_exact_intersection_set = its.calculate_urls_with_exact_intersection_set(categorized_urls, intersection)
    
    print('URLs with exact intersection set:', len(urls_with_exact_intersection_set))
    
    # load the intersection file and print the intersection set
    with open('intersection', 'r') as f:
        content = f.readlines()
    
    print('Intersection of the associated system call numbers for all the sets:', content)
    
    # Calculate the percentage of urls per category
    cat_indices = its.calculate_url_categories_percentage(categorized_urls)
    
    # remove intersection set syscalls from the associated system call numbers for all the sets
    new_categorized_urls = its.remove_intersection_set_from_associated_numbers(categorized_urls, intersection)

    # remove the categories with percentage_urls >= threshold
    new_categories = its.create_new_categories(new_categorized_urls, cat_indices)
    
    # print('Number of categories:', len(categorized_urls))
    print('Number of new categories after removing the high percentage categories:', len(new_categories))
    
    # cluster the rest of the categories
    supersets, cluster_urls, clusters_syscalls = cluster(new_categories, args.pools_num - len(cat_indices))
    
    # create new categories including each cluster and associated urls, and prebuilt categories
    all_clusters = its.create_new_categories_with_clusters(new_categorized_urls, cat_indices, cluster_urls, supersets)
    
    # create new stage2_out file
    its.create_new_stage2_out_file(all_clusters, file_path.split('/')[-1])
    
    nginx_pools_map = its.remove_clusters_empty_syscalls(all_clusters)
    
    print('Number of categories after removing the empty syscalls:', len(nginx_pools_map))
    
    # # restore the default config files
    # # restore_nginx_default_config_files()
    
    # # backup the default config files
    # backup_nginx_default_config_files()
    
    # create nginx url_map_categorynumber.conf, path to nginx conf: /etc/nginx/
    # if dir nginx-url-map-files/ does not exist, create it
    if not os.path.exists('nginx-url-map-files/'):
        os.makedirs('nginx-url-map-files/')
    its.create_nginx_url_map(nginx_pools_map, 'nginx-url-map-files/')
    
    #backup php-fpm pool configuration files
    # backup_php_fpm_pool_config_files()
    
    # creating php-fpm pool configuration files
    if not os.path.exists('php-fpm-config-files/'):
        os.makedirs('php-fpm-config-files/')
    its.create_php_fpm_pool_configurations(nginx_pools_map, 'php-fpm-config-files/')
    
    # # apply changes to nginx-config file
    its.change_nginx_config_file('/etc/nginx/nginx.conf', nginx_pools_map)
    
    # # apply changes to nginx/sites-enabled/default
    its.change_nginx_sites_enabled_config_file('/etc/nginx/sites-enabled/default')
    
    # #  copy the intersection file to the path : /var/www/intersect_filter
    its.copy_intersection_file_to_path('intersection')
    
    # # copy the stage2_out_wordpress_new file to the path : /home/paper/stage2_out_wordpress
    #! commented to keep the stage2_out_wordpress file as it is
    # its.copy_stage2_out_file_to_path('stage2_out_wordpress')
    
    # # copy the new nginx config file to the path : /etc/nginx/nginx.conf
    its.replace_nginx_config_file('nginx.conf')
    
    # # copy the new sites-enabled default file to the path : /etc/nginx/sites-enabled/default
    its.replace_nginx_sites_enabled_config_file('default')
    
    # # copy nginx url_map files to the path : /etc/nginx/
    its.copy_nginx_url_map_files('nginx-url-map-files')
    
    # copy the php-fpm pool configuration files to the path : /opt/php-7.1/etc/php-fpm.d/
    its.copy_php_fpm_pool_config_files('php-fpm-config-files')
    
    # # restart nginx
    its.restart_nginx()   

