#!/bin/sh
RED='\033[0;31m'
NC='\033[0m' 
#FUNCS='data/php7.2-testsuite.withchildren.syscalls'
FUNCS='data/php7.2-static.syscalls2'
#FUNCS='data/php7.2-testsuite.static.syscalls'
FUNCS="$3"
if [ -z "$3" ]
  then
	FUNCS='data/php7.2-testsuite.withchildren.noexec.syscalls'
fi

#FUNCS='data/php7.2-testsuite.static.syscalls'
HEADER='data/unistd_64.h'

printf "[${RED} Removing $2 if it exists ${NC}]\n"
rm -rf $2 $2.sqlite

printf "[${RED} Registering syscalls from unistd.h ${NC}]\n"
build/register-syscalls $2.sqlite $HEADER

printf "[${RED} Registering functions from $FUNCS ${NC}]\n"
build/register-functions $2.sqlite $FUNCS

printf "[${RED} Scanning php files in $1 ${NC}]\n"
build/scan-project $1 $2.sqlite

printf "[${RED} Building flat profile ${NC}]\n"
build/build-filters $2.sqlite > $2 

printf "[${RED} Done. Profile in $2 ${NC}]\n"

# 1-1
# 0-0
# 0-1
