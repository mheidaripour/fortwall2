#!/bin/sh
# filepath: /home/paper/switch_to_prestashop.sh
sudo rm -rf /var/www/html
sudo cp -r /var/www/prestashop /var/www/html
sudo chown -R www-data:www-data /var/www/html
sudo chmod -R 755 /var/www/html