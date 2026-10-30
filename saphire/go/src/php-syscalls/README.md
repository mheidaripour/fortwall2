Usage
=============
Install Go: https://golang.org/doc/install
```bash
git clone https://git-seclab.bu.edu/php-syscalls/php-api-deps $GOPATH/src/php-api/deps
cd $GOPATH/src/php-api/deps
./profile_application.sh PATH_TO_APP_ROOT PATH_TO_OUTPUT_PROFILE PATH_TO_STAGE1_OUTPUT
# eg ./profile_application.sh ~/apps/phpBB2/ phpBB2.sqlite /path/to/api_to_syscall_mapping
```
