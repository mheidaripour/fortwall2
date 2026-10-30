#!/bin/sh
# filepath: switch_to_magento.sh
sudo rm -rf /var/www/html
sudo cp -r /var/www/magento /var/www/html
sudo chown -R www-data /var/www/html