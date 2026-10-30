#!/bin/sh
# filepath: switch_to_moodle.sh
sudo rm -rf /var/www/html
sudo cp -r /var/www/moodle /var/www/html
sudo chown -R www-data /var/www/html