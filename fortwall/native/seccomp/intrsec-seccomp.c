#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DELIM ' '

// initialize an array to store syscall numbers
int syscalls[30] = {0};

/* Function to load and print the syscalls from the file */
int load_and_print_syscalls(const char *file_path) {
    FILE *syscall_file = fopen(file_path, "r");
    if (!syscall_file) {
        perror("Error opening syscall file");
        return -1;
    }

    char buffer[1024]; // Buffer to hold file content
    printf("Loaded syscalls from file:\n");
    
    int i=0;
    // Read each line from the file
    while (fgets(buffer, sizeof(buffer), syscall_file)) {
        char *token = strtok(buffer, "{, }");
        while (token) {
            int syscall_num = atoi(token); // Convert to integer
            if (syscall_num >= 0) { // Validate syscall number
                // printf("%d ", syscall_num);
                // add syscall number to the array
                syscalls[i++] = syscall_num;
            }
            token = strtok(NULL, "{, }");
        }
        // printf("\n");
    }

    fclose(syscall_file);
    return 0;
}

int load_and_print_syscall_2(const char *file_path){
    FILE *intersect_filter = fopen(file_path, "r");
    if (intersect_filter) {
        char buffer[1024]; // Buffer to hold file content
        int i=0;

        while (fgets(buffer, sizeof(buffer), intersect_filter)) {
            char *token = strtok(buffer, "{, }");
            while (token) {
                int syscall_num = atoi(token);
                
                if (syscall_num >= 0) { // Validate syscall number
                    // seccomp_rule_add(ctx, SCMP_ACT_ALLOW, syscall_num, 0);
                    
                    // add syscall number to the array
                    syscalls[i++] = syscall_num;
                    printf("%d ", syscalls[i-1]);
                }
                token = strtok(NULL, "{, }");
            }
            // printf("\n");
        }
        
    fclose(intersect_filter);   
    }   
    return 0;
}

int main(int argc, char *argv[]) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <syscall_file_path>\n", argv[0]);
        return EXIT_FAILURE;
    }

    const char *syscall_file_path = argv[1];

    // Load and print syscalls from the file
    if (load_and_print_syscall_2(syscall_file_path) < 0) {
        return EXIT_FAILURE;
    }

    // Print the syscalls
    printf("Loaded syscalls from file:\n");
    for (int i = 0; i < 30; i++) {
        printf("%d ", syscalls[i]);
    }

    return EXIT_SUCCESS;
}

