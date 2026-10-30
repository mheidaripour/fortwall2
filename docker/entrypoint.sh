#!/bin/bash
# Container entrypoint: bring up the data services Saphire's pipeline expects
# (MariaDB), then hand control to the given command (an interactive shell by
# default). nginx / php-fpm are started explicitly by run_stage3.sh or the
# fortwall deploy step, not here, so you can start/stop them per experiment.
set -e

# MariaDB needs an initialised data dir + a running server for the stage-1 PHP
# test suite (PDO/mysqli tests) and for the web apps.
if [ ! -d /var/lib/mysql/mysql ]; then
    sudo mysql_install_db --user=mysql >/dev/null 2>&1 || true
fi
sudo service mysql start >/dev/null 2>&1 || sudo mysqld_safe --nowatch >/dev/null 2>&1 || true

# Best-effort test DB/user matching run_stage1.sh's MYSQL_TEST_* env.
sudo mysql -e "CREATE DATABASE IF NOT EXISTS test; \
  CREATE USER IF NOT EXISTS 'test'@'localhost' IDENTIFIED BY 'test'; \
  GRANT ALL ON *.* TO 'test'@'localhost'; FLUSH PRIVILEGES;" 2>/dev/null || true

exec "$@"
