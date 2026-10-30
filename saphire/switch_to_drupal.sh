#!/bin/sh
# filepath: switch_to_drupal.sh
sudo rm -rf /var/www/html
sudo cp -r /var/www/drupal /var/www/html
sudo chown -R www-data /var/www/html