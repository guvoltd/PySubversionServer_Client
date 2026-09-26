import subprocess
import os
import datetime

# Configuration
SVN_REPO_PATH = "E:\svn_mcc\A-Projects\laser_IOT"  # Path to your SVN repository
BACKUP_DIR = "D:\svn_test\laser_IOT"  # Directory to store backups
LAST_BACKUP_REV_FILE = os.path.join(BACKUP_DIR, "last_backup_revision.txt")

def get_last_backed_up_revision():
    """Reads the last backed-up revision from a file."""
    if os.path.exists(LAST_BACKUP_REV_FILE):
        with open(LAST_BACKUP_REV_FILE, 'r') as f:
            try:
                return int(f.read().strip())
            except ValueError:
                return 0
    return 0

def set_last_backed_up_revision(revision):
    """Writes the current backed-up revision to a file."""
    with open(LAST_BACKUP_REV_FILE, 'w') as f:
        f.write(str(revision))

def get_youngest_revision(repo_path):
    """Gets the youngest (latest) revision of the SVN repository."""
    try:
        result = subprocess.run(
            ["svnlook", "youngest", repo_path],
            capture_output=True, text=True, check=True
        )
        return int(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error getting youngest revision: {e}")
        return -1

def perform_incremental_backup():
    """Performs an incremental backup of the SVN repository."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    last_backed_up_rev = get_last_backed_up_revision()
    youngest_rev = get_youngest_revision(SVN_REPO_PATH)

    if youngest_rev == -1:
        print("Could not determine youngest revision. Exiting.")
        return

    if youngest_rev <= last_backed_up_rev:
        print("No new revisions to back up.")
        return

    start_rev = last_backed_up_rev + 1
    end_rev = youngest_rev

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file_name = f"svn_incremental_backup_r{start_rev}-{end_rev}_{timestamp}.dump"
    backup_file_path = os.path.join(BACKUP_DIR, backup_file_name)

    print(f"Performing incremental backup from revision {start_rev} to {end_rev}...")

    try:
        with open(backup_file_path, 'wb') as f:
            subprocess.run(
                ["svnadmin", "dump", SVN_REPO_PATH, "--incremental", "-r", f"{start_rev}:{end_rev}"],
                stdout=f, check=True
            )
        print(f"Incremental backup completed successfully: {backup_file_path}")
        set_last_backed_up_revision(end_rev)
    except subprocess.CalledProcessError as e:
        print(f"Error during backup: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    perform_incremental_backup()