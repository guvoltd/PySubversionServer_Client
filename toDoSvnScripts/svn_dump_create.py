import subprocess
import os
import datetime
import sys
import logging
import re

# Configuration
SVN_REPOS_ROOT = r"E:\svn_mcc\REPOS"  # Directory containing SVN repositories
# BACKUP_DIR = r"D:\svn_test\full_dumps"  # Directory to store backups
BACKUP_DIR = r"D:\SVN_DUMPS"  # Directory to store backups

ERROR_LOG_FILE = os.path.join(BACKUP_DIR, "error_log.txt")

if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

# Setup Logging for Interactive Sessions & Error Tracing
logger = logging.getLogger("SVNDump")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

file_handler = logging.FileHandler(ERROR_LOG_FILE)
file_handler.setLevel(logging.ERROR)
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

def get_repositories(repos_root):
    """Gets a list of repository names directly from the SVN server if it's a checkout."""
    repos = []
    
    # Check if the root directory is a working copy (checkout)
    if os.path.exists(os.path.join(repos_root, '.svn')):
        logger.debug(f"Identified {repos_root} as a working copy. Fetching remote info...")
        try:
            # 1. Get the remote repository URL for the local checkout folder
            info_result = subprocess.run(
                ["svn", "info", repos_root],
                capture_output=True, text=True, check=True
            )
            repo_url = ""
            for line in info_result.stdout.splitlines():
                if line.startswith("URL:"):
                    repo_url = line.split("URL:", 1)[1].strip()
                    break

            if repo_url:
                logger.debug(f"Remote repository URL found: {repo_url}")
                # 2. Use 'svn list' to get the full list of directories directly from the server
                list_result = subprocess.run(
                    ["svn", "list", repo_url],
                    capture_output=True, text=True, check=True
                )
                for line in list_result.stdout.splitlines():
                    item = line.strip()
                    # Subversion directories end with a trailing slash
                    if item.endswith('/'):
                        repos.append(item[:-1])
        except subprocess.CalledProcessError as e:
            logger.error(f"Error fetching repository list from server: {e.stderr if e.stderr else e}")
    else:
        logger.debug(f"Scanning local filesystem for repositories in {repos_root}...")
        # Fallback for bare SVN repositories directly on the server filesystem
        if os.path.exists(repos_root):
            for item in os.listdir(repos_root):
                repo_path = os.path.join(repos_root, item)
                if os.path.isdir(repo_path) and os.path.exists(os.path.join(repo_path, 'format')):
                    repos.append(item)

    return repos

def get_youngest_revision(repo_path):
    """Gets the youngest (latest) revision of the SVN repository."""
    try:
        result = subprocess.run(
            ["svnlook", "youngest", repo_path],
            capture_output=True, text=True, check=True
        )
        return int(result.stdout.strip())
    except Exception as e:
        logger.debug(f"Could not determine youngest revision for {repo_path}: {e}")
        return 0

def perform_full_dumps():
    """Performs a full dump for all SVN repositories."""
    repositories = get_repositories(SVN_REPOS_ROOT)
    
    for repo_name in repositories:
        repo_path = os.path.join(SVN_REPOS_ROOT, repo_name)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 2.1 Create new dump with current date appended to the repository name before extension.
        temp_dump_file = os.path.join(BACKUP_DIR, f"{repo_name}_{timestamp}.dump")
        final_dump_file = os.path.join(BACKUP_DIR, f"{repo_name}.dump")
        
        youngest_rev = get_youngest_revision(repo_path)
        rev_info = f" (Latest Rev: {youngest_rev})" if youngest_rev > 0 else ""
        logger.info(f"Creating dump for repository: {repo_name}{rev_info}...")
        
        try:
            error_output = []
            with open(temp_dump_file, 'wb') as f:
                process = subprocess.Popen(
                    ["svnadmin", "dump", repo_path],
                    stdout=f, stderr=subprocess.PIPE
                )
                
                for line in process.stderr:
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if not line_str:
                        continue
                        
                    rev_match = re.search(r'Dumped revision (\d+)', line_str)
                    if rev_match:
                        current_rev = int(rev_match.group(1))
                        if youngest_rev > 0:
                            percent = (current_rev / youngest_rev) * 100
                            bar_length = 40
                            filled = int(bar_length * current_rev // youngest_rev)
                            bar = '█' * filled + '-' * (bar_length - filled)
                            sys.stdout.write(f'\rProgress: |{bar}| {percent:.1f}% ({current_rev}/{youngest_rev})')
                            sys.stdout.flush()
                        else:
                            sys.stdout.write(f'\rProgress: Dumped revision {current_rev}')
                            sys.stdout.flush()
                    else:
                        # Clear progress line before rendering logging
                        sys.stdout.write('\r' + ' ' * 80 + '\r')
                        sys.stdout.flush()
                        logger.debug(f"svnadmin [{repo_name}]: {line_str}")
                        error_output.append(line_str)
                
                process.wait()
                sys.stdout.write('\n')
                sys.stdout.flush()
                
                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode, process.args)
            
            # 2.2 After dump command successfully completed, remove previous dump file and rename new dump file.
            if os.path.exists(final_dump_file):
                os.remove(final_dump_file)
            os.rename(temp_dump_file, final_dump_file)
            logger.info(f"Successfully created dump for {repo_name}.")
            
        except subprocess.CalledProcessError as e:
            # 2.2 If failed, remove current (temp) dump file and log error in error file.
            if os.path.exists(temp_dump_file):
                os.remove(temp_dump_file)
            err_details = " | ".join(error_output[-3:]) if error_output else "Unknown error"
            error_msg = f"Failed to dump {repo_name}. Exit Code: {e.returncode}. Details: {err_details}"
            logger.error(error_msg)
        except Exception as e:
            if os.path.exists(temp_dump_file):
                os.remove(temp_dump_file)
            error_msg = f"Unexpected error dumping {repo_name}. Error: {e}"
            logger.error(error_msg)
        
        # 2.3 Move to next repository (loop automatically continues to the next item).

if __name__ == "__main__":
    logger.info("SVN Dump Backup Script Started.")
    perform_full_dumps()