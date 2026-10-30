import intersection as its
from sen_syscalls import parse_syscall_classifications, calculate_intersection, read_syscall_table, syscall_classifications

total_syscalls = 333
sensitive_syscalls = 20


# syscall_classifications = """
# System Call Classification Applicable System Calls
# Arbitrary Code Execution execve, execveat, fork, vfork, clone, ptrace
# Memory Permissions mprotect, mmap, mremap, remap_file_pages
# Privilege Escalation chmod, setuid, setgid, setreuid
# Networking socket, bind, connect, listen, accept, accept4
# """

file_path = 'stage2_out_backup/stage2_out_wordpress'  # Replace with your file path


# create the total sensitive syscalls set
syscall_table_file = 'unistd_64_.h'  # Update with the actual path to your file
syscall_table = read_syscall_table(syscall_table_file)
classification_dict = parse_syscall_classifications(syscall_classifications)
sen_syscalls = calculate_intersection(classification_dict, syscall_table)
# create a list of syscall numbers from the sensitive syscalls
sensitive_syscalls = []
for classification, syscalls in classification_dict.items():
    sensitive_syscalls.extend([key for key, value in syscall_table.items() if value in syscalls])

# categorize the urls based on their associated system call numbers
categorized_urls = its.categorize_urls_by_numbers(file_path)

# for each category, calculate the SP and SN rates for the associated numbers
sp_values = []
sn_values = []
for i, group in enumerate(categorized_urls):
    
    syscall_profile = group['associated_numbers']
    sp_values.append(round(((total_syscalls-(len(syscall_profile)))/total_syscalls)*100, 2))
    
    # calculate the intersection of the sensitive syscalls with system call set of the current group
    sen_profile = [s for s in sensitive_syscalls if s in syscall_profile]
    sn_values.append(round(((len(sensitive_syscalls)-len(sen_profile))/len(sensitive_syscalls))*100, 2))

    # print(f"Group: {group['urls']}, SP Rate: {sp_rate:.2f}%, SN Rate: {sn_rate:.2f}%")

# print the average of sp and sn values
avg_sp = round(sum(sp_values) / len(sp_values), 2)
avg_sn = round(sum(sn_values) / len(sn_values), 2)
print(f"Average SP Rate: {avg_sp:.2f}%")
print(f"Average SN Rate: {avg_sn:.2f}%")

# print max for sp and sn values
max_sp = max(sp_values)
max_sn = max(sn_values)
print(f"Max SP Rate: {max_sp:.2f}%")
print(f"Max SN Rate: {max_sn:.2f}%")
