#!/bin/bash
#
# system-helper.sh - Privileged helper for SVN Server Admin
#
# This script is executed via pkexec to perform actions that require
# root privileges, such as managing systemd services, creating users,
# and writing system configuration files.
#
# It should be installed to a system location like /usr/bin/ or /usr/libexec/.
# The PkexecRunnerDialog will look for it there, with a fallback to the
# development path in resources/ for testing.

set -e # Exit immediately if a command exits with a non-zero status.

# Check if the last argument is a number (our debug level)
LAST_ARG="${@: -1}"
DEBUG_LEVEL=0
if [[ "$LAST_ARG" =~ ^[0-9]+$ ]]; then
    DEBUG_LEVEL="$LAST_ARG"
    # Remove the last argument so the rest of the script works as before
    # by slicing the arguments array.
    set -- "${@:1:$#-1}"
fi

ACTION="$1"
shift # All remaining arguments are parameters for the action

# --- Helper Functions ---

log_error() {
    echo "Error: $1" >&2
    exit 1
}

# --- Main Action Handler ---

case "$ACTION" in
    "start_service")
        systemctl start svnserve.service
        echo "svnserve service started."
        ;;

    "stop_service")
        systemctl stop svnserve.service
        echo "svnserve service stopped."
        ;;

    "restart_service")
        systemctl restart svnserve.service
        echo "svnserve service restarted."
        ;;

    "write_systemd_unit")
        UNIT_CONTENT="$1"
        echo "$UNIT_CONTENT" > /etc/systemd/system/svnserve.service
        systemctl daemon-reload
        echo "Wrote /etc/systemd/system/svnserve.service and reloaded daemon."
        ;;

    "enable_systemd_unit")
        systemctl enable --now svnserve.service
        echo "Enabled and started svnserve.service."
        ;;

    "add_group")
        GROUP_NAME="$1"
        if ! getent group "$GROUP_NAME" > /dev/null; then
            groupadd "$GROUP_NAME"
            echo "Group '$GROUP_NAME' created."
        else
            echo "Group '$GROUP_NAME' already exists."
        fi
        ;;

    "add_user")
        USER_NAME="$1"
        GROUP_NAME="$2"
        if ! getent passwd "$USER_NAME" > /dev/null; then # Check if user already exists
            # Create a system user (-r) with no login shell (-s /sbin/nologin)
            # and specified group (-g) and home directory (-d).
            # Use -m to create the home directory, but with an empty skeleton (-k /dev/null)
            # to avoid creating localized folders like '模板' (Templates).
            useradd -r -g "$GROUP_NAME" -d "/home/$USER_NAME" -s /sbin/nologin -m -k /dev/null "$USER_NAME"
            echo "User '$USER_NAME' created with an empty home directory at '/home/$USER_NAME'."
        else
            echo "User '$USER_NAME' already exists."
        fi
        ;;

    "add_user_to_group")
        USER_NAME="$1"
        GROUP_NAME="$2"
        usermod -a -G "$GROUP_NAME" "$USER_NAME"
        echo "Added user '$USER_NAME' to group '$GROUP_NAME'. A log out/in is required for this to take effect."
        ;;

    "set_ownership")
        echo "Setting ownership of $1 to $2:$3"
        TARGET_PATH="$1"
        USER_NAME="$2"
        GROUP_NAME="$3"
        # Create the directory if it doesn't exist (-p creates parent directories as needed).
        mkdir -p "$TARGET_PATH"
        # Set ownership recursively.
        chown -R "${USER_NAME}:${GROUP_NAME}" "$TARGET_PATH"
        # Set permissions: rwx for user/group, rx for others. Capital X applies execute only to directories.
        chmod -R u=rwX,g=rwX,o=rX "$TARGET_PATH"
        # Add the setgid bit to all directories to ensure new files inherit the group.
        find "$TARGET_PATH" -type d -exec chmod g+s {} +
        echo "Ensured directory '$TARGET_PATH' exists and set ownership to ${USER_NAME}:${GROUP_NAME} with recommended permissions (g+s set)."
        ;;

    "create_repo")
        REPO_PATH="$1"
        FS_TYPE="$2"
        STD_LAYOUT="$3" # "true" or "false"
        SVN_USER="$4"
        SVN_GROUP="$5"

        # Create the repository. This runs as root, so it will succeed.
        svnadmin create --fs-type "$FS_TYPE" "$REPO_PATH"
        echo "Repository '$REPO_PATH' created."

        if [ "$STD_LAYOUT" == "true" ]; then
            REPO_URL="file://$REPO_PATH"
            # This also runs as root, which has permission.
            svn mkdir "$REPO_URL/trunk" "$REPO_URL/branches" "$REPO_URL/tags" -m "Create standard layout" --non-interactive
            echo "Created standard layout in '$REPO_PATH'."
        fi

        # Now, set the final ownership for the svnserve daemon.
        chown -R "${SVN_USER}:${SVN_GROUP}" "$REPO_PATH"
        echo "Set ownership of '$REPO_PATH' to ${SVN_USER}:${SVN_GROUP}."
        ;;

    "load_dump")
        REPO_PATH="$1"
        DUMP_FILE="$2"
        SVN_USER="$3"
        SVN_GROUP="$4"

        if [ ! -d "$REPO_PATH" ]; then
            log_error "Repository not found at '$REPO_PATH'"
        fi
        if [ ! -f "$DUMP_FILE" ]; then
            log_error "Dump file not found at '$DUMP_FILE'"
        fi

        # Repos are owned by svn:svnserver with no group-write bit, so the
        # invoking desktop user can't write into db/ themselves (this runs
        # as root via pkexec, so it can). svnadmin needs to create temporary
        # files inside the repo while loading.
        svnadmin load "$REPO_PATH" < "$DUMP_FILE"
        echo "Loaded '$DUMP_FILE' into '$REPO_PATH'."

        # Loading as root leaves the new revision files root-owned, which
        # would then block svnserve (running as svn:svnserver) from reading
        # them -- restore the expected ownership, same as create_repo does.
        chown -R "${SVN_USER}:${SVN_GROUP}" "$REPO_PATH"
        echo "Set ownership of '$REPO_PATH' to ${SVN_USER}:${SVN_GROUP}."
        ;;

    "delete_repo")
        REPO_PATH="$1"
        BACKUP_FIRST="$2" # "true" or "false"

        if [ ! -d "$REPO_PATH" ]; then
            log_error "Repository not found at '$REPO_PATH'"
        fi

        if [ "$BACKUP_FIRST" == "true" ]; then
            BACKUP_PATH="${REPO_PATH}.bak"
            svnadmin hotcopy "$REPO_PATH" "$BACKUP_PATH"
            echo "Backed up '$REPO_PATH' to '$BACKUP_PATH'."
        fi

        rm -rf "$REPO_PATH"
        echo "Deleted repository '$REPO_PATH'."
        ;;

    "write_hook")
        # Repos are owned by svn:svnserver with no group-write bit, so the hooks/
        # directory can't be written to directly by the invoking desktop user.
        REPO_PATH="$1"
        HOOK_NAME="$2"
        BASE64_CONTENT="$3"
        HOOKS_DIR="$REPO_PATH/hooks"
        mkdir -p "$HOOKS_DIR"
        HOOK_PATH="$HOOKS_DIR/$HOOK_NAME"
        base64 -d <<< "$BASE64_CONTENT" > "$HOOK_PATH"
        chmod 755 "$HOOK_PATH"
        chown svn:svnserver "$HOOK_PATH" 2>/dev/null || true
        echo "Hook '$HOOK_NAME' written to $HOOK_PATH."
        ;;

    "enable_hook")
        REPO_PATH="$1"
        HOOK_NAME="$2"
        HOOKS_DIR="$REPO_PATH/hooks"
        TMPL_PATH="$HOOKS_DIR/$HOOK_NAME.tmpl"
        HOOK_PATH="$HOOKS_DIR/$HOOK_NAME"
        if [ -f "$TMPL_PATH" ] && [ ! -f "$HOOK_PATH" ]; then
            mv "$TMPL_PATH" "$HOOK_PATH"
            chmod 755 "$HOOK_PATH"
            echo "Hook '$HOOK_NAME' enabled."
        else
            echo "Hook '$HOOK_NAME' already enabled or no template found."
        fi
        ;;

    "disable_hook")
        REPO_PATH="$1"
        HOOK_NAME="$2"
        HOOKS_DIR="$REPO_PATH/hooks"
        HOOK_PATH="$HOOKS_DIR/$HOOK_NAME"
        TMPL_PATH="$HOOKS_DIR/$HOOK_NAME.tmpl"
        if [ -f "$HOOK_PATH" ] && [ ! -f "$TMPL_PATH" ]; then
            mv "$HOOK_PATH" "$TMPL_PATH"
            echo "Hook '$HOOK_NAME' disabled."
        else
            echo "Hook '$HOOK_NAME' already disabled or file not found."
        fi
        ;;

    "create_htpasswd")
        AUTH_FILE="$1"
        USERNAME="$2"
        PASSWORD="$3"
        CREATE_FLAG="$4"

        if ! command -v htpasswd &> /dev/null; then
            log_error "htpasswd command not found. Please install apache2-utils."
        fi

        if [ "$CREATE_FLAG" == "--create" ]; then
            mkdir -p "$(dirname "$AUTH_FILE")"
            htpasswd -cb "$AUTH_FILE" "$USERNAME" "$PASSWORD"
            echo "Created '$AUTH_FILE' and added user '$USERNAME'."
        else
            htpasswd -b "$AUTH_FILE" "$USERNAME" "$PASSWORD"
            echo "Added user '$USERNAME' to '$AUTH_FILE'."
        fi
        # Set secure permissions. Apache's user (e.g., www-data) needs to read it.
        # Chown to root and a group the web server is in, with mode 640 is ideal.
        if getent group www-data > /dev/null; then
            chown root:www-data "$AUTH_FILE"
            chmod 640 "$AUTH_FILE"
            echo "Set ownership to root:www-data and permissions to 640."
        else
            # Fallback for non-Debian systems if www-data group doesn't exist.
            chmod 644 "$AUTH_FILE"
            echo "Set permissions to 644. Adjust ownership for your web server user if needed."
        fi
        ;;

    "write_apache_conf")
        CONF_CONTENT="$1"
        echo "$CONF_CONTENT" > /etc/apache2/sites-available/svn.conf
        echo "Wrote /etc/apache2/sites-available/svn.conf."
        ;;

    "enable_apache_site")
        a2enmod dav >/dev/null 2>&1 || true
        a2enmod dav_svn >/dev/null 2>&1 || true
        a2ensite svn.conf >/dev/null 2>&1
        systemctl restart apache2
        echo "Enabled dav, dav_svn modules and svn.conf site. Restarted Apache."
        ;;
    
    "write_config_via_python")
        FILE_TYPE="$1"
        FILE_PATH="$2"
        BASE64_DATA="$3"
        # Execute the Python helper script with the provided arguments
        # Ensure the Python script path is correct relative to the helper script
        python3 "$(dirname "$0")/privileged_config_writer.py" "$FILE_TYPE" "$FILE_PATH" "$BASE64_DATA" "$DEBUG_LEVEL"
        echo "Config file '$FILE_PATH' written via Python helper."
        ;;

    "write_repo_configs")
        BASE64_DATA="$1"
        # Execute the Python helper script with the batch action
        python3 "$(dirname "$0")/privileged_config_writer.py" "batch_write" "$BASE64_DATA" "$DEBUG_LEVEL"
        echo "Repository configuration files written."
        ;;

    "add_firewall_rule")
        if ! command -v ufw &> /dev/null; then
            echo "Firewall command 'ufw' not found. Rule not added."
            # Exit 0 because not finding ufw isn't a script failure.
            exit 0
        fi

        # Check if ufw is active
        if ! ufw status | grep -q "Status: active"; then
            echo "Firewall is inactive. Enabling firewall..."
            # The following command can be interactive, so we pipe 'y' to it.
            yes | ufw enable
        fi

        echo "Adding rule to allow incoming TCP traffic on port 3690 for SVN..."
        ufw allow 3690/tcp
        echo "Firewall rule for svnserve (port 3690) applied."
        echo "Current status:"
        ufw status
        ;;

    *)
        log_error "Unknown action '$ACTION'"
        ;;
esac

exit 0