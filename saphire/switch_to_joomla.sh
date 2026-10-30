#!/bin/sh
# filepath: switch_to_joomla.sh
sudo rm -rf /var/www/html
sudo cp -r /var/www/joomla /var/www/html
sudo chown -R www-data /var/www/html