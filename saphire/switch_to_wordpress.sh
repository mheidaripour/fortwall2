#!/bin/sh
sudo rm -rf /var/www/html
sudo cp -r /var/www/wordpress /var/www/html
sudo chown -R www-data /var/www/html
